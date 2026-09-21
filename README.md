# My Coding Agent

Windows 优先的个人 coding agent，使用独立 Python 核心与 Electron / React 桌面。已支持 OpenCode Go 对话、项目 → 任务 → 会话、文件与程序工具、Goal / HITL、联网、handoff / Review。M3 接入上下文压缩、本地记忆、协作邮箱与可选子 agent；当前实现与验证范围见 [M3 记录](docs/progress/m3.md)。

有意义的工作结果可以由 Agent 提交报告，任务概览展示工作项、依赖和来源会话；用户维护的目标与共同信息单独保留。报告先随运行事实保存，再幂等同步任务。同步失败时显示“共同进度待同步”，下次明确发送前只补同步已有结果，不重做文件或程序。Goal 连续运行、HITL 和插话已接通；报告仅需 summary / outcome，引用与工作图按需填写，不作为执行门槛。最新规则见 [DSH 运行校验对照](docs/plan/runtime-checks-dsh-review.md)。

开发前阅读 [AGENTS.md](AGENTS.md) 与 [进度总览](docs/progress/README.md)。工程基线见 [M0 方案](docs/plan/m0-implementation-plan.md) 和 [M0 进度](docs/progress/m0.md)；当前功能与验证见 [M1 方案](docs/plan/m1-implementation-plan.md) 与 [M1 进度](docs/progress/m1.md)。

## 安装与启动

本机依赖已安装后，日常启动直接在资源管理器中双击仓库根目录的 [StartAgent.cmd](StartAgent.cmd)。脚本自动定位项目并运行开发入口；可给它创建桌面快捷方式，快捷方式的“起始位置”不影响项目定位。旁边的控制台可以最小化，退出时关闭应用窗口即可；启动失败会保留提示。

双击入口默认使用 `E:\MyCodingAgentData\dev`，项目选择器默认打开 `E:\claude_code\my-coding-agent-test`。可以通过下文的本机路径文件或环境变量覆盖；脚本不会自动安装依赖。

在仓库根目录的 PowerShell 中执行。使用 Node.js **24.16.0**、uv **0.11.32** 和常规 CPython **3.13.14**。Python 使用仓库 `.venv`，不使用全局 Anaconda。准确版本分别保存在 `.node-version`、`.python-version` 和依赖锁文件中。Git 用于仓库开发；只读 Agent 不要求项目已有 Git 提交。搜索优先使用 PATH 中的 ripgrep，缺失时使用同策略的 Python 搜索，不阻止启动。

```powershell
uv python install
uv sync --locked
npm.cmd --prefix apps/desktop ci
npm.cmd --prefix apps/desktop run install:electron
npm.cmd --prefix apps/desktop run dev
```

每条命令成功后再执行下一条。Electron 44 的 npm 包需要显式运行 `install:electron` 下载平台运行文件；只安装 JavaScript 依赖不足以启动窗口。

开发窗口与构建预览默认使用 `E:\MyCodingAgentData\dev`。首次使用时先创建项目选择器的起始文件夹，或把它配置为已有目录；选择确认前不会自动登记项目。

```powershell
# 显式使用另一个独立数据根
npm.cmd --prefix apps/desktop run dev -- --data-dir E:\MyCodingAgentData\dev-other

# 预览已构建资源，仍使用开发数据根
npm.cmd --prefix apps/desktop run build
npm.cmd --prefix apps/desktop run preview
```

本机若无法连接 Electron 的 GitHub 下载地址，可仅在当前 PowerShell 进程配置以下镜像后重试安装；安装器仍使用 Electron npm 包附带的官方校验和验证下载。不要关闭 TLS 校验或修改系统代理。

```powershell
$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
$env:ELECTRON_CUSTOM_DIR = '{{ version }}'
$env:electron_config_cache = Join-Path (Get-Location).Path '.cache\electron'
npm.cmd --prefix apps/desktop run install:electron
```

## 项目目录与应用数据

