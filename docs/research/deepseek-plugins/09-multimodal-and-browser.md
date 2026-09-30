# Modlens、Qwen 社区适配与 dsh-browser：输入和外部操作怎样进入 Agent

> 2026-09-23 核查。本文的主体均非 DeepSeek 官方插件：Modlens 来自 liustack，浏览器桥来自 Lum1104；QwenLM 是多模态能力上游，omdsh-dev 是独立的 DSH 适配 fork。分析基于固定源码，未安装、登录外部服务或调用视觉模型。

## 1. 先理解三种不同的扩展位置

Modlens 在模型请求边界把图像变成文本证据，让原本只接受文本的模型利用图像信息；Qwen-MM-Plugins 提供一组多模态 MCP 工具，DSH carrier 负责装配；dsh-browser 则把宿主工具调用送到用户浏览器，执行后将页面状态返回。

这分别是请求转换、能力调用和远端交互。把它们统称为“支持图片 / 浏览器”会丢失关键区别：图像是否仍在原始历史中、谁真正看图、工具有没有副作用、取消能否停止实际工作，以及用户切换页面后操作还落在哪个目标。

## 2. Modlens：从原始附件到有缓存的视觉证据

固定 `liustack/modlens@9b67ba437dd12e5bcff8f639d6ddd7baa3498d91`，包版本 3.26.3，MIT。

### 2.1 仓库与装配

