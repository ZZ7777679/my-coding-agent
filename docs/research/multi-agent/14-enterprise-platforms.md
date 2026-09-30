# 企业应用平台：Spring AI Alibaba、Coze、Dify 与托管多 Agent

> 核查日：2026-09-22。开源 / 源码可见部分固定到当天提交；云产品依据官方文档。本篇侧重“业务配置怎样成为可执行协作”，不将平台中的每个 LLM 节点都叫作独立 Agent。Strands 的多 Agent 运行时另见 [专篇](15-strands.md)。

## 1. 为什么 Coding Agent 还需要看业务平台

假设一个团队希望把“收集需求—查询资料—形成方案—人工反馈—继续执行”固化下来。Coding Agent 的 CLI 可以完成任务，但企业平台还必须处理配置版本、不同用户会话、流程节点恢复、工具凭据和发布渠道。它们的架构价值主要体现在这些长期维护边界，而非角色提示词写得更多。

需要区分四层：编排库描述执行拓扑；业务平台保存和发布应用配置；运行平台提供进程、隔离和伸缩；观测平台记录行为并支持评估。这些层可能来自同一家，也可能组合使用。选择 Spring AI Alibaba 不等于自动使用阿里云；选择 Strands 不等于已经部署 AgentCore；Dify 可视化工作流也不等于拥有持续通信的团队。

## 2. Spring AI Alibaba：Agent 是图的封装，企业集成位于外层

### 2.1 仓库与输入装配

固定提交：`f82da0b50f35744c13968191be2b1cd2452ef550`。核心阅读范围为 `spring-ai-alibaba-agent-framework` 与 `spring-ai-alibaba-graph-core` 的五个入口文件；本轮未逐行分析全部图调度器与生态集成。

`ReactAgent` 持有模型节点、工具节点、编译配置和 hooks；`FlowAgent` 的具体类型把子 Agent 组合成图；`CompiledGraph` 负责已编译图的执行和状态访问。这样，业务可以以 Agent API 使用完整循环，也可直接控制底层图。[ReactAgent][spring-react] [CompiledGraph][spring-compiled]

一次调用先把 instructions、模型与工具连接为 ReAct 循环。`ReactAgent` 装配时创建 `StateGraph`，加入 model / tool 节点，再按 before / after agent、model 等位置组织 hooks。默认 instruction hook 也通过这条路径进入，而不是在界面层拼出一份不受运行时管理的提示词。

**设计收益：**工具审计、消息改写和人工中断可以找到确定的生命周期位置。**代价：**hook 顺序会影响实际输入，排查问题必须看装配后的链，而不能仅看 Agent 配置。为每个角色复制一份 model-tool 循环会失去这项收益。

### 2.2 如何决定下一位执行者

`SequentialAgent` 表达事先确定的顺序；`ParallelAgent` 表达 fan-out / gather；`LlmRoutingAgent` 持有路由模型，并通过 `FlowGraphBuilder` 构造路由图。前两者主要由程序决定拓扑，后一种让模型参与选择目标。[顺序 Agent][spring-sequential] [并行 Agent][spring-parallel] [路由 Agent][spring-routing]

`ParallelAgent` 把 `maxConcurrency` 写入运行配置元数据，供底层并行节点读取，同时提供 `MergeStrategy` 和输出键。这是两个不同职责：限制同一时刻运行多少节点，不能替代定义怎样合并多个结果。后者可能是结构化结果组合，也可能另交一个模型综合。

例如两个 Agent 分别查产品和库存，结果可以保存在不同字段；若两个节点同时写同名字段，则必须明确是追加、覆盖还是专门归并。所谓“共享状态”如果不说明字段的更新规则，就隐藏了最关键的并发语义。

官方文档还描述 Supervisor 模式，但本轮固定快照中未按旧教程名称找到独立 `SupervisorAgent.java`，因此不把教程类名写成已核对的当前实现。使用时应跟随当前 builder 和示例，而不是照搬旧 API。[官方多 Agent 说明][spring-docs]

### 2.3 回合结束、历史和恢复

`CompiledGraph` 的 `getStateHistory`、`stateOf` 等方法依赖 `CheckpointSaver`；未装配 saver 时不能假定存在历史恢复。图状态和 checkpoint 由这一层管理，应用业务的用户、租户、发布版本仍需外层关联。

这给本项目的参考是“统一图 / Agent 执行接口，具体策略显式装配”，而不是转向 Java 或引入整套 Spring。项目现有 Python SessionService 也应继续承担真正的模型循环，工作流模板不应复制它。

官方 1.0 GA 文章提到 Nacos、Higress、ARMS 等集成。这是生态入口和历史演化证据，不证明每个当前部署都已配置这些组件，也不是必须全部安装的运行门槛。[历史发布说明][spring-ga]

