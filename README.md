# My Coding Agent

Windows 优先的个人 coding agent，使用独立 Python 核心与 Electron / React 桌面。当前已实现项目选择、设置与诊断，以及 M1 的只读对话：通过 OpenCode Go 读取和搜索代码，显示工具过程、支持停止和追问，并在本地保存历史。当前不修改项目文件、不执行项目命令。

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

## 使用只读 Agent

双击 `StartAgent.cmd`，选择项目后进入左侧“只读对话”，选择新会话模型并点击“新建会话”，即可发送问题。例如：“找到启动入口，解释配置如何加载，并标出文件和行号。”

- 工具支持 `list_files`、`read_file`、`search`。展开记录查看实际内容、相对路径、行号和文件版本；模型回答按安全纯文本显示，不自动打开模型给出的链接。
- 一个后端同时运行一个任务。顶部“停止运行”在切换项目或设置页后仍可用；“正在停止”表示正在清理资源。切换视图或重载窗口不会自动重发问题。
- 对话状态显示实际连接、等待响应、思考和正文阶段。“本次请求首字”从 Python 模型调用入口计到首个非空正文，思考状态不算首字，也不包含点击、存储和界面渲染时间。工具续答会开始下一次请求并重新计时；历史保留最近请求的耗时，旧会话没有指标时不补造。
- 会话固定项目和模型，默认模型变更只影响新会话。完整历史允许追问和显式重试；有未配对工具或损坏记录的会话保留可读内容，并提示新建会话。
- 历史保存在当前应用数据根下，重启后从会话列表打开，更早记录支持分页。原生模型续接字段仅在 Python 内保存。当前不提供历史自动修复、数据迁移或从半途自动执行。
- “设置与诊断 → 高级运行预算与读取规则”可调整请求、工具、时间、上下文 / 输出 / 文件容量与扫描范围。初值为 25 请求、60 工具、10 分钟，每次运行取独立快照。上下文使用字节估算；未返回的 token 用量和现金费用显示未知。
- 默认遵守嵌套 `.gitignore`，排除常见凭据、Git 元数据、依赖和构建目录；可显式允许普通忽略文件，凭据保护仍保留。读取前检查真实路径和链接，目前读取可靠 UTF-8 源码；无法解码或过大时返回局部工具错误。

CLI 的 `ask` 使用同一运行服务和工具，以下命令会调用模型。使用与桌面相同的数据根前须关闭桌面，或显式选择独立数据根；项目参数必须是完整绝对路径。

```powershell
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "解释项目启动流程" --project E:\claude_code\my-coding-agent-test

# 预算仅覆盖本次运行；Ctrl+C 会停止并等待清理
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "找到配置加载入口" --project E:\claude_code\my-coding-agent-test --run-json '{"max_requests":5,"max_seconds":180}'

# 使用输出中的真实标识；查看历史不调用模型
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli sessions list <project-id>
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli sessions get <session-id>
uv run --locked my-agent --data-dir E:\MyCodingAgentData\cli ask "继续解释这里的错误处理" --session <session-id>
```

`sessions list --cursor` 和 `sessions get --before-seq` 可继续分页，游标取前一页结果。`ask --json` 输出公开事件 JSONL 和最终快照；全局 `--model` 用于新会话，已有会话不允许无声更换模型。请求不自动重试、不静默更换模型或 provider。

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

数据流为 `Pydantic → JSON Schema 2020-12 → TypeScript`，两侧运行时严格校验。当前协议 v2 保留项目、配置、诊断和关闭接口，新增 `sessions.create/list/get/attach/detach`、`runs.start/cancel/active` 及 `session.event` 通知。普通控制响应不等待模型完成；stdout 专供协议，1 MiB 单帧上限，收到 stdin EOF 后停止任务、清理资源并释放锁。配置 / 项目数据继续使用版本 1，会话事实单独版本化。

[Windows CI](.github/workflows/check.yml) 使用相同锁定版本与聚合入口，不配置模型密钥、不发布安装包。源码窗口与资源构建属于 M0；包含 Python 后端的桌面安装包在 M2 验证。

## 示例与进度

[timeout-config 示例](examples/timeout-config/TASK.md) 故意保留 `timeout=0` 被替换成默认值的缺陷：既有测试通过，独立验收必须失败。检查脚本在临时副本中验证这两种结果；后续阶段在独立工作区修复。

每次开发都更新 `docs/progress/`，总览记录阶段状态，当前阶段文件记录实现、实际命令、结果和接续点。后续阶段结合最新需求逐个规划，不提前生成全部阶段记录。
