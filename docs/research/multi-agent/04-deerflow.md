# DeerFlow 2.0：将多 Agent 委派做成完整的执行产品

> 核查日：2026-09-22。固定主线 `5202068a0e3ba7358db11382deedfed1a17ea319`，产品标识为 DeerFlow 2.0；不是将主线误认为某个稳定发布标签。本文静态阅读 Python harness，未部署网关、数据库、sandbox 或运行真实任务。

## 1. 从研究工作流到通用 harness

DeerFlow 由字节跳动开源。2.0 的定位已超出早期“搜索—研究—生成报告”的预设流程：主 Agent 使用 Skill、工具、文件、执行环境和子 Agent 完成较长任务。当前仓库公开区分 1.x 与重新组织的 2.0，因此早期固定研究角色图不能代表当前实现。[仓库与产品说明][readme]

它值得关注的原因是：LangGraph / LangChain 提供 Agent 循环和图执行后，产品仍要解决大量外围问题。例如子任务排队时是否占线程、父上下文怎样复制、MCP 初始化阻塞时如何响应取消、任务批次如何在 worker 退出后继续、结果如何归因。DeerFlow 把这些能力放进一个可以追踪的 harness 中。

## 2. 仓库结构对应哪些职责

本次重点路径位于 `backend/packages/harness/deerflow/`。这些路径是当前快照的组织方式，不能照搬旧教程中的目录名。

| 目录 / 文件 | 职责 | 阅读顺序和扩展点 |
| --- | --- | --- |
| `agents/lead_agent/agent.py` | 主 Agent 的模型、工具、middleware 装配 | 从入口确定哪些能力实际启用 |
| `agents/middlewares/` | 压缩、记忆、预算、工具错误、子任务限制等 | 查看生命周期钩子顺序，而非只读配置名 |
| `subagents/config.py`、`registry.py` | 子 Agent 定义与选择 | 角色配置属于这里，调度机制不应写进角色 prompt |
| `subagents/context_snapshot.py` | 父对话的不可变数据快照 | 确定子任务知道什么、哪些原生状态被排除 |
| `subagents/executor.py` | 单次子任务的装配、执行、后台登记、终态 | 一次执行的主要所有者 |
| `subagents/capacity.py` | 并发槽位、等待队列、取消释放 | 所有入口应使用同一容量事实 |
| `subagents/batch_service.py` | 持久批次的领取、租约、执行与取消 | 区别于进程内 background registry |
| `tools/`、`skills/`、`sandbox/` | 能力发现、内容投影和执行资源 | 决定工具实际上能做什么 |
| `agents/memory/` | 记忆后端和更新 / 检索职责 | 与子任务短期上下文快照分开 |

主、子 Agent 都依赖 LangChain `create_agent`，但并不意味着两者 middleware 完全相同。`SubagentExecutor._create_agent()` 复用子 Agent 装配函数，并显式传入模型、agent_name、可见 Skill 和延迟工具目录。修改共通执行行为应进入装配 / middleware，修改持久批次语义则进入 batch service。[主装配][lead] [子执行器][executor]

## 3. 第一步：把用户目标变成可委派工作

主 Agent 负责理解目标和安排子任务，宿主负责将子 Agent 配置、模型选择、授权工具和运行上下文解析为一次执行。`execute_async()` 返回新生成的 execution ID，外部 tool-call ID 只保留为关联字段，不作为全局后台任务键。

这个细节有实际价值：不同父 Run 的 provider 可能复用相同 tool-call ID，如果拿它当执行主键，后提交的任务可能覆盖前一个结果。execution ID、外部调用 ID、父 run_id、thread_id 因而应各司其职。UI 也应按 execution ID 观察具体执行，不能把一次重试显示成上一轮还在继续。[执行器 `execute_async`][executor]

执行器先复制父 Context，再注册 PENDING 结果。若复制失败，任务尚未进入注册表；这避免产生一个调用者拿不到 ID、同时也无法清理的幽灵任务。此处处理的是注册时序，不是模型能力。

## 4. 第二步：构造上下文、Skill 和工具视图

### 4.1 父历史是背景资料，不是子任务自己的工具记录

`ParentContextSnapshot` 把保留的父消息和摘要序列化为不可变 JSON。对子 Agent 而言，它是一条单独的背景 HumanMessage；其中父工具调用被转成历史文本，而非可执行的 provider 工具协议帧。未完成工具调用不被当成已完成动作，父消息的元数据、隐藏框架消息、原生推理签名不会原样搬过去。[快照实现][snapshot]

例如父 Agent 已运行过一次构建并失败，子 Agent 需要知道失败现象；但它不能把父 tool_call_id 写入自己的执行证据，或把父尚未收到结果的命令当成自己已经执行。数据化复制保留信息，又避免协议身份串线。创建快照后，父会话的新消息不会自动进入子任务，后续修正需要另一个明确入口。

该实现没有额外偷偷截断保留历史，成本交由调用者和正常子 Agent 压缩处理。优点是少丢要求，代价是上下文可能很贵。对本项目更适合提供“目标 / 约束 / 相关事实摘要”与“继承快照”两种语义，而不是每次默认复制全部历史。

### 4.2 工具发现、授权和 Skill 激活不是同一步

`_build_initial_state()` 先加载 Skill 元数据，再组装发现入口。源码明确把 Skill 当成可发现信息，实际激活后才动态应用其工具策略。工具则先经过授权过滤，再进入延迟目录，避免被拒绝的工具通过搜索目录重新出现。MCP 延迟目录和 Agent middleware 使用同一个装配结果，减少“prompt 说有工具，执行器却没有”的不一致。[执行器][executor]

