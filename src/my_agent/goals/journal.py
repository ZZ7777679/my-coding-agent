"""复用会话单写者日志的 Goal 命令入口。 Goal commands over the session single-writer journal."""

from my_agent.errors import AgentError
from my_agent.goals.state import states
from my_agent.goals.types import GoalControl, GoalCreated, GoalSettled
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import Fact


class GoalJournal:
    """只持久化控制 / 结果，不执行工具，也不拥有另一份会话数据。

    Persist controls and results without executing tools or duplicating session data.
    """

    def __init__(self, sessions: SessionStore) -> None:
        """绑定现有单写者，所有方法在业务线程调用。

        Bind the existing single writer; call all methods on the business worker.
        """
        self.sessions = sessions

    def create(self, log: SessionLog, goal: GoalCreated) -> Fact:
        """幂等保存用户目标，重复身份必须保持原输入。

        Idempotently persist a user goal, requiring identical input for a repeated identity.
        """
        for fact in log.facts:
            if isinstance(fact.data, GoalCreated) and fact.data.goal_id == goal.goal_id:
                if fact.data != goal:
                    raise AgentError("OPERATION_CONFLICT", "该 Goal 标识已用于不同目标。")
                return fact
        return self.sessions.append(log, goal, None)

    def control(self, log: SessionLog, control: GoalControl) -> Fact:
        """用户操作按身份幂等；不会将普通会话输入解释成 HITL 答复。

        Persist idempotent explicit controls; ordinary input is never inferred to be a HITL answer.
        """
        for fact in log.facts:
            if (
                isinstance(fact.data, GoalControl)
                and fact.data.operation_id == control.operation_id
            ):
                if fact.data != control:
                    raise AgentError("OPERATION_CONFLICT", "该控制标识已用于不同 Goal 操作。")
                return fact
        return self.sessions.append(log, control, None)

    def settle(self, log: SessionLog, result: GoalSettled) -> Fact:
        """相同已保存终态只结算一次，故障补同步不重新执行 Run。

        Settle each durable result once; repairing synchronization never reruns the work.
        """
        for fact in log.facts:
            if isinstance(fact.data, GoalSettled) and (fact.data.goal_id, fact.data.result_seq) == (
                result.goal_id,
                result.result_seq,
            ):
                if fact.data != result:
                    raise AgentError("GOAL_RESULT_CONFLICT", "运行结果已结算；接续需新的用户操作。")
                return fact
        return self.sessions.append(log, result, None)

    def pending_results(self, log: SessionLog, goal_id: str) -> set[int]:
        """返回尚未结算的已保存结果身份，仅用于补同步和状态恢复。

        Return durable unsettled results for synchronization and state recovery only.
        """
        from my_agent.sessions.types import RunAccepted, RunFinished

        state = states(log.facts).get(goal_id)
        if state is None:
            raise AgentError("GOAL_NOT_FOUND", "Goal 记录不存在。")
        runs = {
            fact.run_id
            for fact in log.facts
            if isinstance(fact.data, RunAccepted) and fact.data.goal_id == goal_id
        }
        return {
            fact.seq
            for fact in log.facts
            if isinstance(fact.data, RunFinished)
            and fact.run_id in runs
            and fact.seq not in state.results
        }
