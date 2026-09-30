# MetaGPT、ChatDev / DevAll 与 CAMEL：从角色协作到可执行组织结构

> 核查日：2026-09-22。MetaGPT `11cdf466d042aece04fc6cfd13b28e1a70341b1f`；ChatDev `4fb2db0ea90375ce1059f44fe03ffbd191a7a169`；CAMEL `fc27907e31ea2074d6b65ceb121573c5fa1ab345`。主线静态阅读，未复现论文评测。历史论文只解释概念来源，当前行为以固定源码为准。

## 1. 为什么仍要研究这些较早出现的项目

2023 年这一批工作把“多个 LLM 对话”推进为有结构的协作：MetaGPT 强调 SOP 与工作产物，ChatDev 强调软件流程中的沟通链，CAMEL 强调角色交互与任务驱动。它们帮助形成了今天的角色、委派、共享环境和组织式提示词，但也不能用三年前的论文概括当前仓库。[MetaGPT 论文][metagpt-paper] [ChatDev 论文][chatdev-paper] [CAMEL 论文][camel-paper]

尤其 ChatDev 现在主线是 **2.0 DevAll**，1.0 已转入 legacy 分支；2.0 论文在 **2026-09-01** 提交。忽略这一步，会把一个通用图平台误写成固定 CEO / CTO 聊天演示。[当前 README][chatdev-readme] [新论文][devall-paper]

## 2. MetaGPT：用工作产物触发角色，而不是所有人一直群聊

### 2.1 入口与目录职责

`metagpt/team.py` 管团队、预算与外层轮次；`environment/base_env.py` 保存角色及消息路由；`roles/role.py` 管每个角色的 observe / react；`actions/` 定义具体工作；`memory/` 保存角色观察；schema 中的消息带来源与接收者。

该结构把“谁负责某类工作”与“本次怎么做”分开。新增角色通常组合 actions 和 watch 关系；改变通信应看 Environment；改变轮次终止应看 Team。直接让一个 Role 管全部成员会破坏这些职责。[Team][meta-team] [Environment][meta-env] [Role][meta-role]

### 2.2 输入变成可路由消息

用户 idea 进入 Environment。publish_message 根据角色地址和 send_to 判断接收者，把消息放到角色缓冲区，同时写环境 history。路由层只说明交给谁；接收角色还会用 watch / cause_by 判断是否需要对此类工作产物采取行动。

例如架构设计动作产出接口说明，可以触发程序员动作；程序员完成代码后触发审查。它比每轮把所有人叫起来讨论更节省无效参与，也让依赖通过产物类型表达。代价是 watch 关系不完整时，某个角色可能一直没有可处理事件，UI 需要解释等待原因。

### 2.3 角色观察、记忆与动作循环

Role._observe() 取出缓冲消息，过滤关心的来源或指向自己的消息，并通过 memory 避免重复处理。随后 react 选择普通 ReAct / 按序动作 / Plan-and-Act 等策略，完成动作后重置当前反应状态并发布结果。[Role][meta-role]

这里的 memory 主要记录角色已经看过的工作信息，不应直接写成跨项目的长期知识系统。设置“观察全部消息”与“只保存关心的消息”会改变上下文量；多角色系统的成本常常来自这类传播策略，而不只是成员数量。

### 2.4 并行推进与完成条件

Environment 每轮收集非 idle 角色并 `asyncio.gather`；Team 则在轮数、预算和环境 idle 等条件下推进或结束。环境空闲意味着当前没有进一步活动，不保证用户需求已经正确实现。[Environment][meta-env] [Team][meta-team]

这对 coding 任务是实质区别：代码不兼容但没人继续发消息，系统也可能停下来。应用应保存真实构建 / 工具事实，让结果可复查；不能把“所有角色安静了”直接显示为“验收完成”。源码有序列化与归档入口，本次没有验证进程崩溃后的具体恢复保证。

### 2.5 可借鉴与不适用的部分

SOP 产物契约适合接口设计、实现、审查的接力；按消息来源触发角色适合减少全员广播。固定公司职位则未必适合日常小改动，容易增加不必要的计划和文档。工具、MCP、Skill、OS sandbox 等扩展应逐项检查具体配置，本次没有据此宣称每个 Role 默认拥有完整 coding harness。

## 3. ChatDev 2.0 / DevAll：把组织方式变成用户可配置的图