这里可借鉴的是单次装配的一致性。并不需要照搬其所有策略层：本项目已选择由真实边界负责权限，不宜为了复刻框架增加多个重复审批点。Skill 也不能凭文本宣称权限升级。

### 4.3 文件与 sandbox 的共享关系

子任务初始化会携带需要的 sandbox / thread_data，上传文件容器会复制。复制 Python 容器只避免图状态对象互相修改，不能证明底层文件互不共享。若多个成员最终指向同一 sandbox，源文件仍可能冲突。

`SandboxProvider` 将 acquire / get / release 与具体 provider 分开；阻塞式资源获取通过异步包装避免卡住事件循环。它还显式声明是否支持物理 Skill 隔离：若宿主 shell 可绕过映射，就不能声称隔离有效。这种能力声明比仅凭目录命名判断边界更可靠。[SandboxProvider][sandbox]

## 5. 第三步：排队、并发和执行

当前 executor 使用进程拥有的长期异步事件循环，后台任务并非每个都创建一个新 loop。复制 Context 时过滤绑定父图事件循环的回调，保留必要关联信息。这解决跨线程 / 跨 loop 的回调和取消对象不能任意复用的问题。旧资料若把它概括成固定线程池并行，会遗漏当前的运行机制。[执行器][executor]

`SubagentExecutionCapacity` 持有正在运行数量、FIFO waiters、队列上限和超时策略。等待者是 Future，排队本身不占执行线程。释放槽位时，如果存在等待者，就把槽位直接转交，running 数不先减后增。[容量控制][capacity]

取消边界尤其具体：如果等待超时的同时恰好得到槽位，代码检查是否已取得所有权，并负责归还；释放还通过 shield 完成清理后再传播取消。否则一次罕见的竞态就会永久少一个并发槽位，最后表现为系统“越来越慢”。这些机制可以通过宿主实现，不需要模型每轮判断是否有资源。

这是一种集中容量控制，而不是自治团队。它限制可同时运行多少执行，不决定任务分工是否合理，也不解决成员协商或代码集成。主 Agent、任务计划与资源调度应继续分层。

## 6. 第四步：结果汇总、超时和终态

`SubagentResult` 保存状态、时间、输出、token 使用和工具事实，使用线程锁保护终态竞争。正常完成、超时和用户取消都可能几乎同时发生，终态不能被较晚的回调随意覆盖。后台执行用独立 execution ID 查询，工具 receipts 和 shell 事实作为结果依据保留。[执行器][executor]

结果字符串、任务状态和证据不是相互替代的：模型可以产生一段回答，但运行仍可能因超时结束；取消时已经完成的工具也不应从记录消失。反过来，保留 receipts 不能保证模型对结果的解释正确。应用要展示真实执行状态和已有产物，再由用户或适合的评估判断任务质量。

当前子 Agent 图装配使用 `checkpointer=False`。这非常关键：不能因为父系统采用 LangGraph，就声称每个子 Agent 都能从任意模型 / 工具步骤恢复。进程内结果注册表、父图检查点、持久批次是三个不同的恢复层。

## 7. 第五步：持久批次提供什么，又不提供什么

`SubagentBatchService` 从 repository 领取 batch item，使用 hostname + UUID 的 lease_owner 表达当前工作者。它根据持久 execution_spec 重新构造配置和工具，然后启动单次 executor。[批次服务][batch]

一个值得直接阅读的竞态是 MCP 初始化：工具装配可能阻塞，因此放在 loop 外执行。装配期间用户可能取消批次，或 worker 已失去租约；服务在真正启动模型前重新确认租约，防止已取消工作又被启动。这个确认有明确时序原因，不能推广成每次普通工具都重复检查全部任务元数据。

源码会提示批次项在 worker 崩溃后可能重试，并要求利用 item key 维持幂等。这仍只是给 Agent 的说明；外部 API 是否接受幂等键、命令是否可安全重跑，需要实际工具和存储契约支持。批次恢复不等于每个副作用 exactly-once，也不等于自动从子图上次 token 接续。

停止服务时会同时取消 poller、后台 execution 和服务跟踪任务，并等待清理。此类资源所有权适合借鉴；其自动恢复 / 重试策略则与本项目“真实调用故障停止，待用户明确接续”不同，需要保留我们的选择。

## 8. 落地价值、代价和演化方向

DeerFlow 提供的是完整应用样本：长任务的上下文、文件、技能、执行环境、后台任务、结果观察共同工作。适合研究“框架如何变成用户能操作的产品”，尤其适合排查并发调度与取消的实现细节。公开仓库和功能说明不构成某个企业部署规模、可用性或成本收益的独立证明，本次没有取得这些生产指标。

它的代价也明显：executor、middleware、批次和结果验收相互作用后，状态数量大幅增加。应把其价值拆成具体机制吸收，不能为了拥有同样多的模块就复制整个 harness。特别是当前仓库的 acceptance / report 体系，不应直接变成本项目的新语义阻断条件。

建议优先借鉴不可变上下文快照、执行 ID 分离、统一容量控制和取消清理；持久批次等到存在跨进程长任务需求再评估。对于持续成员通信与共享任务认领，仍应对照 [Agent Teams](03-agent-teams.md) 和 [AgentScope](05-agentscope.md)，不能假设 DeerFlow 的后台子任务天然等价于团队成员。

[readme]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/README.md
[lead]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/agents/lead_agent/agent.py
[executor]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/subagents/executor.py
[snapshot]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/subagents/context_snapshot.py
[capacity]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/subagents/capacity.py
[batch]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/subagents/batch_service.py
[sandbox]: https://github.com/bytedance/deer-flow/blob/5202068a0e3ba7358db11382deedfed1a17ea319/backend/packages/harness/deerflow/sandbox/sandbox_provider.py
