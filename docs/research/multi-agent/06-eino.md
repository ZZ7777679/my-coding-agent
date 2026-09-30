# Eino ADK：以调用边界组织 Agent，以 Runner 管理中断与多轮

> 核查日：2026-09-22。源码 `cloudwego/eino@b9539ec114a14c32aa568f05eda5cde1e83fcfc1`，主线静态快照。官方 quickstart 当时推荐 v0.9.0，但本文不将主线所有 API 等同于该发布包。未编译或执行 Go 示例。

## 1. 定位：国内 Go 生态的组件、编排与 Agent 运行层

Eino 不是一个预设“产品经理—程序员—测试员”的组织。底层组件抽象模型、工具和消息；compose 层组合计算图；ADK 提供 Agent、Runner、事件、上下文和恢复；prebuilt 再提供 DeepAgent、Plan-Execute 等组合。角色和业务 prompt 位于这些机制之上。[官方入口][quickstart]

这条路线与桌面 coding 产品的关系是：可以借鉴类型和生命周期设计，但不需要把 Python 核心改成 Go。特别值得看的是，Eino 将“一次调用”“一个持续多轮入口”“调用子 Agent”“把控制权转交另一 Agent”分别表达，避免在一个万能 `chat()` 里混合所有状态。

## 2. 仓库组织及阅读路径

| 位置 | 核心职责 | 与其他层的边界 |
| --- | --- | --- |
| `schema/`、`components/` | 消息和工具 / 模型接口 | 面向可替换组件，不负责产品会话 |
| `compose/` | 图、链、节点与底层运行 | 确定性编排可以包含非 Agent 节点 |
| `adk/runner.go` | 启动、流式事件、checkpoint / resume | 应用入口；不把角色 prompt 当调度器 |
| `adk/agent_tool.go` | 把一个 Agent 封成工具调用 | 控制输入、输出和 action 的传播范围 |
| `adk/workflow.go` | 顺序、并行、循环 Agent | 当前保留，但有明确使用建议变化 |
| `adk/prebuilt/deep/` | 文件 / shell / todo / 子任务能力装配 | 构造 ChatModelAgent，不另造模型循环 |
| `adk/prebuilt/planexecute/` | planner、executor、replanner 协议 | 明确计划如何进入下一轮与如何结束 |

当前代码还提供 `TypedAgent[M]` / `TypedRunner[M]`，兼容不同消息表示。旧的 `Agent` / `Runner` 是常用消息类型的入口。这个泛型不是纯语法替换：完整历史重写逻辑只适用于特定 Message 语义，AgentTool 对不支持的 AgenticMessage 路径明确拒绝，而不是偷偷强转。[Runner][runner] [AgentTool][agent-tool]

## 3. 第一步：Runner 接收输入，Agent 产生事件

Runner 把 Query 或消息数组转成一次执行，管理 flowAgent 路径、名称、回调和取消。应用消费 `AsyncIterator[AgentEvent]`，事件不仅有回答，还可以携带错误、中断或控制动作。这样桌面 UI 能持续观察过程，而业务核心不必直接依赖界面。

CheckpointStore 是可配置的保存接口。声明 Agent 能 Resume，不代表应用已经接入持久存储；只有正确保存状态并使用对应 checkpoint ID，才具备跨调用恢复基础。多轮入口则交给 TurnLoop，以 Push、Preempt、Stop 管理后续输入和在途执行。一次 Runner 调用与一个长期对话因此不是同一对象。[Runner 源码][runner] [官方生命周期说明][extension]

对本项目而言，这支持继续保持 SessionService 与单次 Run 分离。用户追问、后台结果、停止和明确接续都应该落到已有运行入口，而不是为多 Agent 新建一套平行的请求循环。

## 4. 第二步：通过 AgentTool 委派，并限定上下文传播

`NewAgentTool()` 用子 Agent 名称、描述生成工具目录项。默认输入来自工具参数中的 request；只有显式选择时才使用父完整历史。DeepAgent 的 task 工具再把 `subagent_type + description` 映射到对应 AgentTool。因此选择子类型是目录路由，真正执行仍落在同一个 AgentTool 机制中。[AgentTool][agent-tool] [task 工具][task-tool]

这有两个实际收益。首先，角色实现可以独立替换，主 Agent 不必知道子循环细节。其次，子任务所需信息可以设计成稳定输入契约。例如让审查 Agent 接收改动范围、关心的问题和基线，而不是父会话几百轮消息；它得到的输入更容易解释和评估。

但“默认不传完整历史”不能被写成“所有状态绝对隔离”：源码仍存在 parent session 桥接和运行上下文传递。输入投影、事件流、共享会话值和外部工具资源必须分别检查。

### 4.1 子事件可显示，不等于已写进父检查点

开启 EmitInternalEvents 时，子 Agent 的事件可转发到父生成器，让用户看到实时过程；源码明确说明这些事件不因此进入父 runSession 或父 checkpoint。最终工具结果才是父模型通常消费的摘要。[AgentTool 事件契约][agent-tool]

UI 若只保存最终回答就无法复查子过程；若把所有 UI 事件反灌父模型又会失去上下文分区的意义。较合适的设计是完整 trace 留给观察者，相关结果投影给父模型。这是架构推论，不是 Eino 自带的完整桌面产品。

### 4.2 子 Agent 的控制动作有作用域

子 Agent 的 Exit、TransferToAgent、BreakLoop 不直接向外终止或切换父执行。只有中断通过 CompositeInterrupt 传播，以便跨 Agent 的 HITL 恢复。这类似普通函数内部 return 不应退出整个程序：如果缺乏调用边界，一个子审查员宣布结束可能意外结束用户总任务。

