# Better Sidebar、GenUI 与 ChangeLedger：社区工作台、交互结果与恢复

> 核查日期 2026-09-23。三个项目均来自独立社区作者。固定版本见各节；本文按打开会话 → 展示 / 交互 → 产生修改 → 回看 / 恢复组织。未实际启动插件或执行文件恢复。

## 1. Better Sidebar：从一个侧栏发展为会话工作台

`omdsh-dev/DSH-better-sidebar@1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e`，0.19.1、MIT；所声明宿主 peer 包处于 0.1.5-rc.1 接口线。它不是一份 CSS 皮肤：目录、文件、Git、终端、预览、侧聊和子 Agent 活动都需要后端服务支撑。

### 1.1 仓库边界对应真实职责

`src/index.ts` 装配 HTTP / WebSocket 路由与服务；`fs-*` 管文件树、搜索和写入；`path-security.ts` / `session-path.ts` 管路径解释；`pty-manager.ts` 与 `agent-pty.ts` 管两类终端；`sidechat-*`、`subagent-live-*`、`jobs-*` 管工作状态；`src/client/` 提供展示。

插件还导出 `registerTab` / `registerFileViewer` 的服务描述，让其他插件扩展工作台，而不必改侧栏源码。这是生态中出现“次级扩展平台”的例子：DSH 提供运行宿主，Sidebar 又提供面板扩展契约。它增加组合能力，也增加了兼容链长度。[装配入口](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/src/index.ts)

### 1.2 打开会话后，怎样确定文件和终端属于谁

API 带 sessionId，由后端会话记录取得 authoritative cwd；终端按 session 关联。路径不能简单从“现在 UI 显示哪个文件夹”推导，否则用户切换会话时在途请求会落入错误项目。

路径解析还考虑 Windows 中 WSL UNC 会话：在 `\\wsl.localhost\<distro>` 工作区里，`/foo` 表示该发行版路径，不应被 Windows `resolve()` 变成 `C:\foo`。先解释命名空间，再检查真实目标归属，是两项不同职责。[路径投影](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/src/session-path.ts)

现有文件通过 realpath 处理链接；新目标从最近存在的祖先解析后重建。其 workspace fence 可由设置控制，关闭后仍规范化，但不执行相同包含限制。因此不能把“有 path-security 文件”写成所有模式始终限制于工作区，更不能把此文件 API 检查当成 PTY 进程的系统隔离。[路径实现](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/src/path-security.ts)

### 1.3 浏览器请求如何接触本机能力

新增的 `/sidebar/api`、上传、文件预览、HTML 预览和 terminal WebSocket 都经过自己的 trust fence，读取宿主当前信任来源，而不是认为“同一个插件的 URL 天然可信”。HTML 预览另外处理不透明 origin，避免预览的项目网页直接取得 GUI 同源权限。

这是重要的实现成本：把本机文件和终端搬进网页后，必须保护新建的网络入口。对我们目前 Electron + Python 结构，现有有限 preload / RPC 边界更直接；不必为了复刻同样面板而额外开本地 HTTP 服务。

### 1.4 资源何时释放

HTTP route、WebSocket upgrade 与 live assistant listener 通过 Cordis effect 注册，卸载 fiber 时撤销。Agent PTY 有显式 close 路由，用于 WebSocket 已断开但用户关闭 tab 的情形；关闭操作保持幂等，避免视图消失后留下僵尸 PTY。

重型预览 / 终端库按首次使用加载；node-pty 不可用时对应能力降级，不应让整个会话页面打不开。这种“可选 UI 依赖只影响自己的功能”值得吸收，但源码中的平台支持不等于本次做过 Windows 真实验证。

## 2. GenUI：模型输出怎样变成可交互结果

`omdsh-dev/dsh-genui@6a30de34200ed559646fff27bc2872d9b40a914c`，0.11.1-preview.2、MIT。

### 2.1 先定义模型能描述什么

插件通过 system prompt / Skill 告诉模型输出 `dsh-ui` JSON，或使用 `render_ui` 等工具；JSON 描述的是预定义组件与动作，不是直接运行模型生成的 React 源码。宿主渲染层解释它，再把按钮、表单、图表等交给实际组件。

`src/plugin/` 管 prompt 与工具；`src/shared/` 处理 fence 解析 / 修复；`src/client/genui-runtime/` 管 schema 和限制；`blocks/` 渲染组件；action context 接宿主事件，interaction store 管本地交互状态。这个组织将“模型语言”“显示组件”和“发送用户动作”分开。[插件入口](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/plugin/index.ts)

### 2.2 流式生成的半截 JSON 怎么显示

fence pipeline 尝试解析 / 修复结构；无法修复时保留代码或显示诊断，避免悄悄吞掉模型输出。共用限制包括组件深度 8、总节点 200，以及文本、图表和表格大小限制。它们是该渲染器的资源预算，不是模型能力上限。[渲染流程](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/client/fence-render.tsx)、[限制定义](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/client/genui-runtime/limits.ts)

当前兼容层有两条路径：有正式 fence registry 的宿主直接使用注册接口；没有该扩展点的宿主通过 DOM observer 找代码块并挂独立 React root。后者使插件能在未改宿主上运行，但依赖 DOM 结构，升级时更脆弱。不能把两条路径都说成稳定公开 SDK。

### 2.3 用户点击后发生什么

显示状态与模型动作分开：本地选项、表单填写和某些评分无需每次调用模型；需要模型处理的动作经过宿主 action callback。离散点击立即投递，滑块连续拖动按动作名和控件 id 做尾部 debounce，不能让一个滑块的更新覆盖另一个，也不能用防抖吞掉用户的多次按钮意图。[交互实现](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/client/GenuiBlock.tsx)

