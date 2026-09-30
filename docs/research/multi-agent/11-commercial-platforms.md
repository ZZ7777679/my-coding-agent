# 商业 Coding Agent：团队、子任务与多会话产品如何组织

> 核查日：2026-09-22。本文分析公开产品契约与厂商工程披露；未获得闭源服务端源码，未购买套餐或运行产品测试。Claude Code 的历史源码与当前 Teams 单列于 [Agent Teams](03-agent-teams.md)，不能用历史泄露代码证明本文产品的当前内部实现。

## 1. 先明确比较对象

用户同时打开两个聊天窗口，只能证明产品支持并行会话。要形成自主协作，还需要知道谁负责拆解、谁启动执行、成员收到哪些信息、结果如何返回、何时结束。若团队还能跨轮工作，就进一步涉及稳定身份、消息收件箱、共享任务与恢复。

因此，本文沿着一次需求的处理顺序分析三种不同产品单元：用户直接管理的会话、主 Agent 创建的内部子任务、持续存在的团队成员。三者可以同时出现在一个产品里，不能用某个功能名称覆盖整个产品。

| 产品 / 功能 | 公开可见的主要协作单元 | 本轮最有价值的参考 | 证据层次 |
| --- | --- | --- | --- |
| Claude Code Agent Teams | Lead、命名成员、共享任务与消息 | 同一团队内持续协商；当前生命周期和投递限制 | 当前官方文档；历史代码另析 |
| Qoder CLI Agent Teams | 当前 TUI 内的临时团队 | idle 成员再次接单；团队与会话恢复分离 | 官方功能契约 |
| Qoder Quest Experts | Lead 与专家、QA / Review 流程 | 将任务拓扑、成员和成果呈现在画布 | 官方功能契约 |
| Cursor | 子 Agent、独立 Agent 会话、云端工作；另有 swarm 实验 | 上下文分工、可选隔离、规划 / 执行分层 | 产品文档与实验披露分开 |
| Codex | 用户任务与内部子 Agent | 有界委派、结果聚合、子任务可见性 | 官方当前文档 |
| Devin | Coordinator 管理独立 Devin 会话 | 独立执行环境、会话链接与成本 / 生命周期管理 | 官方产品工程文章 |
| TRAE / TraeCode | 多任务面板、主 Agent、Markdown Subagent | 人管理任务与模型委派同时存在 | 当前中国站文档 |
| CodeBuddy | IDE 多任务 Agent 与成果视图 | 多任务工作台的状态、产物入口 | 官方索引可查，正文抓取受限 |
| Google Antigravity | Agent Manager、独立会话、异步 Subagent | 多项目组织与子任务运行视图 | 官方文档；本轮未分析内部实现 |

## 2. Qoder：从一次委派到可重复唤醒的团队

### 2.1 入口与组织：CLI Teams 和 Quest Experts 是不同产品层

CLI Teams 当前是需要开启的 Beta 能力。主会话接收目标后创建命名成员，通过共享 Tasks 记录归属与进度，通过 SendMessage 交换问题和发现。成员有独立上下文；其普通回答不自动等于给某个同伴发送消息。明确要求 Teams，才更能表达“持续共同工作”的意图；仅说并行，产品也可能选择普通子任务。[CLI Teams][qoder-teams]

Quest Experts 则把专家调度做成可视工作流：Lead 组织任务，专家按职责工作，QA 与代码审查参与结果检查。官方配置入口允许定制专家及其 Skill、MCP、模型等能力，画布呈现状态和结果。[Experts 模式][qoder-experts]

**设计解析：**前者提供团队的协作原语，后者进一步提供面向交付的组织方式。把这两者做成可组合层，意味着“做一个审查工作流”可以复用成员执行和消息机制，而无需再实现另一套会话循环。公开文档没有证明两者内部实际共用什么类、数据库或调度器，不能据此画出闭源实现调用栈。

### 2.2 运行：成员身份比单次任务活得更久

Teams 的成员完成一次工作后可进入 idle，再被新任务或消息唤醒；名字用于后续路由。共享任务记录“当前谁在做什么”，成员上下文记录“他已经理解了什么”。若每个小修正都创建全新成员，后者积累的理解就会丢失。

