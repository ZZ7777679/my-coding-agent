# Strands：图协作、Swarm 交接与可装配 Harness

> 核查日：2026-09-22。固定 SHA：`1da0d158db1dbbbd559179bb881e85c267511df5`，通过原 `strands-agents/sdk-python` 地址获取；快照 README 已使用 `strands-agents/harness-sdk` 单仓组织。本文按固定源码分析，不把主线当作某个已发布 PyPI 版本。

## 1. 它已经不只是一个轻量 Agent 循环

Strands 最基本的对象仍是执行模型—工具往返的 Agent；但当前仓库把 Python / TypeScript SDK、完整 Harness、CLI 和文档放到不同目录。`create_harness()` 把工具、上下文、session、记忆和插件组装起来，返回的仍是普通 `strands.Agent`。这与 Deep Agents 的路线相似：保留可组合内核，在上层提供完整默认能力。[仓库入口][readme] [Harness 装配][harness]

多 Agent 则有两种很不同的执行器：Graph 让程序表达依赖，Swarm 让当前成员决定交给谁。Harness 内置的 subagent 又是第三种：父 Agent 调用一个局部工作单元。名称都带“多 Agent”，控制权却分别在图、成员交接与父级工具循环中。

## 2. 仓库组织与修改传播

| 目录 / 文件 | 负责的状态与行为 | 修改什么需求时看这里 |
| --- | --- | --- |
| `strands-py/src/strands/agent/` | 单 Agent 状态与模型工具循环 | 一个 Agent 怎样接收事件、取消和执行工具 |
| `strands-py/src/strands/multiagent/graph.py` | 图节点、边、就绪集合、并行批次与恢复位置 | 确定流程和并行依赖 |
| `strands-py/src/strands/multiagent/swarm.py` | 当前成员、handoff、共享上下文和在途回合 | 动态交接、循环终止和恢复 |
| `harness-py/src/strands_harness/agent.py` | 默认能力装配、资源策略和配置优先级 | 默认 Skill / 记忆 / 工具 / MCP 怎样连接 |
| `harness-py/src/strands_harness/tools/subagent.py` | 委派 schema、子能力配置、历史投影和中断转发 | 子 Agent 能看到什么、能做什么 |
| `strands-cli/`、`site/`、`team/` | 产品入口、文档、设计提案 | 区分实现、说明与尚未落地设计 |

这张图表达依赖责任，不能把 `team/designs` 中存在的方案当作已经启用的代码。本文核心调用链以实现文件为准；TypeScript 分支未做对等审计，不能假定所有 API 和恢复细节完全相同。

## 3. 启动：Harness 配置与本次会话实例分开

`create_harness()` 可以接收模型、工具、MCP servers、plugins、background tasks、context manager、session、skills、memory 等。部分能力可以关闭，已有对象可以显式替代默认装配。

当前 Python 源码定义的默认 session 使用文件快照，新建时生成独立 ID；下一次若不传回该 ID，不会自动知道要接续旧会话。默认长期记忆则有另一套文件存储与生命周期；异步提取在退出时需要相应 flush 边界。这清楚区分了聊天可恢复与长期知识保留。[Harness 参数与实现][harness]

Skill 通过 `AgentSkills` 插件按需提供；上下文管理可以将过大的工具结果移到文件，留下预览和引用。MCP 是能力接入，sandbox 是工具实际执行的位置，session 是对话保存，三者不应在配置里混成“一个工作目录”。

**对本项目的取舍：**可借鉴显式装配和优先级，不能照搬其默认 `./.agent/` 路径。本项目自己的业务数据已经确定保存到数据根，打开用户项目不自动在项目里创建 Agent 运行数据。上游长期记忆自动提取的默认策略也不替代本项目既有记忆与预算规则。

## 4. 子任务入口：将可选自由度直接编进工具 schema

