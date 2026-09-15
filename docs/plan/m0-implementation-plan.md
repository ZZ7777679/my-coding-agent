# M0 实施细化：工程基线、配置诊断与前后端契约

> 日期：2026-09-14
>
> 对应总规划：[从零构建 Coding Agent](coding-agent-from-zero-plan.md) 的 M0。
>
> 开发规范：代码实现与工程化遵循项目根目录 [AGENTS.md](../../AGENTS.md)，本文件负责 M0 的具体范围与验收。
>
> 实施记录：[M0 进度](../progress/m0.md) 保存工作项、验证与下一步，[进度总览](../progress/README.md) 保存阶段状态。本文件的环境盘点为调研时快照，下文定义实施范围与验收，不表示功能已经完成。
>
> 推进方式：由 Codex 按依赖顺序实现，以验收结果推进，不设固定工期。

M0 要交付一个**能够重复安装依赖、运行 CLI 诊断、选择并记住项目目录、在 E 盘保存应用数据的桌面基础工程**。为让项目记录由 Python 统一管理，最小 stdio 连接提前到 M0；M1 集中实现 agent 循环，M2 继续验证任务事件与安装后的桌面后端联调。

## 1. M0 的交付范围

| 工作 | M0 完成到什么程度 | 后续接续 |
| --- | --- | --- |
| Python 工程 | 独立解释器与虚拟环境、包结构、CLI、依赖锁定、检查与构建命令 | M1 加入循环、模型适配器与只读工具 |
| 默认模型配置 | 固定 OpenCode Go、两个模型 ID、凭据引用与配置校验 | M1 进行两个模型的真实结构化工具回合 |
| 诊断 | 本地检查、可选网络检查、稳定错误分类与 JSON 报告 | M1 接入真实模型认证结果，M2 接入桌面诊断 |
| 数据契约与连接 | 配置、存储、项目、诊断和握手 DTO；schema / 类型生成；最小 stdio 网关 | M1 扩充任务事件，M2 接入任务订阅和打包运行 |
| 项目与应用数据 | 原生目录选择、最近项目、重启恢复、默认数据根、原子保存与单写者约束 | 后续加入项目会话、工作副本和历史管理 |
| 桌面工程 | Electron / React 窗口、有限 preload、Python 启动与基本故障提示；开发模式联调和资源构建 | M2 假任务、任务取消、打包及故障恢复强化 |
| 示例与验证 | 一个小型 Python 缺陷项目、任务说明及验收条件 | M1 用于只读问答，M3–M4 用于编辑与修复 |
| 仓库规范 | README、忽略规则、两份锁文件、本地检查入口与 CI 配置 | 后续阶段扩充已有检查 |

M0 的桌面窗口能真实选择项目、显示当前项目与数据位置、恢复最近项目，并展示后端连接状态。完整聊天、流式工具卡片、模型调用、文件修改、命令隔离、会话恢复与安装器分别按总规划推进。

## 2. 本机实测情况与版本选择

### 2.1 环境盘点

以下为 2026-09-14 实测，不代表工程已经通过这些环境的兼容测试。

| 项目 | 实测结果 | 对 M0 的影响 |
| --- | --- | --- |
| 操作系统 | Windows 11 x64，系统版本 `10.0.26200` | 先在该平台验收 |
| 仓库 | `main` 已跟踪 `origin/main`；规划文档已提交到私有仓库 | 继续现有仓库，无须重新初始化 Git |
| 应用数据根 | 已创建 `E:\MyCodingAgentData` 空目录 | 用户指定 E 盘；实际配置、记录和子目录由应用初始化 |
| 默认 `python` | Anaconda Python `3.8.8` | 不用它创建本项目运行环境 |
| uv 已管理的解释器 | 包含 Python `3.12.13`、`3.11.15`；未发现 3.13 | 实施时安装独立的常规 CPython 3.13.x |
| uv | `0.11.32` | 已有工具；先验证能否解析选定解释器与依赖 |
| Node.js / npm | `v24.16.0` / `11.16.0` | 作为桌面开发候选基线，仍需构建验证 |
| Git | `2.44.0.windows.1` | 已完成一次真实推送 |
| ripgrep | `15.1.0` | M0 检查可执行路径，M1 用于搜索 |
| Docker CLI | `29.6.1` | 客户端已安装 |
| Docker daemon | Linux engine 管道连接失败 | 当前不能执行容器任务，不阻塞 M0 |
| WSL2 | `Ubuntu`、`docker-desktop` 均存在，状态为 `Stopped` | 不在 M0 自动启动或改造执行环境 |
| `OPENCODE_API_KEY` | 当前进程与 Windows 当前用户环境均非空 | 凭据来源已确认，未验证认证或模型调用 |
| Python / 前端依赖 | 项目尚无 `pyproject.toml`、`package.json` 和锁文件 | 实施时解析并记录实际版本 |

盘点时，受限执行环境读取 uv 缓存和 WSL 状态失败；在当前用户的正常执行上下文中重新检查后，成功读到了已安装解释器与 WSL2 分发。Docker daemon 在正常上下文中仍未连接成功。**诊断必须记录检查来源和限制，不能将权限不足直接报告为“未安装”或“登录失效”。**

### 2.2 Python 3.13 是否足够稳定