项目目录是用户选择的代码位置。打开项目仅登记身份与路径，不修改项目文件，不初始化 Git。重复选择同一真实目录会复用身份；取消、无效路径或保存失败不会切换当前项目。失效项目保留记录并显示“目录不可用”。

应用数据根独立于项目。Python CLI 和直接 Electron 入口按 `--data-dir` → `MY_AGENT_DATA_DIR` → `E:\MyCodingAgentData` 选择；开发 / 预览启动器另外支持下文的本机文件，无覆盖值时采用独立的 `E:\MyCodingAgentData\dev`。磁盘不可用或路径不可写时报告错误，不回退到 C 盘。项目目录与数据根不得相等或互相包含，junction / 符号链接按实际路径检查。

```text
<data-dir>/
├── config.toml       # 模型、运行预算和连接偏好，不含密钥
├── storage.json      # 数据版本、初始化时间
├── projects.json     # 项目身份、路径、最近记录和当前选择
├── .runtime.lock     # Python 业务数据单写者锁
├── sessions/         # 每会话一个目录，其 events.jsonl 保存版本化事实
├── tasks/            # 任务共享信息、工作依赖和来源的版本化事实
├── environments.json # 已有环境登记、项目默认绑定和执行偏好
├── programs/         # 命令 / 服务历史及有界输出，不作为重启程序的授权
├── changes/          # 按会话保存写入基线、预期内容、来源与实际结果
├── electron/         # Electron 用户状态
├── cache/electron/   # Chromium 缓存
└── logs/             # 只记录固定错误码的应用日志
```

Python 使用同目录临时文件、flush / fsync 与原子替换保存单个文件。损坏或较新版本的记录会保留并报错；这不构成跨文件事务。桌面运行期间，同一数据根的第二个写入实例会被拒绝，不能通过删除锁文件抢占。

最近项目与当前选择按数据根分别持久化。使用同一个数据根重启会恢复记录；自动化验收窗口在 `.artifacts/tests/` 下使用独立数据根，其项目列表不会自动合并到双击入口的开发数据中。首次双击看不到之前验收选过的项目时，先核对两次窗口显示的数据保存位置；配置的 `project_dir` 只设置选择器起始位置，不自动加入最近项目。

## 本机目录配置与仓库可移植性

仓库可以 clone 到其他位置，不要求位于 `E:\claude_code\my-coding-agent`。源码、Python 环境和桌面资源根据启动文件 / 应用位置定位，不依赖终端当前目录。运行时把路径规范化为绝对路径是为了明确访问目标；需要避免的是在源码中写死本机的仓库位置。

| 路径类别 | 定位方式 | Git 中保存什么 |
| --- | --- | --- |
| 仓库源码、脚本、构建资源 | 按入口位置动态定位 | 源码与相对引用 |
| 应用数据根 | 启动参数、环境变量、本机路径文件、集中默认值 | 默认值与配置示例；个人数据不入库 |
| 项目选择器起始位置 | 环境变量、本机路径文件、集中默认值 | 默认值与配置示例 |
| 已打开项目的位置 | Python 校验后保存真实绝对路径 | 仅在数据根的 `projects.json` 中，不入库 |

双击 `StartAgent.cmd`、`npm run dev` 和 `npm run preview` 共用 [路径解析入口](scripts/launch-config.mjs)。首次 clone 后，复制根目录的 [agent.paths.example.json](agent.paths.example.json) 为 `agent.paths.local.json`，按本机磁盘修改；已有本机文件则直接编辑，不覆盖。后者已被 `.gitignore` 排除，不会随 GitHub 提交或更新。

```json
{
  "data_dir": "E:/MyCodingAgentData/dev",
  "project_dir": "E:/claude_code/my-coding-agent-test"
}
```

`data_dir` 是本次启动的完整数据根，不会额外追加 `dev`；`project_dir` 只控制选择器从哪里打开，不自动打开或迁移项目。文件的两个字段均可省略，未设置时使用集中默认值；只支持这两个字段，格式错误、未知字段和空路径会明确报错，不覆盖配置。文件限 UTF-8 JSON、16 KiB，不放密钥。