`dsh/index.js` 适配 DSH 的 tools、agents、attachments、llm；`src/analyzer.ts` 负责通用分析与 provider 选择；发布包的 CLI 是 DSH 工具调用的执行入口。DSH 层通过当前包的路径定位已发布 CLI，而不是每次临时下载一个不确定版本的可执行文件。[DSH 接入](https://github.com/liustack/modlens/blob/9b67ba437dd12e5bcff8f639d6ddd7baa3498d91/dsh/index.js)

这种组织允许同一图像分析能力被不同宿主复用。修改视觉结果 schema 会同时影响 CLI、缓存和 DSH 工具；只改宿主事件接口则主要落在 `dsh/`。独立 analyzer 仍有自身配置和服务依赖，安装 carrier 并不代表视觉服务已经可用。

### 2.2 为什么只添加一个 hook 还不够

某些 DSH 模型元数据声明仅文本，宿主会在插件处理请求之前拒绝粘贴图像。Modlens 因而注册包装 provider：对 UI 宣布允许图像输入，在请求发送前将图像换成视觉服务产生的证据文本，随后委派给原 provider。

用户历史中的附件和缩略图可以保留，实际发送给文本模型的是转换后的内容。这是“存储的事实”与“发出的投影”分离的例子，不等于主模型获得原生视觉能力。视觉服务遗漏或误读的内容，文本模型仍然无法从原图补回来。

包装器可发现已注册 provider，也监听 adapter 更新来处理晚注册路由。发现过程中必须排除自己注册的包装 provider，避免把自己的合成模型当成原生视觉模型，或递归包装。代码还专门处理 Cordis context 尚未 active 就读取 llm 服务的问题，说明插件热装配的时序会成为真实故障来源。

### 2.3 显式工具与自动处理共用什么

`modlens_read_image` 允许模型按路径或 URL 主动取证，返回 OCR、区域、语义和不确定性等结构化信息。自动读取另有开关；当前默认关闭，因为请求期包装已能转换且保留历史缩略图，双重开启可能产生重复工作。

同一插件实例为附件和显式读取管理缓存。相同读取可以共享一个 pending Promise；远程资源有短 TTL，失败有 cooldown，LRU 淘汰优先处理已完成项。这样“模型重复要求看同一图”不必每次都产生视觉费用。[缓存及请求处理](https://github.com/liustack/modlens/blob/9b67ba437dd12e5bcff8f639d6ddd7baa3498d91/dsh/index.js)

共享请求会改变取消语义：单个调用者停止等待，不应取消其他调用者正在等待的同一次分析。代码对等待者使用 `abortableWait`，共享 CLI 读取使用自身 deadline。这能避免串扰，但意味着用户取消这一处等待后，底层共享工作可能暂时仍在运行；不能将 UI 已取消描述成所有子进程已停止。

### 2.4 Provider 策略与实际价值

analyzer 对显式指定的 provider 保持固定选择；其他配置允许候选路由、失败冷却和 fallback，并记录尝试与错误。这些策略属于 Modlens 本身，不是 DSH 或 MCP 自动提供的保证。[Analyzer](https://github.com/liustack/modlens/blob/9b67ba437dd12e5bcff8f639d6ddd7baa3498d91/src/analyzer.ts)

适合参考的部分是稳定历史、请求期转换、证据结构、共享缓存和取消归属。我们项目已经限定模型范围并要求实际故障停止，不能直接复制自动 provider 切换，也不应仅为了支持图像就悄悄增加付费视觉服务。是否接入应是后续明确产品需求。

## 3. Qwen-MM-Plugins：上游能力与社区 carrier 必须分开看

固定上游 `QwenLM/Qwen-MM-Plugins@488e548b454ccc105094be33b83a60c07a5c3abe`；社区 fork `omdsh-dev/Qwen-MM-Plugins@12e0346bbe2fa3a8634ed56ab188101fa8226587`。

### 3.1 能力层的组织方式

上游按 capability 分包：每项能力有 Python MCP 入口与配套 Skill；共享 API、媒体处理和缓存代码放在 shared。core 内又区分 readers、producers、renderers：读取图像 / 视频、裁剪或保存视图，以及把文档 / 数据渲染成可观察形式是不同职责。

Skill 告诉 Agent 何时、按什么顺序使用工具；MCP server 提供可执行的接口。二者版本不一致时，模型可能按旧说明调用新参数，所以手动接入文档要求 Skill 与 MCP 命令使用同一 tag。[上游接入说明](https://github.com/QwenLM/Qwen-MM-Plugins/blob/488e548b454ccc105094be33b83a60c07a5c3abe/docs/zh/manual_harnesses.md)

### 3.2 旧接入中的媒体限制不能当成当前结论

上游手册的 DSH 段落最后验证的是 0.1.0-rc.6：文本和结构化结果可用，部分原生媒体 block 会被丢弃。这个说明真实反映其验证范围，却不能推出九月当前 DSH 仍只能使用文本。

社区 fork 当前的 `packages/dsh/` 明确依赖支持 native media 的 MCP client，要求 `@deepseek-ai/dsh-mcp-client@^0.1.0-rc.8` 这一接口线，并将附件 admission / `finalizeContent` 交回宿主，不再携带旧客户端兼容层。[当前 carrier 说明](https://github.com/omdsh-dev/Qwen-MM-Plugins/blob/12e0346bbe2fa3a8634ed56ab188101fa8226587/packages/dsh/README.md)

### 3.3 当前代码实际怎样运行

入口只强依赖 tools，根据 `capabilities` 构建 server config，逐个 `await ctx.plugin(mcpClient, server)`。每项通过 `uvx --from <PEP 508 package reference>` 启动对应 Python capability；cwd、env、工具超时和启动失败策略显式传递。[装配代码](https://github.com/omdsh-dev/Qwen-MM-Plugins/blob/12e0346bbe2fa3a8634ed56ab188101fa8226587/packages/dsh/src/index.ts)、[配置构建](https://github.com/omdsh-dev/Qwen-MM-Plugins/blob/12e0346bbe2fa3a8634ed56ab188101fa8226587/packages/dsh/src/config.ts)

这个快照的 bundle patch 是 `disabled: false`，source 指向社区 fork，ref 默认 `main`。因此不能沿用旧网页所说“默认关闭、固定 ref、等待工具发现后自动挂 Skill”的描述：当前入口没有那段 Skill 注册逻辑。`main` 也不是可复现的版本标识；需要复现安装时，宜固定与 Skill 匹配的实际版本，而本文的 SHA 只固定调研证据，并没有替用户安装。

它最有价值的演化方向是 carrier 变薄：宿主已提供原生媒体能力后，社区层移除重复转换。这提示我们未来做插件适配时，应该明确哪些职责已下沉到宿主，避免同时维护两套媒体、认证或取消机制。

## 4. dsh-browser：从宿主会话到用户浏览器中的具体操作

固定 `Lum1104/dsh-browser@36fd3ad2d22b814d462b158541c843e6df0bb1cd`，桥包 0.1.4，MIT。

### 4.1 三层代码对应三个执行位置

`packages/browser/bridge-browser/src/` 在 DSH 进程内提供工具与 WebSocket 桥；`extensions/dsh-browser/src/background/` 是浏览器扩展 service worker，管理连接、授权、目标 tab 和工具调度；`content/` 在页面中抽取结构、执行动作；`panel/` 展示对话与用户交互。

DSH 的文件 / 终端工具与网页中的点击不在同一个执行环境。浏览器扩展能接触用户已有页面状态，是它区别于新开无状态自动化浏览器的价值所在，也使 tab 身份、页面来源与会话绑定成为核心设计。

### 4.2 先连接，再建立会话

桥路由 `/ext/bridge` 不在宿主 `/api` 的 trust fence 之内，所以桥自己要求首帧 hello 提供 bearer token，并限制握手时间。敏感宿主方法即使 token 正确也继续要求 loopback 来源。新认证连接会替换旧连接，旧连接的在途工具调用以 `bridge-closed` 结束。[桥服务](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/packages/browser/bridge-browser/src/server.ts)

插件还推迟会话实化，直到第一条 prompt 到达，减少用户只是打开面板就产生空会话。snapshot、prompt 和 cancel 等操作必须尊重同一 session 的顺序。[宿主入口](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/packages/browser/bridge-browser/src/index.ts)

### 4.3 一次 browser tool 的数据流

宿主创建带调用 id、session id 和期限的 `tool.call`；扩展确定受控 tab，经 content script 完成动作；结果以相同关联身份返回。页面文本作为不受信内容包装，不能因为来自工具就取得用户指令的地位。

扩展对 iframe 分配快照预算，动作完成后返回页面变化；导航完成后附新页面 snapshot，减少“点击 → 无信息 → 再截图”的机械往返。这里的收益来自输出协议与状态利用，不是提高主模型智力。[扩展工具分发](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/extensions/dsh-browser/src/background/tools.ts)

### 4.4 用户切换 tab 时，Agent 应该跟着切吗

`TabAffinityController` 分开 controlled tab 与 active tab，使用 unbound、following、handoff、background、lost 等状态。手工切换不会静默改变工具目标；用户可以保持原受控 tab、跟随新 tab，或固定原绑定减少重复询问。session 到 tab 的映射独立于当前面板焦点。[Tab 状态机](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/extensions/dsh-browser/src/background/tab-affinity.ts)

这是多会话桌面产品很直接的参考：**显示焦点不应隐式决定在途动作的目标**。同样的原则可用于我们的项目、终端和成果面板。适合吸收绑定和失效提示；是否增加每次切换确认则需要按既有用户授权决定，不能照搬整个交互策略。

### 4.5 持久化与隔离边界

浏览器目标绑定、会话记录和单次调用等待者有不同寿命；重连不能自动重放结果未知的点击。插件的 token、来源检查和目标控制不构成任意网页脚本或宿主命令的 OS 沙箱。本文没有运行恶意页面、测试扩展权限或验证真实浏览器断线恢复，不能据静态阅读给出安全认证结论。

## 5. 横向参考

| 问题 | 最值得看的实现 | 对本项目的含义 |
| --- | --- | --- |
| 原始输入与模型可见内容不一致 | Modlens 请求期图像转换 | Trace 应解释转换来源，保留原始附件身份 |
| 同一外部工作被多处复用 | Modlens pending Promise / 取消等待 | 区分等待者取消和底层工作取消 |
| 宿主升级后社区兼容层怎样收缩 | Qwen carrier | 优先复用宿主契约，记录真实最低接口要求 |
| 多会话共享外部 UI | dsh-browser tab affinity | 显式绑定资源，焦点切换不重定向在途操作 |
| 工具结果怎样减少下一轮浪费 | 浏览器动作后附状态变化 | 输出应服务下一步决策，而非只返回“成功” |
