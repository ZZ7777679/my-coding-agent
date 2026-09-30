# 证据登记：版本、源码范围、使用材料与未验证事项

> 调研日期：2026-09-23。本文使结论可以回到具体来源；固定源码、作者材料、用户报告和本轮实际验证分别登记。主文分析 21 个产品 / 插件对象，涉及 22 个源码仓库，其中包括局部比较对象与 EverOS 的独立适配仓库；不表示 22 个仓库均已完整审计。

## 1. 时间口径与发现材料

| 材料 | 读取口径 | 可以证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| `topic:dsh-plugin` Star 前 100 | 2026-09-23 06:19:44 UTC / 北京时间 14:19:44，GitHub search API | 当次结果的排名、Star / Fork、push 和元数据 | 全生态穷举、实际安装量、DSH 部分单独热度 |
| 最近更新话题页 | 当日公开页面，第二页遇到限流 | 新样本发现，例如 MCP manager / Claude compat / billion-context | 刚更新就更稳定；没有出现的项目不存在 |
| 社区插件目录 | 固定提交下的目录内容，部分 Star 为 9 月 22 日快照 | 找到包、项目和实际接入路径 | 目录条目全部可用；目录作者已完成我们需要的审计 |
| 原代表仓库复核 | 06:13 UTC 对 22 个原样本读取远端 HEAD，随后比较 5 个变化项 | 这些样本在读取时是否变化、哪些文件变化 | 整个新候选池都经过同样复核 |
| 新主线源码 | 06:51—06:59 UTC 固定 Git HEAD 与源码；dsh-context 07:23 UTC 再取成功 | 正文引用对应的确切代码 | 同 SHA 的第三方运行效果、未来更新 |