文件中的路径可以是完整绝对路径，也可以是相对于 **该文件所在目录** 的路径。例如 `"project_dir": "../my-coding-agent-test"` 指向仓库旁的测试目录；`"data_dir": "../my-coding-agent-data/dev"` 指向仓库外的独立数据。不会展开 `~`、`%VAR%` 或 `$VAR`。相对路径会跟随文件移动；需要始终复用原有数据时使用绝对路径。

| 开发 / 预览配置 | 优先级，从高到低 |
| --- | --- |
| 数据目录 | `--data-dir` → `MY_AGENT_DATA_DIR` → 本机文件 `data_dir` → `E:\MyCodingAgentData\dev` |
| 选择器起始目录 | `MY_AGENT_PROJECT_DIR` → 本机文件 `project_dir` → `E:\claude_code\my-coding-agent-test` |

CLI 参数和环境变量必须使用完整绝对路径；Windows 的 `E:folder`、`\folder` 不算完整绝对路径。项目选择器起始目录不存在时，会提示先创建或修改配置，不回退到系统下载目录。修改文件后重新启动应用生效。

```powershell
# 当前终端临时覆盖；数据根与项目目录需彼此独立
$env:MY_AGENT_DATA_DIR = 'E:\MyCodingAgentData\dev-other'
$env:MY_AGENT_PROJECT_DIR = 'E:\claude_code\my-coding-agent-test'
npm.cmd --prefix apps/desktop run dev
```

本机 JSON 属于源码桌面启动器配置；独立 Python CLI 不自动读取仓库文件，使用同一个 `MY_AGENT_DATA_DIR` 或显式 `--data-dir` 指向相同数据根。模型选项仍保存在数据根内的 `config.toml`，数据根自身由启动输入决定。

移动和迁移时分别处理：

- **重新 clone / 换电脑**：按安装说明重新安装依赖，并创建自己的本机路径文件；`.venv`、`node_modules` 和构建产物不能当作可直接搬运的安装包。本阶段实际支持 Windows 开发运行，跨平台和桌面安装包不属于已验收能力。
- **只移动仓库源码**：资源定位会适配新位置；依赖需在新位置重建。数据路径保持原绝对位置时可继续读取原记录，Git clone 本身不会下载个人记录。
- **更换数据盘 / 移动项目**：修改配置只切换位置，不自动搬迁数据。保留原数据，关闭应用后备份并复制需要保留的数据根，再指向新位置；项目自身若也移动，旧绝对路径会显示不可用，需要重新选择，M0 尚无自动迁移或历史重新关联界面。

## CLI 与模型配置

桌面左侧的 **设置与诊断** 已接入以下能力：

| 功能 | 使用方式与生效范围 |
| --- | --- |
| 默认模型 | 在两个约定模型中选择并保存；Python 写入当前数据根的 `config.toml`，当前页面和后续启动都使用新选择 |
| 公开配置 | 查看服务地址、模型、配置文件位置及凭据来源；“刷新配置”重新读取后端，不展示密钥 |
| 启动目录 | 输入完整路径或打开系统选择器，保存到仓库的 `agent.paths.local.json`；下次通过双击 / dev / preview 启动生效，参数与环境变量优先级不变 |
| 环境诊断 | 默认只检查本机；按需勾选开发工具、网络连通性或写入探测，结果列出状态、原因、修正提示和详情 |
| 模型连接池 | GLM / DeepSeek 独立列出模型名、测试结果、首字耗时与测试时间，各自按钮实际请求对应模型；集中管理共享池的复用开关、超时和释放 |
| JSON 导出 | 用系统保存对话框导出公开配置、项目列表或本次诊断报告；包含目录信息，不包含密钥，禁止覆盖应用记录 |

修改启动目录不会搬迁历史数据或立即改变当前项目。数据目录可指定可用磁盘上尚未创建的位置；项目选择器起始目录须已存在，两者不能相同或互相包含。设置页保存完整绝对路径；需要随仓库搬动的相对路径仍可按上面的文件格式手动配置。已有本机文件损坏时会保留并提示修正。

