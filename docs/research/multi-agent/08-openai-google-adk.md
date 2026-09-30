# OpenAI Agents SDK 与 Google ADK：调用式协作和任务协议的演化

> 核查日：2026-09-22。OpenAI Agents Python 固定 `ad93f5420edfecb30c6d2bc3a1a22047918cba1a`；Google ADK Python 固定 `38339768c6bee499c90d29ac8218916ed1a816ef`。均为主线快照，未执行 SDK 示例。两节各自按输入、委派、上下文、执行、恢复组织。

## 1. OpenAI Agents SDK：先区分委派与控制权转移

### 1.1 适用问题与仓库组织

Agents SDK 提供较小的 Agent / Runner 核心，让应用选择用代码安排流程，还是让模型通过工具和 handoff 决定下一步。它适合在既有服务中嵌入协作能力，不要求先部署一个团队管理平台。[官方编排说明][openai-orchestration]

当前 `src/agents/agent.py` 管 Agent 定义和 `as_tool`；`run.py` 是公共运行入口，复杂推进拆到 `run_internal/` 的 run_loop、turn_preparation、tool_execution、approvals、session_persistence 等模块。`memory/` 管会话后端，`mcp/` 管工具连接，`tracing/` 管观察；新增的 `sandbox/` 又把执行资源和 capabilities 拆出。把整个 SDK 概括成早期 Swarm 的几百行 handoff 循环已不准确。

这种拆分的意义是：调整“交接后谁继续回答”应看 run_loop，调整“子 Agent 接收哪些参数”应看 agent tool，调整“会话怎样保存”应看 persistence，不能全部塞进一个多 Agent manager。

### 1.2 输入进入后：manager 调用和 handoff 是两种控制流

`Agent.as_tool()` 把专家包装成 FunctionTool。主 Agent 生成输入，子 Agent 执行，结果作为工具输出返回，主 Agent 继续综合。handoff 则改变当前 active Agent，使专家接过本轮对话；在 run_loop 中可直接看到 `NextStepHandoff` 更新 current_agent 和 run_state，并发出 AgentUpdatedStreamEvent。[as_tool 源码][openai-agent] [运行循环][openai-loop]

例如需要“分析三个方案后给一个建议”，manager-as-tool 易于保留统一回答责任；需要“判断问题属于数据库后交给数据库专家持续沟通”，handoff 更自然。handoff 的控制权转移并不自动新建一个独立桌面会话，也不等于分布式进程迁移。

### 1.3 子 Agent 的输入输出可以是契约

当前 as_tool 支持 dataclass / Pydantic 参数类型和 input_builder，把结构化工具参数转成子输入；custom_output_extractor 控制回传内容。子 Run 还携带 agent_tool_invocation 关联信息，并可指定 session 或 provider 续接身份。[as_tool 源码][openai-agent]

对 coding 协作而言，可以把目标、相关路径、已确定接口和期望结果做成明确字段；子过程完整 trace 留在观察层，只把必要结论交给 manager。它减少父上下文膨胀，也便于判断“委派信息不足”还是“子 Agent 执行失败”。结构合法不能替代内容正确，schema 不应变成强迫模型填写无用元数据的理由。

默认失败可转换为工具错误交给模型；配置为不使用 failure_error_function 时则抛出异常。这是 SDK 选择，应用必须明确哪些是可修正参数反馈、哪些是真实模型 / 执行故障，不能把所有异常吞进字符串后继续运行。

### 1.4 并行和流式观察

应用可用代码并行运行独立 Agent，模型也可发出多个工具调用；但并行能力与完整 Team 生命周期仍是两回事。SDK 不会因为三个 as_tool 调用就自动生成共享任务所有权、成员收件箱和代码合并策略。[官方编排说明][openai-orchestration]

当前 as_tool 的 `on_stream` 能观察嵌套运行及来源 tool call。默认最多缓存 1024 个待处理事件；处理方持续跟不上时会取消嵌套运行并走失败路径。这个限制针对事件数量，不是字节大小或全部内存。因此多 Agent UI 不能无限积压 token 事件，也不能把一个“队列有上限”的参数宣称为完整内存预算。[as_tool 流事件契约][openai-agent]

### 1.5 Session、RunState 与 SandboxSession 分别保存什么

Session 协议提供 get_items、add_items、pop_item、clear_session，核心是某段对话的消息历史。RunState 表达当前执行与交互接续；sandbox session 表达实际执行环境。它们应使用不同身份和生命周期，不能因为都叫 session 就用一个 ID 替代所有关联。[Session 源码][openai-session]