`subagent.py` 为 instructions、tools、MCP、model、context 等轴提供四种约束方式：`Fixed` 固定值，`Inherit` 继承，`Open` 允许填写，`Choice` 从已知集合选择。它们决定哪些参数会进入模型可见的 schema。`Preset` 则把常用配置组合成命名角色。[Subagent 实现][subagent]

这比“请不要使用未授权工具”更明确。例如应用只允许读取和检索，则无需向模型暴露可任意填写工具名称的字符串；可以直接提供有限选择。调用时仍需检查选择结果，源码对工具能力执行相应约束。

该机制的价值并非增加审批，而是避免模型每次重复填写宿主已经确定的配置。对于本项目，既定模型范围、项目执行方式和工具授权可由宿主继承；局部目标和必要上下文由模型填写。可选项也不应变成所有任务必须提交的冗长表格。

## 5. 上下文如何进入子 Agent

当前实现提供 `none`、`all`、`no_tools` 等历史传递方式。`all` 不是原样复制所有内部对象：它删除未完成的工具调用，保留有效的调用 / 结果配对，并移除不应跨模型传递的原生 reasoning content；限制最近消息数时，还需回退到合法消息边界。

`no_tools` 将选择的父级信息渲染为上下文块；局部任务仍是新的指令。子 Agent 使用自己的上下文管理器适配自己的模型窗口。父 Agent 的压缩策略或容量，不能自动替代子 Agent 的请求约束。[历史投影函数][subagent]

这是非常具体的工程参考：继承上下文时，至少需要区分用户 / 助手可见内容、工具调用配对、provider 原生续接状态和宿主元数据。简单截取最后 N 条 JSON 既可能截断工具配对，也可能把另一个模型无法理解的状态传过去。

本项目现有上下文继承已经有来源与任务快照，不应退回全量复制。若要增加多种继承方式，可先提供局部简报与精确回查；只有确实需要继承完整已投影历史时，才增加兼容投影。

## 6. 子任务运行、取消与返回

每次普通委派构造新的 child。中间事件转成 `ToolStreamEvent`，最终结果转成工具结果。父级取消信号传给 child；child 没有结果或被取消时返回错误状态，不把取消伪装成成功。

人工中断时，工具按 `tool_use_id` 在 `_pending` 字典保存 child，向父级传播 interrupt，便于对应调用接续。这解释了为什么多个并行子任务需要调用级身份，而不能只靠“reviewer”这个角色名称恢复。[子任务流与中断][subagent]

但 `_pending` 是此工具对象中的内存字典；仅阅读这条路径，不能证明进程崩溃后它会自动重建。Harness 默认存在会话快照，也不能因此推导出任意在途 child 对象都持久化。下节 Graph / Swarm 的序列化是另外的机制。

内置 subagent 默认接入 Background Tasks；后台调用并不等于父级可以丢弃结果，当前调用仍等待完成并继续处理。UI 非阻塞、模型可继续工作、父子生命周期脱离是三个不同命题。

## 7. Graph：从依赖图计算可执行批次

`GraphBuilder` 保存节点、边、条件、入口和 session manager。每个节点持有自己的 executor；源码拒绝同一 executor 实例重复充当多个节点，避免并发执行时内部对话状态相互覆盖。[Graph 实现][graph]

执行时，Graph 先获取入口或恢复的待执行节点，组成当前 batch；通过 `asyncio.create_task` 同时运行节点，并由事件队列汇总流式输出。当前批次结束后，再计算下一批已满足条件的节点。某节点异常会取消其他仍在运行的协程；这属于协程生命周期处理，不能单凭它保证任意外部进程已经终止。

边的条件可以读取图状态和 `invocation_state`。后者适合传运行期配置；调用方仍应保证不能让并行成员随意覆盖彼此的执行上下文。

图返回节点结果、顺序和累计使用量。并行让多个局部工作同时推进，但后继仍需知道收集的是哪些前驱结果，以及哪个执行失败。本项目若后续将工作流模板变为执行器，这比“看到两个角色就同时开跑”更可控。

