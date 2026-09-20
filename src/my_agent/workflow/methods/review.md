# 代码审查 / Code review — v1

基于当前任务目标、实际改动和原有代码判断正确性、回归、数据及执行边界。优先报告有证据、可采取行动的问题，说明位置、触发条件与影响，不把个人风格偏好当缺陷。

Assess correctness, regressions and data or execution boundaries against the task goal, actual changes and existing code. Prioritize evidenced actionable findings with location, trigger and impact; do not treat style preferences as defects.

独立 Review 由用户启动；必要自查属于当前工作，不自动新建会话。审查不自动修改代码或跑全量回归；只做已授权且直接相关的检查。无发现与未验证部分分别说明，修复需要既有范围或用户明确要求。

Independent review is user-started; necessary self-review remains within current work without creating sessions. Review does not automatically edit code or run broad regression suites; use only authorized relevant checks. Distinguish no findings from unverified areas and repair only within explicit scope.