尤其不能仅凭 SQLiteSession 就声称拥有持久的分布式任务调度。历史保存、在途调用恢复和外部副作用提交是不同保证。

### 1.6 新增 SandboxAgent：SDK 也开始提供 harness 能力

当前官方把 sandbox agents 标为 beta。源码中 `SandboxAgent` 继承 Agent，持有默认 Manifest、capabilities 和 run_as；实际 client / live session 通过 RunConfig 在运行时传入，避免 Agent 定义永久绑定某台执行实例。[SandboxAgent][sandbox-agent] [官方概念][sandbox-guide]

Manifest 表达工作区 entries、环境、用户和组；capabilities 可提供文件、shell、Skill、记忆和压缩。runtime session manager 区分自己创建与外部注入的 session，cleanup 对借用资源的处理与自己拥有的资源不同。这是可复用 SDK 必须处理的所有权问题。[Manifest][manifest] [资源管理][sandbox-manager]

记忆又与会话历史分开：官方说明支持把已有运行提炼成工作区文件，先提供摘要，再按需读取细节；复用依赖保存对应目录、live session 或快照。多个成员若不加区分地往同一记忆目录写，可能把局部经验混成通用规则，应用应选择哪些角色可生成记忆以及布局范围。[记忆说明][sandbox-memory]

这里值得吸收的是运行配置与定义分开、资源所有权和记忆布局；本项目仍维持 Windows 本机默认执行、sandbox 可选。SDK 中存在 sandbox client 不能成为我们普通任务必须启用容器的理由。

## 2. Google ADK：从 Agent 层级扩展到结构化任务和 Workflow Runtime

### 2.1 当前资料需要补上的变化

当前仓库已把 Workflow Runtime 和 Task API 放在核心能力中；不能只描述早期的 SequentialAgent、ParallelAgent、LoopAgent。ADK 2.0 官方提供 chat、task、single_turn 协作模式，分别表达持续对话、可澄清的任务、以及无用户交互的单次任务。[当前 README][adk-readme] [协作模式][adk-collaboration]

这里的 single_turn 是任务交互模式，不能不加区分地解释成“恰好一次模型 API 请求”；工具驱动过程仍要由具体运行实现处理。

### 2.2 仓库边界

| 位置 | 对应责任 |
| --- | --- |
| `src/google/adk/agents/` | Agent 类型、层级、模型循环、传统模板编排 |
| `agents/llm/task/` | 结构化 TaskRequest / TaskResult 与任务模式协议 |
| `tools/agent_tool.py` | 兼容 AgentTool 与框架内部委派标记 |
| `workflow/` | 图节点、trigger、执行状态与恢复调度 |
| `sessions/`、`events/` | 会话服务与持久事件 |
| `tools/`、`artifacts/` 等 | 工具适配与产物服务；不等同 OS 文件隔离 |

Google 的 Session / Event 模型贯穿协作：节点执行状态可以从事件重建，而用户看到的聊天只是其中一种投影。新增任务类型时，不应只改 LlmAgent 的 prompt，还需要检查任务事件、分支上下文和 workflow 的恢复路径。

### 2.3 输入、委派与自动返回

TaskRequest 包含 agent_name 和已校验 input，TaskResult 包含 output；默认任务输入将 goal / background 分开。一个任务 Agent 通过 finish_task 返回，父协调者继续工作；chat 型交接的返回则需要显式转交。不同模式决定谁负责下一步，不能只靠 prompt 写“完成后告诉老板”。[任务数据模型][adk-task] [官方模式说明][adk-collaboration]

当前 `AgentTool` 的源码说明建议优先用 `mode='single_turn' + sub_agents`，由框架自动暴露内联工具；直接包装 AgentTool 已不再是唯一推荐入口。旧 AgentTool 路径仍有自己的 nested Runner，会把 state_delta 回写到父工具上下文，并关闭 MCP 等资源。因此“AgentTool 里的子 Agent 全部状态隔离”也是不准确的概括。[AgentTool][adk-agent-tool]

### 2.4 上下文分支与产物读取

任务模式把成员放在自己的 session branch 中，模型构造上下文时不自动看见并行兄弟的过程；父协调者接收结果后再推进。需要父 artifacts 时仍应提供对应加载工具。分支隔离解决的是模型输入污染，外部存储或文件是否共享要另行判断。[协作模式][adk-collaboration] [AgentTool][adk-agent-tool]