## 3. Coze Studio：可视应用配置如何进入 Eino 执行图

### 3.1 仓库组织与平台边界

固定提交：`fefb05ff27be1da939612fbf9faf5db62583b8ae`。本轮抓取包含完整可读的相关后端路径；整仓下载在 Windows 超长前端路径处中止，因此不能称为完整仓库镜像。

后端有 `api`、`application`、`domain`、`infra` 等职责。请求入口进入应用层，Agent 定义和发布由领域服务管理；`domain/agent/singleagent/internal/agentflow` 组装执行图，工作流有另一组 schema、节点与执行适配。底层采用 Eino；因此平台保存的产品配置与框架可执行对象并非同一种数据。[Agent 构造器][coze-builder] [节点执行器][coze-node]

Coze Studio 公开仓库不能作为闭源 Coze 产品所有能力的源码说明。特别是从本轮核对的 `singleagent` 执行路径，不能推出已经存在任意持续通信的 Teams。

### 3.2 一次请求的数据流

`agent_flow_builder.go` 把请求映射到 persona 渲染、prompt 变量、知识检索、工具预检索，再进入聊天模板和模型节点。需要工具循环时，模型节点替换为 ReAct 子图；可选的建议问题图在回答之后执行。

值得注意的是，知识检索结果不是直接等于长期记忆。检索节点产生本次请求上下文，变量和业务存储有自己的来源；它们最后进入 prompt 的位置和形式由图决定。研究 Coze 时只写“支持知识库和记忆”会漏掉这一实际装配链。

图编译采用 `AllPredecessor`，依赖输入准备完成后才执行后继；checkpoint 只在 `requireCheckpoint` 成立时装配。这一控制方式很适合需要确定流程的企业应用：哪些准备步骤必须结束，是开发者在图中表达的，不让模型每轮重新猜。

### 3.3 节点适配器承担什么

`node_runner.go` 将平台节点 schema 转成实际 Invoke / Stream / Collect / Transform 调用，并统一接入输入转换、输出处理、超时、配置化重试和错误分支。流式接口不是给非流式返回值简单加一个 SSE 外壳：输入输出转换和回调都需要对应处理。

这种结构能让工作流编辑器更稳定地添加节点类型。但它也意味着自动补默认值、错误回退、重试等行为具有平台语义，不能机械移植。本项目已经明确实际执行故障停止；即使上游支持节点重试，也不构成改变本项目规则的依据。

**落地价值：**借鉴“模板定义—编译适配—执行事件”分层，以及同一种工具支持不同调用形态时的统一适配。**不宜照搬：**完整多租户后台、渠道系统及大量业务节点，它们超出个人桌面产品当前需要。

## 4. Dify：当前主线已经不只是旧版 Agent 策略节点

### 4.1 新旧路径必须分清

固定提交：`a6b41ac6d141ebb28d9b90cbe9d2a487379054ac`。本轮同时发现 `nodes/agent` 和 `nodes/agent_v2`；本文重点分析 v2，不能将其写成所有已安装 Dify 版本的默认行为。

当前 `WorkflowEntry` 引入 `graphon` 的 `Graph`、`GraphEngine`、运行状态、变量池、命令通道及事件类型。它自身负责 Dify 业务上下文、节点工厂和响应适配。代码明确提到 Graphon v0.5.0 原始变量流需要响应顺序过滤器，以保持 Dify 向外提供的行为。[工作流入口][dify-entry]

这是一种重要演化：图运行引擎逐渐成为独立依赖，业务产品保留自己的发布、用户和消息协议。不能继续只画“Dify API → 自带旧 GraphEngine → LLM”而忽略真实模块边界。

### 4.2 Agent 节点怎样成为一次有身份的工作

`DifyAgentNode` v2 注入 binding resolver、runtime request builder、AgentBackend client、event adapter、output adapter、类型检查器与 session store。节点执行开始时先查是否已经存在运行 scope；若有，沿用其 binding 和配置 snapshot，而不是重新采用刚被编辑的 Agent 配置。[Agent v2][dify-agent]

scope 同时保存 tenant、app、workflow、workflow run、node、node execution、Agent、配置快照等身份。这不是字段越多越高级，而是它们回答不同问题：同一节点第二次执行，与另一节点使用同一个 Agent 定义，不应共享错误的在途结果。

请求构建器把图变量转换为 Agent 的调用输入；AgentBackend 返回内部事件；节点再把它们转成图执行事件。输出 adapter 负责工作流需要的返回形式。模型循环因此可以与可视图调度解耦。

### 4.3 多轮对话与一次工作流的工作区不同

