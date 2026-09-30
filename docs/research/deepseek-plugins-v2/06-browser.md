# 浏览器能力如何成为可维护的工具：BrowserSkill 与 dsh-browser

> 截止 2026-09-23。主样本 Tencent BrowserSkill 固定在 `34a07f3c3160b89ce76635d79a810e34b3b25b67`，DSH 包和扩展 package 均为 `0.3.0`。比较样本 Lum1104/dsh-browser 固定在 `36fd3ad2d22b814d462b158541c843e6df0bb1cd`。本轮精读 DSH 适配、会话 / 取消及部分扩展实现；Rust CLI / daemon 内部依据架构契约，未完整审计，未实际操控浏览器。

## 1. 为什么主线选 BrowserSkill

浏览器能力让 coding agent 能查资料、检查自己实现的网页、处理需要登录的网站以及交付用户可见的页面操作。难点不止在 click 或 screenshot：同一浏览器可能同时有用户、几个 Agent、多个任务和自动截图，必须知道谁拥有哪一页，以及取消后是否还有操作在执行。

BrowserSkill 本轮为 6,728 Star / 492 Fork，dsh-browser 为 718 / 52。前者不仅提供一个工具接口，还形成 CLI、daemon、Chromium 扩展、Skill、DSH 工具和观察界面的完整产品链，且有具体 Windows 使用报告，适合优先深入。后者保留为有价值的另一种路线：让已有 DSH Host 直接桥接浏览器，并维护页面与会话之间的连续关系。不能仅凭 Star 判断两者操作成功率。

## 2. 安装与启动：哪些进程承担哪些职责

BrowserSkill 仓库的运行边界如下：

| 目录 | 职责 | 为什么单独存在 |
| --- | --- | --- |
| `crates/bsk-cli` | CLI、IPC 客户端与 daemon | 不要求每个宿主自行实现浏览器协议 |
| `crates/bsk-protocol` | Rust 协议类型与 schema | 约束跨进程消息形状 |
| `apps/extension` | 后台连接、工具分发、页面操作、Agent Window | 真正掌握浏览器标签、节点和窗口状态 |
| `packages/dsh-plugin-browserskill` | DSH Skill / 工具、启动记录、调用、取消、观察 | 把浏览器执行适配到 Agent 和会话生命周期 |
| `packages/vom` 等 | 可视观察相关类型与渲染支撑 | 复用页面表示和界面能力 |

默认本机链路是 DSH 工具 → `bsk ... --json` 子进程 → 本机 daemon → WebSocket → 浏览器扩展 → CDP / WebExtension 操作。Unix 的 CLI IPC 使用 socket，Windows 使用 named pipe；远程模式则把 CLI / daemon 放到服务端，扩展经认证 WSS 连接。这里不是让浏览器扩展直接执行用户机器上的任意 shell。[架构契约](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/docs/architecture.md)

这种结构的成本是组件版本与进程状态更多。CLI 已安装、daemon 已启动、扩展已连接、Skill 已被宿主发现是不同状态；官方 README 也单独提醒 doctor 成功不保证 Skill 已安装。对 Windows 桌面产品，这种分层诊断比一个笼统“浏览器不可用”更能让用户找到解决入口。

## 3. 会话进入：先暴露能力说明，再加载工具 schema

DSH 插件入口创建 runner、会话注册表、按 key 串行队列、观察服务及磁盘启动日志。默认 `lazyTools` 开启，先提供 Skill 目录与可按需读取的正文；成功调用 `browser-skill` 后才注册完整工具集，下一步请求装配便能看到新 schema。它也扫描恢复会话中的持久事件，配对 Skill 的 tool call / result，或识别用户主动调用 Skill 的消息，避免重启后丢失“已经使用过这项能力”的事实。[装配入口](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/index.ts)、[延迟工具注册](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/lazy-tools.ts)

需要注意作用域：已检查实现中的 reveal 会使工具集在该插件进程寿命内可用，不应描述成每个会话都维护一份严格隔离的可见 schema 集合。插件还以可选注入方式使用 webserver 提供观察界面，不把 UI 服务变成 headless 工具运行的强依赖。

