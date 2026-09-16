# 测试与回归

本目录集中管理正式用例、回归脚本、辅助代码和测试专用样本。新增测试按职责归组并更新本清单；规则见 [AGENTS.md](../AGENTS.md)，实际运行结果见 [进度总览](../docs/progress/README.md) 与对应阶段记录。

测试与回归按最小必要原则选择，能省略的新增用例、重复验证与全量回归不做。日常先看实际改动与已有证据，只有需要验证的行为或关键风险才运行相应检查；低影响文档修改无需启动应用测试。集中管理不代表每次都要执行本清单。

## 统一入口

确需完整阶段验收或用户明确要求全量检查时，先按 [安装说明](../README.md#安装与启动) 安装锁定依赖，再从仓库根目录运行：

```powershell
uv run --locked python scripts/check.py --desktop
```

去掉 `--desktop` 可运行不打开窗口的工程检查。CI 使用相同入口，覆盖版本 / 锁文件、格式、类型、测试、协议生成漂移、桌面构建、示例基线、wheel 安装与开发诊断。wheel 依赖安装可能访问包仓库；默认测试不访问模型服务、不读取真实密钥、不消耗模型额度。

## 分组与独立命令

| 目录 | 职责 | 命令（仓库根目录） | 窗口 / 网络 |
| --- | --- | --- | --- |
| `python/` | 配置、存储、凭据、路径与 junction、诊断分类、真实 stdio、进程清理；同源 schema 样本 | `uv run --locked pytest -q` | 无窗口；网络探测使用模拟响应 |
| `contracts/` | Ajv 校验共用正反样本，检查不转换类型、不移除未知字段 | `npm.cmd --prefix apps/desktop run test:contracts` | 无窗口、不联网 |
| `launch/` | 路径优先级、移动仓库、启动文件读写与损坏保护 | `npm.cmd --prefix apps/desktop run test:launch` | UI 子进程使用替身、不联网 |
| `gateway/` | 真实测试子进程的 UTF-8 分块、超限、提前退出、超时、诊断等待和关闭 | `npm.cmd --prefix apps/desktop run test:gateway` | 无窗口、不联网 |
| `maintenance/` | 候选仓库文件的 UTF-8、文档链接与测试目录归属 | `uv run --locked python tests/maintenance/check_repository.py` | 无窗口、不联网；已纳入统一入口 |
| `desktop/` | 真实 Electron / preload / Python 的项目恢复、设置保存、诊断、导出、目录验证 | `npm.cmd --prefix apps/desktop run build` 后运行 `npm.cmd --prefix apps/desktop run test:desktop` | 打开窗口；目录 / 保存对话框和 Explorer 用替身，网络 UI 返回值模拟 |
| `fixtures/` | Python 与 TypeScript 共用的合法 / 非法契约样本 | 两端测试自动读取 `contracts.json` | 不联网 |
| `support/` | Node 入口定位、共用依赖解析与测试专用模型装配 | 由各测试组引用 | 不单独执行 |
| `models/` | 显式启用的 Go 双模型真实工具回合 | `.venv\Scripts\python.exe tests/models/go_roundtrip.py --enable-real-models` | 联网、使用现有 Go 凭据；每模型最多 3 请求 / 3 分钟，默认 CI 不运行 |

首次回复延迟诊断按需显式运行，不加入默认回归：

- `python tests/models/go_latency.py --enable-real-models --case glm-default`：使用生产适配器，记录客户端、TCP / TLS、首事件和首个正文时间；也支持 `deepseek-default`。重复 `--case` 在同一事件循环中连续请求，默认 `--client-mode pooled` 共用生产连接池；`--client-mode fresh` 模拟逐请求新建连接，`--gap-seconds 6` 可验证跨短暂停顿的复用。`--output` 可复用同一个隔离报告目录，累计最多 8 次尝试，每次 60 秒，无重试；请求不含项目内容，报告不含回答 / 思考正文 / 凭据。客户端获取时间包含在诊断首字中，生产指标单独记录模型调用入口口径。
- `python tests/models/connection_checks.py --enable-real-models`：通过桌面同一 RPC 装配验证按模型测试，GLM / DeepSeek 各一次、每次 60 秒、不重试；使用真实模型额度但不发送项目或会话。报告与隔离数据根统一进入 `.artifacts/tests/model-connections-*/`，仅保存公开结果、时序和用量；任一模型失败时返回非零退出码。
- `python tests/models/tls_latency.py --enable-network`：8 次无凭据 TLS 对照，保持证书验证；不发 HTTP、不调用模型。使用系统解析的原始 socket，不采用显式 HTTP 代理；有显式代理的机器上须区分两种路径。
- `python tests/models/network_path.py --enable-network`：对比默认路径和已经配置的 Windows HTTPS 代理，最多 2 次无凭据模型目录 GET，每个 HTTP 探测 20 秒；只保存脱敏代理地址、系统解析与连接阶段，不读取 API key 或修改 VPN / 系统设置。默认路径没有显式代理不代表绕过 TUN；没有真实模型调用，不加入默认回归。
- `node tests/desktop/latency.mjs`：使用已有桌面构建，打开隔离 Electron，3 次固定模型替身测后端 / renderer / DOM 时序，不调用真实模型。仅诊断入口加载 `support/latency_peer.py` / `latency_desktop_peer.cjs`。

M1 核心必要检查集中在 `python/test_agent_core.py` 和 `python/test_go.py`：只读循环、幂等、预算、取消清理、历史 / 损坏保护、旧配置兼容、文件过滤、搜索后备、SSE 分块与完整工具参数；模型组同时检查小片段立即交付和事件容量，避免把网络分块大小当成等待阈值。用 `python -m pytest tests/python/test_agent_core.py tests/python/test_go.py -q` 单独运行，均不读取真实凭据。

`python/test_model_http.py` 使用本地 HTTP 服务验证生产装配跨 run 复用真实套接字、SSE DONE 后读取 HTTP EOF、取消后重新建连、开关复用后的连接数和耗时持久化。`test_go.py` 另覆盖 DONE 后不结束 HTTP 的服务：有界清理不丢失完整回答。可运行 `python -m pytest tests/python/test_go.py tests/python/test_model_http.py tests/python/test_agent_core.py -q`；仅访问环回地址，使用哨兵凭据。

`python/test_connections.py` 覆盖诊断共用生产池、无密钥目录探测、按模型真实请求构建 / SSE 解析、独立进度与结果、超时 / 取消 / 缺凭据、活动回答期间释放 / 切换、保存失败与重启持久化。定向命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_connections.py tests/python/test_model_http.py -q`。不调用外网或真实模型。桌面 `settings.spec.ts` 的 `model settings persist` 场景覆盖复用开关 / 超时保存、GLM 成功和 DeepSeek 失败的独立展示、明确的模型传参、目录探测与释放入口；网络结果在 IPC 层模拟。截图、模拟说明与隔离配置进入该次 `desktop-settings-*` 目录。仅需此场景时执行 `npm.cmd --prefix apps/desktop run test:desktop -- settings.spec.ts --grep 'model settings persist'`。

`desktop/chat.spec.ts` 使用 `support/desktop_peer.cjs` / `agent_peer.py` 测试装配替换模型，保留真实 Electron、preload、RPC、运行核心、只读文件工具和存储；覆盖超过 8 秒等待、窗口重载不重发、停止、错误、历史重启和预算保存。测试入口不会进入产品启动流程，也不会发网络请求。

该场景同时核对请求阶段和首字指标显示；思考阶段用模型替身模拟，不能当作真实服务首字成绩。实际显示链路的计时仍使用上面的 `desktop/latency.mjs`，不把两种指标相加后宣称已做真实端到端测速。

`desktop/runtime.ts` 复用桌面 package-lock 锁定的 Playwright；不另建一套测试依赖。桌面测试实际运行本机 / 开发 / 写入诊断，网络 UI 用例仅验证显式选项传递；Python 的网络测试独立覆盖响应分类和请求边界。模拟通过不代表服务可达、认证成功或真实工具回合通过。

Python 配置组包含白名单顺序调整、成员完整性与保存检查；诊断组包含从其他 cwd 定位后端开发文件，以及安装布局缺少开发文件时的明确报告。这两处修正可按 pytest 用例节点单独验证，无需为了注释补齐运行全量回归。

## 数据与产物

- 自动化只使用 `.artifacts/tests/` 下的独立目录。pytest 默认创建 `python-<id>/`，显式 `--basetemp` 也必须是该根内的独立子目录。集中配置保证直接运行 pytest 不落到系统临时目录。
- 启动、网关和桌面组分别创建 `启动 路径-*`、`gateway-*`、`desktop-*`；其中保存隔离项目、数据根、截图与导出文件。设置验收把真实桌面构建资源复制到隔离工作区，并通过 junction 复用项目 `.venv`；本机启动文件也位于隔离工作区，不修改真实的 `agent.paths.local.json`。
- Playwright 结果和失败 trace 放在 `desktop-results/<id>/`；CI 上传此目录。pytest、Ruff、mypy 缓存分别集中放在 `pytest-cache/`、`ruff-cache/`、`mypy-cache/`，缓存可以跨次复用，业务测试数据不可共用。
- 聚合入口在 `checks-*/` 中验证示例副本和 wheel，结束后清理该临时目录；需要保留的桌面证据仍位于独立桌面产物目录。产物受 Git 忽略。
- `examples/timeout-config/` 是故意保留缺陷的被测项目，它自带的测试可以留在示例中；执行统一由聚合入口在副本中完成。生产 schema 和生成类型继续放在 `schemas/` 与桌面生成目录。

历史 `.artifacts/` 根下的调试脚本与截图作为已有验收历史保留。新的可复用测试源码必须进入本目录，不能继续在产物目录增加脚本。手工原生窗口验收如需保留自动化步骤，也按职责整理到本目录并增加清单，人工结果写入阶段进度。