### 3.1 历史与当前版本必须分开

ChatDev 1.0 的 chat chain 组织设计、编码、测试和文档，研究重点是角色沟通怎样减少信息缺失。2026-01-07 发布的 DevAll 把重点移到可配置的异构 Agent、动态关系、循环和可视化。9 月论文以可执行图和 cycle-aware engine 描述这一设计。[README][chatdev-readme] [论文][devall-paper]

另一个独立研究分支 puppeteer 学习选择和排列 Agent，让编排随任务状态调整；它不是主线里打开一个开关就自动训练整个系统。其强化学习优化编排策略的思路，也不同于模型递归修改自身并持续提升的 RSI。[Evolving Orchestration][puppeteer]

### 3.2 从画布配置到运行对象

当前 `entity/configs/` 定义节点、边和记忆等配置；`workflow/graph.py` 协调执行上下文；`workflow/topology_builder.py` 分析拓扑；`workflow/executor/` 提供 DAG、循环、动态边和并行执行；`runtime/node/executor/` 处理节点类型；`runtime/node/agent/memory/` 提供记忆适配。

一个图节点不是必然一个独立进程或会话窗口。节点表示一次可以被调度的工作，具体 Agent、工具或人工交互由对应 executor 处理。用户修改画布的边，改变的是数据和触发关系；宿主仍需解释节点输入、结果、取消和历史。

### 3.3 DAG 执行：分层屏障

DAGExecutor 按拓扑层遍历，层内检查 node.is_triggered() 后并行执行；当前 ParallelExecutor 用 ThreadPoolExecutor，等待本批 futures 后再进下一层。[DAG][devall-dag] [并行执行][devall-parallel]

这与“任意节点一就绪马上启动其后继”的全局事件调度不同。一个慢节点可能拖住同层其他节点的下游，即使那些下游只依赖已经完成的分支。这种分层屏障较直观，适合可视化演示和可控工作流；复杂任务追求低延迟时，需要衡量屏障带来的空等。

### 3.4 动态展开与循环

DynamicEdgeExecutor 的 map 模式把一组消息拆成 execution units，共享静态输入，每份生成一次目标节点执行。并发上限由 max_parallel 限制，收集可以按完成顺序发生，最终输出重新按原输入索引排列。这避免下游把第一个完成者误认为第一个输入的结果。[动态边][devall-dynamic]

循环则由 topology builder 把识别出的循环作为 super-node 排序，再交 CycleExecutor 推进循环内部与退出条件。图中允许循环不意味着随机无限聊天：循环本身成为有状态的调度单元。具体复杂图的性能和正确性未在本次运行验证。[拓扑][devall-topology] [循环执行][devall-cycle]

### 3.5 Blackboard 具体是什么

当前 BlackboardMemory 是轻量的追加式结果存储：MemoryItem 保留输出 / 输入快照、角色、时间与附件摘要，检索主要按最近 top_k 返回；这里的 query / similarity 参数不意味着进行了语义向量检索。[Blackboard][devall-memory]

这个实现还在读取损坏文件时退回空内容，保存时写 JSON 文件。它适合作为简单信息共享示例，不能在没有额外保护时承担本项目权威会话或多人任务状态。我们现有规则要求保留损坏记录并报告真实错误，也不能把这个 memory class 当成具备跨进程事务的共享黑板。

### 3.6 落地价值

DevAll 的价值是把协作拓扑变成可看、可改、可运行的产品对象。它适合研究后续工作流编辑器、成员图与运行视图。用户看得到图不代表知道当前在哪个节点；需要把执行事件、结果和配置版本关联起来。本次阅读未证明其归档可实现任意中断后的可靠执行恢复，也未验证企业部署规模。

## 4. CAMEL Workforce：从角色扮演走向任务通道和人工干预

### 4.1 目录和对象

CAMEL 的通用 Agent、toolkits、memory 等能力之外，多 Agent 组织位于 `camel/societies/workforce/`。Workforce 管分解、分派、依赖和总体进展；worker 适配单 Agent 或角色交互；TaskChannel 管任务传递；events / callbacks / metrics 负责观察。不能把早期两位角色扮演的示例当成当前全部功能。[Workforce][camel-workforce]

### 4.2 接收任务后选择自动分解或预设 pipeline