React context 必须复用宿主导出的同一个实例。插件自己创建一个名称相同的 context，并不能接到宿主 Provider；当前代码特判这一兼容问题，无可用上下文时仅保持显示能力。[Action context](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/client/action-context.ts)

### 2.4 刷新后保留状态，不等于保存了业务事实

交互状态以 session、块位置 / 工具调用身份和内容指纹关联，保存在 localStorage 并限制条目数；内容换成另一张表单时，不应继续使用旧答案。指纹只是区分内容的键，不是安全摘要。存储失败时仍可保留当前内存交互，不能说它已可靠写回宿主会话。[交互存储](https://github.com/omdsh-dev/dsh-genui/blob/6a30de34200ed559646fff27bc2872d9b40a914c/src/client/interaction-store.ts)

对本项目可参考的是：报告 / 比较 / 用户选项有必要时采用有限 schema；不把模型输出作为可执行 UI 程序；用户提交进入现有会话事实链。完整 GenUI 组件生态仍需维护成本，普通文本和已有确认组件足以表达的流程不必改造。

## 3. ChangeLedger / dsh-turn-rewind：回到过去需要恢复哪些状态

`Anionex/dsh-turn-rewind@4ddc9c1de01cbb740079223df48350976351ae1b`，0.3.8、BSD-3-Clause。当前实现不只是删除最后一条消息：它保存工作区恢复点，比较当前状态，生成恢复计划，执行后检查，并支持文件、消息或组合恢复。

### 3.1 修改发生前：检查点怎样与 turn 对齐

`rewind-host.ts` 在首个 pre-step 启动检查点捕获，先让模型请求链继续；在顶层 tools/execute 处等待本轮捕获的有界结果，再进入工具。这样把“开始读项目树”的延迟与模型思考重叠，同时力求在实际工具修改前保留基线。[回合适配](https://github.com/Anionex/dsh-turn-rewind/blob/4ddc9c1de01cbb740079223df48350976351ae1b/src/rewind-host.ts)

这不是冻结整个工作目录：外部编辑器、其他会话和命令仍可能同时修改文件。按 workspace 的串行队列协调本插件捕获，不能保证所有写入者都参加同一锁。

### 3.2 快照存什么，恢复计划又存什么

`snapshot.ts` 与 `git-checkpoint.ts` 处理普通目录 / Git 后端；`store.ts` 管快照与操作记录；`engine.ts` 管比较、计划、执行和恢复；宿主适配单独关联 session / turn。

0.3.0 路线已支持普通目录；0.3.8 增加 Git native 路线。后者利用 Git 对象降低部分大项目快照成本，但作者 README 的速度数字是上游测量，本文没有复现，也不能外推到我们的 Windows 项目。

捕获范围有排除项和配置；恢复点只能恢复它保存过的状态，不会让依赖目录、远端 API、数据库和正在运行的服务自动回到过去。[项目说明](https://github.com/Anionex/dsh-turn-rewind/blob/4ddc9c1de01cbb740079223df48350976351ae1b/README.md)

### 3.3 用户选中恢复点后：计划不是立即覆盖

`planRestore()` 读取目标快照，重新捕获当前树，核对工作区身份，形成有期限、绑定 session 和具体路径的计划。`applyRestore()` 使用计划时再次核对当前状态、Git 身份及未管理内容冲突，避免用户预览以后发生的其他修改被默默覆盖。

随后创建 rescue point 保存恢复前状态，写 `running` 操作记录，再逐路径恢复和检查。只有检查通过才完成；中途失败则尝试从 rescue 回滚。回滚成功返回“恢复失败但已还原”，回滚也失败则返回 `RECOVERY_REQUIRED`，保留操作 id 与 rescue id。[恢复引擎](https://github.com/Anionex/dsh-turn-rewind/blob/4ddc9c1de01cbb740079223df48350976351ae1b/src/engine.ts)

```text
目标恢复点 + 当前工作区
  → 计划 / 差异
  → 再核对当前状态
  → 保存 rescue point 和操作 journal
  → 执行恢复 → 检查
                 ├─ 成功：完成
                 └─ 失败：尝试 rescue 回滚 → 还原成功或需恢复
```

这里的 journal 帮助解释中断结果，不等于整个目录的原子事务。文件恢复和会话消息处理也有各自失败点，组合操作不能只用一个 UI “成功”掩盖中间状态。

### 3.4 对我们的参考应落在什么地方

本项目已有 before / after 修改记录和真实差异展示，不能重新当成待建功能。ChangeLedger 提供的增量是用户可选择的工作区恢复点、恢复前救援点、操作中断记录和明确的部分失败状态。

如果后续需要撤销一轮，首先明确“只撤销这轮已记录修改”还是“把整个工作区变成旧快照”。多会话共用原目录时，后者可能包含别人的成果；不能因为插件做了检查点就默认可无损撤销。其确认短语和模型回传 hash 也不应照搬到我们普通文件编辑流程，已有约定要求宿主自己保留基线并处理冲突。

## 4. 三者共同揭示的产品方向

Sidebar 把执行资源带到会话旁边，GenUI 让成果可交互，ChangeLedger 让文件修改可回看和恢复。它们共同提高的是用户对任务过程的可见性和控制力，而非替换基础模型。

演化中最值得参考的具体分界是：资源属于哪个 session、显示状态是否已成为持久事实、插件卸载后哪些工作还在运行，以及恢复失败时如何准确说明留下了什么。我们应先围绕现有 Task / Session / Run 和修改记录完善这些关联，再按实际需求增加复杂工作台或插件扩展点。