但成员不是跨产品重启的永久工作进程。当前文档明确：团队仅属于本次打开的 TUI，退出时停止成员并清理团队状态；resume 可以恢复主对话历史，不能恢复旧成员的运行 / 空闲状态。[生命周期说明][qoder-teams]

**对本项目的启发：**可以保留同一个 worker 的历史供后续 Run 复用，同时清楚展示它当前是否存在、能否接续。恢复主会话后看到一条历史“已分派”，不能因此把目标标为仍在运行。反过来，本项目已经持久化的用户会话，也不应为了模仿临时 Teams 而被降格为退出即消失。

### 2.3 工具、文件与结果：配置目录不是权限执行器

Qoder 普通 Subagent 文档将描述、模型、工具、权限与运行配置放在可复用定义中；worktree 是可选工作方式。这里应分别理解“模型可发现哪些能力”“宿主允许哪些操作”“代码实际写到哪里”。它们不能只靠一段角色提示统一表达。[Subagent][qoder-subagent]

成果画布的价值也不只是展示更多卡片。它让用户能定位某项结论来自哪位专家、对应哪个任务，以及后续纠正应该发给谁。适合本项目吸收的是任务—会话—Run—成果的可追踪关联。官方宣称的效率提升来自其自身测试，本轮不把它当作独立验证的普遍收益。

## 3. Cursor：当前产品与大规模 swarm 实验分开看

### 3.1 产品入口：子 Agent 是上下文拆分单元

当前 Subagents 文档描述独立上下文、前台 / 后台执行，以及探索、终端、浏览器等专业任务。普通子任务可以在父级工作环境中执行；当任务需要文件隔离时，可使用独立 worktree 或云端环境，结果再汇回父级。必须阅读具体隔离模式，不能把“独立上下文”自动理解为“每个子 Agent 都有虚拟机”。[Subagents][cursor-subagents]

用户直接管理多个 Agent 与一个 Agent 委派子任务也不同。前者由用户分别给目标、观察产物；后者由父级管理任务边界和结果汇合。Cursor 的多 Agent 工作台与依赖感知的并行构建提供了这两层交互入口。[多 Agent 功能][cursor-multi]

**架构解析：**工作台需要把多个相互独立的运行聚合为界面；内部编排需要处理父子取消、结果接续和预算。若只实现前者，用户仍然是实际调度器。若只实现后者，用户可能看不到谁改了哪个文件。个人桌面 Coding Agent 最适合让这两层共用事件与成果模型，同时保留各自生命周期。

### 3.2 演化：从大量并行，走向明确的决策归属

2026 年 1 月的工程披露讨论了平面协作、锁争用，以及 planner / worker / judge 分工；它属于实验过程，不能直接作为所有 Cursor 产品调用的实现说明。[早期实验][cursor-scaling]

7 月的新实验改进了规划树、冲突处理和共享决策文档。作者将收益的重要来源归于上下文效率：规划者保留目标，执行者专注局部。SQLite 实验控制了任务、模型和时间预算，但仍是厂商实验，不能外推到任意已有仓库。[新版 swarm 实验][cursor-economics]

**我们的推论：**最值得借鉴的不是增加角色数量，而是使一个架构决策只有明确的负责者。例如“导出接口采用流式还是分页”由上层统一决定；前端和后端 worker 可以各自实现，却不能各自重新决定协议。文本合并工具解决不了两个成员对需求的不同理解。

同样，代码冲突应当区分两类：两个编辑替换了相同文本，是写入冲突；两份能够合并的代码遵循了不同契约，是设计冲突。本项目已有唯一原文匹配能处理前一类反馈，后一类更需要共享决策与定向消息，而不是新增更多文件锁。

### 3.3 结果判断：提交量、运行人数和最终质量没有简单对应

大量 Agent 可以产生很多提交，却把时间花在重复实现、相互覆盖和修复接口分歧上。对于本项目的后续试验，必须记录可接受成果、返工和协调时间；“同时运行五个 Agent”本身不是通过指标。

当前官方论坛中的长运行协作讨论可作为需求和失败线索，例如用户对主 Agent 等待、多个 PR 汇合的困惑。讨论发生在具体日期和版本，不能写成今天产品必然存在的缺陷。[2026-05 社区讨论][cursor-discussion]