诊断期间设置页显示等待状态，本机诊断的传输等待为 60 秒；勾选网络时额外保留已保存的连接测试等待时间，模型任务和全局停止入口使用独立通道。配置损坏或数据根被占用时仍可查看诊断；修正文件或关闭占用实例后重新启动。诊断本身不调用模型，报告中的认证 / 工具回合仍为未检查；实际会话的结果单独显示。

“模型连接池”的复用开关默认开启，关闭后仍能聊天，但每次请求结束会关闭所属客户端；偏好保存在当前数据根 `config.toml` 的 `[http]` 表中，旧配置缺少该表时使用集中默认值。手动测试等待默认 20 秒，可在页面调整并保存；环境诊断的网络选项也采用已保存值。查看 / 刷新状态及开启开关不联网，不发送心跳。切换开关或“释放已有连接”不会打断当前回答，旧客户端等活动请求结束后关闭，新请求按最新策略建立连接。

“测试 GLM”与“测试 DeepSeek”分别向对应模型发送一条固定短消息，使用现有凭据和生产客户端，会消耗模型额度；不发送项目内容或会话历史，不创建会话、不执行工具、不重试或更换模型。每个模型独立保留成功 / 失败、首个正文时间、分段耗时与测试时间；等待期间读取本地进度。测试使用页面当前填写的超时，保存后下次启动仍保留。两个模型共用一个 HTTP 池，列表表示模型测试结果，不表示两个独立物理连接或持续在线。

折叠项“网关目录探测与最近请求”及环境诊断的网络选项仍通过当前池请求 Go 的 `/models`，不发送 API key 或生成请求；这只能探测目录，不能证明某个模型可用。最近模型请求附带具体模型名称，最近测试结果只保留在当前后端内存中、重启清空，已保存开关仍保留。所有探测沿用当前网络环境，不修改 VPN / 系统网络；单独运行的 CLI 不管理桌面进程的池。

以下命令默认离线；`config show`、`projects list` 与普通 `doctor` 不初始化应用记录。

```powershell
uv run --locked my-agent --help
uv run --locked my-agent --version
uv run --locked my-agent --data-dir E:\MyCodingAgentData\dev config show --json
uv run --locked my-agent --data-dir E:\MyCodingAgentData\dev doctor --dev --json
uv run --locked my-agent --data-dir E:\MyCodingAgentData\dev projects list --json

# 关闭使用相同数据根的桌面窗口后，CLI 才能登记项目
uv run --locked my-agent --data-dir E:\MyCodingAgentData\dev projects open --root E:\claude_code\my-coding-agent-test --json
```

默认服务为 OpenCode Go，地址 `https://opencode.ai/zen/go/v1`；初始模型为 `glm-5.3-flash`，另一选项为 `deepseek-v4.1-flash`。优先通过桌面保存默认模型；也可关闭应用后在数据根的 `config.toml` 中调整 `[model]` 下的 `model_id`。CLI 可用全局 `--model` 临时覆盖，不写回配置。

若手动配置 `allowed_models`，须完整包含上述两个不同模型，允许调整显示顺序；初始选中项仍由 `model_id` 决定。缺项、重复和其他模型仍会报错。

凭据只引用 `OPENCODE_API_KEY`：优先读取当前进程的非空值，Windows 上缺失时再读取当前用户同名变量。密钥不复制到配置、日志或 renderer；桌面通过专用启动帧传给 Python，并从后端子进程的继承环境中移除。打开应用、项目或历史不调用模型；只有明确发送问题才发起请求，凭据存在不等于认证已通过。

`doctor --network` 显式执行一次不携带凭据的模型目录 GET；`--write-probe` 显式创建并清理独立探测文件。报告区分凭据存在、目录可达、认证和工具回合；后两项保持 `not_checked`。Docker 不可用会显示警告，不阻塞只读 Agent。

## 使用任务、对话与代码执行