我们已有按需 MCP schema 和 Skill 目录，增量启发在于恢复后的可见性有明确依据，以及可选观察界面不阻塞工具。不能再次把“渐进披露”列为本项目从未实现的新能力。

## 4. 创建浏览器：先记住请求，再等待结果

普通实现容易在 CLI 返回 `session_id` 后才登记会话。如果浏览器已经创建，但进程超时、宿主退出或返回消息丢失，就出现一个没有所有者记录的浏览器实例。

BrowserSkill 用 `SessionStarts` 管理这段空隙。开始前生成带时间信息的 request ID，记录发起会话及祖先拥有者，保存 journal，再向 CLI 发送 prepare。只有准备成功且没有并发取消，才继续；得到浏览器 session 与 instance ID 后先更新日志，再纳入注册表，随后 claim 并转为 active。尚未返回 session ID 的启动也占容量，两个并发调用不能都以为还有最后一个空位。[启动状态机](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/session-starts.ts)

`DiskStartJournal` 为每个进程实例建立独立 owner 目录。恢复时检查旧 owner 是否仍活跃，通过 rename 领取失去宿主的日志，再读取其待处理请求。它避免新宿主直接覆盖仍在运行的插件账本；PID 复用保守处理，不能声称单靠 PID 就能完美判断原实例。该日志是资源生命周期记录，并不是对所有网页操作的事务日志。[磁盘启动日志](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/start-journal.ts)

对本项目最可迁移的思想是：“尚不知道结果”也需要有任务身份和后续查询 / 清理入口。将来若启动浏览器、远端 worker 或其他长寿命资源，应关联已有 project / session / run，而不是仅记录一个 PID，或在超时后直接重放可能已经成功的操作。

## 5. 执行操作：拥有者、页面与节点引用分别管理

DSH `SessionRegistry` 只登记由该插件创建的浏览器会话。列表、显式 session 参数和清理都以这份注册表为范围，不能顺手清理同一 daemon 上其他终端或 Agent 的资源。省略 session 时使用插件的当前指针，多浏览器并行任务最好明确传递身份，不能把“当前”理解为某个模型永远私有的浏览器。[注册表](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/sessions.ts)

扩展侧 `SessionContext` 则进一步管理 Agent Window、借用的用户页面、Agent 创建的页面、观察到的页面和 ref store。页面出现在同一个窗口，并不总能自动推导为受 Agent 控制，远程模式尤其区分显式创建或借用。节点引用如 `@e1` 属于会话最近一次观察；`RefStore.replace()` 为新快照整体替换映射并增加内部 generation，页面文档变化也会使节点引用失效。因此引用是一次观察的定位结果，不能当作跨导航持久身份。[页面所有权](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/apps/extension/src/session-manager/manager.ts)、[节点引用](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/apps/extension/src/session-manager/ref-store.ts)

每个浏览器会话的业务工具与观察截图共同进入 `KeyedExecutor`。不同会话可并行，同一会话按序运行。队列尾部等待前一个任务和当前任务都结束：如果等待中的任务被取消，后续调用仍不能越过尚未结束的前一个调用。这是在异步代码中容易漏掉、又会真实造成重叠点击的边界。[串行队列](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/queue.ts)

## 6. 显示进展：观察流不要改变业务事实

`ObservationService` 为已拥有的会话维护当前动作、页面 URL 和缩略图，图片仅保留进程内两帧环形缓存。截图通过 runner 和同一会话队列执行，但不经过模型工具调用的业务埋点，不改当前会话指针，也不把每次缩略图刷新写成一次模型动作。排队后还会再次确认是否仍有观察者、是否已出现更重要的前台工作。[观察服务](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/observation.ts)

这为多会话界面提供了直接参考：用户要知道 Agent 在做什么，但旁观面板不应无意消耗业务额度、污染 Trace 或改变任务选择。观察流可以暂时不可用，真正的工具结果和运行状态仍由执行链负责。我们后续若做页面预览或 worker 实时缩略图，也应保留这种职责划分。

## 7. 取消与退出：不能只杀掉调用协程