`session_store.py` 的 `resolve_workflow_agent_workspace_owner_scope` 明确分支：Chatflow 带有 `conversation_id` 时，工作区归属于会话，可跨轮保留 Agent 记忆；纯 workflow 的工作区归属于本次 workflow run。另用节点与 binding 区分参与者。[会话存储][dify-session]

这与本项目很相关：用户侧会话是长期容器，内部委派是某次任务安排，两者不宜简单共用一份不分来源的消息列表。记忆可以有跨轮范围，但一次执行的结果和取消仍需绑定 Run。

### 4.4 人工输入如何暂停和接续

Agent 请求人工输入时，外层图暂停。恢复后 Graphon 可能再次进入节点 `_run`；节点从已有 session 中读取待处理表单与 tool call 标识，将人工回答转为 deferred tool results。如果表单仍未结束，它会再次产生暂停，而不是把未回答当作空字符串继续。

这里的关键不是“增加一次审批”，而是把已有交互的挂起状态和对应调用保存下来。对于真正需要澄清的信息，这能避免重启后重复提问或把答案交给错误调用。本项目已有 HITL，不应借此新增普通工作不需要的确认。

### 4.5 输出检查与副作用边界

v2 保存 session snapshot 后，对声明输出做类型检查，并可按配置重试、使用默认值或进入失败分支。类型满足节点接口，只能证明下游拿到可消费的数据，不证明模型说的业务结论正确。重试同样不能自动保证不会再次调用外部工具。

Dify 的许可证是带附加条件的修改版 Apache 2.0，并非可以无条件等同于标准 Apache 2.0。本文仅作阅读比较；源码复用时应针对具体版本重新审查。[许可证][dify-license]

## 5. 腾讯 ADP：从路由委派扩展到可选团队通信

当前 ADP 资料不宜只沿用早期 RAG / Workflow / Multi-Agent 三分法：2026 年文档还包含 Claw 模式，其应用配置和工作空间与另外几种模式不同。[当前模式说明][adp-modes]

2026-08-14 更新的多 Agent 文档把两种机制明确分开：默认主 Agent 分配、子 Agent 返回；可选 Teams 允许主动反馈、成员直接通信和共享进度。开启能力后，也不强制每轮组队。产品动态记载了 6 月子 Agent、7 月团队通信的演化。[协同文档][adp-teams] [产品动态][adp-updates]

**架构解析：**一组既有子 Agent 定义，可以被不同调度策略使用。先有“可调用能力”，再有“允许持续协调”的运行规则，比把 Teams 永久写死为另一套角色配置更容易维护。对本项目，可将既有协作授权与 worker 定义作为基础，另表达此次运行是否需要 peer 消息和共同任务，不必把所有子任务都升级成团队。

闭源文档没有提供消息投递事务、共享任务认领实现或 crash replay 证据。本文不把“团队可直接通信”解释为消息必达、去重已完善或未知副作用可安全重放。它是产品能力证据，不能替代代码和故障测试。

## 6. AWS：Strands、AgentCore 与 Agents Classic 不是同一层

### 6.1 当前产品路线

官方文档说明，原 Amazon Bedrock Agents 自 2026-07-30 起成为 Agents Classic，不再向新客户开放，推荐迁移至 AgentCore。该变化针对 Agent 编排层，不是整个 Bedrock 模型服务停用。[维护模式说明][aws-classic]

新的选型应将 Strands 等框架负责的执行逻辑，与 AgentCore 提供的托管运行、记忆、工具连接和观测分开。AgentCore managed harness 当前官方 FAQ 标注 preview，不能与成熟 SDK 或全部托管能力混写成同一稳定版本。[当前 FAQ][aws-faq]

### 6.2 会话怎样映射到执行环境

AgentCore 文档描述基于会话的计算环境与生命周期；microVM 模式有独立资源和短暂上下文，持久文件需配置 session storage，长期结构化记忆使用另外的持久能力。用户身份与 session ID 的绑定仍由应用维护。[会话生命周期][aws-session]

当前又有 Instances 运行方式，允许在托管 EC2 实例上运行，并支持多 Agent 同实例共享文件系统。因此“AgentCore 所有模式始终每个成员一台 microVM”也已经不准确。[Instances][aws-instances]

**对本项目的启发：**运行身份、对话身份、工作目录和真正的操作系统隔离应独立表达。一个 Task 可以包含多个 Run；多个 Run 可以在同一原目录操作；是否沙箱化取决于实际执行后端。不能把一组会话 ID 或新的工作目录当作沙箱。

## 7. 阿里云与微软：托管平台补的是服务运营能力