## 4. Codex：把主目标、委派范围与子任务结果分开

### 4.1 公开流程

当前官方文档将 Subagent 描述为主任务派生的专门工作单元：并行处理适合独立开展的工作，再由主任务收集结果；客户端允许查看子任务活动。文档也明确额外 Agent 会增加 token 消耗，并建议优先把上下文密集的读取、分析和日志处理交给子任务。[官方 Subagents][codex]

本轮读取到的当前本地客户端契约要求用户或适用项目 / Skill 指令提出委派；不能沿用旧版“任何复杂任务都自动派生”的描述。这只是本轮版本和入口事实，不能与云端产品不同配置混为一谈。

### 4.2 机制价值与边界

主任务持有目标和最终责任，子任务拥有局部输入、自己的执行轨迹和输出。把整个分析过程留在子任务，父级只引入结论及必要依据，可以避免日志挤占父级上下文。但摘要必须支持回查：如果父级无法追溯具体文件、事件或产物，较短上下文也可能只是隐藏了错误。

这一设计很适合本项目既有的内部 worker：不需要先变成用户侧的完整新会话，仍能承担可复用的小任务。用户直接创建的长期任务则应继续保留独立管理、归档与历史入口。

这里的事实来自官方契约，不是对 Codex 桌面闭源控制平面的源码审计。OpenAI Agents SDK 的 `as_tool`、handoff 和 session 已在 [SDK 专题](08-openai-google-adk.md) 分析；SDK 与 Codex 产品之间不能直接画等号。

## 5. Devin：Coordinator 管理的是完整远程工作环境

### 5.1 输入如何分派

2026-03-19 的官方说明中，一个 Devin 可以创建、安排、观察多个其他 Devin。每个子会话拥有自己的执行环境，包括终端、浏览器和开发环境；Coordinator 按任务范围分配，并汇总或集成结果。用户可以打开具体会话查看过程和纠正方向。[Devin 管理 Devin][devin-manage]

### 5.2 生命周期如何进入产品

这是完整远程工程会话的调度，成本与资源也必须独立管理：后台成员是否仍工作、何时休眠或终止、某个会话消耗多少，都会影响总任务。单纯“调用子模型函数”无法完整描述这种产品。

**设计解析：**将一次大型迁移分为若干包级任务，会使执行环境和失败范围更清晰；汇合端却承担分支整合、依赖一致性与最终检查。云端隔离减小文件直接覆盖，不会消除成员对共享接口理解不同的问题。本文没有足够公开证据说明其消息持久化协议、跨数据库事务或失败重放语义。

### 5.3 落地证据如何使用

官方自用文章说明 Devin 被用于 Cognition 自身研发，但自用叙述不能证明所有列举工作都采用同一种多 Agent 调度，也不能作为本项目的收益承诺。[Cognition 自用案例][devin-self]

新 CLI 的本地 / 云端接续、后台子任务与 Fusion 模型组合是另一组能力。[Devin CLI][devin-cli] 应分别比较：混合模型改变一次工作由什么模型执行；多 Agent 改变任务、上下文和控制权分给哪些执行者。两者可以组合，却不是同义词。本项目现有模型范围已经明确，本调研不建议据此擅自扩展 provider。

## 6. TRAE / TraeCode：多任务面板与 Subagent 是两条路径

### 6.1 用户先组织会话

当前中国站“多任务并行”描述同一项目内多个独立任务，用户在任务面板切换状态和对话。这解决的是一个人同时管理前后端开发或辅助询问的问题，并不单凭这个面板就构成 Agent 自主相互通信。[多任务并行][trae-tasks]

主 Agent 的公开工作流则是需求分析、方案、代码与成果预览，并可调用工具、MCP 和子 Agent。当前页面名称已经使用内置“Agent”，不能不加日期地把早期 SOLO Coder 术语套到所有版本。[内置 Agent][trae-agent]

### 6.2 模型再选择专业执行者

Subagent 由 Markdown 定义，项目级配置可以覆盖同名用户级配置；主 Agent 根据描述匹配专门任务，子 Agent 使用独立上下文并返回结果。当前文档还注明调用主体限制。这是声明式能力目录和上下文委派的组合。[Subagent][trae-subagent]