runner 为子进程设置超时与取消处理。Windows 下 Node 的 SIGINT 会直接结束子进程，因此此实现优先关闭 stdin，让支持该约定的 CLI 发取消 RPC 并等待浏览器整理状态；超过宽限期才强制结束。正常 `exit` 后，输出收集另有有限等待，因为 daemon 可能继承管道句柄，使 `close` 很久不触发。执行期限、清理期限、输出收尾期限在这里是三个不同概念。[runner](https://github.com/Tencent/BrowserSkill/blob/34a07f3c3160b89ce76635d79a810e34b3b25b67/packages/dsh-plugin-browserskill/src/runner.ts)

停止浏览器也有持久意图。接受 stop 后先保存 cleanup / stop 状态；调用者取消等待，不等于撤销已经接受的资源清理。多个待确认停止结果存在时，要求指定对应 session 或 request ID，避免错误清除另一个请求的回执。归档会话时按拥有者关系清理，插件卸载只处理自己的资源。

上游另有对特定 `session_busy` 整理窗口延迟 100ms 后重试一次的机制。这不能泛化为“所有错误自动重试”，也不能照搬成本项目既定的故障处理规则。我们需要学习的是识别执行、清理、结果确认各自的状态，而非自动增加重试。

## 8. 与 dsh-browser 的对照：独立运行时和宿主桥接

dsh-browser 的 `packages/browser/bridge-browser` 直接在 DSH Host 上挂 WebSocket upgrade 路由，首帧 hello 携带自己的 token，桥接浏览器工具与扩展；扩展侧负责后台连接和页面执行。因为该路由在一般 API 边界之外，不能认为“同一 Host 已有 API 认证”就自动覆盖它。[桥接入口](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/packages/browser/bridge-browser/src/index.ts)

其 `PageSessionContextTracker` 用 live tab、window、origin 和 path 匹配历史会话，并移除了旧的全局最近会话方式。浏览器标签替换时迁移映射，导航到不匹配的页面不自动沿用原对话。这里刻意没有把 query / fragment 纳入 URL key，适合哪些站点要按页面语义判断，不能称作完整网页内容身份。[页面连续性](https://github.com/Lum1104/dsh-browser/blob/36fd3ad2d22b814d462b158541c843e6df0bb1cd/extensions/dsh-browser/src/background/session-continuity.ts)

| 比较项 | BrowserSkill | dsh-browser |
| --- | --- | --- |
| 运行组织 | CLI / daemon 可服务不同 Agent，DSH 是一种适配 | 更紧密依赖 DSH Host 的连接与会话能力 |
| 重点资源 | 创建请求、浏览器 session、Agent Window、页面与节点 | Host 会话、桥接连接、受控页面与页面续接 |
| 用户吸引力 | 可见浏览执行、多宿主复用、完整安装与诊断入口 | 在浏览器与 DSH 对话之间保持工作连续性 |
| 维护成本 | 多组件版本、后台进程、Windows 更新 / 清理 | Host 协议升级、扩展连接恢复和会话归属 |
| 本项目借鉴 | 启动账本、取消收尾、观察与业务分离 | 页面与任务显式绑定，避免全局最近对象误配 |

## 9. 真实使用证据与演化方向

BrowserSkill #305 报告 Windows 上正在运行旧 CLI，而新版一直处于 staged；自动启动的 daemon 重新占用可执行文件，另一个目录又存在旧副本，导致下载、替换和实际执行版本不一致。该报告涉及旧版本到新版本的升级过程，不能写成本文固定 `0.3.0` 已由我们复现的缺陷；报告目前也不能单独证明所有 Windows 用户受影响。[用户报告 #305](https://github.com/Tencent/BrowserSkill/issues/305)

从当前机制可以看出，它已从“能操作浏览器”向“多个宿主长期共用、可以取消和恢复、用户能看到”的产品推进。带来源的版本状态、资源拥有者、启动未决状态和输出收尾，是工业可用性的重要组成部分；实际企业部署规模及稳定性数据，本轮没有取得。

BrowserSkill 文档中的 browser sandbox 主要描述页面、窗口和操作范围；现有浏览器 profile、登录态及本机进程仍有各自的权限。不能把 Agent Window 或标签归属称为 Windows 文件系统 / 网络隔离。对我们目前优先的 coding 流程，先吸收这些生命周期设计，比直接引入整个浏览器运行时更有确定价值；是否新增浏览器能力，仍应由具体网页开发与验收需求决定。
