# 证据、版本与覆盖边界

> 本轮核查日期：2026-09-22，Asia/Shanghai。正文的“当前”指本轮读取到的固定源码或官方页面；不能解释成永久有效，也不表示已在本机运行验证。

## 1. 本轮怎样调研

先读取本项目规范、进度和实际代码，再按控制权与数据流选择代表框架。对源码可见项目固定提交，顺着入口、装配、上下文、调度、事件、结果和恢复路径阅读；对闭源产品核查官方契约、工程披露和有日期的社区讨论。最后将机制对应到本项目已经存在的模块，而非从零列功能清单。

正文区分四种证据：固定源码能够说明该快照怎样实现；当前官方文档能够说明公开支持什么；厂商案例说明其公开披露的采用关系和场景；论文 / 社区讨论提供实验结果或问题线索。它们不能互相替代。本文档中的架构分析也不等于逐行审计所有仓库。

本轮主要分析一个当前固定快照，必要时解释历史路线；没有对下表每个项目都做两个完整版本的逐行对比。此前用户要求的四个 Coding Agent 多版本独立分析，保存在 [上一专题](../agents/README.md)。本轮复用其中 DSH 和 Claude 的两份历史材料，并与当前官方文档明确分开。

## 2. 当前源码固定表

以下 18 个仓库身份在 2026-09-22 固定。SHA 是当时 HEAD，除正文另有说明，不等同某个正式 tag、包版本或线上服务部署版本。