发现入口：[GitHub 热度查询](https://github.com/search?q=topic%3Adsh-plugin&type=repositories&s=stars&o=desc)、[近期更新](https://github.com/topics/dsh-plugin?o=desc&s=updated)、[社区目录](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)。本轮逐项处置见 [候选表](10-candidates.md)。

GitHub 搜索返回的 15,879 是带话题仓库的计数。教程、目录、图片素材、其他 Agent 和泛产品也会出现，因此不能写成已经确认的可安装插件总量。`pushed_at` 也可能反映测试、文档或其他分支变化，不等同于发布日或 DSH adapter 的更新时间。

## 2. 正文源码身份与实际阅读边界

下表提交链接均固定到 40 位 SHA。版本来自该提交的 package / pyproject / Skill 元数据，不自动等于注册表最新稳定发布。许可栏记录已读声明及其范围，不代替实际复用时按文件核查第三方内容。

| 对象 / 源码仓库 | 固定提交 | 版本 / 许可口径 | 本轮精读与限制 |
| --- | --- | --- | --- |
| Anywhere `anywhere-labs/dsh-desktop` | [827bd251ef4b](https://github.com/anywhere-labs/dsh-desktop/tree/827bd251ef4b74a3738fc083878a8b921ea7852e) | stable `dsh-plugin-desktop` 2.0.14；MIT | stable main、启动 generation、Host 子进程、profile checkpoint；未将 beta / next 行为算入 stable |
| OpenDesign `nexu-io/open-design` | [b40f25a1c895](https://github.com/nexu-io/open-design/tree/b40f25a1c89552725f1fc31f8c2fad172f92acfe) | 根 0.23.1；dsh-runtime 0.1.0；Apache-2.0 | daemon DSH bridge、协议及 companion 执行 / 取消 / flush；未审计全部设计渲染功能 |
| iPolloWork `Devin-AXIS/iPolloWork` | [2b560bd9bfcc](https://github.com/Devin-AXIS/iPolloWork/tree/2b560bd9bfcc6b1d4211978e58b3b5734fb3bbcf) | 以 SHA 定位；LICENSE 为 Source Available License 1.0 | 仓库树、DSH runtime、read model、前端 engine、插件版本投影等选定文件；非完整归档，LICENSE 于重连后补取成功 |
| LoopX `loopx-project/loopx` | [e57b49e7b6b4](https://github.com/loopx-project/loopx/tree/e57b49e7b6b485c7f3c364e22b3abe078e693b9b) | dsh-loopx-plugin 0.1.1-beta.5；Apache-2.0 | DSH activation / driver / Host / client 与 Python binding；未审计完整外部控制层 |
| Nanmi Agent Teams | [87c95c94d784](https://github.com/NanmiCoder/dsh-agent-teams/tree/87c95c94d7847e4a242cb589916adc519981175f) | 0.1.20；MIT | team / scheduler、attempt、mailbox、持久恢复与报告条件；未实测并发团队 |
| wowyuarm Agent Team | [ef47ef7a7279](https://github.com/wowyuarm/dsh-agent-team/tree/ef47ef7a72794e6c053012f03043343f20bf18b3) | 0.1.14；MIT | Member / Session 分离、ledger、member context 和 recovery；不能声称兼容最新 0.1.7 线 |
| EverOS `EverMind-AI/EverOS` | [5076683ab88d](https://github.com/EverMind-AI/EverOS/tree/5076683ab88d714390573d8f88ff3c470e51129a) | Python 1.3.1；Apache-2.0 | Markdown / SQLite / 索引协调、记忆提取 / 反思调度；everalgo 独立算法依赖未完整审计 |
| EverOS adapter `EverMind-AI/plugins` | [f76f4d06135a](https://github.com/EverMind-AI/plugins/tree/f76f4d06135a0b5d784d15eed133ecdcedc12d47) | dsh 0.1.0；Apache-2.0 | identity、recall、capture、memory-runtime、provision；不能用 EverOS 主库版本代表适配版本 |
| MemOS `MemTensor/MemOS` | [a7367d07e55d](https://github.com/MemTensor/MemOS/tree/a7367d07e55db61099f7b4e2c1108bc5831a24f3) | 本地包 2.0.16-beta.1 声明 MIT；根 LICENSE Apache-2.0 | 本地 DSH adapter、MemoryCore 的 recall / capture / skill；未混用 Cloud 与 Python 全部能力 |
| OpenViking `volcengine/OpenViking` | [563313ebe10a](https://github.com/volcengine/OpenViking/tree/563313ebe10a1b33d0ae736ab8b97ca713ff91f9) | DSH adapter 0.5.0 声明 Apache-2.0；根 LICENSE AGPL-3.0 | `examples/dsh-memory-plugin`；较新 HEAD 见下一节，适配目录未改；非服务端完整审计 |
| WeKnora `Tencent/WeKnora` | [e179f4444592](https://github.com/Tencent/WeKnora/tree/e179f4444592929f9e95be98713883d6c14a7677) | dsh-weknora 0.1.0；MIT 与第三方声明 | `packages/dsh-weknora` 的配置、client、四类工具；未深入 Go 后端 |
| Archify `tt-a1i/archify` | [8809b273c278](https://github.com/tt-a1i/archify/tree/8809b273c278a813a47fa37698864779c0d4cf08) | 核心 2.17.0-dev.1；DSH 0.2.0；MIT | Skill、schema / renderer 组织、deliver / checker 与薄适配；未实测图形质量 |
| Distilly `titanwings/distilly` | [b830d3dcbde0](https://github.com/titanwings/distilly/tree/b830d3dcbde006370f141155795b89021e3a947b) | package / Skill 1.0.0；MIT | 分析提示、writer、章节合并、correction 与版本恢复；未收集个人资料或调用外部账号 |
| Vibe-Skills | [ddcaa2affca9](https://github.com/foryourhealth111-pixel/Vibe-Skills/tree/ddcaa2affca93c1efe026d008b6b93709e5fb7e2) | pyproject / CLI 4.1.0；Apache-2.0 | CLI 迁移、共享 route contract、目录评分与无匹配分支；评测是另一个仓库的作者材料 |
| SkillCorpus `EverMind-AI/SkillCorpus` | [7b3a0eaec559](https://github.com/EverMind-AI/SkillCorpus/tree/7b3a0eaec5594b7f6cb301189c3d626f15409ed0) | DSH search 0.4.0；Apache-2.0 | aggregate / curate / models、match 说明及 TS engine 的模式、检索、bundle / refs；未训练匹配模型 |
| BrowserSkill `Tencent/BrowserSkill` | [34a07f3c3160](https://github.com/Tencent/BrowserSkill/tree/34a07f3c3160b89ce76635d79a810e34b3b25b67) | DSH plugin / extension 0.3.0；MIT | DSH 工具、queue、runner、session starts / journal、观察及部分 extension；Rust 层依据架构契约，非完整源码审计 |
| dsh-browser，现 `omdsh-dev/dsh-browser` | [36fd3ad2d22b](https://github.com/omdsh-dev/dsh-browser/tree/36fd3ad2d22b814d462b158541c843e6df0bb1cd) | root / extension 0.1.4；MIT | bridge 与 extension 页面连续性；正文旧 Lum1104 路径对应同 SHA |
| dsh-context | [2ae7cfa7f8f1](https://github.com/bowenliang123/dsh-context/tree/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7) | 0.54.4；Apache-2.0 | projection / fold、backfill、pricing 与最新 decode block 统计；未测面板性能 |
| billion-context | [b2f28c6a4a85](https://github.com/ranxianglei/billion-context/tree/b2f28c6a4a854d88382509eb4f5531465c989793) | 0.1.139；acp-kernel 0.0.82；MIT | DSH native、fetch intercept、session / 原文 / decompress；独立 kernel 未完整审计 |
| dsh-mcp-manager | [7f5675fda2fa](https://github.com/zhang-guo-wen/dsh-mcp-manager/tree/7f5675fda2fac4fc2dabc1554b85a1e71a54f703) | 0.1.0；Apache-2.0 | loading、composition gate、按 agent 的连接 / 过滤 / 清理；未运行实际 MCP server |
| dsh-claude-compat | [0f9253a5fbb8](https://github.com/zhang-guo-wen/dsh-claude-compat/tree/0f9253a5fbb80c97660eee95e0ce56facdc6a886) | 0.2.0；Apache-2.0 | Skill / instructions / path rules 的激活与去重；不是 Claude 全部行为兼容证明 |
| dsh-market | [90a31aed5a65](https://github.com/dsh-market/dsh-market/tree/90a31aed5a65d5f5ddaa6cb99432b047c4923581) | 1.58.0；MIT | registry / profile、install、snapshot、restart / recovery；未实际安装或更新插件 |

## 3. 本轮特意核对的时效与身份问题

1. **Anywhere**：仓库旧名称已跳转到 `anywhere-labs/dsh-desktop`；本篇采用新读取的 stable 2.0.14，不将 beta / next 目录内容混入。
2. **OpenViking**：当日较新 HEAD 为 `34840c24f92ed04b19dac559dd2a6f13c336742f`。与固定阅读版本之间有四个提交，涉及文件系统、HTTP 观测、grep 与 MCP 文档 / 实现，未修改 `examples/dsh-memory-plugin`。正文保留旧固定适配源码，同时说明差异；这不表示其服务端所有实现没有变化。[固定版本比较](https://github.com/volcengine/OpenViking/compare/563313ebe10a1b33d0ae736ab8b97ca713ff91f9...34840c24f92ed04b19dac559dd2a6f13c336742f)
3. **dsh-context / market**：更新后再次获取快照，正文引用新 SHA；context 首次 TLS 中断后于 07:23 UTC 成功，失败记录不被删除。package 版本不变仍可能已有源码增量。
4. **dsh-browser**：对 Lum1104 与 omdsh-dev 两个公开 Git 地址分别执行 `git ls-remote ... HEAD`，均返回 `36fd3ad2d22b814d462b158541c843e6df0bb1cd`。前 100 元数据采用新组织名，旧链接和缓存用旧名，不能算两个项目。
5. **Vibe-Skills / SkillCorpus / billion-context**：旧脚本、文件头注释或薄转发入口可能与当前默认执行路径不同。分别追到共享 runtime core、默认 on-demand 分支、DSH native 和独立 acp-kernel 依赖，不只摘录 README 的概括。
6. **兼容范围**：Nanmi package 枚举若干 0.1.2 / 0.1.5 prerelease；wowyuarm 上界为 `<0.1.6`；LoopX 当前源码范围较宽但仍不能代替实测。某仓库当天有提交，不能推出它已兼容当日全部 DSH 发布。
7. **许可范围**：OpenViking 的根 AGPL 与适配 package Apache 声明、MemOS 的根 Apache 与本地 package MIT 声明均分开记录。WeKnora 的 GitHub `NOASSERTION` 不能替代已读 LICENSE。iPolloWork 于 07:48 UTC 补取固定 LICENSE 成功，确认当前为带用途 / 人数等条件的 source-available 许可，未作允许移植的判断。

## 4. 用户使用与作者效果材料

| 一手材料 | 本轮采用的事实 | 结论限制 |
| --- | --- | --- |
| [Anywhere #1115](https://github.com/anywhere-labs/dsh-desktop/issues/1115) | 带 Windows / Desktop / DSH / 插件版本的更新失败过程，涉及文件占用、恢复与入口缺失 | 用户报告，未由本轮复现；不能推导最新 stable 必现或整个产品不可靠 |
| [BrowserSkill #305](https://github.com/Tencent/BrowserSkill/issues/305) | Windows 上 staged 新版与运行旧版不同，daemon 与多份 CLI 造成升级判断复杂 | 报告涉及旧版本升级过程；没有作为当前固定版本缺陷实验 |
| [Nanmi #176](https://github.com/NanmiCoder/dsh-agent-teams/issues/176) | 队长会话 fork 后团队还在，但新会话管理关系出问题 | 用于识别身份与会话寿命边界，不扩展成所有 fork 必现 |
| [Nanmi #187](https://github.com/NanmiCoder/dsh-agent-teams/issues/187) | 请求兼容 0.1.6-alpha.2 | 用户需求信号，不代表兼容已通过 |
| [market #639](https://github.com/dsh-market/dsh-market/issues/639) | 旧版在官方 desktop 下误选 web profile 的环境、过程与源码定位 | 本轮当前源码已处理 profileContext；报告不是最新版本尚未修复的证据 |
| [Vibe 作者评测](https://github.com/foryourhealth111-pixel/vibeskills-benchmark/tree/main/studies/full-skills-comparison) | 任务集、去重、有效样本、reward / token 数与最佳记录筛选规则 | 作者材料；非全尝试均值，未公开完整原轨迹，本轮未重跑，不预测本项目收益 |
| [billion-context 作者材料](https://github.com/ranxianglei/billion-context) | 长期运行与规模宣称、代理 / 原生模式说明 | 没有独立核查原始长期记录；不得升级为企业部署实证 |

这些来源中的测试目录、示例与 issue 能说明工程问题和实际使用形态，但不等于本轮已部署成功。所有项目均没有在本轮取得足以统一声称“大规模企业生产验证”的采用资料。国内组织与海外社区都包含在候选中，但没有按组织名称、品牌或语言推定维护质量。

## 5. 获取与验证限制

匿名 GitHub core API 达到额度后，后续固定源码使用公开 Git HEAD、codeload 或 raw 文件，不读取用户账号或凭据。最近更新页第二页限流，没有把它替换成完整长尾覆盖声明。

iPolloWork 压缩包超过本次筛选的 72 MiB 获取上限，随后用无 checkout 的过滤 Git 元数据读取树，并按固定 SHA 定向读取所需源码。该上限只是本次研究工具选择，不是产品能力限制。部分 raw 文件 TLS 获取失败；LICENSE 重连后补取成功，部分远端适配等文件仍未取得，正文不对未取得的实现下结论。

文本快照按研究需要筛选后缀，跳过依赖 / 构建目录、大文件、链接和不适合当前 Windows 缓存路径的项目。BrowserSkill 的 Rust CLI / daemon、WeKnora Go 后端并未包含在已读核心源码中；相应主文清楚区分架构契约与直接实现。成功缓存几千个文本文件不表示每个文件都已精读。

未安装或执行第三方 Agent、服务、浏览器扩展与 Skill 脚本，未运行模型效果测试，未验证 OS 沙箱。没有以本轮纯文档改动触发本项目应用测试、依赖升级、提交或推送。缓存中的工具小脚本只用于读取、筛选和文档检查，不是产品实现。

## 6. 本地证据位置与检查口径

正式产物都在本目录；旧 `../deepseek-plugins/` 已标记为历史，不作为当前推荐。下面的原始证据归 Git 忽略的 `.artifacts/research/`，不会被当作正式源码或承诺随提交分发。

| 缓存位置 | 内容 |
| --- | --- |
| `.artifacts/research/deepseek-plugins-20260923/selection-popularity-top100.json` | 当次 GitHub 前 100 原始元数据 |
| 同目录 `selection-candidate-pool.json` | 固定目录的问题导向候选与近期发现 |
| 同目录 `selection-freshness.json`、`selection-upstream-deltas.json` | 旧样本 HEAD 与变化文件复核 |
| 同目录 `snapshot-manifest.json` 与各仓库 `source/` | 同日早些时候取得、仍被本轮明确采用的固定源码 |
| 同目录 `selection/` | 四个机制补充样本的源码、提交和阅读行段 |
| `.artifacts/research/deepseek-plugins-v2-20260923/` | 新主线、EverOS adapter、SkillCorpus、Vibe 及刷新快照；各 manifest 保留获取成功 / 失败 |
| 各缓存的 `read-ranges.jsonl` | 工具读取的文件与行段；不是逐行审计覆盖率 |
| V2 缓存 `document-check-final.json` | 正式文档的结构、链接目标与固定源码目标检查 |
| V2 缓存 `local-source-snapshot.json` | 研究时本项目相关源码身份；共享工作区后续可能变化 |

最终检查直接验证 UTF-8 / LF、BOM / 替换字符、末尾换行、尾空格、代码围栏、引用定义、本地目标及固定 SHA 对应的缓存路径。它只能排除结构与定位错误；正文的机制、默认行为和证据等级仍需语义复核，也没有宣称所有外网链接完成实时可达性测试。具体检查结果保存在上述报告和独立 [研究进度](../../progress/research.md)。