双击 `StartAgent.cmd`，选择项目后点击“新建任务”，填写阶段目标并创建任务与首会话。在任务概览点击“打开 / 补齐首会话”，即可发送问题，例如：“找到启动入口，解释配置如何加载，并标出文件和行号。”项目、任务和会话都在左侧展开；概览中的“创建新的工作会话”可选择模型、角色与工作范围。

任务共享目标、约束、进度、结论、未决事项和成果入口由你在概览维护，新会话及下一次模型请求自动带入已保存版本，不额外调用摘要模型。旧会话位于“未归属会话”，从输入框内的“··· → 归属与分工”可归入同项目任务；归属调整保留原会话 ID、模型选择和历史。创建 / 切换任务不会自动调用模型、初始化 Git 或生成项目文件。工作报告已同步至任务概览，保留来源且不覆盖用户目标。

在输入框内的“··· → 会话协作”中，选择同任务已有会话，写一句分工并选择只读 / 可执行范围，保存后即可按需读取历史或发送职责内请求。读取不调用模型，发送会使用接收会话的模型及运行预算；卡片显示排队、执行、结果及实际 Run 来源。接收方忙时排队，暂停、失败、等待用户输入的 Goal 保持状态。请求结果不会自动恢复发起方；重启后未开始请求需明确继续。可独立停止某项请求，正式会话始终由用户创建。

角色范围内允许双向请求；只有实际互相等待时，后进入等待的工具才返回当前状态与原因，已投递请求保留。Goal 等待协作时可先回答普通插话，再继续原目标。长结果和历史按偏移继续读回。M3 被动等待不计入活跃时间，不消耗轮询模型请求；普通邮箱消息不会自行启动空闲会话，执行工作使用协作请求。

会话输入区附近提供按需打开、可关闭的入口：

- **上下文**：用 token / K / M 显示最近输入用量与模型窗口；查看上次实际发送的材料来源和固定预览，区分下次组装规则。可压缩当前会话、查看摘要，参数与字节预算在高级详情。摘要通过同一 Go 模型生成，活动 Run 的摘要计入原预算。
- **查找历史**：查询区、结果列表、单条原文都能自由展开 / 收起；续读不替换其他结果。关闭保留关键词、结果和分页，后台更新不重开。历史和记忆可加入这次提问，以可移除标签显示，发送后作为带来源的参考输入保存；仅查看不会发送。
- **记忆**：独立搜索、添加、修改、优先召回、停用或忘记项目 / 用户条目。“上次带入”是最近请求实际使用的条数，不是总库存。常用开关是自动带入和空闲提取，高级设置保留主动保存、维护参数和实验。可直接说“记住这个项目用 uv”，也可手动保存；临时进度与任务决定仍分别归报告和已确认结论。
- **子 agent**：默认关闭。开启后 Agent 按实际收益拆分有明确目标 / 范围的内部子任务，可选独立 / 继承上下文；卡片显示运行状态、结果、用量及停止 / 补充入口，不新增左侧用户会话。请求、工具与活跃时间共用父安排预算；停止父任务会清理所属子工作。

记忆与摘要存在应用数据根，重启不重新调用模型。纠正 / 遗忘从下一请求生效，不清除原聊天或强制重建摘要。项目移动后可在项目列表重新定位，保留身份和记忆。M3 协议为 v4，桌面与 Python 后端需使用同一源码版本；M2 原始会话继续可读。

同一卡片的“工作安排”可选择“交接工作”或“独立 Code Review”。选择已有接收会话并填写目标即可发起，无需再保存一次协作约定。应用带入任务事实、来源 Goal / Run 和历史改动，接收方可按需读来源会话及差异。交接默认移交当前 Goal / 运行的推进责任，等待指定工作停止后再接手；取消勾选可只传递成果，保留原工作。独立 Review 使用只读工具，报告可定位发现，不自动修改。来源简报保留在卡片中，后续调整直接向接收会话发送新要求。