当前有 AUTO_DECOMPOSE 与 PIPELINE 两种模式。自动模式用 task_agent 根据主任务和可用成员生成 subtasks，并更新依赖关系；pipeline 则保留用户预设任务，支持串行、并行和 fork / join 组合。主入口选择相应路径，避免已经有业务计划时仍重复让模型拆任务。

自动分解是模型建议，依赖和分派是宿主后续需要维护的状态。若主任务变化，旧子任务的产物是否仍适用不能只看它们已经 DONE；应关联目标版本或至少保留创建时目标与时间。这是对实现的应用建议。

### 4.3 TaskChannel 怎样防止重复领取

TaskChannel 使用 asyncio.Condition，保存 task_id → Packet 以及状态、接收者、发布者索引。成员领取时，在同一个 condition 临界区内取出 SENT 任务并将其改为 PROCESSING，再返回。任务返回或状态改变会通知等待者。[TaskChannel][camel-channel]

这使同一进程中的并发消费者不会同时领到相同工作，不需要模型反复发消息确认。但它是内存通道，不是 Redis / 数据库持久队列。重启后的恢复必须另有保存与重建；不能把 atomic claim 的范围扩大成跨机器保证。

### 4.4 回收结果、暂停与快照

自动分解路径收集 subtasks 结果，检查子状态决定主任务 DONE / FAILED。interactive 入口可进入暂停、继续、查看 / 修改 pending task 和快照流程。暂停事件还会传递到工作 Agent，减少只有上层 UI 显示暂停而子执行仍不停的情况。[Workforce][camel-workforce]

`save_snapshot()` 当前将 WorkforceSnapshot 追加到对象内部 `_snapshots`。快照复制队列、完成列表、依赖和 assignees 等容器，不因此成为磁盘检查点，也没有保存任意操作系统进程。讨论“支持恢复”时，应明确是对象仍存活时的人机干预快照，还是独立实现的持久恢复路径。

### 4.5 参考价值

CAMEL 适合研究自治分解与用户显式 pipeline 的共存，以及任务通道如何独立于模型实现。其丰富工具和研究场景有探索价值，但 Workforce 对象本身不提供本项目的项目目录登记、编辑冲突策略或 Windows 进程隔离。我们可吸收任务领取与事件通知，不必移植整个生态。

## 5. 三条演化路径对本项目的意义

MetaGPT 把组织经验转成产物与触发关系；ChatDev 从固定流程发展到可编辑执行图；CAMEL 从角色交互扩展成任务调度与人工干预。共同经验是：prompt 可以指导分工，但稳定协作需要宿主持有可解释的状态。

本项目已有自由会话与委派，应先补足成员、工作项和结果的清楚关系，再评估可视化图或自适应编排。也应保留一个简单入口：一个 Agent 足以处理的任务直接完成，不要求先扮演一家软件公司。

[metagpt-paper]: https://arxiv.org/abs/2308.00352
[chatdev-paper]: https://arxiv.org/abs/2307.07924
[camel-paper]: https://arxiv.org/abs/2303.17760
[devall-paper]: https://arxiv.org/abs/2609.00714
[puppeteer]: https://arxiv.org/abs/2505.19591
[meta-team]: https://github.com/FoundationAgents/MetaGPT/blob/11cdf466d042aece04fc6cfd13b28e1a70341b1f/metagpt/team.py
[meta-env]: https://github.com/FoundationAgents/MetaGPT/blob/11cdf466d042aece04fc6cfd13b28e1a70341b1f/metagpt/environment/base_env.py
[meta-role]: https://github.com/FoundationAgents/MetaGPT/blob/11cdf466d042aece04fc6cfd13b28e1a70341b1f/metagpt/roles/role.py
[chatdev-readme]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/README.md
[devall-dag]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/workflow/executor/dag_executor.py
[devall-parallel]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/workflow/executor/parallel_executor.py
[devall-dynamic]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/workflow/executor/dynamic_edge_executor.py
[devall-topology]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/workflow/topology_builder.py
[devall-cycle]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/workflow/executor/cycle_executor.py
[devall-memory]: https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/runtime/node/agent/memory/blackboard_memory.py
[camel-workforce]: https://github.com/camel-ai/camel/blob/fc27907e31ea2074d6b65ceb121573c5fa1ab345/camel/societies/workforce/workforce.py
[camel-channel]: https://github.com/camel-ai/camel/blob/fc27907e31ea2074d6b65ceb121573c5fa1ab345/camel/societies/workforce/task_channel.py