**继续推荐常规 CPython 3.13.x，最终选择以依赖和构建验证为准。** 3.13 于 2024-10-07 正式发布；本次核查时仍处于 bugfix 维护阶段，官方支持计划到 2029 年 10 月。3.12 当前处于安全维护阶段，也可作为有具体兼容阻塞时的备选。[官方版本状态](https://devguide.python.org/versions/)

Python 自身稳定不等于全部第三方依赖组合都已验证。对本项目，重点检查编译扩展、模型 SDK 的依赖链和 PyInstaller 收集动态依赖的行为。例如，当前 `pydantic-core` 已提供 `cp313-cp313-win_amd64` wheel；这是该扩展具备安装支持的证据，但不能代替本项目测试。[发布文件](https://pypi.org/project/pydantic-core/)

具体实施规则：

1. 使用普通 Windows x64 CPython，采用其默认 GIL 构建；不启用 3.13 的实验性 free-threaded 或 JIT 路径。[3.13 发布说明](https://www.python.org/downloads/release/python-3130/)
2. 从 uv 可获取的正式 3.13 维护版本中选择补丁版本，写入 `.python-version`；不把文档里的 `3.13.x` 当作实际配置值。
3. 在项目 `.venv` 中解析、安装、导入直接依赖，执行 CLI、类型检查、契约测试并构建 wheel；记录 Python 与锁文件版本。
4. 在 M2 最开始验证实际 Python 后端的 Windows 打包与启动。PyInstaller 的支持声明提供选型依据，安装目录中的真实运行结果才是交付依据。[PyInstaller 文档](https://pyinstaller.org/en/stable/)
5. 如果出现必须使用的依赖没有兼容 wheel、无法导入或打包失败，先确认可用的稳定依赖版本；若仍阻塞，再统一切换到 3.12，并同步版本文件、锁文件、CI 与本文。不会让开发环境和桌面包长期使用不同 Python 次版本。

采用 3.13 是工程基线选择，不承诺同时维护 3.12、3.13、3.14 的完整支持矩阵。agent 将来修改的目标项目可以使用其自己的 Python 版本，由执行环境管理，不必跟随 agent 本身。

## 3. 创建哪些文件

总规划展示了最终模块布局；M0 只建立当下有实际内容的文件。以下结构省略 Python 包内常规的 `__init__.py`。

```text
my-coding-agent/
├── README.md
├── AGENTS.md                  # 已有：开发行为、代码与工程规范
├── .gitignore
├── .gitattributes
├── .editorconfig
├── .python-version
├── .node-version
├── pyproject.toml
├── uv.lock
├── src/my_agent/
│   ├── cli.py                  # help、version、config show、doctor、projects、serve
│   ├── config.py               # 受信配置加载与校验
│   ├── storage.py              # 数据根、原子写入、schema 与进程锁
│   ├── projects.py             # 路径验证、项目登记、最近项目
│   ├── credentials.py          # 环境变量来源与延迟解析
│   ├── diagnostics.py          # 有时限的检查与报告
│   ├── errors.py               # 对外错误结构与分类
│   ├── models/types.py         # 模型回合与工具调用的最小内部类型
│   ├── runtime/events.py       # 最小事件草案，尚无循环
│   └── rpc/
│       ├── dto.py              # 握手、项目、存储与诊断 DTO
│       └── server.py           # M0 最小 stdio 服务
├── apps/desktop/
│   ├── package.json
│   ├── package-lock.json
│   ├── electron.vite.config.ts
│   ├── tsconfig*.json
│   ├── src/main/index.ts
│   ├── src/main/backend.ts     # Python 进程与请求配对
│   ├── src/preload/index.ts
│   ├── src/renderer/           # 基础页面、样式与挂载入口
│   ├── src/generated/         # 从 Python schema 生成的类型
│   └── tests/contracts/       # TypeScript 侧共享样本校验
├── schemas/
│   ├── protocol-v1.schema.json
│   └── fixtures/              # 两端共用的合法与非法数据样本
├── scripts/
│   ├── export_schemas.py
│   ├── generate_types.mjs
│   └── check.py               # 聚合检查，失败时返回非零退出码
├── tests/                     # 配置、凭据、诊断、契约与 CLI 边界
├── examples/timeout-config/   # 待修复的小型项目和 TASK.md
├── .github/workflows/check.yml
└── docs/
    ├── plan/
    │   ├── coding-agent-from-zero-plan.md
    │   └── m0-implementation-plan.md
    └── progress/              # 已有：实际进度与验证记录
        ├── README.md          # 阶段状态、当前工作与下一步
        └── m0.md              # M0 工作包与验证证据；后续阶段按需新增
```

包的暂定命名保持一致：Python distribution 为 `my-agent`，导入名为 `my_agent`，CLI 为 `my-agent`，桌面包为私有的 `@my-coding-agent/desktop`。产品名暂用 `My Coding Agent`。两个工程的初始应用版本统一为 `0.0.0`，通过检查脚本约束一致；Python 从包元数据读取版本。

M0 在服务入口显式装配配置、存储、项目和诊断服务。M1 再创建核心 `bootstrap.py`、循环、具体模型适配器和文件工具；M2 加入 `packaging/` 与任务事件联调。

## 4. 依赖、构建与仓库规则

### 4.1 依赖按阶段加入

| 用途 | M0 选择 | 说明 |
| --- | --- | --- |
| Python 打包 | uv + `uv_build` | 配置 `src/my_agent` 与 CLI 入口，提交解析生成的 `uv.lock` |
| CLI 与校验 | Typer、Pydantic | 配置和边界 DTO 严格校验；先覆盖实际 CLI 需求 |
| 持久写入锁 | portalocker | Python 持有同一数据根的排他锁，桌面与 CLI 共用约束 |
| 基础能力 | 标准库 `tomllib`、`pathlib`、`logging`、`subprocess`、`urllib` | 网络诊断可使用标准库；HTTP 模型客户端在 M1 加入 |
| Python 检查 | pytest、Ruff、mypy | 选定一套静态检查；pytest-asyncio 在加入异步循环测试时再引入 |
| 桌面 | Electron、React、TypeScript、Vite、electron-vite | electron-vite 统一构建 main、preload、renderer |
| 协议生成与校验 | `json-schema-to-typescript`、Ajv 的 2020-12 实现 | 从同一 schema 生成类型并进行运行时校验 |
| 后续依赖 | `openai` 在 M1；PyInstaller、electron-builder、Monaco 在 M2 | 随实际使用加入并完成对应验证 |

uv 的项目虚拟环境与锁文件支持重复安装；锁文件由工具生成，不手工编辑。[uv 项目管理](https://docs.astral.sh/uv/guides/projects/) electron-vite 提供三个进程入口的统一构建配置；实际采用的版本必须与本机 Node.js、Vite、Electron 一起通过构建。[electron-vite 文档](https://electron-vite.org/guide/)

依赖第一次解析时选正式发布版本并锁定，不使用上游 `main` 分支依赖。构建后端 `uv_build` 在 `[build-system]` 中固定经过验证的准确版本，构建依赖不假定由运行依赖的锁文件自动管理。初期将 Python 支持范围收敛到 `>=3.13,<3.14`，准确补丁版本另由 `.python-version` 固定。Node.js 先用已安装的 `24.16.0`，提交 `.node-version`，并在 npm 配置中声明已验证的主版本范围。

### 4.2 Windows 与仓库细节

- 源码、配置、schema 和 Markdown 统一 UTF-8、LF，工具执行显式处理编码。中文、空格路径列入验收。
- 项目 Python 命令通过 `uv run --locked` 执行；不依赖全局 Anaconda，也不要求手工激活环境。
- PowerShell 文档使用 `npm.cmd`。跨平台检查脚本在 Windows 选择对应程序入口，参数逐项传递；不依靠 Bash、`make` 或修改系统脚本执行策略。
- `.venv/`、`node_modules/`、缓存、构建输出、诊断原始日志和本地会话数据不进入 Git；提交 `uv.lock`、`package-lock.json`、schema 和生成类型。
- 忽略 `.env` 与本地凭据文件。配置示例仅含环境变量名称，没有密钥占位值的真实替换版本。
- schema 生成结果可读、稳定排序、不含时间戳或个人绝对路径；重复生成不得产生无意义差异。
- 延续现有私有仓库，阶段提交只包含本阶段相关文件，不提交用户环境、模型响应原文或安装缓存。

## 5. 配置与 OpenCode Go 接入准备

### 5.1 M0 固定的模型配置

沿用总规划，不增加默认 provider 或模型列表。官方 Go 文档目前列出了以下两个模型及 Chat Completions 接口。[Go 接口](https://opencode.ai/docs/go/#endpoints)

```toml
[model]
provider = "opencode-go"
base_url = "https://opencode.ai/zen/go/v1"
api = "chat_completions"
model_id = "glm-5.3-flash"
allowed_models = ["glm-5.3-flash", "deepseek-v4.1-flash"]
api_key_env = "OPENCODE_API_KEY"
```

M0 将 provider、接口地址、协议和可选模型范围视为受信内置设置；个人配置可以选择这两个模型中的一个。未知字段、拼错的模型 ID、空变量名和不支持的地址均应返回明确配置错误，不能静默恢复成另一个 provider。

`allowed_models` 校验完整且不重复的成员范围，允许两个模型调整顺序；默认选择由 `model_id` 独立决定，不把显示顺序作为配置有效性的前提。

模型请求的公共约定同步写入适配器接口说明：`User-Agent: my-coding-agent/<app-version>`；每个会话生成一个稳定的 `session_id`，供该会话全部模型请求的 `x-opencode-session` 使用。这些是 Go 对接入客户端的要求，M1 再验证实际请求和重试是否保留这些头。[Go 客户端要求](https://opencode.ai/docs/go/#where-can-i-use-it)

### 5.2 配置来源与凭据

先按第 5.4 节确定数据根，再读取其下的 `config.toml`。普通配置按“内置默认 → 用户配置 → 明确的 CLI 参数”合并并校验。桌面与 CLI 的默认数据根均为用户指定的 `E:\MyCodingAgentData`；桌面将实际绝对路径通过 `--data-dir` 传给 Python。数据根不能由其内部尚未加载的配置反过来决定，避免循环依赖。诊断显示实际配置路径与字段来源。

运行时读取的目标项目配置、README 和 `AGENTS.md` 不能覆盖宿主的 provider 地址、凭据来源和执行权限。这与开发本仓库时遵循根目录开发规范的职责不同。M0 不自动加载目标项目里的 `.env`。`config show --json` 只返回经过筛选的公开字段，不对整个内部配置对象做通用序列化。

默认凭据解析顺序：当前进程中的非空 `OPENCODE_API_KEY` 优先；Windows 下若缺失，再读取当前用户环境中的同名变量。非 Windows 平台只使用当前进程来源。读取失败、变量缺失、找到凭据分别记录，不能都归为“未登录”。若两处都有值，使用当前进程来源即可，不比较或输出内容。

密钥按需读取，只在受信宿主/模型客户端内存中使用。公开配置、diagnostics、RPC DTO 和日志中只出现 `env_var`、`source`、`present` 等状态；没有前后缀、长度或凭据哈希。测试使用人工构造的哨兵值，不使用真实密钥。M2 的手工凭据保存功能再接 Electron `safeStorage`。

### 5.3 项目目录选择与最近项目

项目目录是用户准备让 agent 处理的代码位置；应用数据根用于保存 agent 自身状态。两者分别展示和管理。

首次打开没有历史项目时，显示“选择项目文件夹”。Electron 主进程使用原生 `dialog.showOpenDialog`，指定 `openDirectory`、单选，并正确处理取消；支持普通文件夹和 Git 仓库。[Electron 目录对话框](https://www.electronjs.org/docs/latest/api/dialog#dialogshowopendialogwindow-options)

选择后的流程为：**系统对话框返回路径 → 主进程转交 Python → 验证目录 → 登记项目并保存 → UI 显示当前项目**。M0 仅查询必要的目录元信息，不扫描全部代码、不自动初始化 Git，也不在选中项目内创建 agent 配置目录。

| 场景 | M0 行为 |
| --- | --- |
| 选择有效目录 | 显示项目名、完整路径，生成稳定 `project_id` 并保存最近打开时间 |
| 重复选择同一目录 | 复用原项目记录；规范化真实路径，存在时按文件系统身份去重，不仅做字符串小写比较 |
| 取消选择或验证失败 | 保留当前项目，不写入新的最近记录 |
| 目录不存在、不可读、实际为文件 | 明确显示原因，允许重新选择；不会创建用户原本想打开的项目 |
| 中文、空格、符号链接 / Windows junction | 保留显示路径，按解析后的真实目录验证身份与边界 |
| 与应用数据根重叠 | 解析链接后检查相等及双向包含，拒绝把 agent 数据目录或其父目录作为项目 |
| 打开最近项目 | 再验证可访问性，成功后切换；首版展示最近 20 项，保留其他项目的身份记录 |
| 重启应用 | 恢复上次有效项目；失效记录显示“目录不可用”，不自动创建目录或选择另一个项目 |
| 切换项目 | 更新当前选择，保留其他项目及后续会话记录；后续已启动任务始终绑定启动时的 `project_id` 与目录 |

`projects.json` 保存 `schema_version`、`last_active_project_id` 与项目记录；记录包含 UUID、显示名称、显示路径、规范路径、最近打开时间。目录改名或搬迁的重新关联界面后续实现，M0 保留旧记录并允许选择新位置，不自动合并两组历史。

### 5.4 agent 数据默认保存到 E 盘

**按用户最新要求，Windows 首版默认数据根固定为 `E:\MyCodingAgentData`。** 此目录已实际创建，目前为空。项目源码仍在用户选中的项目目录，例如本仓库位于 `E:\claude_code\my-coding-agent`。

数据根解析顺序是：显式 `--data-dir` → 宿主环境变量 `MY_AGENT_DATA_DIR` → `E:\MyCodingAgentData`。自定义值要求绝对路径，变量名和实际来源由 `StorageInfo` 返回。这个环境变量是新增的应用配置约定，不表示本机目前已经设置。

以下是应用运行后逐步建立的布局，M0 只创建当下有数据的部分：

```text
E:\MyCodingAgentData\
├── config.toml                 # M0 非敏感配置，默认文件仅首次初始化
├── storage.json                # M0 数据格式版本与初始化信息
├── projects.json               # M0 项目记录与上次选择
├── .runtime.lock               # Python 写入者持有的锁
├── logs/                       # M0 脱敏诊断，Python / Electron 分文件
├── electron/                   # Electron 自身状态，与 Python 配置分开
├── cache/electron/             # Chromium 缓存与浏览器会话数据
├── sessions/<session_id>/      # M1 起：事件、快照与产物，记录 project_id
├── workspaces/<run_id>/        # M3 起：任务工作副本
└── dev/                        # 开发入口显式选用的另一数据根
```

M0 设置区显示实际保存位置和“打开数据文件夹”按钮，主进程只打开已确定的数据根。Python 负责初始化配置、存储元数据与项目记录；Electron 只创建和管理自身缓存、日志、浏览器状态目录。首次启动使用默认值，已有文件不得被默认模板覆盖。

为使 Chromium 状态也遵循 E 盘选择，主进程在 `ready` 前创建目录，并显式将 Electron `userData` 指向 `<data_dir>/electron`、`sessionData` 指向 `<data_dir>/cache/electron`，应用日志也指定在该根下。Electron 要求自定义目录预先存在，修改 `sessionData` 必须早于 `ready`。[Electron 官方 app API 源文档](https://github.com/electron/electron/blob/main/docs/api/app.md#appsetpathname-path)

如果 E 盘不存在、不可写或剩余空间不足，显示实际保存路径及错误，停止写入；不悄悄改到 C 盘、安装目录、项目目录或临时目录。M0 可通过上述启动参数或环境变量选用其他位置；完整的设置页迁移功能后续实现，需要复制校验、切换和失败恢复。

开发入口显式传入 `E:\MyCodingAgentData\dev`；桌面开发脚本和 CLI 开发说明保持一致。自动化测试使用独立临时目录，不读取日常项目记录；缓存清理仅针对明确的缓存子目录，不递归清理整个数据根。切换项目不改变数据根，升级不按应用版本另建一套日常数据。

### 5.5 本机启动路径与仓库迁移

仓库资源、脚本、虚拟环境与构建资源按入口位置定位，不绑定本机仓库绝对位置。运行时访问与项目登记仍使用规范化后的绝对路径；个人记录保存在仓库外的数据根，Git 不保存实际项目列表。

显式开发诊断同样从后端源码位置定位开发文件，不借用终端 cwd 或用户项目目录。独立 wheel 缺少开发仓库文件时如实报告，普通启动不依赖开发诊断通过。

源码桌面入口 `StartAgent.cmd`、`dev`、`preview` 共用 `scripts/launch-config.mjs`，读取仓库根目录的 `agent.paths.local.json`。该文件由 Git 忽略，只提交 `agent.paths.example.json`；仅允许可选的 `data_dir` 与 `project_dir` 字符串字段，限制 UTF-8 JSON、16 KiB，拒绝格式错误、未知字段和空值，不输出原始配置内容。示例与本机初值保留用户指定的 E 盘位置。

- 数据根：`--data-dir` → `MY_AGENT_DATA_DIR` → 本机文件 `data_dir` → `E:\MyCodingAgentData\dev`；配置值是完整根，不再追加 `dev`。
- 选择器起始位置：`MY_AGENT_PROJECT_DIR` → 本机文件 `project_dir` → `E:\claude_code\my-coding-agent-test`；不代替用户选择和确认，目录失效时明确提示修正，避免系统回退到下载目录。
- 文件路径值可为绝对路径或相对于配置文件位置的路径；CLI / 环境变量只接受完整绝对路径。拒绝 Windows 的仅盘符相对路径和缺少盘符的根相对路径，不依赖启动 cwd，也不展开环境变量模板。
- 本机文件属于受信源码启动器，Python CLI 不自动读取仓库文件，仍按第 5.4 节使用 `--data-dir` / 环境变量。启动器确定路径后通过环境变量交给 Electron，Electron 将最终绝对数据根传给 Python；不复制 Python 业务存储或模型配置职责。

重新 clone 或移动源码后重新建立依赖环境。数据根保持原位置时可继续读取记录；变更路径配置本身不复制数据。跨盘迁移数据先关闭应用并备份、复制，再切换根；被移动项目的旧绝对路径保留为不可用，M0 不自动迁移或重新关联项目历史。安装包与跨平台能力在对应阶段单独验收。

必要验证覆盖本机文件的优先级、未知 / 损坏 / 超大输入、中文与空格、相对路径在不同 cwd 下的稳定解析、迁移后的启动入口，以及实际桌面读取数据根、选择器起始路径与失效提示。自动化使用隔离配置与测试目录。

### 5.5 持久化归属与最小连接

项目登记、路径检查和 Python 业务数据保存只实现一套，CLI 直接调用服务，桌面通过最小 RPC 调用。Electron 不直接编辑 `projects.json`，renderer 的 localStorage 不作为项目或会话的事实来源。

M0 提供 `initialize`、`projects.open`、`projects.list`、`diagnostics.get`、`shutdown` 五个 RPC 方法。`projects.list` 返回最近列表和已保存的选择；打开最近项目按 ID 解析其登记路径。主进程负责目录选择和“打开数据文件夹”，它们不作为模型工具。`serve` 子进程在 stdin 关闭时退出，释放锁；M0 不开放 `runs.start`、模型或命令执行接口。

写入配置、存储元数据和项目记录时使用同目录临时文件、flush / fsync、原子替换；成功保存后才通知 UI。已有 JSON 损坏或数据版本过新时保留原文件并报错，不覆盖成空列表。

Python 使用 portalocker 的排他文件锁约束同一数据根只能有一个业务写入者；桌面已经占用时，第二个写入型 CLI 返回 `DATA_DIR_BUSY`。锁的获得以实际文件锁为准，不以 PID 文件存在与否推断。诊断等只读命令允许读取原子写入的快照，不能借读取绕过写入约束。[portalocker 文档](https://github.com/wolph/portalocker)

这些小型元数据的初始化、版本检查和原子保存属于 M0；完整会话日志、任务恢复、数据迁移和工作副本仍按后续阶段实现。

## 6. `doctor` 怎样设计才有实际价值

### 6.1 CLI 表面

M0 提供以下命令，名称在实现时保持稳定：

```powershell
uv run --locked my-agent --help
uv run --locked my-agent --version
uv run --locked my-agent config show --json
uv run --locked my-agent projects list --json
uv run --locked my-agent --data-dir E:\MyCodingAgentData\dev projects open --root .
uv run --locked my-agent doctor
uv run --locked my-agent doctor --dev --json
uv run --locked my-agent doctor --network --json
```

普通 `doctor` 检查应用解释器、配置、数据根来源、所在盘可用性、读写条件、剩余空间、数据版本、写入锁状态和凭据来源。写入探针需显式执行且只创建并清理自己的临时文件；读取诊断不能初始化或重写项目记录。`--dev` 额外检查 uv、Node.js、npm、Git、rg、开发依赖与锁文件；WSL/Docker 状态作为后续执行能力提示。这样桌面包将来不会因为用户未安装 Node.js 或 uv 就报错。

默认诊断不联网。`--network` 显式读取配置的 Go 模型目录，设置超时、响应大小上限与整体截止时间，不发起生成请求。检查不自动安装依赖、启动 Docker、修改代理或写入凭据。

### 6.2 检查结果与退出码

每项结果使用稳定的 `check_id`、`status`、`code`、`summary`、`remediation`、`blocking`，并附脱敏的证据。状态限定为 `ok`、`warning`、`error`、`not_checked`；报告附 `checked_at`、应用版本、报告 schema 版本及所选检查模式。

| 情况 | 建议业务码 | 处理 |
| --- | --- | --- |
| 解释器版本不符 | `PYTHON_VERSION_UNSUPPORTED` | 阻塞当前工程验收，指出应使用项目环境 |
| 必需开发工具缺失 | `DEPENDENCY_MISSING` | `--dev` 下阻塞，说明缺失工具 |
| 配置非法 | `CONFIG_INVALID` | 阻塞；显示字段位置，不回显可能含秘密的原始输入 |
| 数据盘不可用、不能写入、空间不足 | `DATA_DIR_UNAVAILABLE`、`DATA_DIR_NOT_WRITABLE`、`DISK_FULL` | 停止写入，保留当前路径；不切换到 C 盘 |
| 数据已被其他写入者占用 | `DATA_DIR_BUSY` | 拒绝第二个写入者；允许不修改数据的诊断 |
| 项目路径无效或与应用数据重叠 | `PROJECT_UNAVAILABLE`、`PROJECT_DATA_OVERLAP` | 不切换当前项目，不保存无效选择 |
| 密钥来源为空 | `CREDENTIAL_MISSING` | 本地工程诊断警告；M1 真实模型任务启动时阻塞 |
| 读取受限 | `ENVIRONMENT_RESTRICTED` | 报告实际限制；必需检查未完成时不能宣称通过 |
| Docker CLI 存在但 daemon 不可用 | `EXECUTION_BACKEND_UNAVAILABLE` | M0 警告，M4 的容器验收前解决 |
| DNS、连接、TLS、代理、超时错误 | 分别使用 `DNS_ERROR`、`CONNECT_ERROR`、`TLS_ERROR`、`PROXY_ERROR`、`TIMEOUT` | 指出失败层，不建议用户盲目重新登录 |
| 返回 HTML、非法 JSON 或结构不符 | `INVALID_SERVICE_RESPONSE` | 不能当成有效模型目录 |

CLI 退出码约定为：`0` 表示所选检查无阻塞项，允许存在明确警告；`1` 表示存在阻塞失败或必需项无法验证；`2` 表示命令参数使用错误。显式要求的网络探测失败时返回 `1`，但它不替代离线 M0 工程检查的结果。JSON 模式 stdout 只输出一份合法报告；日志进入 stderr，子进程输出必须先捕获和清洗。

### 6.3 网络与认证必须分别报告

诊断至少区分四个事实：`credential_present`、`catalog_reachable`、`authentication_verified`、`tool_roundtrip_verified`。未进行的检查使用 `not_checked`，不填 `true`，也不冒充认证失败。

M0 网络探测先对模型目录发送不带密钥的请求。成功只证明本次目录请求可用；若服务要求认证，记录 `CATALOG_AUTH_REQUIRED`，不能据此判定尚未发送的密钥无效。目录缺少某个默认模型时报告该项未确认，不自动换模型。

M0 用模拟 HTTP 响应验证未来认证请求的错误映射：401 为认证失败；403 为访问受限，原因未知时保留未知；429 结合结构化错误区分限流与额度问题，无法区分时使用通用受限状态；5xx 为服务端错误。映射测试不是账户认证通过的证据。

M1 才通过一个明确的、小型 coding 任务验证真实密钥和两个模型的工具回合，并记录预算、客户端标识、会话标识与调用结果。即使 M0 网络暂不可用，配置、离线契约、FakeModel 准备和桌面工程仍可继续。

## 7. 契约先明确，实现逐步加入

### 7.1 M0 定义的数据

| 数据 | M0 需要明确的内容 | 边界 |
| --- | --- | --- |
| `PublicConfig` | provider、模型 ID、允许模型、凭据来源状态 | 不含密钥，不等于内部配置对象 |
| `UpdateConfigParams` | 待保存的模型 ID | 仅接受两个已约定模型，不允许携带密钥或修改 provider |
| `StartupPathsParams/StartupPaths` | 待保存的数据 / 项目起始目录，以及当前数据根与本机文件位置 | 主进程管理受信启动文件；与 Python 业务存储区分 |
| `ChooseDirectoryParams/DirectorySelection` | 目录用途枚举与选择 / 取消结果 | 使用原生目录选择器，不提供通用文件访问 |
| `ExportParams/ExportResult` | 公开配置、项目列表或诊断的枚举，以及导出 / 取消结果 | 内容由后端事实生成，renderer 不能指定任意文件内容 |
| `DiagnosticReport` | 检查项、模式、时间、错误码与公开证据 | CLI 与桌面共用 |
| `AppInfo` | 应用名、版本、协议版本、当前阶段 | 支持基础 preload 的有限信息查询 |
| `StorageInfo` | 实际数据根、来源、数据版本与可用状态 | 由宿主确定，不接受模型指定保存路径 |
| `ProjectSummary/ProjectsView` | 项目标识、路径、最近记录、已保存的当前选择与可用性 | Python 管理事实，UI 根据结果展示 |
| `InitializeParams/Result` | 应用/后端版本、协议版本、数据版本、能力清单 | M0 完成开发环境中的真实握手 |
| `RpcRequest/Response/Notification` | 请求配对、通知与错误结构 | JSON-RPC 封装和业务 DTO 分开 |
| `ToolCall/ToolResult/ModelTurn` | 调用标识、工具名、JSON 参数、结果与规范化模型输出 | 最小内部草案，M1 按真实工具和模型补齐 |
| `SessionEvent` | 会话/运行标识、事件类型、持久序号 | M0 仅用少量样本表达语义，不预先实现完整事件系统 |

PI 对模型消息、应用消息和运行时事件的分离，以及 DSH 的显式装配与会话事件设计，继续作为模块边界参考；M0 通过独立 DTO 落实这些边界，M1 再在装配和循环中落实行为。具体来源见[总规划第 2、5、6 节](coding-agent-from-zero-plan.md)。

内部模型的 provider continuation 数据不会导出给前端。首批冻结的是公开配置、项目、存储、诊断和握手；尚未投入实际运行的任务事件草案可以在 M1 调整，同时更新样本和类型，避免为猜测的需求固定复杂结构。

### 7.2 版本、标识与错误格式

- `app_version` 初始 `0.0.0`，`protocol_version` 初始整数 `1`；保留独立的 `data_schema_version = 1`。应用版本、通信协议和持久数据格式不是同一个版本号。
- 初期前后端成套开发与交付，协议版本不一致就拒绝进入任务流程，不实现复杂的多版本协商。M0 不创建会话库或数据迁移器。
- RPC `id` 用字符串配对请求；`session_id`、`run_id`、`tool_call_id` 各有用途。示例和测试中不互相借用。
- 成功响应只有 `result`，失败响应只有 `error`。`error.code` 保持整数，业务码放到 `error.data.code`；错误无法识别请求 ID 时允许响应 `id: null`。[JSON-RPC 2.0](https://www.jsonrpc.org/specification)
- 持久 `seq` 是会话内单调增加的序号；实时文本增量的 `delta_seq` 归属于消息。M0 约束字段含义，顺序分配与重放在后续运行时实现。
- 能力清单只声明真实可用的方法，不能因为 DTO 已存在就宣布支持 `runs.start` 或文件工具。

M0 的最小网关采用 UTF-8 JSONL；stdout 专用；单帧初始上限 1 MiB；按字节组帧后解码，拒绝非法或超限输入。主进程关联请求 ID，设置请求与启动超时，消费 stderr，并在 EOF / 子进程退出时结束未完成请求。M2 再加入任务事件、文本流、取消、重连与安装目录下的运行验证；M0 不宣称能够执行 agent 任务。

### 7.3 Python 与 TypeScript 如何保持一致

采用 `Pydantic DTO → JSON Schema → TypeScript 类型` 的单向生成。Pydantic 支持 schema 导出；本项目显式选择 JSON Schema Draft 2020-12，并在导出物中写明 `$schema`。[Pydantic 文档](https://docs.pydantic.dev/latest/concepts/json_schema/)

TypeScript 类型由 `json-schema-to-typescript` 生成；运行时使用 Ajv 对相同 JSON Schema 做验证，选择 `ajv/dist/2020`，不混用 draft-07 的默认实例。[类型生成工具](https://github.com/bcherny/json-schema-to-typescript)、[Ajv 2020-12 支持](https://ajv.js.org/json-schema.html#draft-2020-12)

首批 schema 限定为基础 JSON 类型、对象、数组、枚举、常量、显式联合与 `$defs/$ref`。不使用需要猜测映射的动态引用和 Python 对象类型。DTO 中的时间和路径在传输层是明确格式的字符串，内部再转换；整数限制在 JavaScript 可安全表达的范围。

两端对未知字段默认拒绝，不自动类型转换、移除字段或填充默认值。Pydantic 的额外业务校验未必能自动体现在 JSON Schema 中，因此两端必须运行同一批合法/非法样本，覆盖缺失字段、未知字段、错误类型、非法版本和结果/错误互斥。若存在无法由 schema 表达的规则，就在边界显式校验并共享对应反例。

生成脚本提供写入模式和只检查模式。只检查模式在内存或临时目录生成后比较，不悄悄重写仓库。schema 与 TypeScript 类型都提交；CI 检查新 DTO 是否忘记重新生成。

## 8. 桌面项目入口与存储显示

M0 使用 electron-vite 建立主进程、preload、renderer 三个入口。窗口包含当前项目、最近项目、“选择项目文件夹”、数据位置及“打开数据文件夹”，同时显示真实后端状态。初次没有项目时保留明确的空状态，不默认把应用安装目录或启动 cwd 当作用户项目。

开发验收的项目目录使用用户指定的 `E:\claude_code\my-coding-agent-test`，未打包的开发窗口以此作为系统目录选择器的默认位置，不采用系统下载目录。这个路径只决定选择器从哪里打开；用户确认前不登记项目。自动化边界用例使用各自的隔离目录，不能覆盖该测试项目已有内容。

preload 按用途暴露有限方法，主进程逐项校验调用来源与参数：

| 用途 | 方法 |
| --- | --- |
| 项目与状态 | `getAppInfo()`、`chooseProject()`、`listProjects()`、`openRecentProject(project_id)`、`getStorageInfo()`、`openDataDirectory()` |
| 模型设置 | `getConfig()`、`saveConfig({model_id})` |
| 环境诊断 | `runDiagnostics({dev, network, write_probe})` |
| 启动目录 | `getStartupPaths()`、`saveStartupPaths({data_dir, project_dir})`、`chooseStartupDirectory({kind})` |
| JSON 导出 | `exportJson({kind})` |

新项目路径来自系统选择器，最近项目路径由后端按 ID 解析。“打开数据文件夹”不接受 renderer 传入的任意路径。

采用 `contextIsolation: true`、`nodeIntegration: false`，保持渲染器沙箱，限制页面导航与窗口创建；preload 不导出通用 IPC、任意文件读取或命令执行方法。这些边界从基础工程建立时配置，具体实现核对所选 Electron 版本的官方建议。[Electron 安全说明](https://www.electronjs.org/docs/latest/tutorial/security)

M0 验证开发模式下真实 Electron 窗口能打开、中文正常、preload 可用，选择项目后关闭再打开能够恢复；显示的数据根与 Python 实际写入位置一致，并验证生产资源构建成功。页面挂载、资源加载或后端启动失败应留下明确可见的错误；后端未就绪时禁用依赖后端的操作。这里验收的是开发窗口与开发环境中的 Python 连接；安装后的独立运行在 M2 验证。

Python `spawn`、stdio 握手、启动超时、退出清理和基本错误显示前移到 M0。开发时主进程从受信工程入口启动 Python，传参数数组及明确的数据根，Windows 隐藏子进程控制台；M2 换用打包后的可执行文件并加入假任务、取消与故障恢复验证。模型请求仍只在 Python 侧发生。

### 8.1 设置与诊断页面

按用户要求把已有 CLI 配置与诊断能力接入桌面。侧栏新增页面，使用真实服务结果，提供加载、不可用、失败、保存成功与重试状态；项目工作台继续共用同一后端及数据根。

- 模型选择只显示 `glm-5.3-flash` 和 `deepseek-v4.1-flash`。新增 `config.get` / `config.update` RPC；Python 持有单写者锁，重新校验现有配置后原子保存模型选项，保留其余配置值，成功后更新前端。保存会按应用格式重写 TOML，不保留手工注释。公开配置不含密钥，显示来源、位置和是否检测到凭据。
- 环境诊断复用 `diagnostics.get`，三个探测选项默认关闭，打开页面不自动联网或写入探测。显示报告时间、状态、错误原因、修正方法和公开证据；认证与工具回合保持 `not_checked`。默认不初始化记录；配置损坏或写者占用导致初始化失败时，保留诊断通道，其他业务写入继续被拒绝。
- 诊断最长等待 60 秒，普通 RPC 维持 8 秒上限。Python M0 串行处理请求，因此普通刷新等待当前诊断结束后再开始自己的计时；重复诊断被拒绝，UI 运行期间暂停业务操作。关闭应用时终止未完成等待并清理自有后端进程树，不向已关闭的管道发请求。
- 数据目录和项目选择器起始目录通过输入或原生选择器设置，宿主解析绝对 / 真实路径，校验磁盘、目录类型及 junction 包含关系。数据位置允许尚未创建，项目起始目录须存在。主进程调用与启动器共用的本机文件模块，原子保存 `agent.paths.local.json`；renderer 不读写文件，Python 仍是业务数据唯一写者。启动文件不保存密钥。
- 保存启动目录只影响下次双击 / dev / preview 启动，显示当前实际数据根；参数与环境变量仍优先，不自动搬迁数据、不自动登记项目。文件损坏或保存失败时保留旧文件；迁移与独立安装设置留待后续阶段。
- JSON 导出使用原生保存对话框，只导出后端公开配置、项目视图或刚完成的诊断报告。主进程限制 JSON 大小、拒绝覆盖应用配置 / 元数据 / 项目索引 / 启动文件，使用同目录临时文件和原子替换；取消无副作用。renderer 只传导出种类，不能传任意内容或目标路径。

对应验收包括模型保存及重启、CLI 一致性、诊断等待与关闭、默认只读、显式探测、凭据脱敏、配置损坏、目录选择 / 取消 / 重叠 / 下次生效，以及 JSON 导出 / 取消 / 失败恢复。普通回归使用模拟网络响应，实际模型调用仍留在 M1。

## 9. 演示项目与必要测试

### 9.1 timeout 配置缺陷

在 `examples/timeout-config/` 准备一个很小的 Python 项目：缺少 `timeout` 时默认 `30`，显式 `0` 表示不超时；缺陷实现错误地把 `0` 当作缺省值。加入少量覆盖缺省值和普通正数的既有测试，以及说明目标行为的 `TASK.md`。

M0 保留缺陷，记录基线：既有测试应通过，而独立的 `timeout=0` 验收检查能暴露错误。根项目 pytest 显式使用 `testpaths = ["tests/python"]`，不会把这个待修复项目的验收失败混进工程检查。后续评测复制到临时工作区运行，不直接改仓库中保存的基线。

M1 首先用它回答“配置入口在哪里、默认值如何决定、为什么 0 会被覆盖”；M3–M4 再要求 agent 修复、增加回归测试、运行并交付 diff。

### 9.2 M0 测试重点

以下是 M0 阶段验收的关注范围，不是每次修改必须全量执行的清单。日常开发按 [最小验证规则](../../AGENTS.md#业务推进优先验证保持最小) 选择与实际影响直接相关的检查，复用已有证据，省略不必要的新增测试与重复回归。

| 验证 | 为什么需要 | 预期结果 |
| --- | --- | --- |
| 配置优先级与非法配置 | 防止配置被静默覆盖或错误接受 | 选择与来源明确；非法字段返回结构化错误 |
| 凭据缺失、进程来源、用户来源、读取失败 | 防止再次把环境限制误判成登录失败 | 各状态可区分，输出中没有测试哨兵密钥 |
| 子进程超时、不可执行、非零退出、受限访问 | 诊断可能遇到不完整环境 | 有界结束，报告保留事实，不猜测成功 |
| 模拟网络错误与认证响应 | 无须消耗 API 额度就能验证错误边界 | 分类正确；未进行的认证标为未检查 |
| Python / TypeScript 共用样本 | 静态类型无法保证跨进程输入合法 | 合法与非法结果一致，生成文件无漂移 |
| JSON CLI 的失败输出 | 便于桌面和脚本稳定消费 | stdout 一份 JSON，退出码与报告相符 |
| 中文、空格路径 | 覆盖本机真实使用条件 | 配置读取、诊断与命令参数不乱码或截断 |
| 选择、取消、重复选择、路径失效、数据目录重叠 | 保证项目身份和切换行为准确 | 无效或取消不改当前项目；重复选择不重复登记 |
| 保存后重启、写入中断、元数据损坏、第二个写入者 | 项目记录从 M0 起就是真实用户数据 | 重启可恢复；失败保留旧记录；并发写入被拒绝 |
| E 盘缺失、不可写、自定义数据根、开发数据隔离 | 防止默认保存位置与用户约定不同 | 明确报错，不回退 C 盘；UI 与 Python 使用同一根 |
| stdio 分块、中文跨字节、协议不匹配、后端提前退出 | M0 已有跨进程连接 | 正确组帧，失败可见，无悬挂请求与残留写入锁 |
| wheel 安装后运行 CLI | 源码目录可运行不代表打包配置正确 | 临时干净环境中 `--help`、`--version` 可用 |
| Electron 开发窗口与生产构建 | 尽早发现入口、项目选择与资源问题 | 选目录、恢复记录、打开数据目录可用，构建成功 |

仅为配置、协议和诊断的实际边界写测试；基础样式和空组件不建立大量快照。真实模型测试在 M1 单独运行，默认本地检查和 CI 都不需要 API key。

### 9.3 测试与回归统一管理

正式测试源码统一位于根目录 `tests/`，按 `python/`、`desktop/`、`contracts/`、`gateway/`、`launch/` 分组；通用辅助代码放 `support/`，共用契约反例放 `fixtures/`。后续阶段按需扩展分组，不在 `apps/desktop/`、业务源码或 `.artifacts/` 新建测试脚本。[测试清单](../../tests/README.md) 维护命令、边界与是否联网。

`scripts/check.py` 是本地与 CI 的共同入口；独立测试命令也指向上述目录。截图、trace、临时项目、数据根与报告统一进入 `.artifacts/tests/`，每次运行使用独立子目录，不能修改日常数据或默认测试项目。历史调试产物保留在原位置并在进度中注明，生产 schema / 生成类型不挪入测试目录。

## 10. 实施顺序与验收

### 10.1 可直接执行的工作包

| 顺序 | 工作包 | 完成依据 |
| --- | --- | --- |
| M0-01 | 建立 Python 3.13 项目环境，锁定首批依赖并做兼容检查 | CLI 可运行；依赖可导入；版本与构建结果有记录 |
| M0-02 | 加入仓库规则、配置、凭据、数据根与项目服务 | E 盘路径规则、原子存储、项目身份及凭据边界测试通过 |
| M0-03 | 实现 `doctor` 与统一错误结构 | 本地诊断、模拟故障与 JSON 输出验证通过 |
| M0-04 | 定义 DTO / schema / 生成类型并实现最小 stdio 服务 | 两端校验一致；真实握手、项目请求与退出清理通过 |
| M0-05 | 建立 Electron / React 项目入口并连接 Python | 可选目录、查看数据位置、重启恢复；生产资源可构建 |
| M0-06 | 准备 timeout 示例与任务说明 | 已记录缺陷基线和后续验收方式 |
| M0-07 | 汇总检查脚本、CI、README 和 M0 验证记录 | 在锁定依赖下可重复检查与构建，已知限制明确 |

M0-04 和 M0-05 可以按文件依赖穿插，但不会为前端单独手写第二套 DTO。某个可选网络检查受阻时，继续不依赖网络认证的工作；必需工程检查未通过时保留未完成状态。

M0-01 与 M0-07 分别把 [AGENTS.md](../../AGENTS.md) 中的工程规则落实到工具配置和 CI：依赖锁定、Ruff、mypy、TypeScript、契约样本、生成漂移检查和构建。涉及数据与凭据的行为规则由相应服务和测试验证，文档本身不替代这些约束。

### 10.2 预期检查入口

下列命令在对应文件和脚本实现后运行，实际执行情况与结果写入 [M0 进度](../progress/m0.md)：

```powershell
uv lock --check
uv sync --locked
npm.cmd --prefix apps/desktop ci

uv run --locked my-agent --help
uv run --locked my-agent doctor --dev --json
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/my_agent
uv run --locked pytest
uv run --locked python scripts/export_schemas.py --check
uv build

npm.cmd --prefix apps/desktop run types:check
npm.cmd --prefix apps/desktop run typecheck
npm.cmd --prefix apps/desktop run test:contracts
npm.cmd --prefix apps/desktop run build
```

实际顺序由 `scripts/check.py` 在依赖安装后统一组织，开发工具诊断安排在两侧依赖均准备好之后。CI 先在 Windows runner 运行离线测试与构建，显式固定已验证的 Python、Node.js 和 uv 版本；不配置用户模型密钥，不推送安装包或发布 release。网络诊断和 Electron 人工窗口体验另记录，不把无图形界面的构建成功写成桌面交互通过。

### 10.3 M0 完成标准

下列条目定义验收标准；通过情况与证据仅记录在 [M0 进度](../progress/m0.md)，不在本规划中重复维护勾选状态。

- 锁定的 Python 环境可安装、导入依赖、运行 CLI，产出可安装的 wheel。
- 桌面依赖可按锁文件安装，TypeScript 与生产构建通过，开发窗口真实连接 Python。
- 原生目录选择、最近项目、重复选择和重启恢复可用；取消、路径失效不错误覆盖选择。
- 默认业务数据、Electron 状态与缓存进入 `E:\MyCodingAgentData`；自定义和开发数据根两端一致，盘不可用时不回退 C 盘。
- 项目元数据原子保存，版本或内容异常不覆盖；同一数据根只有一个业务写入者。
- 默认配置准确选择 OpenCode Go 与 GLM-5.3-Flash，另一模型只能切换为指定的 DeepSeek V4.1 Flash。
- 凭据只解析已有环境来源，报告和测试产物没有秘密；缺少 key 时离线工程仍可检查。
- `doctor` 对缺失工具、读取受限、未启动服务和网络错误给出准确状态；未认证不能显示已验证。
- 公开 DTO 在 Python 与 TypeScript 中通过同一组正反样本；schema 和类型生成无漂移。
- timeout 示例具有可复现的缺陷与验收规则。
- README 中的安装、检查和启动命令与实际结果一致，M0 验证记录明确列出未检查项。

本阶段结束时，交付的是能选择项目并保存自身状态的工程基线。M1 的第一个目标是使用 FakeModel 跑通“请求工具 → 返回工具结果 → 完成”的只读闭环；M2 在既有桌面连接上接入任务事件、假任务并完成安装后的验证。