- 新会话默认“常规 · 对话与执行”，根据本次请求读取或编辑代码；既有只读会话默认保持 Plan，可显式切换。“Plan · 讨论与规划”默认只读，在“允许保存的计划文档”填写相对路径后，仅允许保存该文件；不会因口头认可方案自动开启代码写入。
- 工具支持 `list_files`、`read_file`、`search`，常规模式还支持 `create_file` 和 `edit_file`。新建不覆盖已有文件；编辑只需路径、原文和新文，保留其他位置的改动、UTF-8 / BOM 与换行。准备后若文件又被修改，本次不覆盖，模型可重新读取后调整，同一个 Goal 继续推进。文件工具不要求或返回 hash。直接写入原项目，Git 可选。
- `web_search` 使用现有 OpenCode Go key 调用 DeepSeek 原生搜索，`web_fetch` 直接读取公开网页；Plan / 常规 / Goal 均可按需使用，主会话模型不变，无需另配搜索 key。可直接要求“搜索 Python 官方 JSON 文档，读取原文并附上来源”。可折叠卡片显示搜索模型、查询、实际来源 / 用量，或网页正文、时间与截断位置；点击来源在系统浏览器打开。搜索辅助请求计入本次运行 / Goal 预算，网页读取不携带模型凭据；需要登录或 JavaScript 的页面暂不支持。
- 点击输入框内的“··· → 查看修改成果”，可查看准备 / 成功 / 失败状态、来源、文件版本及分页 diff。历史两端快照保存在数据根，不能把它当当前磁盘内容；读取 diff 不再核验 hash，个别记录不可读只影响该条历史，不终止当前任务。“结果尚未确认”须核对实际文件，不自动重放或回滚。模型文本与 diff 按纯文本展示。
- 独立会话可以同时运行，单个会话仍只有一个执行入口；Goal 中的普通插话会排队处理。左侧会话树显示各自状态，点击会话后可在输入区停止当前运行；主对话顶部不另设会话入口。停止一项不影响其他会话。“正在停止”表示正在清理资源，切换视图或重载窗口不会自动重发问题。
- 输入区上方的一行状态显示实际连接、等待响应、思考和正文阶段，展开“详情”查看完整收包、用量和首字信息。“本次请求首字”从 Python 模型调用入口计到首个非空正文，思考状态不算首字，也不包含点击、存储和界面渲染时间。工具续答会开始下一次请求并重新计时；历史保留最近请求的耗时，旧会话没有指标时不补造。
- 模型返回的思考文本逐段显示在回答的“思考”区，默认展开，可手动折叠；折叠后仍接收内容，回答完成时保留当前折叠选择。已完成的新记录保存思考文本，重启后可查看；旧记录不补造，未完成流不承诺在退出后恢复。
- 会话固定项目；输入框内可随时在 GLM / DeepSeek 中选择后续请求模型，保存后重启仍保留。已经发出的请求保持原模型，下一次请求（包括工具续答或 Goal 续跑）采用新选择，不另建会话；消息标注实际使用的模型。设置中的默认模型仍只影响新会话。完整历史允许追问和显式重试；中断后直接发送新消息或接续 Goal，后端核对已开始工具的现状并保存观察，无须单独恢复确认、不重放旧副作用。损坏记录保留可读内容并报告具体原因。
- Goal 位于输入框上方，默认折叠为状态和目标；展开后查看进度、预算、暂停 / 接续等控制，需要答复的问题出现时自动展开。选择 Goal 模式后，“Goal 完成条件与预算（可选）”可展开填写，不长期挤占对话区。完整 trace 与工具摘要合并尚未实现，设计见 [主界面与运行轨迹](docs/plan/main-interface-and-trace.md)。
- 历史保存在当前应用数据根下，重启后从左侧会话树打开，更早记录支持分页。原生模型续接字段仅在 Python 内保存。重启不自动执行工具或恢复 Goal；当前不提供数据迁移。
- “设置与诊断 → 高级运行预算与读取规则”可调整请求、工具、时间、上下文 / 输出 / 文件容量与扫描范围。初值为 25 请求、60 工具、10 分钟，每次运行取独立快照。上下文主显示使用服务报告的 token；请求处理和自动压缩仍用独立可调字节预算，未返回用量与费用显示未知。
- 默认全项目发现遵守嵌套 `.gitignore` 并跳过 Git 元数据、依赖和构建目录；明确文件 / 子目录访问不受忽略或文件名限制。读取可使用明确的项目外路径，写工具仍作用于项目内真实路径。目前支持可靠 UTF-8 文本。参数遗漏、原文匹配问题和写入前的文件变化反馈给模型调整；实际网络、执行或保存故障会停止并保留结果。

