# CrewAI 与 Agno：角色团队怎样变成任务、状态和执行循环

> 核查日：2026-09-22。CrewAI 主线 `0a3b8912b39fb72fac74758069fda523697ffabc`；Agno 主线 `cffd892a9024249f15e2cf556398444b221829af`，其包清单版本为 3.0.10。静态代码与官方资料分析，未运行示例或商业平台。

## 1. CrewAI：角色是入口，Task 和 Process 决定实际执行

### 1.1 它适合解决什么

CrewAI 用 Agent、Task、Crew 和 Process 表达多人分工：Agent 有角色、目标、工具；Task 描述工作和期望输出；Crew 把这些组合起来；Process 决定任务怎样执行。它让业务开发者较容易描述研究、写作、审查等分工。但“角色设定很完整”不等于调度机制很复杂，必须看任务如何真正进入运行时。

当前仓库核心位于 `lib/crewai/src/crewai/`，不是许多旧文章中的根 `src/crewai`。`crew.py` 负责组合调度，Agent / Task 各自执行；Flow 则继续拆成 `flow/dsl`、`flow_definition`、`flow/runtime` 和 conversational 扩展。旧 `flow/flow.py` 仅保留兼容导出。这体现了从“角色示例”到可序列化定义和独立运行时的演化。[Crew 源码][crew] [Flow 入口说明][flow]

### 1.2 输入进入 Crew 后，顺序与层级怎样工作

顺序 Process 遍历任务列表；hierarchical Process 先创建 manager，再调用同一个 `_execute_tasks()`。manager 获得委派工具，把工作交给成员。因此 hierarchical 主要改变任务由谁判断和委派，不等于自动获得一个分布式抢任务队列。[Crew ` _run_hierarchical_process`][crew]

例如“先搜集资料，再给出设计，再审查设计”适合显式 Task 序列。若需要 manager 根据过程中遇到的问题临时请专家，可使用委派。若需要十个常驻成员自主认领并交换消息，还需要额外的生命周期和共享工作项设计，不能从 hierarchical 这个名称推导出来。

### 1.3 上下文传递是输出聚合

`_get_context()` 区分三种情况：明确关闭上下文时为空；未显式指定时聚合已有任务输出；显式列出依赖 Task 时只聚合它们。它传递的是工作产物，不是成员间持续同步所有思考过程。[上下文实现][crew]

这种方式容易理解，但任务输出很长时，下游 prompt 仍可能膨胀；输出缺少来源和假设时，下游也可能把推测当成事实。实际应用应设计适合下游消费的结果，例如接口约定、变更路径、尚未确定的问题，而不是无限扩展角色 backstory。

### 1.4 并发发生在何处

标记 `async_execution` 的 Task 返回 Future，Crew 收集这些 futures；遇到后续同步 Task 或条件判断边界时，先汇合异步结果，再继续执行。最后仍有一次未收集 futures 的汇合。因此它是一种带显式等待边界的任务列表，不是所有任务永远自由并行。[调度源码 L1596–1640][crew]

若 B 需要 A 的输出，A、B 都标 async 并不会自动消除依赖。配置需要正确表达 context 和顺序，否则 B 拿到的只是此前已确定的输出。理解这个机制比仅知道“支持 async”更能预测实际表现。

### 1.5 工具、MCP、记忆与执行资源

Crew 的工具准备阶段按 Agent / Task 装配委派、代码执行、多模态、平台工具、MCP、记忆与文件读取。记忆优先选 Agent 自身配置，再考虑 Crew 级配置；工具列表是动态形成的。[工具装配][crew]

这说明不同角色可以得到不同能力。但角色名不是权限边界，允许执行代码也不自动意味着每个成员拥有独立工作区；具体执行工具和后端才决定隔离。MCP 服务连接可提供能力，同样不能代替 Task 编排。Skill / Flow 技能化入口也需要结合实际加载与执行配置，不能把所有角色 prompt 都称为 Skill。

### 1.6 Flow 为什么成为推荐外层

当前仓库的 production architecture 文档推荐以 Flow 作为应用入口，在流程状态与分支中嵌入 Crew。Flow DSL 的 start / listen / router 表达触发关系，运行时推进状态；Crew 在需要开放式协作的步骤里执行。[官方架构文档][flow-first]