公开文档目前还存在发布范围提醒：Python v2.0.0 的 task mode 在 graph-based workflows 中被注明暂时禁用，同页又讨论通用图节点语义。不能把后者理解为所有发行版已支持。本次固定主线能看到新的 task / workflow 代码，但没有运行某个 wheel 验证组合，故保留这个兼容性限制。

### 2.5 并发事件如何汇合

`ParallelAgent` 使用 TaskGroup 推进子生成器，每个子分支放出一个事件后等待上游消费信号，再继续产生事件。这种背压防止某个快速成员把结果流淹没，也让 Session 层按自己的速度处理事件。[并行源码][adk-parallel]

分支异常先作为完成信号中的错误放入队列，由汇合生成器抛出；代码专门避免在生成器暂停于 yield 时由 TaskGroup 直接异常取消调用者。失败、用户取消和正常结束因此保持不同语义。这个实现细节直接关系桌面 streaming UI，不是一个 `asyncio.gather` 示例能完整表达的。

### 2.6 Workflow 如何恢复

`workflow/_workflow.py` 的 `_LoopState` 保存本次运行的节点、pending tasks、trigger buffer、缓存输出与动态节点状态。它明确不整体持久化；恢复时从 Session events 重建节点执行，并用 node_name@run_id 识别执行、sequence barrier 保持重放顺序。[Workflow][adk-workflow]

这条路线与 MAF 保存 checkpoint 对象的方式不同，但都必须保存“发生了什么”以及“下一步该推进谁”。恢复时重建的 Python task 不是崩溃前原任务，外部命令和网络副作用仍不能凭事件重放宣称 exactly-once。

## 3. 两条路线怎样为本项目提供参考

| 问题 | OpenAI SDK 的参考 | ADK 的参考 | 本项目可吸收的部分 |
| --- | --- | --- | --- |
| 委派后谁继续回答 | as_tool 与 handoff 分开 | chat / task / single_turn 分开 | 明确调用式结果回收与会话交接 |
| 子任务输入如何控制 | 结构化参数和 input_builder | TaskRequest schema 与分支 | 使用已有上下文快照，允许小范围输入 |
| UI 怎样看子过程 | 嵌套流事件与来源关联 | 分支事件汇合及背压 | 完整 Trace 与父模型摘要分开 |
| 多轮保存什么 | Session / RunState / sandbox 分开 | Session events 与图执行重建 | Task、Session、Run、Execution 身份分离 |
| 是否自带完整团队 | 需应用补任务与成员层 | 模式与层级仍需产品工作项 | 不把 SDK 接入当作 Teams 已实现 |

二者都在从早期的轻量编排向更明确的任务、执行资源和状态管理演化。对本项目最有价值的是这些边界，而非为了框架兼容重写现有模型接口。主线新能力也需要版本固定和小范围真实验收，不能根据 README 的能力清单直接宣称落地成功。

[openai-orchestration]: https://openai.github.io/openai-agents-python/multi_agent/
[openai-agent]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/agent.py
[openai-loop]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/run_internal/run_loop.py
[openai-session]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/memory/session.py
[sandbox-agent]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/sandbox/sandbox_agent.py
[manifest]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/sandbox/manifest.py
[sandbox-manager]: https://github.com/openai/openai-agents-python/blob/ad93f5420edfecb30c6d2bc3a1a22047918cba1a/src/agents/sandbox/runtime_session_manager.py
[sandbox-guide]: https://openai.github.io/openai-agents-python/sandbox/guide/
[sandbox-memory]: https://openai.github.io/openai-agents-python/sandbox/memory/
[adk-readme]: https://github.com/google/adk-python/blob/38339768c6bee499c90d29ac8218916ed1a816ef/README.md
[adk-collaboration]: https://adk.dev/workflows/collaboration/
[adk-task]: https://github.com/google/adk-python/blob/38339768c6bee499c90d29ac8218916ed1a816ef/src/google/adk/agents/llm/task/_task_models.py
[adk-agent-tool]: https://github.com/google/adk-python/blob/38339768c6bee499c90d29ac8218916ed1a816ef/src/google/adk/tools/agent_tool.py
[adk-parallel]: https://github.com/google/adk-python/blob/38339768c6bee499c90d29ac8218916ed1a816ef/src/google/adk/agents/parallel_agent.py
[adk-workflow]: https://github.com/google/adk-python/blob/38339768c6bee499c90d29ac8218916ed1a816ef/src/google/adk/workflow/_workflow.py
