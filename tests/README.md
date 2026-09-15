# 测试与回归

本目录集中管理正式用例、回归脚本、辅助代码和测试专用样本。新增测试按职责归组并更新本清单；规则见 [AGENTS.md](../AGENTS.md)，实际运行结果见 [M0 进度](../docs/progress/m0.md)。

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
| `support/` | Node 入口定位与共用依赖解析 | 由各测试组引用 | 不单独执行 |

`desktop/runtime.ts` 复用桌面 package-lock 锁定的 Playwright；不另建一套测试依赖。桌面测试实际运行本机 / 开发 / 写入诊断，网络 UI 用例仅验证显式选项传递；Python 的网络测试独立覆盖响应分类和请求边界。模拟通过不代表服务可达、认证成功或真实工具回合通过。

Python 配置组包含白名单顺序调整、成员完整性与保存检查；诊断组包含从其他 cwd 定位后端开发文件，以及安装布局缺少开发文件时的明确报告。这两处修正可按 pytest 用例节点单独验证，无需为了注释补齐运行全量回归。

## 数据与产物

- 自动化只使用 `.artifacts/tests/` 下的独立目录。pytest 默认创建 `python-<id>/`，显式 `--basetemp` 也必须是该根内的独立子目录。集中配置保证直接运行 pytest 不落到系统临时目录。
- 启动、网关和桌面组分别创建 `启动 路径-*`、`gateway-*`、`desktop-*`；其中保存隔离项目、数据根、截图与导出文件。设置验收把真实桌面构建资源复制到隔离工作区，并通过 junction 复用项目 `.venv`；本机启动文件也位于隔离工作区，不修改真实的 `agent.paths.local.json`。
- Playwright 结果和失败 trace 放在 `desktop-results/<id>/`；CI 上传此目录。pytest 缓存集中放在 `pytest-cache/`，缓存可以跨次复用，业务测试数据不可共用。
- 聚合入口在 `checks-*/` 中验证示例副本和 wheel，结束后清理该临时目录；需要保留的桌面证据仍位于独立桌面产物目录。产物受 Git 忽略。
- `examples/timeout-config/` 是故意保留缺陷的被测项目，它自带的测试可以留在示例中；执行统一由聚合入口在副本中完成。生产 schema 和生成类型继续放在 `schemas/` 与桌面生成目录。

历史 `.artifacts/` 根下的调试脚本与截图作为已有验收历史保留。新的可复用测试源码必须进入本目录，不能继续在产物目录增加脚本。手工原生窗口验收如需保留自动化步骤，也按职责整理到本目录并增加清单，人工结果写入阶段进度。