选定项目后默认使用本机工具，不必先导入环境、进入设置或勾选信任。需要特定解释器时，在“设置与诊断 → 项目执行环境”导入已有 Python / venv、Conda prefix / launcher 或 uv + 已有解释器。环境路径可以保存为项目相对路径，管理器入口使用本机绝对路径；这些引用只写入应用数据，不进入 Git。导入不安装依赖，“检查此环境”按需单独运行已选入口的版本检查。

常规模式可直接调用 `run_command`、`start_service`、`read_program`、`stop_program`；环境绑定只用于按需选择解释器或工具环境。本机直接执行**未隔离**，程序具有当前 Windows 账户的访问能力；沙箱、Docker / WSL 管理尚未提供。显式绑定的环境失效只阻止执行，不阻止讨论或文件编辑，也不会自动换解释器。启动继承普通工具环境变量并筛除凭据及应用内部变量；环境修改作用于下一次启动。Python 别名使用所选解释器；`.cmd` / `.bat`、管道与重定向使用显式 PowerShell。

最小体验可从真正空目录开始：“创建一个单页计数器，按钮加一，localStorage 保存数字，刷新仍保留；只需要 index.html 和简短 README。用已选 Python 的 http.server 启动预览，不安装依赖。”先用 Plan 简述方案，再用 Goal 实现；打开预览点击并刷新。之后新建接手会话只改标题，再主动发起独立 Review。工具 / 条件性行为的覆盖安排见 [简单计数器场景](docs/plan/next-stage-implementation-plan.md#81-空目录主场景)，不用添加复杂业务。

Agent 的文件修改和程序均有实际记录。会话中及“项目工作台”可展开运行卡片，查看命令、环境、输出、退出码、地址并停止程序。命令 cwd 可以是项目内的相对或绝对路径，按解析后的真实目录检查归属。HTTP 已响应不等于业务验收通过；普通命令非零退出保留为结果，不自动变成修复授权。

已交付服务在回复结束、切换会话或停止 Agent 后保留，真正退出应用时停止；再次启动恢复历史与环境绑定，不自动重跑。程序执行时限、就绪等待、清理宽限、环境探测时限与输出容量可在同一区域的“程序执行预算”调整，影响后续启动。CLI 复用同一数据根的环境绑定；CLI 进程结束也会清理其自有服务，不作为后台守护入口。

CLI 的 `ask` 使用同一运行服务和工具，以下命令会调用模型。使用与桌面相同的数据根前须关闭桌面，或显式选择独立数据根；项目参数必须是完整绝对路径。

```powershell
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "解释项目启动流程" --project E:\claude_code\my-coding-agent-test

# Plan 默认只读；显式指定唯一允许保存的文档
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "讨论实现方案并保存文档" --project E:\claude_code\my-coding-agent-test --mode plan --plan-document docs/plan/task.md

# 预算仅覆盖本次运行；Ctrl+C 会停止并等待清理
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "找到配置加载入口" --project E:\claude_code\my-coding-agent-test --run-json '{"max_requests":5,"max_seconds":180}'

# 使用输出中的真实标识；查看历史不调用模型
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli sessions list <project-id>
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli sessions get <session-id>
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "继续解释这里的错误处理" --session <session-id>
```

`sessions list --cursor` 和 `sessions get --before-seq` 可继续分页，游标取前一页结果。`ask --mode normal|plan` 选择本次方式，省略时沿用会话最近模式；`ask --json` 输出公开事件 JSONL 和最终快照。全局 `--model` 用于新会话，已有会话不允许无声更换模型。请求不自动重试、不静默更换模型或 provider。

同一后端默认共用 HTTP 连接池，可在诊断页关闭复用；服务端关闭或连接失效时可能需要重新建连，后端退出统一释放；分别启动的 CLI 进程不会跨进程共享连接。应用沿用当前网络环境，不绑定代理方式。开启复用时，有效连接不因固定空闲秒数被应用主动淘汰；正常 SSE 结束后最多用集中默认值中的 1 秒读取 HTTP 尾部以便复用，超时只放弃连接复用，已经完整校验的回答仍有效。该清理发生在首字之后，不缩短单请求 / 运行预算，不增加隐式重试。

`doctor --dev` 的开发文件检查按后端源码位置定位仓库，不依赖终端当前目录或选中的项目；报告详情包含实际检查位置。独立安装的 wheel 不包含开发仓库文件时会如实报告缺失，只影响显式开发诊断，不成为日常启动条件。

## 检查与构建

日常开发按改动选择最小必要检查，能省略的测试与回归不做，具体见 [测试清单](tests/README.md)。需要完整阶段验收时，安装锁定依赖后在仓库根目录运行：

```powershell
# 包含真实 Electron 窗口测试
uv run --locked python scripts/check.py --desktop

# 不打开窗口的工程检查
uv run --locked python scripts/check.py
```

入口检查版本与锁文件、Ruff 格式和 lint、mypy、pytest、协议生成漂移、Prettier、TypeScript、共享契约、启动路径、网关故障、桌面构建、示例基线和 wheel 安装。安装依赖与验证 wheel 时可能访问包仓库；默认测试不访问模型服务、不需要 API key。

正式用例、回归脚本与测试专用样本统一放在根目录 [tests/](tests/README.md)，按职责分组；截图、trace、临时项目与数据进入 `.artifacts/tests/` 的独立运行目录。单独运行 pytest 也会自动使用该位置。规则写入 [AGENTS.md](AGENTS.md)，本地与 CI 共用 `scripts/check.py`。

桌面自动化运行真实 Electron、preload、Python 和文件系统；目录 / 保存对话框返回值及资源管理器调用使用受控替身，使取消、无效路径、导出和恢复用例可重复。网络选项的 UI 回归使用模拟报告；本地 / 开发 / 写入诊断实际运行。Windows 原生选择及实际打开文件夹另有本机验收记录，不能与自动化替身混为一谈。

修改公开 DTO 后按顺序生成：

```powershell
uv run --locked python scripts/export_schemas.py
npm.cmd --prefix apps/desktop run types:generate
```

数据流为 `Pydantic → JSON Schema 2020-12 → TypeScript`，两侧运行时严格校验。当前协议 v3 在既有会话 / 运行接口上增加任务、环境、程序、成果和 Goal 接口，来源卡片随会话事件同步。普通控制响应不等待模型完成；stdout 专供协议，1 MiB 单帧上限，收到 stdin EOF 后停止任务、清理资源并释放锁。配置 / 项目数据继续使用版本 1，会话事实单独版本化。

[Windows CI](.github/workflows/check.yml) 使用相同锁定版本与聚合入口，不配置模型密钥、不发布安装包。源码窗口与资源构建已有验证；包含 Python 后端的安装包保留为后续独立验收，不计入当前 M2 已完成能力。

## 示例与进度

[timeout-config 示例](examples/timeout-config/TASK.md) 故意保留 `timeout=0` 被替换成默认值的缺陷：既有测试通过，独立验收必须失败。检查脚本在临时副本中验证这两种结果；后续阶段在独立工作区修复。

每次开发都更新 `docs/progress/`，总览记录阶段状态，当前阶段文件记录实现、实际命令、结果和接续点。后续阶段结合最新需求逐个规划，不提前生成全部阶段记录。
