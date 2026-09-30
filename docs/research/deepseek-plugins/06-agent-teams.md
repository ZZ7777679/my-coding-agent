# dsh-agent-teams：持续成员、共享任务与改派的一致性

> 核查日期：2026-09-23。`NanmiCoder/dsh-agent-teams` 0.1.20，固定提交 `87c95c94d7847e4a242cb589916adc519981175f`，MIT。作者推荐 DSH 0.1.5-rc.1；0.1.20 主要同步发布引用，实质行为来自 0.1.19。不能据此声称已支持本次官方 0.1.7-alpha.2。

## 1. 先区分它与其他“Agent Teams”

这是社区 DSH 插件，不是 Claude Code 的 Agent Teams，也不是 DSH 官方已有 taskboard / mailbox 插件的别名。它把当前会话作为 captain，创建可持续的成员，把目标拆成带依赖的任务，再通过持久 mailbox 协调多轮工作。

普通一次性子 Agent 返回答案就结束；这里的 member 可以完成一个任务后变为空闲，再接收下一轮。Team、member、task、task attempt 和模型 turn 因而必须是不同身份。

## 2. 仓库按状态与执行分工

`index.ts` 装配和注入 captain protocol；`tools.ts` 提供操作；`state.ts` 管 team / mailbox 的持久状态；`members.ts` 封装持续子 Agent；`scheduler.ts` 决定何时派发；`harness-compat.ts` 收敛宿主差异；`quality-gates.ts` 管可选质量流程；`src/client/` 展示 DAG、成员和活动。

这种拆法使“调度决定”“真正调用子 Agent”“保存决定”可以分别理解。不过执行仍有多步：保存 claim 不等于 Agent 已接受输入，Agent 接受输入也不等于任务已经完成。源码的大量 attempt、handoff 和 mailbox 字段正是为这些间隙服务。

## 3. 从自然语言目标到尚未运行的计划

普通入口先建立 staged roster 与 DAG，不马上启动成员。批准后才启用 scheduler；成员在自己的首个 ready task 到来时创建。计划可以原位修订，避免每次讨论都留下已经运行的空成员。

这是该产品的交互选择：研究可以借鉴“计划和执行状态分开”，但我们项目不应自动增加每次委派都必须确认的门槛。现有用户授权足够时仍应直接推进。[入口与协议](https://github.com/NanmiCoder/dsh-agent-teams/blob/87c95c94d7847e4a242cb589916adc519981175f/src/index.ts)

## 4. ready task 怎样交给空闲成员

scheduler 在任务图变化和成员 idle 等事件发生时运行，不维持一个模型持续轮询任务列表。每个 member 有 Promise queue，team mutation 也通过 `withTeamLock()` 串行化。

取任务前先处理当前 mailbox，再读取新状态、检查 team 未 halted / staged、成员可用、依赖已完成，然后建立 DispatchTicket。Ticket 包含 taskId、memberId、attempt、attemptId、角色协议和依赖结果。依赖结果按拓扑顺序收集，并设置单项与总量上限，避免把所有上游对话复制给每个成员。[调度器](https://github.com/NanmiCoder/dsh-agent-teams/blob/87c95c94d7847e4a242cb589916adc519981175f/src/scheduler.ts)

这里的锁是进程内 Map / Promise 链，team.json 使用原子写。它能协调同一进程里的多个事件处理器，不能因此宣称两个独立 DSH 进程同时操作同一 team 也具备分布式互斥。[状态实现](https://github.com/NanmiCoder/dsh-agent-teams/blob/87c95c94d7847e4a242cb589916adc519981175f/src/state.ts)

## 5. attempt_id 为什么比“谁负责”更重要

设任务 T 先给 A，后来改派给 B。A 的旧模型请求仍可能在途，晚一些返回“已完成”。只检查 task.assignee 不足以解释所有异步间隙，因此每次尝试都产生新的 attempt capability。

`beginTaskAttempt()` 增加 attempt 并激活新身份；`invalidateTaskAttempt()` 清除旧 attemptId，设置 handoffId，回到 pending / reassigning 状态。更新任务必须携带当前 attemptId；旧尝试的迟到更新被识别为 stale。改派还需等待旧执行静止，避免仅改状态就让两个成员同时写同一文件。

它保护的是调度状态，不是磁盘上的所有副作用。旧成员已发出的 shell 进程、外部 API 或编辑结果，仍依赖宿主取消和实际资源隔离。attempt id 不能取代执行停止。

## 6. 多轮消息和结果回收

成员是 continuable subagent，保持自己的对话。源码指出在所支持宿主契约下，不能把 final assistant message 当成一个始终可直接读取的统一结果接口，于是正式输出写入 task record 和 captain mailbox。

mailbox 先持久保存，再 claim delivery，宿主接受 follow-up 后标记 delivered；失败则释放 delivery claim。直接 steer 与下一轮 queue 是不同交付方式。delivered 表示宿主接受，不表示模型已理解或产出正确结论。[成员生命周期](https://github.com/NanmiCoder/dsh-agent-teams/blob/87c95c94d7847e4a242cb589916adc519981175f/src/members.ts)

持续成员还有一个细节：当前进程已经观察到成员 idle、但任务仍未报告完成时，scheduler 把该 attempt parked，不因下一次状态查询就自动重试；冷启动时，未在本进程观察过的遗留尝试走另外的恢复逻辑。两种情况不能统称为“空闲就继续”。

## 7. 可选质量流程是更高一层状态机

requirements → implementation → verification → review → integration 可附带 acceptance、verify、inScope 等契约。失败 review 可以生成 repair 和下一轮 review，并重接下游依赖；契约写错时允许 captain amend，而不是逼工作者伪造通过。

但这些字段与审查并不构成操作系统权限边界。项目自己明确 scope control 是完成时审计，并非宿主逐次文件写拦截。复杂流程还增加判断、模型调用和修复轮数，不能不计成本地说必然提升质量。

## 8. 对本项目的具体价值

最值得借鉴的是稳定成员与单次 Run 分开、改派尝试号、事件驱动唤醒、限定的依赖摘要、停止与恢复分开。现有 Session / Run / worker / collaboration 已能承接其中一部分。

不应直接照搬冷恢复自动重试、完整表单式完工门槛、默认多模型或每次计划审批。当前项目规定调用故障停止、报告最小输入为 summary / outcome；采用持续团队时应在此基础上增量设计，不能用插件的产品规则覆盖已确定的行为。
