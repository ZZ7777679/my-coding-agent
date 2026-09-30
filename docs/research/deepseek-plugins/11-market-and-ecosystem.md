# 从 dsh-plugin 话题到可安装生态：dsh-market 与社区目录

> 核查日期：2026-09-23。这里研究第三方生态，不把官方仓库内置插件算作社区成果。主要源码是 `dsh-market/dsh-market@e2c53bcb5f5e38a360c44304298196dca46fc4aa`（1.58.0，MIT），辅以三个独立目录快照和 GitHub 话题页。

## 1. 用户指出的入口，实际包含哪些东西

官方跳转的 [GitHub dsh-plugin 话题](https://github.com/topics/dsh-plugin) 确实能发现很多非官方二次开发。本轮复查默认排序前两页与最近更新入口，再结合社区目录选取代表项目。话题不是兼容性认证，也不是所有条目都可执行 `dsh plugin add`：其中同时存在原生插件、桌面产品、MCP 服务、Skill、独立 Agent、教程和关联很弱的条目。

判断一个项目如何接入，至少要看到其真实入口：`package.json` 中的 DSH 声明、Cordis patch、宿主服务依赖，或者明确的 MCP / Skill 接法。不能只因项目名包含 DeepSeek 或 harness 就分类。我们对 Open Design、Ruflo 和 Reasonix 的核对实例见 [补充调查](14-topic-products.md)。

## 2. 三类目录各自提供什么证据

| 目录 | 它提供的主要价值 | 本轮如何使用 |
| --- | --- | --- |
| awesome-dsh-plugin/awesome-dsh-plugin | 以可安装 bundle 为中心的分类清单，同时提供市场可用目录 | 发现插件、定位作者和源码；不将收录等同于质量审计 |
| awesome-deepseekharness/awesome-deepseek-harness | 更广的 Harness 生态线索 | 补充产品与项目入口，核心机制仍回到目标仓库 |
| dshworks/awesome-dsh-plugins | 机器可读条目、形态 / 功能分开、版本 / 日期 / evidence 字段及排除记录 | 对照“主题相关”和“确有接入路径”的差别 |

第一个目录明确收录 `dsh.bundle` 可安装项目，也明确不提供安全背书；因此其安装规则比 topic 标签更具体，但不能保证装入任意当前 Desktop 都能工作。[固定目录说明](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/7983709b6ebfca1d50d134f2c5c5f660308bd879/README.md)

dshworks 的具体经验很有价值：作者曾把 repo 内 package name 当成已经发布的 npm 包名，随后发现包不存在，甚至同名包属于另一个作者。当前目录记录安装证据，并核对发布包的 repository 身份。其 README 的覆盖数字是维护者统计，本文没有重跑全量爬取，不能据此宣称自己覆盖了整个话题。[目录维护说明](https://github.com/dshworks/awesome-dsh-plugins/blob/7ebdc0869ca62a837c34066f57d2f8bd547d9775/README.md)

可迁移的原则是：发现身份、安装来源、包身份和启用结果需要关联，却不是同一个字段。我们现有 Skill 原站浏览也遇到“网页能看到，但条目没有可识别 GitHub 来源”的情形；此时应准确显示可浏览 / 可下载 / 可导入的区别，不能猜一个安装目标。

## 3. dsh-market 的仓库怎样划分

`registry.ts` / `catalog-*` 管发现；`sources.ts`、`profile.ts` 管安装目标与配置身份；`install.ts` / `dsh-cli.ts` 管包管理执行；`compatibility.ts`、`check.ts` 管已装依赖分析；`hot.ts` 管热挂载；`snapshot.ts` / `backup.ts` / `recovery.ts` 管不同恢复方式；`routes.ts` 装配用户操作；客户端展示列表、状态和操作。

因此市场的复杂性不主要来自搜索框，而是“用户点击安装之后，哪个配置发生变化，当前进程是否真的加载成功，失败后能否恢复”。模块很多，但 routes 仍聚合大量跨模块步骤，不能把文件拆分视作安装事务已经天然正确。

## 4. 打开市场：目录时效性怎样表达

`registry.ts` 当前每次请求都询问来源；内存中保留 ETag / Last-Modified 或 npm 版本标识，由来源确认未变后复用内容。它区分“没有发请求、沿用一小时前缓存”和“刚确认来源未变”。来源切换时 validator 也按来源身份隔离，不能给 A 站发送 B 站的 ETag。

旧版短超时后静默返回小型内置清单，可能把网络慢表现成插件不存在；当前代码取消这种隐式替代，返回具体错误。上游注释包含作者计时，本次没有复测其网络性能。[目录加载](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/registry.ts)

这一变化对“保证时效性”的启发很直接：缓存应该说明来源何时确认，失败不能伪装成一份完整的新目录。同样，本次研究固定的是 9 月 23 日取得的源码快照，不声称之后的 main 仍完全一致。

## 5. 点击安装：先确定正在使用哪个 profile

profile 是一套插件依赖和配置组合，不等于项目工作目录。dsh-market 既能运行在普通 DSH，也能被第三方桌面壳装入，因此不能仅从 `argv --profile` 猜当前配置。

当前入口支持官方 `profileContext` 提供的名称、目录和可选 package manager；对 Anywhere Desktop 使用其公开 `desktopProfiles` / `desktopPnpm` 服务。目录随真实 profile 身份传递，不再从名字重建一个假定路径。[宿主适配入口](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/index.ts)

[issue #639](https://github.com/dsh-market/dsh-market/issues/639) 报告的具体故障是：某桌面启动方式没有 CLI flag 和第三方 desktopProfiles，旧市场退回 web profile，用户看着一个配置却修改了另一个。网页核查时该 issue 仍显示 Open；当前源码已出现 profileContext 处理，但本次没有在报告环境复现验证，所以应称“源码已调整”，不能称“该问题已实测修复”。

这比一般的插件安装失败更值得参考：操作成功返回并不等于改对对象。我们已有 project / session / run 身份，同样应让变更关联实际目标，而不是当前显示焦点或一个业务默认值。

## 6. 版本兼容不是简单比较字符串

`classifyPeer()` 从确实不满足的 peer 关系中区分方向：低于最低要求、超出明确上限 / 精确版本，以及超出隐含 caret 上限的警告；optional peer 单独告警，不与必需依赖混为一谈。无法解释的范围不凭空产生确定结论。

安装前后比较新引入的风险和 duplicate Loader name，避免把早已存在的无关告警全部归咎于本次安装。这是减少误阻断的实用设计，而不是自动证明 ABI 兼容。[兼容性分类](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/compatibility.ts)

“声明版本兼容”“服务能激活”“真实工具回合通过”仍是三个层次。本文逐项目注明旧 peer / 新宿主差异，没有批量安装来验证，因此不提供所有插件与 DSH 0.1.7-alpha.2 兼容的结论。

## 7. 包管理执行、热装载与真实状态

安装最终仍要交给宿主指定的包管理方式。`withHoistRecovery()` 识别 pnpm 大版本造成的 hoist 布局差异、release age、未发布的宿主 peer 和网络等问题，某些分支会重建或调整本次参数后重试。它区分 manifest 显式依赖与被 peer 自动引入的包，减少错误诊断。[安装处理](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/install.ts)

这些是 dsh-market 的产品策略，不能自动移植到我们要求故障停止的运行策略。尤其不应把某个安装故障转换成修改全局 pnpm、代理或自动切换来源的普遍许可。

包落盘后，运行树和浏览器页面仍可能使用旧代码。带 `dsh.client` 的插件变化涉及页面刷新；热挂载输入、下一次启动的 bundle 和当前 live tree 也要协调。routes 维护安装、兼容检查、启停及刷新反馈；UI 不能只把 package manager 退出码 0 当作全部生效。[操作装配](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/routes.ts)

## 8. 恢复：配置快照和独立救援入口是两件事

`snapshot.ts` 保存 profile 的关键组合文件：package.json、cordis.patch.yml、市场 state，并记录某文件原先不存在，恢复时才能删除后来新增的文件。它提供逐步恢复失败后的补偿，但不是 node_modules、所有插件数据和任意安装脚本副作用的完整事务。[配置快照](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/snapshot.ts)

更特别的是 `recovery.ts`：如果某插件让整个 DSH 启动失败，市场 UI 也会随宿主消失。因此重启 helper 可以启动独立恢复页面，允许调整下次启动要启用的既定插件，并释放端口。救援进程不依赖已经损坏的插件树，才有机会在宿主坏掉时继续工作。

代码还记录一个真实设计修正：端口刚监听并不等于启动成功，因为后面的激活检查可能让进程退出。恢复逻辑等待一段持续可用窗口；这改善了其探测，但仍是启动健康判据，不是所有业务能力已验收。[独立恢复入口](https://github.com/dsh-market/dsh-market/blob/e2c53bcb5f5e38a360c44304298196dca46fc4aa/src/recovery.ts)

## 9. 本轮能确认哪些落地，不能确认哪些

可确认的是：有实际市场源码、可安装声明、多个社区 Desktop 的集成路径、版本迁移逻辑，以及具体用户故障报告。它们已经远超一个概念 demo。

不能据此推断大规模企业生产部署、插件组合稳定率、安装成功率或商业收入。作者 / 项目组织属性与企业实际落地证据是不同事实。本轮未访问私人群组、未核实付费用户案例，也没有运行市场安装链。

对我们的优先参考是安装来源身份、项目启用状态、版本证据和失败后的可恢复入口。当前 M4 的 Skill / MCP 资源能力已存在；是否再引入可运行任意代码的通用插件市场应由产品需求决定，不能从“生态很丰富”直接跳到复制整个 Cordis 运行时。