阿里云 Model Studio 当前应用说明以 Agent / Workflow 为主要入口；Agent Studio 的观测文档又针对应用内部多节点行为。它们与开源 Eino、Spring AI Alibaba 或 AgentScope 属于不同交付层，不因生态关系就拥有完全相同的运行时。[应用类型][bailian-types] [观测入口][bailian-observe]

本轮 Agent Studio 观测正文抓取失败，只保留官方索引可验证的入口与适用范围提示，不进一步描述内部数据库或图调度器。腾讯 ADP 的具体团队契约比这一入口资料更充分，因此本文深度也不同。

微软方面，[Agent Framework 专篇](07-microsoft-agent-framework.md) 分析开源编排；Azure / Foundry 等托管服务负责另外的环境、身份与部署。不能根据开源 `Workflow` 的 checkpoint 接口，推断某个云套餐已经为任意外部写入提供 exactly-once。

## 8. 企业落地证据怎样转化为本项目参考

LangChain 发布的 Klarna 案例公开说明 LangGraph 用于多 Agent 路由、LangSmith 用于逐步观察与评估。这是供应商署名案例，能证明公开采用关系和架构方向；它披露的效率数字不构成本轮独立复测，也不能推断 2026-09 的完整内部架构。[Klarna 案例][klarna]

Anthropic Research 的生产工程文章展示了 orchestrator-worker 研究系统，强调委派说明、工具选择与结果综合。它比单纯演示更接近真实产品，但研究任务对文件互相修改的要求与 Coding Agent 不同。[生产 Research 系统][anthropic-research]

这些案例共同提供的参考是：分工必须与上下文、工具、评估和运行数据一起设计。若只将一套聊天变成几个角色轮流发言，无法得到可维护的应用；若一开始复制企业云平台全部基础设施，也会偏离本项目个人桌面、原项目目录直接工作的目标。

[spring-react]: https://github.com/alibaba/spring-ai-alibaba/blob/f82da0b50f35744c13968191be2b1cd2452ef550/spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java
[spring-parallel]: https://github.com/alibaba/spring-ai-alibaba/blob/f82da0b50f35744c13968191be2b1cd2452ef550/spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/agent/ParallelAgent.java
[spring-sequential]: https://github.com/alibaba/spring-ai-alibaba/blob/f82da0b50f35744c13968191be2b1cd2452ef550/spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/agent/SequentialAgent.java
[spring-routing]: https://github.com/alibaba/spring-ai-alibaba/blob/f82da0b50f35744c13968191be2b1cd2452ef550/spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/agent/LlmRoutingAgent.java
[spring-compiled]: https://github.com/alibaba/spring-ai-alibaba/blob/f82da0b50f35744c13968191be2b1cd2452ef550/spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java
[spring-docs]: https://java2ai.com/docs/frameworks/agent-framework/advanced/multi-agent/
[spring-ga]: https://java2ai.com/en/blog/spring-ai-alibaba-1.0-ga-release/
[coze-builder]: https://github.com/coze-dev/coze-studio/blob/fefb05ff27be1da939612fbf9faf5db62583b8ae/backend/domain/agent/singleagent/internal/agentflow/agent_flow_builder.go
[coze-node]: https://github.com/coze-dev/coze-studio/blob/fefb05ff27be1da939612fbf9faf5db62583b8ae/backend/domain/workflow/internal/compose/node_runner.go
[dify-entry]: https://github.com/langgenius/dify/blob/a6b41ac6d141ebb28d9b90cbe9d2a487379054ac/api/core/workflow/workflow_entry.py
[dify-agent]: https://github.com/langgenius/dify/blob/a6b41ac6d141ebb28d9b90cbe9d2a487379054ac/api/core/workflow/nodes/agent_v2/agent_node.py
[dify-session]: https://github.com/langgenius/dify/blob/a6b41ac6d141ebb28d9b90cbe9d2a487379054ac/api/core/workflow/nodes/agent_v2/session_store.py
[dify-license]: https://github.com/langgenius/dify/blob/a6b41ac6d141ebb28d9b90cbe9d2a487379054ac/LICENSE
[adp-modes]: https://cloud.tencent.com/document/product/1759/122549
[adp-teams]: https://cloud.tencent.com/document/product/1759/134193
[adp-updates]: https://cloud.tencent.com/document/product/1759/104191
[aws-classic]: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html
[aws-faq]: https://aws.amazon.com/bedrock/agentcore/faqs/
[aws-session]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html
[aws-instances]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html
[bailian-types]: https://www.alibabacloud.com/help/zh/model-studio/application-introduction
[bailian-observe]: https://docs.agent.bailian.aliyun.com/zh/loop/observability/introduction
[klarna]: https://www.blog.langchain.com/customers-klarna/
[anthropic-research]: https://www.anthropic.com/engineering/multi-agent-research-system
