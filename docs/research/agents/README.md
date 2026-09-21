# 四个 Coding Agent 的源码与架构深度调研

> 核查截止：2026-09-21。Hermes、Claude Code、Pi、DeepSeek Harness 各选两个代表版本，共八篇完整独立分析。每篇版本正文按用户进入项目后的数据流展开，并补充仓库组织、依赖方向、状态所有权和改动传播。本文及专题只做研究，不改变本项目运行代码或开发阶段。

结合本项目当前实现的总结见 [核心模块、演化路径与本项目的吸收建议](core-module-lessons.md)。该文按运行核心、会话、模型、上下文、记忆、工具、Skill、MCP、执行、工作流、协作与恢复组织，区分已有能力、值得加强的部分和后续扩展。

## 1. 文档入口与版本选择

| Agent | 较早的完整实现 | 较新的代表实现 | 为什么选这两版 |
| --- | --- | --- | --- |
| Hermes | [v2026.3.12](hermes-v2026.3.12.md)，包版本 0.2.0 | [2026-09-21 固定主线](hermes-2026-09-21.md)，包版本 0.21.3 | 观察集中式 AIAgent、显式 memory/skill 如何演进到阶段模块、项目登记、会话租约、上下文引擎和后台复盘 |
| Claude Code | [0.2.8](claude-code-v0.2.8.md)，2025-02 发布包映射 | [2.1.88](claude-code-v2.1.88.md)，2026-03 流出的发布包映射 | 两个可以核对包体与 source map 的历史样本；从递归 query / React 会话到流式调度、复杂压缩、技能、记忆和子任务 |
| Pi | [v0.50.0](pi-v0.50.0.md)，2026-01-26 标签 | [2026-09-21 固定主线](pi-2026-09-21.md)，包版本 0.86.1 | 早版已具备 SDK、扩展和树状会话；新版可观察协议演进、缓存、资源信任与新 Harness，同时辨认 CLI 尚未完全迁移的事实 |
| DeepSeek Harness | [v0.1.0-rc.7](deepseek-harness-v0.1.0-rc.7.md)，2026-08-17 | [v0.1.6-alpha.2](deepseek-harness-v0.1.6-alpha.2.md)，2026-09-17 | 两个官方预发布标签，可观察事件 / surface 体系从逐 chunk 日志走向 attempt 结算，以及 Worker 到受管进程 PTC 的变化 |

每篇都重新说明背景、启动、项目与会话、上下文、模型和工具循环、扩展、执行、压缩、持久化与恢复。较新版文档可以独立阅读，旧版不是几段“与新版不同”的补充。这两个版本是研究样本，不是声称覆盖全部发布历史，也没有用相邻补丁版本凑数量。

推荐先读 Pi v0.50.0 建立消息 / 工具 / 会话三层认识，再读 DSH 新版理解事件、投影和执行 provider。Hermes 适合理解跨时间的记忆与技能产品，Claude Code 2.1.88 适合研究复杂 Coding 产品如何协调流式工具、权限和上下文。若希望理解某个产品自身的演进，则直接按表中同一行阅读。

## 2. 时效性与材料可信度怎样界定

版本号、发布日期、仓库提交和读取日期是四件事。Pi 与 Hermes 的新样本是 **2026-09-21 主分支固定提交**，包含对应包版本发布之后的修改；本文没有把它们冒充同名 release tag。DSH 两个样本是正式发布页面上的预发布标签，不称作稳定版。Claude 两个样本是历史分发产物，不能用于证明 2026-09 的闭源产品内部仍完全相同。

| 文档样本 | 仓库与固定提交 | 证据状态 |
| --- | --- | --- |
| Hermes v2026.3.12 | `NousResearch/hermes-agent@a370ab8391ca5f8de7ebbc449f05cb0df36ade7c` | 官方标签源码；日期标签与 Python 包版本分开 |
| Hermes 2026-09-21 | `NousResearch/hermes-agent@5470f260cac7bafc7b98676dfba1c12fcddc3234` | 官方主线快照；本地 HEAD 与文档引用一致 |
| Claude Code 0.2.8 | `lyconear/Claude-Code@da716d77b251868918bb5776377f85a18a47ffdf` | 非官方历史发布包镜像；检查内嵌映射的一致性 |
| Claude Code 2.1.88 | `Shengfu-Zhang/claude-code-public-package-extract@4e5426b82ab19c81244f165b4f18306944b8a169` | 非官方提取镜像；检查保留 npm 原包与源码映射 |
| Pi v0.50.0 | `earendil-works/pi@453e104d3a32c02c5f586d1652636ca8b71d6d05` | 官方历史标签；原 badlogic/pi-mono 地址当前重定向 |
| Pi 2026-09-21 | `earendil-works/pi@8bfef4de880cd529b8d4fc164497a723542780c3` | 官方主线快照；与 v0.86.1 tag 不完全相同 |
| DSH v0.1.0-rc.7 | `deepseek-ai/deepseek-harness@99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` | 官方 release candidate |
| DSH v0.1.6-alpha.2 | `deepseek-ai/deepseek-harness@ddefc45fbc7f8e46dd73185e68295696d1297887` | 官方 alpha 预发布 |