中断时 AgentTool 保存 bridge store；恢复时利用保存状态重建内部 Runner 并 Resume。这里传递的是恢复协议，不是让父 Agent 把中断文本重新解释成全新任务。[AgentTool][agent-tool]

## 5. 第三步：DeepAgent 在这些边界上组装能力

`prebuilt/deep/deep.go` 组装 built-in middleware、todo、文件 backend、shell，以及可选通用子 Agent 和显式子 Agent 列表，最终返回 `TypedChatModelAgent`。task 工具按类型查表，找不到就返回明确错误；它本身没有团队收件箱、成员认领或跨进程租约。[DeepAgent][deep]

文件 backend 与 Shell / StreamingShell 是执行能力入口。是否隔离、是否共享项目文件由具体实现决定，不能因为类名包含 DeepAgent 就宣称带 OS sandbox。记忆、Skill 和压缩也属于配置与 middleware 能力，不能与持久会话 checkpoint 混为“一个 memory”。

这个设计适合本项目的地方是：把子 Agent 当现有运行时的另一种装配配置，而不是不同职责就新写一种循环。角色可以改变 Skill 目录、工具集合和输入构造，取消、预算、错误与持久化仍应复用统一服务。

## 6. 第四步：计划、执行和再计划怎样形成循环

Plan-Execute 的当前组合是 `Sequential(planner, Loop(executor, replanner))`。Planner 写出结构化计划；Executor 根据计划和已执行步骤处理下一步；Replanner 同时看到原目标、当前计划和 executed_steps，选择更新计划或使用 respond 工具结束。迭代上限由配置控制，默认值不等于任务成功条件。[Plan-Execute 源码][plan]

例如“迁移接口并保持旧客户端兼容”可能先计划改服务端、改调用方、验证。执行第一步发现协议生成器也需要更新，replanner 可以插入新步骤。若只用一份初始 todo 并逐项打勾，就无法表达这种基于执行反馈的计划变化。

这仍不是证明计划正确的系统。模型可能错误判断完成，或重复改写计划而没有实质进展。应观察真实产物和执行结果；但本项目不应因此强制每轮附完整证明表或引入新的任务结束门槛。

## 7. 第五步：并行分支和定向恢复

`workflow.go` 的并行执行为各分支建立上下文，用 goroutine 推进并把事件交给生成器。恢复时只继续仍有中断点的分支，已完成分支不再次运行；无中断时再合并子上下文。保存每个分支的中断数据，避免一个用户回答让所有分支从头开始。[Workflow 源码][workflow]

定向 Resume 则把恢复数据映射到具体组件地址。没有被选中的中断组件仍需保持中断状态。这对多个成员同时等待不同用户回答很重要：用户同意了一次部署，不等于批准其他成员所有待处理请求。[HITL 设计][hitl]

不过，已完成图步骤不重跑并不能保证外部命令只执行一次；若命令已经产生副作用但 checkpoint 尚未保存，仍存在提交窗口。恢复契约必须结合工具幂等或明确用户接续，不能只依赖图运行时。

## 8. 当前主线最值得注意的设计转向

本次快照在 `NewSequentialAgent`、`NewParallelAgent`、`NewLoopAgent` 注释中标记 **NOT RECOMMENDED**，理由是这些 Workflow Agent 建立在完整上下文共享的 Agent transfer 上，未被证明更有效；建议大多数多 Agent 场景优先考虑 ChatModelAgent + AgentTool 或 DeepAgent。[源码 L689–714][workflow]

这是当前源码的建议，不是“顺序执行、并行计算或所有图编排已经废弃”。compose 图仍有独立价值，Plan-Execute 当前实现也仍组合这些 API。真正改变的是对通用 Agent 协作边界的偏好：逐渐强调小范围委派和输入输出控制，而不是默认所有参与者传递全部历史。

我们不应仅凭这个注释宣布它性能更好；源码没有提供可直接复现的比较结果。本项目可以把它转成后续评估问题：相同任务与预算下，完整继承、摘要委派和结构化输入各自的成功率、成本和返工量是多少。

## 9. 适用性与落地价值

Eino 对已有 Go 服务、需要严格类型接口、事件消费和 HITL 的团队尤其有意义。对本项目，最有用的是 AgentTool 的控制作用域、子事件与父模型输入分离、分支定向恢复。它没有自动提供个人桌面所需的项目登记、Windows 进程管理、团队 UI 或代码集成策略；这些仍是应用责任。

本次证据是官方设计与开源实现，没有独立验证生产规模或吞吐。国内 Java 路线 Spring AI Alibaba、工作流平台 Coze 的对照见 [企业应用平台](14-enterprise-platforms.md)；不要把 Go / Java / Python 的语言选择误当成多 Agent 协作质量的结论。

[quickstart]: https://www.cloudwego.io/docs/eino/core_modules/eino_adk/agent_quickstart/
[extension]: https://www.cloudwego.io/docs/eino/core_modules/eino_adk/agent_extension/
[hitl]: https://www.cloudwego.io/docs/eino/core_modules/eino_adk/agent_hitl/
[runner]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/runner.go
[agent-tool]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/agent_tool.go
[deep]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/prebuilt/deep/deep.go
[task-tool]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/prebuilt/deep/task_tool.go
[plan]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/prebuilt/planexecute/plan_execute.go
[workflow]: https://github.com/cloudwego/eino/blob/b9539ec114a14c32aa568f05eda5cde1e83fcfc1/adk/workflow.go
