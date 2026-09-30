# 多 Agent 协作框架调研

> 完成本轮整理：2026-09-22。共 16 份 Markdown，覆盖 18 个当日固定源码快照、Claude / DSH 历史团队实现，以及国内外商业产品与托管平台。重点是架构、仓库组织、执行链和落地取舍；只有静态阅读与文档核查，没有运行上游或真实模型。

本专题回答两个不同问题：多个长期会话怎样分工通信；一个完整多 Agent 框架怎样装配成员、分配上下文、调度工具工作、汇合结果并处理接续。Deep Agents 与 Agent Teams 是重点，其他项目用于对照不同实现路线。

每篇先引入所解决的问题，再顺着输入、执行与结果流展开，关键结论链接到固定提交中的实现或官方契约。开源、源码可见、闭源产品和厂商实验分开判断，不把“支持多 Agent”当作所有机制都已实现。

## 从哪里开始读

先看 [架构模型与数据流](01-collaboration-models.md)，建立各类协作的区别；再看 [本项目吸收建议](12-project-implications.md)，确认已有能力与候选增量；具体机制沿下表进入源码专题。核查日期、完整 SHA、获取失败与深度边界在 [证据登记](13-evidence-register.md)。

| 文档 | 重点问题与可获得的参考 |
| --- | --- |
| [01 架构模型、协议与评估](01-collaboration-models.md) | 子任务、handoff、图、Supervisor、Teams、共享工作区；身份、通信、恢复、LangSmith / Langfuse；MCP / A2A / ACP 当前边界 |
| [02 Deep Agents / LangGraph](02-deepagents-langgraph.md) | middleware 装配、isolated / fork、同步与远程异步子任务、checkpoint、文件与记忆状态；重点深读 |
| [03 Agent Teams：Claude Code 与 DSH](03-agent-teams.md) | 历史源码与当前产品变化；成员生命周期、邮箱确认、任务 CAS、写范围与真实恢复；重点深读 |
| [04 DeerFlow 2.0](04-deerflow.md) | 完整 Harness 如何组合上下文、Skill、MCP、sandbox、后台子任务和 durable batch |
| [05 AgentScope 2.0](05-agentscope.md) | Agent / Session / TeamMember 身份、消息总线、成员唤醒、租约与团队收尾 |
| [06 Eino](06-eino.md) | Go typed Agent、AgentTool 控制作用域、HITL、DeepAgent、plan-execute-replan 与历史投影 |
| [07 AutoGen → Microsoft Agent Framework](07-microsoft-agent-framework.md) | 消息 runtime 到类型化工作流；GroupChat / Handoff / Magentic、superstep 与 checkpoint |
| [08 OpenAI Agents SDK / Google ADK](08-openai-google-adk.md) | as_tool 与 handoff、结构化委派、嵌套流、SandboxAgent；ADK task 模式、分支与恢复 |
| [09 CrewAI / Agno](09-crewai-agno.md) | Crew / Flow 分工、manager、上下文依赖；Team 四模式、task loop 与完成语义 |
| [10 MetaGPT / ChatDev 2.0 / CAMEL](10-metagpt-chatdev-camel.md) | SOP 与消息订阅如何演变为图平台、动态展开、Workforce 与共享任务通道 |
| [11 商业 Coding Agent](11-commercial-platforms.md) | Qoder、Cursor、Codex、Devin、TRAE、CodeBuddy、Antigravity；团队、子任务和用户工作台如何区分 |
| [12 本项目的参考与吸收顺序](12-project-implications.md) | 按核心模块对照现有实现，给出具体增量、代价和可验证问题 |
| [13 证据与覆盖边界](13-evidence-register.md) | 完整源码版本、当前变化、访问限制、静态验证边界及后续复查方法 |
| [14 企业应用与托管平台](14-enterprise-platforms.md) | Spring AI Alibaba、Coze、Dify v2、腾讯 ADP、AgentCore、百炼；配置如何成为可执行流程 |
| [15 Strands Harness SDK](15-strands.md) | 新单仓组织、能力 schema、上下文继承、Graph / Swarm、提交 frontier 与恢复 |

## 本轮最值得带回项目的结论

当前工作区已包含会话协作、内部 worker、上下文 / 记忆，以及 M4 Skill、MCP、工作流模板和 Trace。后续重点应是把这些能力组合得更清楚，而不是再建一套重复 Agent 核心。

第一，角色定义、长期成员、局部委派和具体 Run 需要分清。第二，独立上下文、独立目录和 OS sandbox 解决不同问题。第三，消息保存、送入模型、任务完成和业务成果有效不能混成一个状态。第四，恢复聊天历史不等于恢复在途执行；持久化图也不能保证外部副作用不重复。

优先候选是跨运行成果导航、局部简报与来源回读、角色配置快照，再根据真实任务验证可执行工作流或持续团队。保持原目录协作、实际故障停止与现有模型范围；没有建议普通任务必须先建团队、画 DAG、开 worktree 或连接云服务。具体对应代码和取舍见 [12](12-project-implications.md)。

## 时效性与可信度如何判断

本轮补查了 AgentScope 2.0 / Runtime 迁移、ChatDev 2.0 的 9 月论文、Dify Graphon / Agent v2、Strands Harness 单仓、Claude 当前 Teams 变化、腾讯 ADP 团队能力、AWS Agents Classic 转向 AgentCore，以及 MCP 2026-07-28 / SDK v2、A2A 1.0。它们影响了具体架构判断，详细出处见 [13](13-evidence-register.md)。

深度并非所有产品一致：核心开源框架分析到实际调用和状态更新；闭源产品只分析可验证契约和厂商披露；CodeBuddy、百炼部分页面获取受限，明确保留未知项。企业案例和实验结果没有独立复测。本轮也未穷尽市场，不对未读源码的项目作实现断言。

## 与已有调研的关系

此前 [四个 Coding Agent 的多版本源码研究](../agents/README.md) 解释单 Agent 核心及其演化；本轮沿用其部分团队证据，重点扩展到多执行者之间的数据与控制关系。本专题独立维护，避免与其他任务正在编辑的上级索引、规划和 M4 进度发生写冲突。