例如用户先上传需求，确定项目类型后才创建研究 Crew，研究结束再进入代码生成或人工修改阶段。外围步骤本来就是确定业务逻辑，不必每次花一次模型调用判断。反过来，具体如何排查一个异常可以交给 Crew，避免把每个探索动作都画成固定节点。

### 1.7 保存和 replay 的边界

SQLiteFlowPersistence 按 flow UUID 和 method_name 保存状态，并单独保存待处理 human feedback；加载时读取最近状态。Crew replay 则会校验任务身份和已保存前缀，避免任务定义已经改变时错误复用旧输出。[Flow persistence][flow-persistence] [Crew replay][crew]

这些机制提供应用状态恢复基础，不是把 Python 调用栈或任意外部副作用冻结下来。尤其“从某个 Task replay”与“继续原在途工具”不同。若 Task 内已创建文件或调用外部服务，重放仍需考虑实际结果。

### 1.8 落地价值与代价

CrewAI 适合快速把明确角色和交付物组织成可观察流程。其商业 AMP 提供部署和运营层，但这些是平台能力，不能当成开源 Crew 对象自带的保证。[AMP][amp]

对本项目最有用的是工作项输入输出与 Flow / Crew 的层次分离。最不宜直接照搬的是按组织职位堆 prompt，或为了流程图漂亮强制所有 coding 任务走固定审批和报告步骤。

## 2. Agno：Team 是直接可运行的组合对象

### 2.1 从对象定义到运行模式

Agno 以 Agent、Team、Workflow 等对象组合应用。Team 的成员可以是 Agent，也可以是嵌套 Team；leader 负责路由、协调或维护任务列表。当前代码明确有四种模式，旧资料只介绍 route / coordinate / collaborate 的概括不适用于这个快照。[模式源码][agno-mode]

| 模式 | 谁决定任务 | 谁组织回答 | 适合的场景 |
| --- | --- | --- | --- |
| coordinate | leader 选择成员并生成输入 | leader 综合 | 不同专长解决不同子问题 |
| route | leader 选择一位成员 | 直接返回成员回答 | 明确分流 |
| broadcast | 同一任务送所有成员 | leader 综合 | 多视角审查 / 比较 |
| tasks | leader 建工作项并持续执行 | 任务循环后输出 | 较长目标与显式进展 |

broadcast 的 `arun()` 才并发推进成员，同步 `run()` 按顺序执行。这是源码明写的区别，不能把 broadcast 一律画成并行执行。[模式源码][agno-mode]

### 2.2 仓库如何拆开复杂 Team

`libs/agno/agno/team/team.py` 提供配置和公共入口；`_run.py` 管不同模式及流式 / 非流式推进；`_task_tools.py` 管工作项操作和执行；`task.py` 定义 Task / TaskList；`_storage.py`、`_session.py` 管历史和存储；`_tools.py`、`_messages.py` 管委派能力与模型上下文。

这不是每个 Team 都一个新类。模式共享会话、工具与记录，再由运行分支改变调度。代价是 `_run.py` 很大，阅读时必须确认处于 sync、async、stream 哪条路径；看到一个分支的限制不能推广为全部入口。

### 2.3 Task 模式的数据流

TaskList 保存在 session_state，Task 包含 id、标题、说明、状态、assignee、parent、dependencies、result 和 notes。leader 使用 create_task、update_task_status、execute_task 等工具维护列表。每一轮后再次读取 TaskList，并将必要状态送入下一轮模型输入。[任务模型][agno-task] [任务工具][agno-task-tools]

这是比一次“委派给专家”更完整的机制：工作项可以独立于当下某次成员响应而存在，成员能执行多个任务，依赖也能影响可用工作。它仍由 leader 循环驱动，不是成员对等竞争的分布式 task board。

### 2.4 共享状态怎样传播

官方说明 coordinate 的成员通常拿到当前状态的浅拷贝，task mode 使用深拷贝，返回后再合并；配置数据库后随团队 Session 保存。并行修改同一个键不具备数据库事务语义。[共享状态说明][agno-state]

例如两个成员都读取 `review_count=0`，各自加一后合并，不一定得到 2。把 state 存进数据库也不能修复已经发生的内存合并覆盖。适合共享的内容应有清楚所有者或合并规则，例如每个成员写自己的结果项；需要原子认领时则用宿主领域操作。