源码与发布页面提供不同证据：发布说明能确认发布意图和版本状态，具体行为以相应提交的入口、默认配置和调用分支为准。正文中的文件引用固定 SHA；若引用的是发布说明，会明确标注，避免滚动 README 更新后改变本文依据。比如 DSH 9 月版的 PTC、Inbox 恢复和插件管理均回查源码，未仅照抄功能列表。[DSH 9 月发布页](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.6-alpha.2)

### Claude Code 的来源核对

0.2.8 镜像的 `cli.mjs` 包头及编译常量显示相同版本；内嵌 source map 有 2,783 条 source，其中 211 个应用 `src/` 文件与 sourcesContent 在统一换行后全部一致。原 cli.mjs 的 SHA-256 为 `c75232619433601d01a7c058b2c2e67bdc5b05a5b8683955fd20560ac2af2b27`。[0.2.8 镜像](https://github.com/lyconear/Claude-Code/tree/da716d77b251868918bb5776377f85a18a47ffdf)

2.1.88 镜像保留 `claude-code-2.1.88.tgz`，其中 package 版本与 source map 一致；4,756 条 source 中，1,902 个应用 `src/` 文件全部存在并在统一换行后匹配。原 tgz 的 SHA-256 为 `d836a86d9150ecc594a7025524c50e24080478904c979f386d447770275ef813`。[2.1.88 镜像与原产物](https://github.com/Shengfu-Zhang/claude-code-public-package-extract/tree/4e5426b82ab19c81244f165b4f18306944b8a169)

这证明提取物和镜像保留包体的**内部一致性**，不等于官方签名验证。纯类型、未打包模块、测试、构建系统、内部服务和线上实验配置可能缺失；`feature(...)` 源文可见也不代表外部构建启用。Claude Code 仍按专有软件材料分析，本文只作原创解释，不将源码直接搬入本项目。其他三个官方仓库按所取快照的 MIT 许可标识，采用代码时仍需保留来源与许可。

## 3. 八篇统一解释了哪些问题

各篇按使用顺序回答：

1. **开始之前**：它面向什么产品，版本与材料能证明什么；仓库的入口、装配和依赖在哪里。
2. **进入项目**：cwd、project/workspace、session、task、agent 各持有何种状态，是否实际创建工作副本。
3. **接纳输入**：普通追问、运行中 steering、队列、取消和维护操作怎样交接。
4. **准备请求**：项目规范、persona、memory、skill、工具目录如何加载，哪些稳定、哪些按需变化。
5. **调用模型**：内部消息怎样投影为协议，思考配置和 provider 原生续接数据怎样处理。
6. **调用工具**：参数、权限、并发、执行后端、MCP、结果裁剪与错误如何进入下一步。
7. **长任务继续**：子 Agent、工作流、Goal 或 stop hook 在哪里决定继续；哪些能力本版没有或默认不启用。
8. **窗口变满**：触发、计量、切点、摘要、保留尾部、提交、失败和历史回读如何协作。
9. **结束与重启**：保存什么、谁保存、怎样恢复，以及会话恢复为什么不等于外部文件 / 进程回滚。

没有某项内建能力时，文档说明缺口和可扩展位置，不用“支持插件”代替已实现的记忆、MCP 或 sandbox。流程中的实现解释包含状态结构、具体函数 / 文件、运行案例、收益和失败条件；链接用于支持这些解释。

## 4. 仓库组织补充的主要结论

用户补充要求后，八篇第 1 节分别增加了源码组织分析。以下只是跨项目定位，完整调用链与改动例子在正文。

| 产品 / 版本 | 组织方式 | 不能忽略的耦合或过渡状态 |
| --- | --- | --- |
| Pi 0.50.0 | ai / agent / coding-agent 主分层；SDK 统一装配，AgentSession 连接内存执行与会话树 | 包依赖与职责图不完全一致；AgentSession 仍引用 theme / export，并是较大的协调中心 |
| Pi 9 月主线 | 保留 CLI 的 AgentSession，同时在 agent 包新增 Harness / lane / operation / session 路径 | 新旧路径共存，不能只修改新 harness 就期待影响当前 CLI；同名 compaction 文件需沿调用者辨认 |
| Hermes 3 月 | 顶层 AIAgent + agent 帮助模块；工具模块自注册到共享 registry | 主运行器集中，模块级导入与环境副作用、进程共享 registry 影响复用 |
| Hermes 9 月 | phase、mixin、provider、context engine、DB 子模块进一步拆分 | AIAgent 仍共享大量状态；forwarding 保持兼容；打包清单必须跟随文件拆分 |
| Claude Code 0.2.8 | React/Ink REPL 持消息，query 异步生成器，工具按功能纵向组织 | 工具同时含执行与 React 展示，日志接入 hook；不宜描述成完全 UI 无关内核 |
| Claude Code 2.1.88 | query 周围拆出工具调度、压缩、记忆、任务等服务；bootstrap 延迟加载 | QueryEngine 此时负责 headless，REPL 尚未统一；ToolUseContext、utils、主入口仍是耦合中心 |
| DSH rc.7 | 能力契约 / provider / consumer 分包，bundle 作装配根 | npm 依赖和 Cordis 服务图不同，scope / waterfall 引入运行时依赖；核心 Tools / Session 仍集中 |
| DSH alpha.2 | 持久 Inbox、流式 attempt、PTC、格式与投影的所有权更清楚；host/client 契约生成 | 多组合、动态插件卸载、原生与发布闭包提高维护成本；实验包不是默认最小系统 |

分析这些组织方式时，不能只问“有几个包”。更有效的问题是：增加一种工具要改哪几处，改压缩会不会影响恢复，更换远端执行后文件与命令是否仍指向同一项目，界面能否脱离模型驱动更新。各篇给出了这样的改动路径，用以检验分层究竟减少了什么修改、保留了什么复杂度。

## 5. 按数据流比较四种设计取向

### 5.1 开始工作：产品身份决定哪些状态必须先建立

Pi 主要围绕 cwd 与可恢复会话树装配资源；Hermes 还要处理个人助手的 profile、渠道、长期记忆和项目任务；Claude Code 围绕编码会话叠加较多产品政策；DSH 从 profile / preset 的宿主服务组合建立 Workspace、Session 与 Agent。差别来自产品形态，不宜用一个“哪个更高级”排名代替。

对本项目的参考是先明确项目、任务、会话、运行的身份关系，再决定是否需要每种额外实体。跨消息渠道、可卸载插件和多宿主部署会显著增加状态，不应只因别的仓库存在这些目录就自动引入。

### 5.2 进入模型：历史、当前上下文和长期记忆是不同数据

Pi 的会话树与当前分支投影分开；DSH 明确区分 event log、surface 和 request messages；Claude Code 有持久轨迹、压缩边界及恢复材料；Hermes 则把会话、memory、skill 和历史搜索组合起来。共同点是实际模型请求不能简单等于全量持久历史。

但长期记忆的产品程度不同。Hermes 直接把个人记忆与技能经验作为持续使用的主能力；Claude 2.1.88 可见自动记忆与整理实现但须保留 gate 条件；本文研究的 Pi / DSH 默认主链没有可直接等同的个人画像自动提炼。给所有产品都填“支持长期记忆”会掩盖最有价值的差异。

### 5.3 开始执行：并发、权限和隔离必须分开说明

Pi 早版工具回合较简单，新版增加调度能力；Claude 与 DSH 都需要对并发安全工具和独占工具排序；Hermes 新版还考虑工具段与实际文件目标。并发带来的成本是取消、结果提交、共享状态和部分成功，不能只看一次能发几个调用。

权限回答是否允许，sandbox 回答进程实际受到什么约束。Pi 的可扩展工具、Claude 的规则、Hermes 的多终端后端、DSH 的 sandbox provider 都需要逐层判断。尤其是 Worker / VM、cwd、Git worktree、会话隔离和 OS 文件 / 网络隔离，不能相互替代。

### 5.4 工作变长：压缩是一个提交过程

四种实现都面临摘要遗漏、工具配对、近期内容与旧历史回读的问题。Pi 强调分支和切点；Claude 的恢复材料比单段摘要丰富；Hermes 结合记忆抢救、减量与上下文引擎；DSH 用日志事件与 surface 替换显式表达提交。摘要是否成功、提交是否成功、是否真的减少下一请求压力，需要分别观察。

旧版本的局限也应保留：Hermes 早版摘要失败有丢弃中段的兜底；Pi 新旧请求与循环语义并非相同；DSH 新版将系统提示放进 surface 后，需要排除首部系统节点并修改计价。不能把“都支持 compact”当成已经完成比较。

### 5.5 一轮之后：持续推进、自改进与正确性没有必然等号

Goal、stop hook、workflow、Ralph、后台 review 分别控制持续运行、回合结束判定、子任务编排、fresh-agent 迭代和经验整理。Hermes 写入 skill 或记忆，不等于模型权重递归提升；DSH 的 Ralph worker 自报完成，也不等于独立验证任务正确。把这些统称 RSI 会失去评估对象。

真正可落地的自改进需要明确改什么、依据哪次经历、怎样验证、失败怎样撤回。本文中可确认的对象主要是工具 / 插件 / skill / memory / 运行策略，而非训练模型本身。四个源码专题补充的是实现证据，广义 RSI 与研究路线仍见上级调研的[自进化专题](../03-self-evolution.md)。

## 6. 如何沿源码继续阅读

下表给每个样本一条最短的机制阅读路径；不是必须从第一行顺读完整仓库。

| 样本 | 建议先读的调用链 | 读完应能回答 |
| --- | --- | --- |
| Hermes 3 月 | `cli.py` → `run_agent.AIAgent` → `model_tools` / registry → memory / compressor → SessionDB | 为什么一次编码工作会分别留下代码、轨迹和长期知识 |
| Hermes 9 月 | AIAgent → TurnFacade / lease → conversation_loop → turn phase → provider projection / executor → persistence / review | 哪个阶段拥有输入、并发资格、发送上下文及回合后整理 |
| Claude 0.2.8 | CLI → REPL → query → services/claude 或 Tool → useLogMessages | 模型每次工具反馈怎样成为下一次请求，UI 与内核在哪里耦合 |
| Claude 2.1.88 | bootstrap / main → REPL 或 QueryEngine → query → StreamingToolExecutor / compact → sessionStorage | 何时调度工具、何时压缩、停止为何可能继续、哪些状态由入口持有 |
| Pi 0.50.0 | main → createAgentSession → AgentSession → Agent / agent-loop → SessionManager | 内存执行状态为什么不同于树状持久历史 |
| Pi 9 月 | 同一实际 CLI 链，另读 agent/harness 的 Context、runtime、session | 新 Harness 与当前 CLI 的边界在哪里，改动会走哪一条路径 |
| DSH rc.7 | CLI / bundle → AgentLoop factory → agent.ts → tool-calls → Session / compaction | 装配、策略与事件事实怎样组成一轮 |
| DSH alpha.2 | bundle → durable Inbox → SystemPromptProjection → AssistantStreamAttempt → Tools/PTC → generation / projection | 实时、持久、请求视图和执行进程如何保持各自所有权 |

## 7. 核查范围、交付边界与复用方式

实际核查包括八个固定快照、入口与默认装配、关键运行 / 工具 / 上下文 / 持久模块、版本间相关文件差异，以及 Claude 两份映射的提取一致性。正文区分已启用、可选、experimental、源码分支可见和仅有设计推导。没有运行第三方 Agent、测试它们的 sandbox、消耗模型额度、验证企业内部部署或测量性能。

源码仅保存在 Git 忽略的 `.artifacts/research/agent-source-20260921/`，版本文档引用公共固定提交，不依赖读者机器拥有这些缓存。检查记录包括 snapshot manifest、Claude provenance 与源码读取范围；这些属于本地核查辅助，不是第三方源码交付。正式产物为八篇版本正文、本索引与按核心模块组织的总结，共十个 Markdown；模块总结另引用本项目实际源码。

文档验证检查 UTF-8 / LF、围栏、引用定义、本地文档目标与固定提交中的源码路径；源码路径存在不等于逐条外网链接都做了可达性检查。对于架构结论，仍以正文指定函数与默认配置为依据。未执行应用回归，因为此次没有修改产品代码。

其他任务正在修改 `docs` 和实现代码。本次写入限定在新建 `docs/research/agents/` 与独立 [研究进度](../../progress/research.md)，不覆盖共享 M3 规划、进度总览或上级研究索引，也没有提交 / 推送。