**实现层面的可借鉴点：**Agent 定义需要稳定的来源优先级；否则用户看到“同名 reviewer”，却不知道本次运行采用哪个版本。描述应负责可发现性，工具配置负责能力，运行实例负责历史，三种信息应分开保存。启动后继续修改定义，也不应悄悄改变已经运行的成员。

对于本项目，M4 已有 Skill 导入、引用和版本归档，可复用其来源与快照思路；无需把每个 Skill 都创建为一个常驻 Agent。只有需要独立上下文、调度或历史时，再建立执行者。

## 7. CodeBuddy 与 Antigravity：工作台形态的补充样本

CodeBuddy 官方 2026-09-07 更新的 IDE 文档索引描述 Agents 的多任务与成果管理。本轮正文获取超时，因此只确认该公开功能入口，不推测其 peer-to-peer 消息、任务 CAS 或重启恢复实现。[官方文档][codebuddy]

它仍提供一个值得比较的产品问题：用户关心的是哪些任务在运行、是否需要输入、改了哪些文件、成果能否查看。底层采用哪种编排库应当服务这些问题，不必直接暴露为产品术语。

Antigravity 的官方资料区分项目 / 多文件夹配置、Agent 会话和异步 Subagent。Agent Manager 展示运行层级；项目可选择本地共享目录，独立会话与内部子任务不是同一身份。[项目组织][agy-projects] [异步 Subagent][agy-subagents]

**我们的推论：**适合吸收的是统一查看、定位和控制入口。父级等待成员时，用户应看见它在等谁、成员是否需要输入，而不是所有任务都显示相同的旋转图标。本轮没有对 Antigravity 内部调度器、云隔离或状态数据库做源码核查。

## 8. 对多会话产品的共同启发

沿一次工作流看，商业产品正在补齐四个层次：入口明确区分用户任务与内部委派；执行期显示局部上下文、成员身份和工作归属；协作期提供定向消息和真实等待；交付期把成果、变更及实际检查关联到产生它们的运行。

其中最容易被忽视的是“恢复什么”。Qoder Teams 的退出 / resume 边界有明确限制；其他产品若只声明保存聊天历史，本文不据此推断能重建在途进程。应分别核实历史可读、成员可继续、任务可恢复、未知副作用不重放四项能力。

对本项目最直接的价值是补全既有机制的可见性和组合方式：把现有邮箱、内部 worker、Goal、任务阶段和 Trace 连接成可解释的数据流。是否进一步增加共享任务认领、自动调度或远程运行，分别依据真实场景决定，详见 [本项目吸收建议](12-project-implications.md)。

[qoder-teams]: https://docs.qoder.com/cli/agent-teams
[qoder-experts]: https://docs.qoder.com/user-guide/quest/experts-mode
[qoder-subagent]: https://docs.qoder.com/cli/subagent
[cursor-subagents]: https://prod.cursor.com/docs/subagents
[cursor-multi]: https://prod.cursor.com/help/ai-features/multi-agent
[cursor-scaling]: https://cursor.com/blog/scaling-agents
[cursor-economics]: https://prod.cursor.com/blog/agent-swarm-model-economics
[cursor-discussion]: https://forum.cursor.com/t/workflow-long-running-multi-agent-orchestration-root-agent-parallel-sub-agents-separate-prs/160563/7
[codex]: https://learn.chatgpt.com/docs/agent-configuration/subagents
[devin-manage]: https://cognition.com/blog/devin-can-now-manage-devins
[devin-self]: https://cognition.com/blog/how-cognition-uses-devin-to-build-devin
[devin-cli]: https://devin.ai/cli
[trae-tasks]: https://docs.trae.cn/ide_task-management
[trae-agent]: https://docs.trae.cn/ide_built-in-agent
[trae-subagent]: https://docs.trae.cn/ide_subagents
[codebuddy]: https://cloud.tencent.com/document/product/1831/137517
[agy-projects]: https://www.antigravity.google/docs/projects?tab=cli
[agy-subagents]: https://antigravity.google/docs/subagents?tab=cli