## 8. Swarm：动态交接并不意味着所有成员同时说话

Swarm 保存 `current_node`、handoff 目标与消息、节点历史、SharedContext 和完成状态。主循环执行当前成员，再根据该回合产生的交接改变下一执行者。它主要表达动态控制权转移，不能仅因名称叫 swarm 就描述成全体 Agent 并行。[Swarm 实现][swarm]

SharedContext 为可序列化信息提供共享通道；它不等于把每个成员的完整历史持续广播。运行限制包括交接次数、迭代、时间，以及可配置的重复交接检测。当前默认的重复交接窗口为零，不应把可选检测写成默认已启用。

这一模式适合问题性质在途中变化的流程：分析者发现需要执行工具，交给执行者；执行者发现需求缺失，再返回负责澄清的成员。它不适合只需要两个独立检索结果的简单 fan-out，因为反复选择下一位成员会增加协调成本。

## 9. 最值得借鉴的恢复细节：待交接与已完成交接不同

Swarm 的 `_InflightTurn` 记录开始本回合时继承的 handoff、共享上下文，以及 `open / committed / rolled_back`。源码注释指出一个真实歧义：checkpoint 可能发生在执行循环应用交接之前；此时看到一个 handoff 字段，并不能知道它是上回合留下的，还是当前回合已经完成的新决定。

`serialize_state()` 因此根据回合是否已提交，选择恢复 frontier，并避免重复保存已经由 frontier 表达的交接。否则恢复可能跳过尚未执行的成员，或再次执行已经完成的转移。这是状态机设计，不是多写一个 JSON 文件就能解决。[在途回合与序列化][swarm]

Graph 的序列化也显式保存下一待执行集合、已完成 / 失败 / 中断节点、结果和预算累计。恢复时若没有 frontier，会按重新执行的语义重置；有 frontier 才进入继续执行路径。这是上游公开实现的行为，应用需要决定何时允许调用该路径。

另一个易误读处：Graph 可装配 session manager，但节点若是已经带独立 session manager 的 Agent，当前验证会拒绝。不能把报错概括成“Strands Graph 完全不支持持久化”，它限制的是内外层持久化组合。[Graph 验证和恢复][graph]

## 10. 对本项目的参考次序

首先吸收身份与继承设计：角色定义、worker 实例、Run、工具调用各有用途，宿主确定的配置无需让模型重复声明。其次吸收取消和结果路由：中断要回到对应调用，取消不能返回成功。再次关注恢复 frontier 与提交边界，避免把历史消息中的“已发送”当成在途执行事实。

是否采用 Graph 或 Swarm 应由任务决定：确定依赖适合图，动态交接适合 Swarm，有界委派适合 subagent。三者可以共用单 Agent 运行核心，无需把本项目已经可用的会话与 Goal 全部换掉。云托管、远程执行和 sandbox 另见 [企业平台](14-enterprise-platforms.md)，它们不是选择协作模式后的自动前置条件。

[readme]: https://github.com/strands-agents/harness-sdk/blob/1da0d158db1dbbbd559179bb881e85c267511df5/README.md
[harness]: https://github.com/strands-agents/harness-sdk/blob/1da0d158db1dbbbd559179bb881e85c267511df5/harness-py/src/strands_harness/agent.py
[subagent]: https://github.com/strands-agents/harness-sdk/blob/1da0d158db1dbbbd559179bb881e85c267511df5/harness-py/src/strands_harness/tools/subagent.py
[graph]: https://github.com/strands-agents/harness-sdk/blob/1da0d158db1dbbbd559179bb881e85c267511df5/strands-py/src/strands/multiagent/graph.py
[swarm]: https://github.com/strands-agents/harness-sdk/blob/1da0d158db1dbbbd559179bb881e85c267511df5/strands-py/src/strands/multiagent/swarm.py