历史、知识、记忆和 session_state 也要区分：历史用于续接，知识用于检索，记忆影响未来输入，TaskList 则是当前目标进展。它们可以被模型同时看见，但不应使用一套任意字典承担所有持久规则。

### 2.5 完成、失败、HITL 和迭代终止

成员暂停会把 pending requirements 传播到 Team，任务回到待处理位置；错误结果写 failed；普通返回进入 completed。源码甚至允许无 content 的正常返回标为 completed。这表明 Task 完成是运行时结果约定，并不等于用户目标已通过验收。[任务工具结果处理][agno-task-tools]

leader 循环检查 goal_complete、任务终态和迭代上限。所有任务 terminal 时仍区分是否有 failed；空任务列表也有结束处理，避免一句普通问候烧满全部迭代预算。`mark_all_complete(summary)` 直接写总目标完成标记，本质上仍是模型声明。[任务循环][agno-run]

这个实现提醒我们：运行事实、模型报告、用户目标应分别展示。没有必要因此引入严格证明门槛；保留真实错误和工具记录、让结果可复查，往往比逼模型生成更多完成表格有效。

### 2.6 保存到数据库不等于自动可靠恢复

`_storage.py` 提供 Team Session 与 Run 输出读写。配置持久数据库可保存 session_state 和历史，InMemoryDb 则只随对象存活。恢复哪个成员、是否重新执行某个 task、如何处理重复外部动作，仍需按具体 Run / HITL 路径判断。[存储实现][agno-storage] [运行契约][agno-running]

因此 Agno 很适合快速构建有记忆、状态和工具的团队服务；若要作为本机 coding 工作区的唯一协调内核，还需明确代码写入、执行取消和任务重启策略。本次没有验证 AgentOS 的商业部署内部机制或性能，不把它们归入开源 Team 的代码结论。

## 3. 两者共同提供的经验

CrewAI 的强项是角色与 Task 交付物表达，以及 Flow 外层的业务控制；Agno 的强项是统一 Team 对象、明确运行模式和任务列表。它们都说明“协作质量”主要取决于输入输出、状态归属、结束条件和执行环境，而不取决于角色名字听起来多专业。

本项目可以借鉴可复用的分工模板、清楚的结果汇合、可观察的任务状态；依然保留用户自由会话、当前故障停止规则和按需工作项。若简单任务无需团队，运行时应允许直接完成，不能为展示协作能力而强制创建多个成员。

[crew]: https://github.com/crewAIInc/crewAI/blob/0a3b8912b39fb72fac74758069fda523697ffabc/lib/crewai/src/crewai/crew.py
[flow]: https://github.com/crewAIInc/crewAI/blob/0a3b8912b39fb72fac74758069fda523697ffabc/lib/crewai/src/crewai/flow/flow.py
[flow-first]: https://github.com/crewAIInc/crewAI/blob/0a3b8912b39fb72fac74758069fda523697ffabc/docs/edge/en/concepts/production-architecture.mdx
[flow-persistence]: https://github.com/crewAIInc/crewAI/blob/0a3b8912b39fb72fac74758069fda523697ffabc/lib/crewai/src/crewai/flow/persistence/sqlite.py
[amp]: https://docs.crewai.com/enterprise/introduction
[agno-mode]: https://github.com/agno-agi/agno/blob/cffd892a9024249f15e2cf556398444b221829af/libs/agno/agno/team/mode.py
[agno-task]: https://github.com/agno-agi/agno/blob/cffd892a9024249f15e2cf556398444b221829af/libs/agno/agno/team/task.py
[agno-task-tools]: https://github.com/agno-agi/agno/blob/cffd892a9024249f15e2cf556398444b221829af/libs/agno/agno/team/_task_tools.py
[agno-run]: https://github.com/agno-agi/agno/blob/cffd892a9024249f15e2cf556398444b221829af/libs/agno/agno/team/_run.py
[agno-storage]: https://github.com/agno-agi/agno/blob/cffd892a9024249f15e2cf556398444b221829af/libs/agno/agno/team/_storage.py
[agno-state]: https://docs.agno.com/state/team/overview
[agno-running]: https://docs.agno.com/teams/running-teams
