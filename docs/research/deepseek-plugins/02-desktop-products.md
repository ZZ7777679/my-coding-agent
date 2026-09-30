# 两种 DSH 桌面二次开发：Anywhere Labs 与 DataElement

> 核查日期：2026-09-23。两者均读取固定源码，不把同名 Desktop 当成同一产品，也不把社区发行者视为 DeepSeek 官方。上游现在也有 `apps/desktop`，应与这两套社区方案分开。本文未安装发行包、验证签名或运行桌面。

## 1. 共同问题与两种答案

浏览器版 Agent 可以工作，却没有自然的安装入口、后台进程管理、原生目录选择、故障恢复和升级体验。Desktop 的价值不是在网页外面画窗口，而是让这些生命周期成为可管理的产品。

Anywhere Labs 选择让桌面能力进入 Cordis 组合，使桌面本身成为插件；DataElement 选择在 Electron 主进程管理一个独立 Harness runtime，通过附加包补齐 Preset、手机接续和文档产物能力。前者重点是可组合的宿主服务，后者重点是发行应用对 runtime 的管理。两者都值得参考，但故障域和升级边界不同。

## 2. Anywhere Labs：启动一次，就拥有一代完整资源

固定仓库抓取名 `anywhere-labs/deepseek-harness-desktop`，提交 `763a793df1834c6ae60288371d7b91f848f79784`，MIT；稳定桌面包清单版本 2.0.14。9 月 23 日网页核对旧地址已重定向到 [anywhere-labs/dsh-desktop](https://github.com/anywhere-labs/dsh-desktop)，是仓库更名，不是第三个产品。当前文档包含 stable / beta 两个实体包，以及 next 目录；不能将它们的能力合并成一个已经发布的版本。

### 2.1 仓库不是一个 Electron 单包

`dsh-plugin-desktop/` 是稳定桌面包，`dsh-plugin-desktop-beta/` 是独立 Beta 包；`dsh-community-market/` 实现社区市场；`dsh-community-fabric/` 是互操作提案材料；`dsh-desktop-next/` 是另一条开发路径。`docs/` 解释总体架构，包内 docs 规定服务契约。

这里最重要的分界是“已运行的服务”与“未来的公共规范”。仓库明确把 Community Fabric 的 manifest、capability 和统一事件模型标为 RFC Draft，不能把它当成现成接口依赖。稳定 / Beta 的上游固定与打包闭包也应分别读取。[架构](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/763a793df1834c6ae60288371d7b91f848f79784/docs/architecture.md)

### 2.2 从启动到用户看到窗口

Electron 先拿单实例锁，读取自身 profile / mode 状态；Launcher 准备选定 profile，把 native runtime、profile 事实和 pnpm 环境提供给 Host。随后 Cordis 加载官方 base / web-app 与第三方 bundle，HTTP / WebSocket carrier 就绪后，沙箱化 BrowserWindow 加载同源页面。

关键是“成功”的时点：不是 Node 进程创建成功，而是 Web surface 真正加载后，才提交 last-known-good。这样下一次恢复能区分“新配置写进去了”和“新配置确实能启动界面”。

renderer 使用普通 DSH Web 接口，不直接获得 Electron API。第三方需要原生能力时，应使用公开服务；`desktopRuntime`、BrowserWindow、托盘和 Node helper 仍是内部实现，不因为出现在运行上下文中就成为兼容承诺。

### 2.3 generation 解决的是真实资源残留

`DesktopStartupGeneration` 保存唯一 Host、资源释放回调、共享 dispose / release Promise。每个 `own()` 返回幂等释放函数，正常退出和失败恢复都收敛到同一路径。释放时先停止 Host，再按逆序清理资源。

恢复操作先 `quiesceForRecovery()`。如果旧 Host 未能停止，返回 false 并禁用会修改状态的恢复操作，而不是一边旧进程运行、一边替换它的配置。这个限制针对具体写者仍活动的场景，不应扩展成普通任务必须先通过一套健康检查。[generation 实现](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/763a793df1834c6ae60288371d7b91f848f79784/dsh-plugin-desktop/src/startup-generation.ts)

### 2.4 插件怎样安装其他插件

公开 `desktopProfiles` 提供当前身份、只读列举和切换请求；`desktopPnpm` 接受 argv，返回 stdout / stderr、done 与 cancel。`runPlugin()` 走 DSH CLI 的 profile / bundle 语义，而不是让每个市场重新实现包管理。

源码把操作绑定到当前 generation；卸载时标记 closed，终止活跃子进程并等待 done。调用完成应表示进程生命周期结束，而不只是取消某个等待 Promise。[pnpm 服务](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/763a793df1834c6ae60288371d7b91f848f79784/dsh-plugin-desktop/src/pnpm.ts)

### 2.5 落地收益与成本

收益是第三方插件能复用同一 Web、工具和服务体系，桌面无需另造一套 renderer 插件 API。成本是 Electron 主进程内承载 Host 后，插件错误和资源清理更贴近桌面生命周期；ASAR、需物理解包的原生依赖、内置 pnpm 和服务引用的代际失效必须一起维护。Cordis scope 不是操作系统隔离。

## 3. DataElement：把 Harness 当作受管理的本地运行时

固定仓库 `dataelement/dsh-desktop`，提交 `969bfb5dc0704f516d8f351ba85e8626650bc13a`，根清单 MIT / 0.1.1；README 指向 `@deepseek-ai/dsh@0.1.5-rc.2`。根包号、产品发行号和嵌入 Harness 号是三个不同身份，不能用一个替代另外两个。

### 3.1 仓库围绕“启动、状态与恢复”拆分

`src/main/runtime/` 管运行时启动；`src/main/state/` 管插件启停、恢复与更新等持久状态；preload / shared 承接桌面边界；`packages/dsh-desktop-preset-transfer/` 管便携 Preset；`packages/ppt-runtime/` 管文档能力资产。

这比“用了 Electron + React”更能说明设计：最复杂的逻辑不是聊天组件，而是如何将不断变动的上游装配成可升级、可修复的桌面发行物。

### 3.2 用户启动到 runtime 可用

`harness-runtime.ts` 单独构造入口、环境、参数、数据目录与启动 token。它还处理从桌面图标启动时缺少交互 shell 环境的问题，预热环境读取以减少主进程启动阻塞，并处理字符解码损坏。

这些机制能解释“终端里命令可用，桌面中找不到”的真实问题。但它的整份 shell 环境捕获策略不应直接照搬本项目：本项目已有凭据筛除和环境装配边界，需要保留。研究只读取实现，未执行环境枚举。[运行时实现](https://github.com/dataelement/dsh-desktop/blob/969bfb5dc0704f516d8f351ba85e8626650bc13a/src/main/runtime/harness-runtime.ts)

### 3.3 插件坏了，恢复界面仍须能打开

应用提供临时屏蔽第三方插件的 safe mode，以及独立于故障页面的恢复显示。`SafeModeOverlay` 用独立 WebContentsView，开启 contextIsolation / sandbox、关闭 nodeIntegration，独立处理窗口 resize、focus 与 close，并移除监听。

它解决的不是“插件已经可靠”，而是“插件失败后，用户仍能操作宿主”。这对开放扩展尤其重要：如果插件管理页本身依赖那个失败插件，卸载入口也会一起消失。[恢复视图](https://github.com/dataelement/dsh-desktop/blob/969bfb5dc0704f516d8f351ba85e8626650bc13a/src/main/safe-mode-overlay.ts)

### 3.4 Preset 导入：角色配置是有依赖的制品

`.dshpreset` 是带 manifest 的 ZIP，包含 `agent.cordis.yml`、可选 preset 元数据以及技能、插件等自有资产。导出边界是 preset 目录，不主动纳入会话、workspace 或模型凭据。

导入先预览，检查版本、组成、路径和命名冲突，再写临时目录、调用 Harness scanner 验证、原子移动到目标根。已有标识不覆盖。这个设计把“分享一份角色提示词”扩展成“分享一份有依赖和执行能力的配置”，也因此不能把包格式检查等同于代码安全。

在线 Skill 可通过本地 transfer API 调用同一导入路径；不是让模型自行解压并绕过已有实现。[Preset 格式和流程](https://github.com/dataelement/dsh-desktop/blob/969bfb5dc0704f516d8f351ba85e8626650bc13a/docs/preset-packages.md)

## 4. 对我们的桌面项目最直接的参考

本项目已有 Electron 主进程管理 Python 后端、数据根、有限 preload 和故障状态。最有价值的增量是：一次后端启动拥有一组可统一释放的资源；配置变更先保存身份与来源，恢复以真实启动结果判断；资源包与业务数据分离；扩展失败时保留宿主恢复入口。

如果未来分享 Agent 配置，可以借鉴 Preset manifest 和完整依赖快照，但当前工作流模板仍只是数据，不能把导入模板写成可执行编排已经实现。两套 Desktop 都未提供本轮可独立验证的企业内部采用数据；发行包、README 签名声明和真实企业部署应分别记录。
