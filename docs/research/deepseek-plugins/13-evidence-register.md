# 证据登记：发现入口、固定版本、源码阅读范围与未验证项

> 检索与源码固定日期：2026-09-23。本文用于复核本轮非官方 DSH 二次开发调研。正文中的实现结论来自指定提交的静态阅读；作者报告、版本声明、社区问题和本次实际验证分开记录。

## 1. 从哪里发现，为什么没有把话题页当作插件清单

发现起点是 DeepSeek Harness 官方仓库指向的 [GitHub dsh-plugin 话题](https://github.com/topics/dsh-plugin)。本次查看默认页、后续页及按最近更新排序的结果，再交叉查看三个社区目录。目录负责发现候选；能否原生接入、实际运行哪个入口、解决什么问题，需要进入仓库核对。

分类采用实际装配关系：

| 类别 | 判断依据 | 本轮例子 |
| --- | --- | --- |
| DSH 原生插件 | Cordis entry、inject / 服务注册、宿主事件或 tools 注册 | dsh-context、Agent Teams、dsh-market |
| 适配已有能力 | 将 MCP、记忆服务、外部执行桥接到 DSH | Qwen carrier、OpenViking、Ouroboros DSH bridge |
| 基于 DSH 的产品 | 自己的桌面 / Web / daemon 负责产品流程，嵌入或调用 DSH runtime | 两套 Desktop、Open Design、dsh-web |
| 名称相近的其他生态 | 实际入口是其他 Agent 的插件或独立模型客户端 | Ruflo 的同名子包、Reasonix 的独立应用 |
| 发现与参考 | 目录或官方契约，用于检索和解释，不能算成第三方实现成果 | 三个 awesome 目录、官方宿主 |

话题是可变标签，不是官方接入认证，也不是完整性保证。检索期间页面计数有变化，本轮没有把页面总数、星数、下载量换算成已分析或已落地项目数。企业维护仓库与企业已在生产使用，也属于不同证据。

## 2. 固定了什么版本，具体读了哪里

共成功取得 **28 个仓库的固定快照**：22 个第三方项目的代表实现 / 集成链、2 个边界筛查仓库、3 个目录及 1 个官方基线。对较大项目只深入与 DSH 接入及本轮模块相关的部分，不能称为完整仓库审计。下表的 SHA 链接固定到当日取得的提交，不会跟随 main 移动；正文再链接具体文件。

### 2.1 桌面、上下文与记忆

| 仓库 / 快照 | 版本与实际阅读边界 | 正文 |
| --- | --- | --- |
| [anywhere-labs/dsh-desktop · 763a793df1834c6ae60288371d7b91f848f79784](https://github.com/anywhere-labs/dsh-desktop/tree/763a793df1834c6ae60288371d7b91f848f79784) | 通过旧名 deepseek-harness-desktop 获取，旧 URL 已跳转到现名；stable 包 2.0.14。读 architecture、startup-generation、pnpm、profile / runtime 边界与恢复；Cloud Fabric 仅按设计草案对待 | [Desktop](02-desktop-products.md) |
| [dataelement/dsh-desktop · 969bfb5dc0704f516d8f351ba85e8626650bc13a](https://github.com/dataelement/dsh-desktop/tree/969bfb5dc0704f516d8f351ba85e8626650bc13a) | 根包 0.1.1，内嵌 DSH 0.1.5-rc.2。读 harness-runtime、启动环境、safe-mode-overlay 和 preset 导入 / 切换 | [Desktop](02-desktop-products.md) |
| [bowenliang123/dsh-context · 6064731c9f1c2fd77df40e3b951ed54df6c0f60a](https://github.com/bowenliang123/dsh-context/tree/6064731c9f1c2fd77df40e3b951ed54df6c0f60a) | 包 0.54.4。读 host/index、fold、backfill、compatibility；分析事件投影、shadow 范围、冷历史和 UI 指标 | [上下文](03-context-inspection.md) |
| [csyangwen/dsh-memory-evolve · c337dc1af7b5c8a5578e03150bf5c4d6133f66f9](https://github.com/csyangwen/dsh-memory-evolve/tree/c337dc1af7b5c8a5578e03150bf5c4d6133f66f9) | 包 0.1.0。读实际 lib/index.js、review、skills、store；区分记忆文件、候选审查与额外模型调用 | [记忆维护](04-memory-evolve.md) |
| [volcengine/OpenViking · 563313ebe10a1b33d0ae736ab8b97ca713ff91f9](https://github.com/volcengine/OpenViking/tree/563313ebe10a1b33d0ae736ab8b97ca713ff91f9) | 重点为 examples/dsh-memory-plugin 的 index / runtime 及共享记忆适配代码；读召回、身份、capture / commit 和 pending queue。未审计整个服务端检索 / 存储引擎 | [远程记忆](05-memory-backends.md) |
| [mem9-ai/mem9 · 3a61b2b9fd1dbbfb84df891c632bcd27b4b665ce](https://github.com/mem9-ai/mem9/tree/3a61b2b9fd1dbbfb84df891c632bcd27b4b665ce) | 重点为 dsh-plugin/src/index.ts 和集成说明；读 pre-step recall、完整 turn capture、session Promise 队列、卸载 drain / abort。未对 Mem9 服务质量做独立评测 | [远程记忆](05-memory-backends.md) |

### 2.2 协作、工作流和自进化

| 仓库 / 快照 | 版本与实际阅读边界 | 正文 |
| --- | --- | --- |
| [NanmiCoder/dsh-agent-teams · 87c95c94d7847e4a242cb589916adc519981175f](https://github.com/NanmiCoder/dsh-agent-teams/tree/87c95c94d7847e4a242cb589916adc519981175f) | 包 0.1.20。读 index、members、scheduler、state 及 mailbox / 任务链；重点为 staged member、attempt、DAG、改派、idle / recovery | [Agent Teams](06-agent-teams.md) |
| [icetomoyo/dsh_workflow · 44b83c182aa02d1be8a0803e8446cb495f93cd8f](https://github.com/icetomoyo/dsh_workflow/tree/44b83c182aa02d1be8a0803e8446cb495f93cd8f) | 包 0.1.2，依赖声明仍是早期 DSH 0.0.1-rc.2。读 runtime、engine：QuickJS 执行、effect occurrence、回放和中断边界；README 安装别名未当作已核实的新发布 | [工作流与协调](07-workflow-and-coordinator.md) |
| [Kayungko/dsh-plugin-task-coordinator · 5861812edf762ece99e65171cf14f161f0ff7aa2](https://github.com/Kayungko/dsh-plugin-task-coordinator/tree/5861812edf762ece99e65171cf14f161f0ff7aa2) | 包 0.26.7。读 ops.mjs、架构文档、会话注册 / spawn / send / wait 逻辑；重点为正式可见会话、模型选择和恢复数据 | [工作流与协调](07-workflow-and-coordinator.md) |
| [Q00/ouroboros · 2f4564619fb9bdd0dca8faf3a650e0d8b9b2f81b](https://github.com/Q00/ouroboros/tree/2f4564619fb9bdd0dca8faf3a650e0d8b9b2f81b) | 读 integrations/dsh-plugin、host_dispatch、evolution/loop、convergence、evaluation/pipeline；聚焦宿主分派与多代反馈，不声称完成整个 Ouroboros 引擎审计 | [Ouroboros / Odai](08-ouroboros-and-odai.md) |
| [orziz/odai · 6c6b411ddec23008ba35d87065eeca4baf22209a](https://github.com/orziz/odai/tree/6c6b411ddec23008ba35d87065eeca4baf22209a) | DSH 插件 0.2.36。读 dsh/runtime/src/*.mts 中入口、lifecycle、prompt、session-evidence、semantic-memory、skill-evolution；未将文档中的跨平台能力全部视为 DSH 当前能力 | [Ouroboros / Odai](08-ouroboros-and-odai.md) |
| [yjh051108/dsh-routing-suite · 195273352f23bff7f9023ebe2ec0cdbdf9c98f10](https://github.com/yjh051108/dsh-routing-suite/tree/195273352f23bff7f9023ebe2ec0cdbdf9c98f10) | 根包 0.3.3。沿 agent.cordis.yml → router-bootstrap-v34 → router-core-v34 阅读，另读 injector、graded 状态与工具、作者实验；未复跑实验 | [推理与阶段路由](15-reasoning-router.md) |

### 2.3 多模态、浏览器、工作台与恢复

| 仓库 / 快照 | 版本与实际阅读边界 | 正文 |
| --- | --- | --- |
| [liustack/modlens · 9b67ba437dd12e5bcff8f639d6ddd7baa3498d91](https://github.com/liustack/modlens/tree/9b67ba437dd12e5bcff8f639d6ddd7baa3498d91) | 包 3.26.3。读 dsh/index.js、分析器 / CLI 生命周期、缓存与取消；不把转换后的请求当作原始会话被改写 | [多模态与浏览器](09-multimodal-and-browser.md) |
| [QwenLM/Qwen-MM-Plugins · 488e548b454ccc105094be33b83a60c07a5c3abe](https://github.com/QwenLM/Qwen-MM-Plugins/tree/488e548b454ccc105094be33b83a60c07a5c3abe) | 第三方模型团队上游，相对 DSH 并非官方插件。读 MCP 组织与手动 DSH 接入说明；其历史验证版本不能当作当日宿主兼容测试 | [多模态与浏览器](09-multimodal-and-browser.md) |
| [omdsh-dev/Qwen-MM-Plugins · 12e0346bbe2fa3a8634ed56ab188101fa8226587](https://github.com/omdsh-dev/Qwen-MM-Plugins/tree/12e0346bbe2fa3a8634ed56ab188101fa8226587) | 社区 fork；深入 packages/dsh/src/index.ts / config.ts 和 patch 装配。当前为较薄 MCP carrier，不能沿用旧网页的内置 Skill / 完整多模态运行时描述 | [多模态与浏览器](09-multimodal-and-browser.md) |
| [Lum1104/dsh-browser · 36fd3ad2d22b814d462b158541c843e6df0bb1cd](https://github.com/Lum1104/dsh-browser/tree/36fd3ad2d22b814d462b158541c843e6df0bb1cd) | bridge 包 0.1.4。读 bridge index / server、extension tools / tab-affinity；关注握手、连接代际、session / call / tab 身份和结果回传 | [多模态与浏览器](09-multimodal-and-browser.md) |
| [omdsh-dev/DSH-better-sidebar · 1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e](https://github.com/omdsh-dev/DSH-better-sidebar/tree/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e) | 包 0.19.1。读 Host 路由 / WS、session-path、path-security、PTY 与清理；未全面审阅每个 UI 控件 | [工作台与恢复](10-workbench-and-rewind.md) |
| [omdsh-dev/dsh-genui · 6a30de34200ed559646fff27bc2872d9b40a914c](https://github.com/omdsh-dev/dsh-genui/tree/6a30de34200ed559646fff27bc2872d9b40a914c) | 包 0.11.1-preview.2。读 plugin、fence-render、GenuiBlock、action-context、limits、interaction-store；关注声明式 UI 与会话动作回传 | [工作台与恢复](10-workbench-and-rewind.md) |
| [Anionex/dsh-turn-rewind · 4ddc9c1de01cbb740079223df48350976351ae1b](https://github.com/Anionex/dsh-turn-rewind/tree/4ddc9c1de01cbb740079223df48350976351ae1b) | 包 0.3.8。读 rewind-host、engine 与 README 演化记录；关注检查点、预演计划、rescue、应用与验证，不宣称整个文件系统具备原子回滚 | [工作台与恢复](10-workbench-and-rewind.md) |
| [dsh-market/dsh-market · e2c53bcb5f5e38a360c44304298196dca46fc4aa](https://github.com/dsh-market/dsh-market/tree/e2c53bcb5f5e38a360c44304298196dca46fc4aa) | 包 1.58.0。读 registry、routes、compatibility、install、snapshot、recovery、index；关注来源身份、profile、挂载、配置快照和独立救援进程 | [市场与生态](11-market-and-ecosystem.md) |

### 2.4 产品化案例与边界筛查

| 仓库 / 快照 | 版本与实际阅读边界 | 正文 |
| --- | --- | --- |
| [nexu-io/open-design · b40f25a1c89552725f1fc31f8c2fad172f92acfe](https://github.com/nexu-io/open-design/tree/b40f25a1c89552725f1fc31f8c2fad172f92acfe) | DSH runtime 包 0.1.0。读 daemon 的 dsh-profile/session、runtime definition、packages/dsh-runtime 协议 / 入口；仅深入 DSH 运行桥，不覆盖整套设计编辑器 | [话题页产品](14-topic-products.md) |
| [zhu1090093659/dsh-web · 5106ea71022191b75bd841535be196379839421b](https://github.com/zhu1090093659/dsh-web/tree/5106ea71022191b75bd841535be196379839421b) | task-board 包 0.3.24。读聚合装配与 patch 身份、host-ledger、host-runner、host-service、session-reuse；未审计全部 SSH、远程认证、桌面和附带插件 | [话题页产品](14-topic-products.md) |
| [ruvnet/ruflo · 9c61c86f06b439af2a95085ae9bb0ca839662e41](https://github.com/ruvnet/ruflo/tree/9c61c86f06b439af2a95085ae9bb0ca839662e41) | **边界筛查**：仅核对 plugins/ruflo-deepseek-harness 的 .claude-plugin/plugin.json、脚本和 README；该子包入口属于 Claude 插件及 DeepSeek API 使用，不推论整个 Ruflo 没有其他 DSH 路径 | [话题页产品](14-topic-products.md) |
| [esengine/DeepSeek-Reasonix · 4d4700a39af7fcc695581e08930325246bbf0952](https://github.com/esengine/DeepSeek-Reasonix/tree/4d4700a39af7fcc695581e08930325246bbf0952) | **边界筛查**：仓库树与中文 README 中的 Go engine / sidecar 组织；归为独立 Agent 产品候选，没有对其内部循环做完整源码分析 | [话题页产品](14-topic-products.md) |

### 2.5 发现目录及官方对照

| 仓库 / 固定 SHA | 本轮用途 |
| --- | --- |
| [awesome-dsh-plugin/awesome-dsh-plugin · 7983709b6ebfca1d50d134f2c5c5f660308bd879](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/7983709b6ebfca1d50d134f2c5c5f660308bd879) | 社区条目、分类及来源发现；不以目录中的营销陈述作为实现证明 |
| [awesome-deepseekharness/awesome-deepseek-harness · 726797f11695284967f723e131950f5bdc8633a2](https://github.com/awesome-deepseekharness/awesome-deepseek-harness/tree/726797f11695284967f723e131950f5bdc8633a2) | 第二个发现入口，交叉核对名称与链接 |
| [dshworks/awesome-dsh-plugins · 7ebdc0869ca62a837c34066f57d2f8bd547d9775](https://github.com/dshworks/awesome-dsh-plugins/tree/7ebdc0869ca62a837c34066f57d2f8bd547d9775) | 从 desktop / workflow 等类别补充候选；完整目录不等于本轮全部已读 |
| [deepseek-ai/deepseek-harness · 00102833dfaee1da9f48a3a8eae9d34005a75218](https://github.com/deepseek-ai/deepseek-harness/tree/00102833dfaee1da9f48a3a8eae9d34005a75218) | 根包 0.1.7-alpha.2。只作契约对照：Cordis primer、capability seams、插件管理 / 安装和 ACP inject 丢失复盘；见 [附录](01-plugin-contract.md) |

版本表采用读取到的对应 package / 配置声明，不把 monorepo 任意根包版本当成所有插件版本。主线 SHA 也不等于 npm 已发布该代码。

## 3. 与旧网页、旧文档不一致的地方

这些差异直接影响架构判断，因此正文采用当前固定源码，历史说法保留为演化背景：

| 容易沿用的判断 | 当前可确认事实 | 影响 |
| --- | --- | --- |
| Ouroboros 接入 DSH 后默认再启动一个 DSH runtime | 当前 DSH patch 的 OUROBOROS_AGENT_RUNTIME 默认为 host；DSH backend 是另一种显式配置方向 | 任务由谁执行、结果如何等待和取消都不同 |
| Qwen 社区 DSH 包仍内置完整工具 / Skill 执行层 | 当前 packages/dsh 主要配置和挂载 MCP client；入口没有旧描述中的 Skill 注册逻辑 | 应参考适配边界，不能分析不存在的当前模块 |
| router 的 README 就是当前运行路径 | preset YAML 指向 v34 bootstrap；首轮 persona / phase_begin 与后续 promoted 分支不同于旧分类介绍 | 首轮上下文和工具集合实际改变，需要按入口核对 |
| 名称包含 deepseek-harness 就是 DSH 原生插件 | Ruflo 本轮所查子包是 .claude-plugin 入口，脚本直接用 DeepSeek API | 不能据名称充实“DSH 插件数量” |
| 安装快照恢复意味着所有磁盘状态回滚 | dsh-market 保存的是有限配置文件；依赖安装和外部状态不是同一事务 | 不应夸大失败恢复保证 |
| 底层结果标为 completed 就是目标完成 | Open Design 的桥接可将 max-tokens 映射为 completed，同时保留 stop_reason | 上层仍需保留停止原因，不能据此自动验收 Goal |

社区讨论也需要保留时间边界：[dsh-market issue #639](https://github.com/dsh-market/dsh-market/issues/639) 报告的是较早组合的 profile 问题；本次查看时 issue 仍为 Open，当前源码已有相关 profileContext 处理，不能据静态变化宣布作者场景已实测修复。[Ouroboros issue #2163](https://github.com/Q00/ouroboros/issues/2163) 涉及的历史运行方向，也不能覆盖当前 host 默认值。

## 4. 兼容性和许可记录怎样使用

### 4.1 不混淆四种版本事实

当日官方主线是 0.1.7-alpha.2；这只说明我们用什么契约作对照。插件 peer 范围、作者实际测试版本、打包内嵌版本、某篇旧教程版本，分别说明不同事实：

- Agent Teams 文档推荐 0.1.5-rc.1；task-coordinator 的客户端 peer 为 `>=0.1.5-rc.1 <0.1.6`，不能直接写成已验证当日官方版本。
- dsh_workflow 的早期依赖对迁移评估有价值，但本次没有安装它证明当前兼容或不兼容。
- Qwen 上游手动教程的 DSH 0.1.0-rc.6 验证记录，与社区 fork 的 MCP client 要求不是同一条兼容证据。
- Open Design 的 runtime 策略显式处理若干早期 rc / stable，不据此承诺 0.1.7-alpha.2 已被产品支持。
- dsh-web task-board 的要求已推进到至少 0.1.7-alpha.1；仍需按它的整个聚合装配而非单包版本理解运行环境。

因此本文既不把旧 peer 字符串当成必然不兼容，也不把“源码看起来能用”当成已经验证组合。

### 4.2 许可只记录所见事实

多数代表插件使用宽松许可证，但不能因此默认所有项目都相同。本次读到 OpenViking 根 LICENSE 为 AGPL-3.0，Mem9 根 LICENSE 为 Apache-2.0，dsh-turn-rewind 声明 BSD-3-Clause。dsh-routing-suite 的根 LICENSE / README 与根 package.json、graded package.json 存在不同声明，正文已标出；没有替作者裁定所有文件统一适用哪一项。

当前产物是分析，没有搬用实现代码。以后实际复用时，应重新核对所选提交、具体文件及依赖的许可；仓库名称、介绍页或本表都不能代替文件级来源记录。

## 5. 本地证据在哪里，怎样复核

忽略目录 `.artifacts/research/deepseek-plugins-20260923/` 保存本次辅助材料，正式交付为 docs 下的正文。缓存不要求进入 Git：

| 文件 / 目录 | 含义与限制 |
| --- | --- |
| snapshot-manifest.json | 仓库、完整 SHA、获取时间、筛选保存的文件数、压缩包大小或失败；文件数不等于阅读数 |
| fetch-attempts.jsonl | 获取尝试及错误；失败不会被改写成成功 |
| owner__repo/metadata.json、paths.json、source/ | 固定提交的元数据、选取路径和源码；跳过依赖 / 构建目录、符号链接、过大文件与过长路径，不是完整 git clone |
| read-ranges.jsonl | 主要源码阅读的路径和行段，辅助说明研究依据；搜索 / 单独命令阅读未必全部进入该记录 |
| local-source-snapshot.json | 对照本项目时的选定文件身份；当前工作区会继续变化，不能把本次结论无限期当作当前状态 |
| document-check-final.json | 正文的编码、格式、本地目标和固定源码目标检查结果；不是行为测试或全面事实验证 |

首次筛选没有包含 Odai 的 `.mts` / `.cts`，发现实际入口后已按同一 SHA 补取并阅读；不能据第一次缺失判断仓库没有实现。Anywhere 缓存仍用旧仓库名称，现名跳转不改变固定 SHA 的身份。结构检查对该别名作对应处理。

本项目参考总结依据当前 M4 及 `runtime`、`context`、`memory`、`collaboration`、`delegation`、`skills`、`mcp_client`、`workflow`、`sessions/trace` 等实际文件。已有 Skill / MCP / Trace 不再重复列为待实现；其他任务正在写入的代码与共享 docs 未被本轮覆盖。

## 6. 明确没有取得或没有验证的部分

1. `amplifthq/oh-my-dsh` 的 `git ls-remote` 获取失败，未进入成功快照与实现分析。失败只能说明本次未取得，不能推断仓库不存在、已停止维护或没有参考价值。
2. 没有穷举整个 dsh-plugin 话题。代表选择覆盖了本次关注的核心模块；其他记忆服务、设计工具、浏览器适配和整合发行版仍可按具体需求继续深入。
3. 没有安装插件、运行上游 Agent / 桌面、部署服务、调用真实模型或使用个人账号。有关 sandbox、取消、恢复等结论是代码所表达的机制和边界，未提升为本机故障注入验证结果。
4. 没有独立测量任务成功率、延迟、Token 成本或生产规模。作者实验只说明其报告的方法和观察，不能用作横向排行榜或本项目采用后的收益承诺。
5. 结构检查只核对本地可得的证据与链接目标，没有宣称所有网络 URL 均逐一在线可达，也没有自动证明每段分析语义正确；关键机制仍靠源码交叉阅读。

这一轮已完成选定范围的调研交付。后续最有效的深入方式，是从 [本项目参考总结](12-project-implications.md) 选定一个真实问题，重新固定候选版本并验证其关键路径；不需要先安装整个生态才能使用这些研究结论。