| 项目 | 完整提交 SHA | 实际阅读重点 | 正文 |
| --- | --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | `49cce0ca852be4cfb567a1cbe0e511ff325a1682` | 状态、增量通道与 checkpoint 边界 | [02](02-deepagents-langgraph.md) |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | `0a6bd899a0760af76bca025ea6af39997b78e611` | graph 装配、同步 / fork / 异步子 Agent | [02](02-deepagents-langgraph.md) |
| [DeerFlow](https://github.com/bytedance/deer-flow) | `5202068a0e3ba7358db11382deedfed1a17ea319` | harness、上下文快照、后台执行器与 durable batch | [04](04-deerflow.md) |
| [AgentScope](https://github.com/agentscope-ai/agentscope) | `226daf0193a9e5b336289051adb4bd01531303eb` | Team、成员会话、Redis / 内存 bus、服务端生命周期 | [05](05-agentscope.md) |
| [Eino](https://github.com/cloudwego/eino) | `b9539ec114a14c32aa568f05eda5cde1e83fcfc1` | Runner、AgentTool、DeepAgent、plan-execute、HITL | [06](06-eino.md) |
| [AutoGen](https://github.com/microsoft/autogen) | `027ecf0a379bcc1d09956d46d12d44a3ad9cee14` | 维护状态、Core / AgentChat 分层与消息 runtime | [07](07-microsoft-agent-framework.md) |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | `98a982a147212424d766ed993e6ecda13abe5faf` | Python 协作 builders、Executor、superstep 与 checkpoint | [07](07-microsoft-agent-framework.md) |
| [OpenAI Agents Python](https://github.com/openai/openai-agents-python) | `ad93f5420edfecb30c6d2bc3a1a22047918cba1a` | as_tool、handoff、stream、Session、SandboxAgent | [08](08-openai-google-adk.md) |
| [Google ADK Python](https://github.com/google/adk-python) | `38339768c6bee499c90d29ac8218916ed1a816ef` | chat / task 模式、并行分支、workflow 与恢复 | [08](08-openai-google-adk.md) |
| [CrewAI](https://github.com/crewAIInc/crewAI) | `0a3b8912b39fb72fac74758069fda523697ffabc` | Crew 调度、上下文依赖、Flow DSL 与运行分层 | [09](09-crewai-agno.md) |
| [Agno](https://github.com/agno-agi/agno) | `cffd892a9024249f15e2cf556398444b221829af` | Team 四种模式、成员上下文、任务完成与状态 | [09](09-crewai-agno.md) |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | `11cdf466d042aece04fc6cfd13b28e1a70341b1f` | Environment、Role、消息订阅和 SOP | [10](10-metagpt-chatdev-camel.md) |
| [ChatDev / DevAll](https://github.com/OpenBMB/ChatDev) | `4fb2db0ea90375ce1059f44fe03ffbd191a7a169` | 2.0 图平台、依赖层、动态展开、黑板 | [10](10-metagpt-chatdev-camel.md) |
| [CAMEL](https://github.com/camel-ai/camel) | `fc27907e31ea2074d6b65ceb121573c5fa1ab345` | Workforce、任务 channel、认领与快照 | [10](10-metagpt-chatdev-camel.md) |
| [Coze Studio](https://github.com/coze-dev/coze-studio) | `fefb05ff27be1da939612fbf9faf5db62583b8ae` | 后端 Agent 图构造和 workflow 节点适配 | [14](14-enterprise-platforms.md) |
| [Dify](https://github.com/langgenius/dify) | `a6b41ac6d141ebb28d9b90cbe9d2a487379054ac` | Graphon 入口、Agent v2、节点会话与 HITL | [14](14-enterprise-platforms.md) |
| [Spring AI Alibaba](https://github.com/alibaba/spring-ai-alibaba) | `f82da0b50f35744c13968191be2b1cd2452ef550` | ReactAgent、三种 FlowAgent、CompiledGraph | [14](14-enterprise-platforms.md) |
| [Strands Harness SDK](https://github.com/strands-agents/harness-sdk) | `1da0d158db1dbbbd559179bb881e85c267511df5` | Python Graph / Swarm、Harness 装配与 subagent | [15](15-strands.md) |

Strands 最初经 `strands-agents/sdk-python` 获取，快照已采用 `harness-sdk` 单仓结构；随后对新地址再次执行只读 `git ls-remote`，得到相同 SHA。缓存目录保留原名，正文源码链接采用当前仓库名。

## 3. 复用的历史源码

| 对象 | 版本 / 日期 | 固定提交 | 如何使用 |
| --- | --- | --- | --- |
| Claude Code 发布包泄露提取镜像 | 2.1.88，2026-03-31 历史材料 | `4e5426b82ab19c81244f165b4f18306944b8a169` | 解释当时 in-process teammate 与 mailbox；不据此宣称当前实现相同 |
| DeepSeek Harness | 0.1.6-alpha.2，2026-09-17 发布基线 | `ddefc45fbc7f8e46dd73185e68295696d1297887` | 复核 experimental agent-team 的 mailbox、task board 与事件设计 |

DSH 源码在上一轮 9 月 21 日研究缓存中，本轮重读相关团队模块；没有将它标为 9 月 22 日最新 main。Claude 镜像不是 Anthropic 官方开源仓库，其可获取性不代表许可复用。本文不复制大段泄露代码，也不把第三方镜像包装成官方发布。

## 4. 时效性核查中影响结论的变化

| 变化 | 依据与日期 | 对分析的影响 |
| --- | --- | --- |
| Claude Teams 生命周期与工具变化 | [当前 Teams](https://code.claude.com/docs/en/agent-teams)，本轮读取到 2.1.178 等版本说明 | 不能继续以旧 TeamCreate / TeamDelete 为当前必需流程 |
| Claude inbox 写失败反馈修正 | [错误文档](https://code.claude.com/docs/en/errors#failed-to-write-to-a-teammates-inbox)，2.1.224 说明 | 历史 mailbox catch 行为与当前工具契约分开 |
| Qoder 团队属于本次 TUI | [当前 Teams](https://docs.qoder.com/cli/agent-teams)，9 月 22 日核查 | 恢复主历史不等于复活团队 |
| AutoGen 维护模式、MAF 1.0 路线 | 固定 AutoGen README 与 [迁移文档](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/) | 不把 AutoGen 0.2 作为当前推荐架构 |
| AgentScope Runtime 迁入 2.0 | [旧 Runtime 官网迁移通知](https://runtime.agentscope.io/) | 避免拼接不兼容的旧部署说明 |
| Eino typed API 与 workflow 建议变化 | 固定 `adk/agent_tool.go`、`adk/workflow.go` | 输入投影与整段历史传递必须分别讨论 |
| ChatDev 2.0 新论文 | [2026-09-01 论文](https://arxiv.org/abs/2609.00714) 与固定代码 | 分析可配置图平台，不能只讲早期软件公司角色链 |
| Strands 仓库扩展为 Harness 单仓 | 同 SHA 的 README / Harness / multiagent 实现 | 区分基础 Agent、Graph、Swarm 和组装后的产品能力 |
| Dify Graphon 与 Agent v2 | 固定源码 | 旧版 Agent 策略节点不足以解释当前主线 |
| 腾讯 ADP Teams | [2026-07 产品动态](https://cloud.tencent.com/document/product/1759/104191)、[2026-08-14 协同文档](https://cloud.tencent.com/document/product/1759/134193) | 默认单向委派与可选持续团队分开 |
| AWS Agents Classic | [维护模式说明](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)，2026-07-30 | 不能把旧托管 Supervisor 当作新项目唯一入口 |
| MCP 2026-07-28 与 TypeScript SDK v2 | [正式发布](https://blog.modelcontextprotocol.io/posts/2026-07-28/)、[SDK](https://ts.sdk.modelcontextprotocol.io/v2/) | 协议日期、SDK 主版本、扩展版本分开 |
| A2A 1.0.0 | [发布规范](https://a2a-protocol.org/v1.0.0/specification/) | 不沿用 0.3 字段和旧规范链接作为当前依据 |
| MAST 的 v3 样本范围 | [2025-10-26 修订](https://arxiv.org/abs/2503.13657v3) | 采用 7 框架、1600+ 轨迹说明，避免引用初版数量 |

上述版本号只证明对应说明或包内标识，未统一核查 PyPI / npm / Docker 包是否已与主线同步。文档中 ADK 的模式限制与源码差异、OpenAI Sandbox Agents 的 beta 等均单独保留，不能用主线能力抹平发布边界。

## 5. 本项目基线如何定位

核查时 Git HEAD 为 `2937d5f07ac98df769d14b46cfe30064eee3fada`，工作区另有 M4 及其他任务修改。因此正文的本地代码链接指向当前工作区，不是这个提交的纯净快照。主要阅读以下模块：

- `bootstrap.py`：模型循环、协作、worker、Skill、MCP 的共同装配。
- `collaboration/{types,service,arrangements}.py`：安排、消息投递、目标 Run 结果、等待、恢复。
- `delegation/{types,service}.py`：内部 worker、上下文、预算与取消。
- `tasks/{types,store}.py`、`workflow/{types,templates}.py`：共同事实、工作图、模板与阶段信息。
- `context/service.py`、`sessions/{service,trace}.py`、`tools/files.py`、`mcp_client/service.py`：上下文、事实、Trace、并发写与工具资源边界。

本轮没有认领或修改这些实现。其他任务可继续推进，因此建议采用前应对照最新工作区复核，不能把此处阅读结果当作冻结接口或新阶段验收。

## 6. 获取限制与已采用的替代方法

GitHub REST 提交元数据出现匿名限流 403，改用官方仓库只读 `git ls-remote HEAD` 固定 SHA，再获取该 SHA 的 codeload 文本源码。未关闭 TLS 验证，未使用私人凭据，未安装或运行下载内容。

源码缓存按后缀、大小和路径筛选，不是完整克隆。Coze 与 Spring 初次下载遇到 Windows 超长路径中止；Coze 的引用后端文件已保存，Spring 后续从同一固定压缩包定向补齐五个核心 Java 文件，记录在 `targeted-files.json`。没有因为目录存在就宣称全仓完整获取。

部分官方页面正文无法通过工具取得：CodeBuddy 指定页面、腾讯云部分正文、百炼 Agent Studio 观测入口、Strands 若干旧文档路径。相应结论仅使用官方搜索索引能够支持的内容；Strands 的架构分析改以固定源码为主。OpenAI 文档工具的一个详情请求失败后，改读官方网页。失败不被解释为产品没有该能力。

这也限制了深度：Deep Agents、Teams、DeerFlow、AgentScope、Eino、MAF、SDK、Strands 有执行路径分析；Spring / Coze / Dify 侧重关键集成路径；Qoder、TRAE、Cursor、Devin、Codex、Antigravity 等以公开契约为主；CodeBuddy 与百炼部分仅能做有限产品对照。不能把最后一类写成同等深度的源码结论。

## 7. 辅助证据保存位置

正式文档位于 `docs/research/multi-agent/`。第三方材料与核查输出保存在 Git 忽略目录 `.artifacts/research/multi-agent-20260922/`：

- `snapshot-manifest.json`：18 个当前快照、获取方式和保留的初始错误。
- 各仓库目录下的 `metadata.json` / `paths.json` / `source/`：按需保存的源码和元数据；并非每个仓库均有相同完整度。
- `alibaba__spring-ai-alibaba/targeted-files.json`：定向补读的五个核心文件。
- `read-ranges.jsonl`：使用辅助阅读器读取的文件与范围；少量 `rg` / `Get-Content` 读取保留于工具记录，不伪称该日志覆盖所有阅读动作。
- `local-baseline.json`：本项目 15 个相关源码文件的身份记录和当时 Git HEAD，用于辨认并发开发期间的阅读基线，不是产品运行要求。
- `document-check-final.json`：交付前对 UTF-8、LF、围栏、引用和本地 / 固定源码目标的结构检查结果。

历史 DSH / Claude 材料仍位于 `.artifacts/research/agent-source-20260921/`，来源登记沿用上一专题。不在 Git 中新增第三方源码或模型日志。

## 8. 没有验证的内容，以及覆盖边界

本轮没有安装上游依赖、运行 Agent、部署数据库 / 云平台、测试 sandbox、进行断电恢复实验或调用真实模型。没有独立验证产品吞吐、延迟、成功率、节省成本、企业案例的经营指标。源码推导的风险明确作为分析，不写成已复现缺陷。

文档检查能够发现缺失目标、错误版本链接和格式问题，不能证明所有语义都正确；正文另按调用链和公开资料人工复核。没有声称全部外部网页均可达，也没有将社区个例当作全体用户的统计结论。

本轮覆盖代表性架构，不声称穷尽市场。PydanticAI、LlamaIndex AgentWorkflow、Mastra、Haystack 及更多专用框架未做同等源码深读；没有给这些项目虚构比较分数。后续若出现类型化业务代理、检索工作流、TypeScript 原生产品等明确需求，可另选与需求直接相关的项目补充。当前选择优先覆盖用户点名的 Deep Agents / Agent Teams，以及本项目最相关的上下文委派、持续团队、图调度和恢复机制。

所有候选改进仍是研究建议。它们不改变本仓库既定模型、故障停止、原目录协作、可选沙箱或最小验证规则。
