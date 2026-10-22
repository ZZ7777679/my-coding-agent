# 测试与回归

子任务失败回读：`pytest tests/python/test_delegation.py -q` 验证原安排失败停止、部分输出与错误分离、重启后四个旧结果读完及诊断关联；夹具明确加载完整工具目录以隔离调度语义，产品默认按需发现不变。`test_go.py -k 'http_rejection or auth_failure'` 检查 HTTP 400 原因、认证正文不回显及无重试；双端契约过滤 `worker-failure`。桌面构建后 `knowledge.spec.ts` 用隔离离线模型验证错误卡片与再次查询完成，截图归 `.artifacts/tests/desktop-knowledge-*/worker-failure.png`。不重发个人历史请求。

旧会话读取／请求积压：`pytest tests/python/test_session_read_cache.py tests/python/test_goal_records.py -q` 检查解析复用、变更／损坏／删除失效、缓存淘汰不限制读取及 Goal 原持久规则；桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- old-session.spec.ts` 使用 `tests/support/long_session.py` 的隔离 180 轮样本，观测慢读取下的请求合并、会话切换、忙碌提示恢复和历史不变。知识面板兼容用 `knowledge.spec.ts`。产物归 `.artifacts/tests/desktop-old-session-*/`，不调用模型、不写个人历史；只在涉及这条链路时运行。

M7 独立改进预算：`pytest tests/python/test_evolution_budget.py -q` 通过真实服务和离线模型检查调查／提案／指定资源生成的独立预算、接纳快照、持久化、旧记录兼容、有限／不限与取消。`test_go.py -k 'unlimited_model_budget or frame_limits or failure_cause'` 覆盖真实客户端的省略 token 参数、HTTP 超时关闭、300K 大帧／取消及原数值限制；`test_evolution.py -k review_evidence` 包含不限选材的 Trace 分页。桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- evolution.spec.ts -g "independent budgets"` 检查首屏入口、八项有限／不限切换、普通配置不变、重启和恢复单项限额；截图／隔离数据在 `.artifacts/tests/desktop-m7-budget-*/`。预算正反字段沿用共享契约 `-k m7-budget`／`--test-name-pattern=m7-budget`。不访问网络、个人历史或真实模型，按相关改动选择执行。

M6 独立审查修复：`test_checkpoints.py -k unignored` 覆盖取消忽略的既有文件、目录／Windows 大小写和旧快照；`test_workstyles.py` 覆盖套用后的负责人／报告／删除标记、其它工作保留、幂等与重启。`test_sandbox_usability.py -k 'ancestor_denial or cleanup_without'` 检查祖先拒绝与无 ACE 清理；按既有隔离运行时配置执行 `test_sandbox_stability.py -k 'system_volume_project or required_grant_denial'` 实测系统卷项目的 Python／PowerShell／终端与清理。系统卷兼容样本仅在用户临时目录创建唯一临时项目，结束删除并核对祖先 DACL 恢复；数据根和报告仍归 `.artifacts/tests/`，不提权、不操作个人项目。桌面 `m6-workstyles-rollback.spec.ts` 同时覆盖真实 Run 的 Trace 与 `RUN_BUSY` 接纳失败卡片不可打开无关轨迹。

沙箱可用性修复：`pytest tests/python/test_sandbox_usability.py -q` 验证变量筛选／显式名称保存、发现兼容性、未派发 MCP 反馈后接续及坏租约不跳过其他记录；无外网、真实模型或系统授权。沿下述隔离运行时配置，`test_sandbox_stability.py::test_sandbox_local_git_and_python_inspection` 实测普通权限 Git 初始化／暂存／提交／差异／历史与 Python 探测、退出清理。构建桌面后 `npm.cmd --prefix apps/desktop run test:desktop -- sandbox-settings.spec.ts` 验证名称保存／重新加载及本地 MCP 兼容提示，不启动项目进程。`m6-environment-*` 共用契约样本检查只传名称的协议；既有 `bind-environment*` 保持兼容。

导航右键：`pytest tests/python/test_navigation.py -q` 验证名称、身份、任务内容、重启与回退兼容；桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- navigation-menu.spec.ts` 验证三个层级右键／键盘、剪贴板、重命名及任务草稿保留。隔离根和截图进入 `.artifacts/tests/desktop-navigation-*/`；不调用真实模型或网络。

M6 真实材料对照：`.venv/Scripts/python.exe -X utf8 tests/models/m6_materials_live.py --enable-real-models` 在隔离样本中对比完整与按需工具定义，分别运行 GLM 读取和切换 DeepSeek 的只读接续；记录实际工具、服务端用量和时序。仅显式启用时使用 Go 额度，最多 20 请求／600 秒，无自动重试；报告进入 `.artifacts/tests/m6-live-*/`，不加入普通 CI。这些上限仅用于验收，不写入产品设置。

M6 回退与复用：`pytest tests/python/test_checkpoints.py tests/python/test_workstyles.py -q` 使用生产存储／RPC 和离线模型，覆盖原始字节、有效历史、记忆来源、撤销恢复、组合模板及材料范围。构建后 `npm.cmd --prefix apps/desktop run test:desktop -- m6-workstyles-rollback.spec.ts` 验证真实 Electron 入口，产物进入 `.artifacts/tests/desktop-m6-*/`。

原生沙箱显式验收：`tests/support/appcontainer_probe.py --runtime <隔离 Python 副本>` 与 `tests/python/test_sandbox_execution.py`；后者仅在设置 `MY_AGENT_TEST_SANDBOX_RUNTIME` 指向 `.artifacts/tests/` 内运行时副本后运行。创建临时 AppContainer 与目录 ACL，不提权、不修改防火墙／VPN／代理。本机 HTTP 通过普通权限管道转发，使用服务返回的实际 URL。不属于普通 CI；是否通过和清理状态以本次产物及 M6 进度记录为准。

稳定性补验：同一运行时变量下执行 `pytest tests/python/test_sandbox_stability.py -q`。验证项目内外／额外目录／junction／子进程边界、20 次串行与 8 次并行、超时／取消后接续、双项目 HTTP、2 MiB GET／POST、升级后双向字节、活动连接退出、准备时取消、宿主崩溃恢复。实验要求非管理员宿主并禁止 UAC 启动入口。fixtures 在 `tests/fixtures/sandbox_boundary.py`、`sandbox_http.py`，独立崩溃宿主在 `tests/support/sandbox_crash_host.py`；报告归本次 `.artifacts/tests/python-*/`。不使用真实模型或外网服务。

该文件的 `-k shells_without_network` 复用系统 PowerShell 和复制的 Node，覆盖项目 cwd、子进程、目录内外写入、交互式 PowerShell 与清理，不启动 HTTP 授权；`-k command_terminal_and_service` 覆盖 Python／CMD／HTTP。`-k optional` 模拟恢复 I/O 故障，核对可选沙箱失败不阻断直接模式。M6 桌面样本同时覆盖沙箱设置保存；`knowledge.spec.ts` 核对工具加载／后台压缩选项实际保存和原知识入口。执行范围按本次变更选择，不要求每次全跑。

M6 定向入口：`pytest tests/python/test_capability_discovery.py -q` 验证能力发现／卸载持久化、大 Skill 目录按需加载、跨模型原生历史投影、后台压缩的前台并行／失败／新尾部与设置保留，以及回退取消在途摘要、防止旧分支进入新请求；使用隔离数据和模型替身。`test_checkpoints.py` 包含回退不扫描记忆整库、来源投影与独立有效来源保留。记忆接续／长条目／纠错复用 `test_context_memory.py -k 'memory_followup or memory_correction or memory_search_pinning'`。Windows 受限执行环境若在 asyncio 的本机 socketpair 初始化阻塞，需允许本机回环再运行，不修改系统网络或产品实现。

2026-10-19 M5 收尾搜索 / Git：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_search_git_tools.py -q` 覆盖真实 rg 正则 / 上下文 / 路径筛选、201 文件批处理、无效模式在真实 Run 中纠正接续、字面后备、有界输出，以及模型 Git 初始化 / 双区差异 / 暂存 / 提交 / 历史、Plan、归档、关闭 / 重建服务 / 恢复、上层仓库保留和备份冲突。使用隔离项目、测试仓库本地身份和 Git ceiling；无远端、无真实模型。桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- search-git.spec.ts` 验证 201 文件搜索、普通请求继续可用、Git 开关及退出重启恢复；时序、截图与数据归 `.artifacts/tests/desktop-search-git-*/`。按本批变更选用，不加入每次开发必跑清单。

`node --test --test-name-pattern="search and Git waits" tests/gateway/backend.test.mjs` 使用真实 Python / RPC / 文件移动，仅通过 `support/search_git_backend.py` 注入慢查询与 17 秒移动延迟；验证新查询停止旧查询、Git 锁等待不阻塞普通控制、正常退出等待迁移、搜索进程清理和重启恢复。数据归 `.artifacts/tests/gateway-*/search-git-*/`，不打开窗口或访问网络，不在产品入口加入测试开关。

2026-10-19 协作修复定向验证：`pytest tests/python/test_collaboration_fixes.py -q` 覆盖接纳反馈、只读 Goal 接续、候选 / worker 状态、等待到期、精确取消、跨会话成果、图删除与迟到报告、长输入、增长历史和旧快照兼容。复用真实服务、离线模型和隔离目录；按相关改动选择运行。桌面 `work-graph.spec.ts` 补连线 / Delete、拖动位置、删除节点、分配统一保存及重启，`spaces.spec.ts` 检查团队图与各折叠区；结果和限制见 [M5 进度](../docs/progress/m5.md)。

2026-10-19 协作可落地性审查观察器：`.venv/Scripts/python.exe -X utf8 -m tests.maintenance.collaboration_audit`。复用既有模型替身与真实 RPC / 工具 / Goal，观察未安排协作的失败传播、生成节点删除、Review 接续模式、长输入与累计历史容量；输出位于独立 `.artifacts/tests/collaboration-audit-*/report.json`。退出码 0 只表示观测完成，不把已知缺陷编码为健康验收；不加入日常必跑检查、不访问外网或个人数据。结论见 [审查报告](../docs/research/reports/collaboration-usability-audit-2026-10-19.md)。

任务工作图：`pytest tests/python/test_work_graph.py -q` 用模型替身驱动真实 RPC、工具与 Goal，覆盖模板骨架、用户定义 / 报告分离、阶段 Skill、单次 / 连续执行、失败停止和重启恢复。桌面构建后运行 `npm.cmd --prefix apps/desktop run test:desktop -- work-graph.spec.ts`，验证首会话接入、图编辑、分配 / 反馈、折叠和宽窄窗口。均零真实模型请求；产物归 `.artifacts/tests/`，按本批影响选择执行。

M5 A–F 首版的服务、工作台与联合验收入口见下方 [M5 定向入口](#m5-定向入口)。离线模型决策、真实 ConPTY / Git / LSP、原生 Electron 窗口和显式真实模型分别标注；不把模拟通过记为真实模型成功。

M4 后续定向入口：`python/test_file_changes.py -k read_argument_feedback` 复现原 `limit` 错误并检查具体字段反馈；`python/test_agent_core.py -k read_field_correction` 检查同一 Run 修正字段 / 类型后完成；`python/test_go.py -k 'reasoning_stream_does_not or failure_cause_is_separate'` 检查思考即时输出、状态节流与真实失败分类。均离线。`python -m tests.models.persona_coding_live --enable-real-models --diagnostics` 使用原双模型加法器，最多 12 次请求 / 10 分钟，记录思考 / 正文 / 工具片段和生产回调耗时，仅在显式运行时联网；不更改产品默认模型参数，产物位于 `.artifacts/tests/persona-coding-live-*/`。

同入口 `--resume-report <report.json> --diagnostics --followup` 明确追加一个 `--abs` 小修改，保存原报告快照，另有最多 12 次请求 / 5 分钟、每模型 6 请求的验收保护；不是自动继续原失败或产品默认限制。`--finish-report` 与 `--followup` 互斥，只明确请求报告已完成结果，另最多 2 次 / 2 分钟、每模型 1 请求，提示不再调用工具；真实工具事实仍保留，不能把预算失败改写成成功。9 月 30 日追加样本原配置只有每模型 4 请求，已执行修改 / 两次运行却缺最终回答，两个预算终态保留；随后明确收尾 2 请求通过。修正的是后续实验默认保护，不回写旧证据。该观察器串行包裹原模型解析 / 回调，计时不改变模型参数，不保存第二份流原文；回调耗时属于后端，不能代表完整 Electron 渲染。

匿名 MCP 定向入口：显式设置 `MY_AGENT_TEST_MCP_SERVICES=1` 后运行 `pytest tests/python/test_mcp_presets.py -k context7_anonymous_tool`，在指定的隔离 `--basetemp=.artifacts/tests/<本次目录>` 中，经生产 McpTools 将 Context7 启用到项目、发现并选中库检索 / 文档工具、真实查询 React 文档。不读取个人服务令牌、不调用模型；报告在该 pytest 临时目录内。与账号发现 / OAuth 测试分开，不进入普通 CI。Skill 导入材料 / 刷新与工作流快照复用 `test_online_skill_snapshot_install_project_and_restart`、`test_skill_selection_refresh_and_project_rules`、`test_templates_snapshot_and_task_edits_preserve_reports`，不额外造验证框架。

本轮补核：`python/test_go.py -k reported_usage_survives` 用合成断流 / 无效 JSON 验证已报告计量不丢失；`python/test_mcp_arguments.py` 使用真实 SDK 内存服务验证参数错误零派发、可修正及真实执行失败仍停止，另核对本地 / 外部 schema 引用边界，均不访问网络或模型。`models/ticket_experiment.py --variant <baseline|implement_only|tools_subset|brief|examples|batch> --only-phase <implementation|followup>` 在独立根进行单变量真实对照；真实请求必须显式 `--enable-real-models`，同限额用 `--output-tokens` / `--request-timeout`，已有结果不自动重放。`--seed-project` 仅复制 Agent 已完成答案用于后续编辑对照，manifest 保存种子指纹；`--probe-reference` 引用旧探测，不计作新增请求。

2026-09-30 实验反馈增量：`python/test_trace.py` 覆盖失败请求关联、usage 保存 / 未知及重启；`python/test_go.py` 覆盖尾部真实缓存字段；`python/test_ticket_manifest.py` 覆盖源码指纹、补丁不落盘与阶段配置保留。共享 `v6-*` 正反样本覆盖真实缓存 / 未知 / 非法计量与旧协议拒绝；该轮协议为 v6，M5 当前协议为 v7。`models/ticket_manifest.py` 为既有 ticket 实验保存独立阶段快照，不采集凭据或项目外文件；格式 / 类型和相关隔离检查按改动选择，真实对照另显式启用，保留原实验记录。

本目录集中管理正式用例、回归脚本、辅助代码和测试专用样本。新增测试按职责归组并更新本清单；规则见 [AGENTS.md](../AGENTS.md)，实际运行结果见 [进度总览](../docs/progress/README.md) 与对应阶段记录。

测试与回归按最小必要原则选择，能省略的新增用例、重复验证与全量回归不做。日常先看实际改动与已有证据，只有需要验证的行为或关键风险才运行相应检查；低影响文档修改无需启动应用测试。集中管理不代表每次都要执行本清单。

## 统一入口

确需完整阶段验收或用户明确要求全量检查时，先按 [安装说明](../README.md#安装与启动) 安装锁定依赖，再从仓库根目录运行：

```powershell
uv run --locked python scripts/check.py --desktop
```

去掉 `--desktop` 可运行不打开窗口的工程检查。CI 使用相同入口，覆盖版本 / 锁文件、格式、类型、测试、协议生成漂移、桌面构建、示例基线、wheel 安装与开发诊断。wheel 依赖安装可能访问包仓库；默认测试不访问模型服务、不读取真实密钥、不消耗模型额度。

## 分组与独立命令

用户视角探索性评价（2026-09-22）：`npm.cmd --prefix apps/desktop run test:desktop -- persona-onboarding.spec.ts`、`persona-coding.spec.ts`、`persona-long-tasks.spec.ts` 分别覆盖首用 / 资源接入、编码 / Trace / 程序、工作流 / 协作 / 记忆 / Goal。均使用真实 Electron / RPC 与隔离项目，仅模型决策为替身；不登录个人账号。测试记录当前观察到的行为，不将已知问题当成修复后的验收预期；评价与证据见 `docs/progress/m4-user-evaluation-2026-09-22.md`。本轮按用户明确要求执行，不加入每次小改动必跑清单。

同轮真实编码样本：`.venv/Scripts/python.exe -X utf8 -m tests.models.persona_coding_live --enable-real-models`，GLM / DeepSeek 各接受普通自然语言加法器任务，仅发送隔离素材，总预算 12 次 / 600 秒。`--resume-report <report.json>` 只在原报告剩余预算内接续未完成会话，不重复已完成模型；报告保留测试截止和后续接续，不把它们误判为默认产品限制。自动后台记忆提取在该编码样本中关闭，正常记忆工具仍可调用；产物在 `.artifacts/tests/persona-coding-live-*/`，不进入普通 CI。

GitHub OAuth TLS 排查：`.venv/Scripts/python.exe -X utf8 -m tests.models.mcp_tls --enable-network` 仅读取公开授权元数据，记录 TCP / TLS / HTTP 时序与异常类型。可用 `--client httpx` 对照旧客户端，`--certifi` 对照已有 CA 库，`--system-proxy` 仅对该请求使用现有 Windows 代理；均保留证书校验，不修改系统。`--url` 可指定另一公开元数据地址，报告在 `.artifacts/tests/mcp-tls-*/`。此诊断不进入默认测试或正常应用启动。

OAuth 定向验证：`pytest tests/python/test_mcp_oauth.py -q` 使用 `support/mcp_oauth_fixture.py` 的真实本机 HTTP、SDK 与 Windows DPAPI，覆盖授权码 / PKCE、静态身份、刷新 / 重启、取消 / 拒绝、端点变更和失败不重放；无个人账号、默认不联网。桌面构建后运行 `npm.cmd --prefix apps/desktop run test:desktop -- mcp-oauth.spec.ts`，真实 Electron 验证表单、授权状态、重启与退出，系统浏览器入口接隔离样本同意页。四个 `mcp-oauth-*` 共享契约可用 Python `-k mcp-oauth` 与 Node `--test-name-pattern=mcp-oauth` 单独检查。外网公开发现需显式设置 `MY_AGENT_TEST_MCP_OAUTH_DISCOVERY=1`，再运行 `test_mcp_oauth_discovery_live`；只读取 Context7 / GitHub 的认证元数据，不登记客户端或登录真实账户，产物仍归 `.artifacts/tests/`。

程序与 Goal 收尾的定向检查复用 `desktop/execution.spec.ts` 和 `desktop/goals.spec.ts`：真实 Electron 验证逐调用卡片、输出、服务保留 / 退出清理，以及终态 Goal 只在历史出现、活动 Goal 仍可控制。`python/test_goal_records.py::test_ended_goal_is_history_for_followup_and_after_reload` 验证完成 / 取消后的上下文标注、普通新请求、工具配对和重载原记录不变。使用模型替身与隔离目录，不调用真实模型；按改动选择，不自动重复全部 UI 检查。

主界面与模型切换的定向检查复用 `desktop/chat.spec.ts`、`goals.spec.ts` 和 `concurrency.spec.ts`：覆盖实际 Electron / IPC / Python 链路下的思考分片、折叠与完成 / 重启、运行中更换模型、输入区 Goal、左侧会话状态和小窗口布局，模型使用替身，不联网。构建后按实际影响选择 `npm.cmd --prefix apps/desktop run test:desktop -- <用例文件>`；无需为其他样式修改重复整组。

`python/test_agent_core.py::test_model_selection_mid_request_and_reasoning_snapshots` 验证已接纳请求继续使用原模型、下一请求采用新选择，以及思考 / 正文顺序、快照和重启。`python/test_go.py::test_text_delivered_before_next_network_chunk_with_frame_limits` 同时检查思考与正文在下一网络片段前交付。`fixtures/contracts.json` 的 `composer-*` 三项共用于 Python / Ajv，分别验证模型选择、既定模型范围和思考增量 DTO。以上均不调用真实模型；实际执行记录见 M2。

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

## M5 定向入口

2026-10-19 Go / 合作空间修复：`test_config_storage.py::test_legacy_go_endpoint_is_adopted_without_rewriting_on_read` 检查旧地址采用新协议路由但不在读取时改写配置；`test_go.py -k 'fragmented_tools_headers or auth_failure'` 检查路由、完整工具参数与过期凭据说明；`test_web_tools.py::test_search_in_real_run_and_goal` 包含超过文件读取容量的原生搜索响应、不透明数据不入会话。`test_space_team.py::test_three_organisations_routes_busy_queue_and_goal_stop` 检查消息 / 轮次归属，`node --test-isolation=none --test tests/contracts/space-stream.test.mjs` 检查流文本与等待元数据独立更新。

`npm.cmd --prefix apps/desktop run test:desktop -- spaces.spec.ts` 真实窗口验证手动组队、自动排布、拖动、保存 / 重启和 1440 / 1000 宽度下六处折叠区域，无模型请求。`tests.models.connection_checks --enable-real-models` 各测试一次双模型；`tests.models.go_roundtrip --enable-real-models` 每模型最多三次只读代码请求；`tests.models.go_native_search --enable-real-models` 一次公开查询（`--max-response-bytes` 仅约束原始协议诊断，不是产品限额）。上述 Python 模块使用 `.venv/Scripts/python.exe -X utf8 -m` 启动。`tests.models.go_routes --enable-real-models` 比较新旧 Chat 路由，首包即结束；`--compare-payloads` 则在当前路由用四个短请求比较可选字段及输出预算，仅保存时序和类别，不把首包到达当作完整模型回合通过。

以下命令在仓库根目录运行，只选择当前改动涉及的文件 / 节点。所有项目、数据和报告归 `.artifacts/tests/` 独立目录，不使用个人数据根。服务用例默认不调用真实模型；其中真实本机工具不是模型替身。安装锁定 Python / 桌面依赖后运行，语言服务用例使用实际 Pyright / TypeScript 服务；可选服务缺失只影响对应能力。

`go_native_search` 加 `--production-client` 使用应用真实搜索适配器，验证大封装的实际提取，不使用原始协议探测的容量参数；仍只有一次请求。`go_routes --with-tool` 则以一个简单非空工具定义比较新旧路径，同样只测首包，不执行返回工具。`--compare-payloads` 中的 `production` 是修复前包含空 tools 的复现样本，不是当前生产请求格式。

| 用例 | 直接覆盖范围 | 运行条件 / 产物 |
| --- | --- | --- |
| `python/test_spaces.py` | 旧任务不自动迁移、草稿不建会话、有向循环图 / 布局恢复、组建部分失败显式接续 / 幂等、换绑历史与最新成员简报 | 生产服务 / 隔离存储；离线模型决策，无窗口 / 外网；`python-*` |
| `python/test_space_team.py` | 真实 Run 装配下的团队草稿、模板保存 / 复制 / 导入导出、claim 与重启、三种组织路由、成员忙时排队和 Goal 停止 | 模型决策为替身；真实控制器 / 服务，无窗口 / 外网；`python-*` |
| `python/test_documents.py` | 草稿 / 手动保存、Agent 冲突、BOM / CRLF、批量 patch 部分结果、选定恢复、创建 / 移动 / 删除和可修正反馈 | 实际隔离文件与共享 writer，无窗口 / 外网；`python-*` |
| `python/test_m5_terminals_git.py` | ConPTY Unicode / 长行、成员控制移交、Ctrl+C 子进程、CMD 退出；无 remote 的 Git 暂存 / 差异 / 本地提交 / 历史与上层仓库范围 | Windows、pywinpty、本机 Git / Shell；不配置全局身份，不调用模型；`python-*` |
| `python/test_m5_intelligence.py` | 真实 Pyright / TypeScript 的定义、引用、hover、补全、符号、诊断、两种 rename 编辑；草稿并发、捕获基线 / 过期拒绝、取消初始化清理、可选缺失可修正且文件工具可用 | 本机 Node 与锁定语言服务依赖；无窗口 / 模型请求；`python-*` |
| `python/test_attachments.py` | 超过单页限额的文本 / 图片完整分页拼接、无效图片分块的上传清理 | 生产附件服务 / 隔离存储，无窗口 / 外网；`python-*` |
| `python/test_m5_joint.py` | 同一计数器场景贯通团队、文件 / patch / 选定恢复、报告、成员独立停止、附件材料、实际命令与重启不重放 | 模型决策为替身，命令 / 文件 / 服务实际执行；不证明浏览器像素理解；`python-*` |
| `python/test_m5_shared_bootstrap.py` | CLI / RPC 共用 M5 服务及工具装配；单个资源清理失败不跳过其余资源 | 仅装配 / 清理，不启动可选进程或请求模型；`python-*` |
| `contracts/space-stream.test.mjs` | 群聊快照与迟到 delta 不重复、不同 message 的流式水位隔离 | 无窗口 / 外网 / 模型请求 |
| `desktop/spaces.spec.ts` | 手动编辑团队图、保存草稿、显式组建 / 打开成员会话、重启布局与折叠恢复 | 实际 Electron / RPC / Python；仅目录选择替身，零模型请求；`desktop-spaces-*` |
| `desktop/workbench.spec.ts` | 文件编辑 / 保存、BOM / CRLF、Agent 冲突、选区引用、Markdown 与重启；第二条实际 Monaco / Pyright 诊断、引用、emoji 重命名预览及明确保存 | 原生 Electron 窗口；文件场景模型为替身，LSP 场景零模型请求；`desktop-workbench-*` / `desktop-language-*` |
| `desktop/workbench-runtime.spec.ts` | 默认 PowerShell / PSReadLine 的实际 xterm 输入、长命令、resize、Ctrl+C / 关闭；明确独立 Git 初始化、两文件 stage / unstage / index diff | 原生 Electron + 生产 Python，无模型替身输入 / 请求；本机 Shell / Git，无 remote；`desktop-runtime-*` |

Python 的最小入口是单个文件或节点，例如：

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_spaces.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_space_team.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_documents.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_m5_terminals_git.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_m5_intelligence.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_attachments.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_m5_joint.py -q -p no:cacheprovider
.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_m5_shared_bootstrap.py -q -p no:cacheprovider
node --test-isolation=none --test tests/contracts/space-stream.test.mjs
```

原生窗口测试先构建最新资源；以下入口串行运行，避免窗口互相干扰。需要只复核 LSP 时，可选择第二条用例的名称。

```powershell
npm.cmd --prefix apps/desktop run build
npm.cmd --prefix apps/desktop run test:desktop -- spaces.spec.ts
npm.cmd --prefix apps/desktop run test:desktop -- workbench.spec.ts
npm.cmd --prefix apps/desktop run test:desktop -- workbench.spec.ts --grep "real LSP"
npm.cmd --prefix apps/desktop run test:desktop -- workbench-runtime.spec.ts
```

最后一条原生窗口复验通过：真实长命令 READY 输出为 46 ms，默认 PSReadLine 保留，15 秒等待保护未放宽。截图 / 报告在 `.artifacts/tests/desktop-runtime-PeqrNO/`；LSP 窗口证据在 `.artifacts/tests/desktop-language-1hR4u0/`。这属于已执行证据，不要求每次重复。

`models/m5_images.py` 在生产模型客户端发送独立图片，分别核对 GLM / DeepSeek 的实际像素回答和后续不重放图片。`models/m5_joint.py` 使用实际团队生成、代码工具、终端预览、Playwright MCP 浏览器、只读 Review、明确修改、截图读取 / 下一请求视觉理解以及重启不重放；需要兼容浏览器运行包或通过 `MY_AGENT_TEST_BROWSER` 指定已有浏览器程序，会打开实际浏览器窗口。二者只在明确启用时使用现有 Go 凭据和额度，不进入普通 CI；验收请求 / 时间保护不是产品默认门槛。

```powershell
.venv/Scripts/python.exe -X utf8 -m tests.models.m5_images --enable-real-models --request-limit 4 --time-limit-seconds 480
.venv/Scripts/python.exe -X utf8 -m tests.models.m5_joint --enable-real-models --implementation-model deepseek-v4.1-flash --request-limit 20 --time-limit-seconds 1200

# 仅明确接续已有视觉步骤；保留原报告，不重放已验证的代码 / Review
.venv/Scripts/python.exe -X utf8 -m tests.models.m5_joint --enable-real-models --resume-vision-report '.artifacts/tests/m5-joint-<id>/report.json' --request-limit 24 --time-limit-seconds 360
```

联合入口默认实现模型为 GLM；上述命令显式选择已通过的 DeepSeek，实现模型可选范围仍只有两个约定模型。`--probe-only` 只做短诊断，不代表联合业务通过；`--verify-saved-only --resume-vision-report <report.json>` 仅读取保存的验证事实，不发新增模型请求，入口仍要求显式 `--enable-real-models` 标记。产物分别为 `.artifacts/tests/m5-images-*/` 与 `m5-joint-*/`，保存请求计量、终态、报告和浏览器产物；接续累计原请求数，预算截止与失败不改写为成功。

2026-09-30 真实验收总计 29 次请求：双模型图片 2 项通过；DeepSeek 计数器 / Review / 截图链路累计 21 次请求通过，包含一次验收预算截止后的明确接续。GLM 长业务超时 / 传输失败未通过，短诊断截断，因此没有双模型长链路成功结论。具体失败、接续和保存证据见 [M5 进度](../docs/progress/m5.md)。附件 / 可选 LSP 反馈最终定向复验产物在 `.artifacts/tests/m5-attachment-feedback-final/`；完整阶段验收以进度记录为准。

## M4 定向入口

- `models/ticket_experiment.py` / `ticket_browser.mjs`：合成工单 CSV → 标准库清洗 / 统计 / 离线 HTML，追加搜索及负责人统计并验证真实后端重启接续。`.venv/Scripts/python.exe -X utf8 -B -m tests.models.ticket_experiment --root .artifacts/tests/<独立实验目录>` 默认仅准备合成输入；加 `--enable-real-models` 后才经生产 RpcApplication 使用指定模型运行，要求该目录已有真实 `probe.json` 成功证据且尚无运行报告，不自动重放。失败报告检查后，仅明确授权的 `--resume` 可接续原会话，备份原报告并跳过已通过阶段；当前输出截断接续使用单次 16384 输出 / 300 秒等待，不改产品默认值。实验保护最多 50 个编码请求 / 1200 秒，含接续；两轮间关闭并重开后端。Python oracle 和已安装 Edge（经 Playwright）独立验证固定 / 留出样本及实际筛选，0 新依赖；默认 CI 不运行，公开模型调用需用户授权，无个人项目 / MCP / OAuth。
- `desktop/persona-long-tasks.spec.ts -g associates`：来源 Run 完成后显式交接，接收方已有不同答案时仍按新 Run / 结果序号关联；检查来源简报、角色 / 阶段、双方事实与请求在重启后不变、无活动运行。`desktop/chat.spec.ts` 保留独立 wait 标记的长等待 / 停止语义，两者使用真实 Electron / RPC 和模型替身，不联网。
- `python/test_mcp_presets.py`：预设不自动连接、旧配置兼容、环境引用、Windows DPAPI 加密 / 重启 / 删除、实际本地 HTTP 401、重连与项目范围；默认无外网或真实模型。设置 `MY_AGENT_TEST_MCP_SERVICES=1` 后可单独运行 `::test_mcp_public_services_live`，使用隔离目录查询 Context7 的公开 React 文档，明确配置 `GITHUB_MCP_TOKEN` 时只读发现 GitHub 工具；摘要保存到该测试临时目录的 `report.json`，不写远端仓库。
- `desktop/mcp-services.spec.ts`：真实 Electron + `support/mcp_http_fixture.py` 本地 MCP，检查预设取消、普通表单、合成令牌加密、401 修复、工具目录、配置重连、项目启停、重启与清除。先构建，再运行 `npm.cmd --prefix apps/desktop run test:desktop -- mcp-services.spec.ts`；不访问真实外部账户，不请求模型，截图归 `.artifacts/tests/desktop-mcp-services-*/`。
- `fixtures/contracts.json` 的 `mcp-preset-*` 四项验证新增只写凭据与旧目录兼容；Python / Ajv 共用。可分别运行 `pytest tests/python/test_diagnostics_contracts.py -k mcp-preset` 与 `node --test --test-isolation=none --test-name-pattern=mcp-preset tests/contracts/schema.test.mjs`，无需完整契约回归。

- `python/test_trace.py`：事件配对、分页、迟到结果、参数 / 结果详情及原生状态排除。
- `python/test_skills.py`：来源覆盖、会话引用、版本归档、坏配置局部降级、资源库及项目导入（含附属文件）。
- `python/test_workflow_templates.py`：模板快照、任务修改、报告保留及旧任务兼容；三个开源适配流程的阶段 Skill 实际装配、内置模板复制约定、零项目写入与重启恢复。
- `desktop/workflow-presets.spec.ts`：真实 Electron 中查看 / 复制三个流程、新建任务选择、切换阶段和重启恢复；零模型 / 外网请求，截图与报告在 `.artifacts/tests/desktop-workflows-*`。运行 `npm.cmd --prefix apps/desktop run test:desktop -- workflow-presets.spec.ts`（先构建桌面）。
- `python/test_mcp_http.py`：真实本地 Streamable HTTP，工具 / 资源、全局测试与项目启用范围、慢目录及多会话清理，无外网或模型。
- `python/test_mcp.py`：仅在 `MY_AGENT_TEST_MCP=1` 下启动锁定的 Playwright MCP；`MY_AGENT_TEST_BROWSER` 可指定已有兼容浏览器。实际导航、点击、截图、两会话隔离、取消与清理。仅本机页面；可选 `MY_AGENT_TEST_INSTALL_BROWSER=1` 会联网下载安装配套运行包，不在普通 CI 默认运行。
- `python/test_m4_journey.py`：同一 MCP 开关下运行真实文件 / 命令 / 浏览器的空白计数器场景，仅替换模型；覆盖 Goal 中阶段切换、Skill、浏览器动作、既有 Review 会话、显式修改及重启恢复。
- `desktop/m4.spec.ts`：实际 Electron 检查左侧资源入口、Skill 项目导入、MCP 项目启用、会话选择、工具摘要、Trace 折叠 / 关闭与重启。先构建，再运行 `npm.cmd --prefix apps/desktop run test:desktop -- m4.spec.ts`；不调用模型。
- `desktop/mcp-layout.spec.ts`：本地 stdio MCP 样本检查工具名称 / 用途搜索、参数、原始定义折叠与连接状态；隔离会话验证默认及较小窗口的对话滚动、输入可见、Trace 与子任务面板。先构建，再运行 `npm.cmd --prefix apps/desktop run test:desktop -- mcp-layout.spec.ts`；使用 `support/mcp_catalog_fixture.py` 和模型替身，无真实模型或外网调用，截图及布局数据归 `.artifacts/tests/desktop-mcp-layout-*/`。
- `fixtures/contracts.json` 中 `m4-*` 共用样本分别由 `pytest tests/python/test_diagnostics_contracts.py -k m4` 和 `node --test --test-name-pattern=m4 tests/contracts/schema.test.mjs` 使用。
- `models/m4_tools_checks.py --enable-real-models`：GLM / DeepSeek 各一次隔离计数器闭环，首次最多 12 次 / 900 秒；只有明确补充验收时才使用 `--resume-report <已有报告>`，跳过已成功模型、每次最多补 6 次 / 300 秒，并继续累计同一报告内的真实请求。已保存截图时只接续回答，不重做工具。2026-09-22 实际 19 次请求（GLM 6、DeepSeek 13），初次预算结束与接续事实全部保留。

产物统一归 `.artifacts/tests/`。以上是按改动选择的入口，不是普通任务或每次修改的前置检查。

## M3 定向入口

- 压缩收益修正：`python/test_context_memory.py` 的 `test_old_lookup_outputs_retire_without_changing_current_chain_or_history`、`test_larger_summary_keeps_previous_window_without_stopping_run`、`test_work_status_pages_without_duplicating_or_omitting_references` 覆盖当前工具链保留 / 旧输出回读、检索自我排除、无收益摘要不采用与不重复自动请求、证据分页。沿用隔离模型与数据；桌面 knowledge 场景同时展示压缩前后大小。
- 记忆实际使用修正：`python/test_context_memory.py::test_memory_correction_uses_relevant_entries_and_actual_program_output` 使用本机隔离 Python 输出与可控模型验证相关候选、原条目修订和后续召回；`test_memory_search_pinning_and_inactive_replacement` 覆盖搜索与固定召回分开、固定条目后台保护和失效替代。状态工具场景同时核对预览字段不会误导模型。均不调用真实模型。
- `python/test_context_memory.py`：超窗历史分段整理、最新输入保留、原历史不变、摘要预算继承 / 旧默认迁移 / 显式覆盖、截断用量与失败归属、独立整理不阻塞普通运行；记忆改正 / 遗忘 / 启用边界、知识页来源失效、项目重新定位、归档分页与可选摘要故障。`python/test_go.py` 同时覆盖末尾 usage、length / content_filter 区分及重复结束标记兼容；均使用模型或 HTTP 替身。
- `python/test_context_memory.py::test_context_token_display_uses_latest_main_usage_and_model_window`：单次主请求实际 token 与累计费用分离，模型切换 / 摘要后等待新计量，缺失 usage 不回填旧值。`desktop/knowledge.spec.ts` 同时检查 K / M 与比例显示及压缩后的待计量状态；仍用原隔离桌面场景，不请求真实模型。
- `python/test_delegation.py`：内部子任务结果、源安排共享预算、停止清理及 Goal 插话期间继续工作。`python/test_collaboration.py` 继续覆盖既有会话队列与等待。
- M3 增量审查回归沿用 `python/test_delegation.py`：运行中修改开关仍可返回结果、续跑失败不串用旧答案、可选配置损坏不拦普通对话且可显式恢复；`python/test_context_memory.py::test_user_memory_changes_invalidate_other_project_derivatives` 覆盖用户级记忆纠错 / 遗忘跨项目传播，召回范围保持不变。均为隔离离线验证。
- `python/test_m3_journey.py`：真正空目录中创建 / 修改计数器、本机命令、摘要后接续、协作 README、继承上下文的子任务、新会话使用记忆。只替换模型决策，不替换文件、进程、RPC 或存储。
- `desktop/knowledge.spec.ts`：实际 Electron 验证上下文 / 历史 / 记忆入口、分层折叠与 Escape、长原文续读 / 分页、关闭及页面切换后的查询 / 草稿 / 材料保留，发送材料和摘要 / 能力重载；先构建，再运行 `npm.cmd --prefix apps/desktop run test:desktop -- knowledge.spec.ts`，仅模型是替身。
- `python/test_context_memory.py` 同时核对实际请求材料与输入一致、修改记忆不改写旧清单，以及 `get_context_status` 分页和 `compact_context` 使用既有作业 / 预算。不请求真实模型。
- `models/m3_knowledge_checks.py --enable-real-models`：显式授权后运行，GLM / DeepSeek 的摘要与记忆专项；最多 8 请求 / 600 秒，失败不重试，素材来自隔离合成历史。报告 `.artifacts/tests/m3-models-*/report.json`。不加入普通 CI。
- 压缩第二版仍由 `python/test_context_memory.py` 验证：手动 / 自动切点、绝对 token 迁移、usage 基准失效、头尾与配对、零模型请求减量及重启恢复、只含最新要求时不发无效摘要。原来“每次新提问自动裁剪”的预期已按新策略替换。
- 最终方案沿用同一文件：800K 新默认与旧值保留、摘要逐条来源、Unicode 中段命中与精确分页、跨 Run 重复调用 ID 关联、无收益前缀去重（含减量成功组合）与有效输出容量；桌面 knowledge 场景补充从头查看和关联结果折叠；共享契约含新字段与旧响应兼容。
- `.venv/Scripts/python.exe -X utf8 tests/models/context_compaction_v2_checks.py --enable-real-models`：新版本专项，GLM / DeepSeek 各 1 次摘要 + 2 次主请求（关键词命中历史中段 / 最终回答），总计最多 6 次 / 600 秒。生产 RPC / 工具 / Go，合成准备阶段替换模型；产物 `.artifacts/tests/compaction-v2-live-*/report.json`。可显式 `--resume-report <报告路径>` 接续脚本准备故障，已记录请求仍占用原总预算和原截止时间，不重复已成功摘要。不会在普通 CI 执行。
- 同入口加 `--scenario mid-turn`：一轮最多 10 次 / 600 秒，用较低的测试触发点让大日志读取后自动压缩，再回读旧错误、完成回答、接收新的端口纠正。完整尾部可超过默认 15K 目标；样本末行放在工具实际交付范围内，避免把源工具首次截断误认作压缩丢失。该模式同样需要显式真实模型授权，不更改产品默认值。

本地最小组合：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_context_memory.py tests/python/test_delegation.py tests/python/test_m3_journey.py -q`。各文件继续被统一检查入口自动发现，是否运行按本次影响选择。

模型能力、首次回复延迟与网络诊断按需显式运行，不加入默认回归：

- `python tests/models/go_latency.py --enable-real-models --case glm-default`：使用生产适配器，记录客户端、TCP / TLS、首事件和首个正文时间；也支持 `deepseek-default`。重复 `--case` 在同一事件循环中连续请求，默认 `--client-mode pooled` 共用生产连接池；`--client-mode fresh` 模拟逐请求新建连接，`--gap-seconds 6` 可验证跨短暂停顿的复用。`--output` 可复用同一个隔离报告目录，累计最多 8 次尝试，每次 60 秒，无重试；请求不含项目内容，报告不含回答 / 思考正文 / 凭据。客户端获取时间包含在诊断首字中，生产指标单独记录模型调用入口口径。
- `python tests/models/connection_checks.py --enable-real-models`：通过桌面同一 RPC 装配验证按模型测试，GLM / DeepSeek 各一次、每次 60 秒、不重试；使用真实模型额度但不发送项目或会话。报告与隔离数据根统一进入 `.artifacts/tests/model-connections-*/`，仅保存公开结果、时序和用量；任一模型失败时返回非零退出码。
- `python tests/models/go_native_search.py --enable-real-models`：单次验证 Go `/messages` 上既定 DeepSeek 模型的 `web_search_20250305`；默认 90 秒、2048 输出 token、一次服务端搜索，无重试或重定向，不带项目内容。`--timeout-seconds` / `--max-tokens` 可调整本次诊断预算。仅结构化搜索来源确认成功；报告进入 `.artifacts/tests/go-native-search-*/`，不保存密钥、头或模型正文，不加入默认回归。
- `python tests/models/tls_latency.py --enable-network`：8 次无凭据 TLS 对照，保持证书验证；不发 HTTP、不调用模型。使用系统解析的原始 socket，不采用显式 HTTP 代理；有显式代理的机器上须区分两种路径。
- `python tests/models/network_path.py --enable-network`：对比默认路径和已经配置的 Windows HTTPS 代理，最多 2 次无凭据模型目录 GET，每个 HTTP 探测 20 秒；只保存脱敏代理地址、系统解析与连接阶段，不读取 API key 或修改 VPN / 系统设置。默认路径没有显式代理不代表绕过 TUN；没有真实模型调用，不加入默认回归。
- `node tests/desktop/latency.mjs`：使用已有桌面构建，打开隔离 Electron，3 次固定模型替身测后端 / renderer / DOM 时序，不调用真实模型。仅诊断入口加载 `support/latency_peer.py` / `latency_desktop_peer.cjs`。

M1 核心必要检查集中在 `python/test_agent_core.py` 和 `python/test_go.py`：只读循环、幂等、预算、取消清理、历史 / 损坏保护、旧配置兼容、文件过滤、搜索后备、SSE 分块与完整工具参数；模型组同时检查小片段立即交付和事件容量，避免把网络分块大小当成等待阈值。用 `python -m pytest tests/python/test_agent_core.py tests/python/test_go.py -q` 单独运行，均不读取真实凭据。

M2 A 的最小检查位于 `python/test_tasks.py`：真实 RPC / 存储配合模型替身，覆盖任务幂等、部分创建接续、版本冲突 / 保存失败 / 损坏保护、旧日志字节保留、同项目归属和逐请求上下文版本。命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_tasks.py -q`。协议当前为 v3，旧 v2 握手被明确拒绝，已有配置 / 会话数据继续兼容；共享样本同步检查任务参数。`desktop/tasks.spec.ts` 用隔离空目录验证任务创建 / 共享信息编辑 / 旧会话归入 / 重启，不调用模型；构建后执行 `npm.cmd --prefix apps/desktop run test:desktop -- tasks.spec.ts`。`chat.spec.ts` 与可选 `latency.mjs` 的导航同步到任务树入口，原有对话断言保留。

M2 D 的直接检查：`python/test_goal_controller.py` 用离线模型和实际文件 / RPC 检查完整 Goal、插话、HITL、累计预算、退出与中断接续；恢复用例直接发送新消息或接续 Goal，没有单独恢复确认，`run_command` 分支启动隔离项目内的短 Python 命令。`python/test_goal_records.py` 检查报告 / 账本 / 版本，`python/test_work_reports.py` 检查任务同步。按改动选择具体用例，不默认全跑。桌面构建后执行 `npm.cmd --prefix apps/desktop run test:desktop -- goals.spec.ts`，包含空目录、Goal / HITL / 预算与中断后直接发送；模型 / 指定工具返回等待使用 `support/goal_model.py` 和 `support/agent_peer.py`，实际工具、文件、存储和 IPC 不替换。没有真实模型或外网调用，产物统一归 `.artifacts/tests/desktop-goal-*/`。

`python/test_model_http.py` 使用本地 HTTP 服务验证生产装配跨 run 复用真实套接字、SSE DONE 后读取 HTTP EOF、取消后重新建连、开关复用后的连接数和耗时持久化。`test_go.py` 另覆盖 DONE 后不结束 HTTP 的服务：有界清理不丢失完整回答。可运行 `python -m pytest tests/python/test_go.py tests/python/test_model_http.py tests/python/test_agent_core.py -q`；仅访问环回地址，使用哨兵凭据。

状态归因直接检查位于 `python/test_go.py::test_failure_cause_is_separate_from_last_reasoning_phase`：模拟初次连接失败，以及先收到思考后读超时、总期限到达和流传输故障，核对实际错误类别、最后收包信息、无重试和响应关闭。已有 `::test_fragmented_tools_headers_native_state_and_partial_rejection` 同时核对工具参数阶段不会黏在思考阶段。新指标正反样本与缺省兼容共用 `fixtures/contracts.json`，按相关节点执行即可，不要求全量测试。

连续正文显示的定向检查复用计时入口：构建后运行 `node tests/desktop/latency.mjs --streaming`，只发一次离线替身请求，先模拟非正文进度，再连续发送 12 个正文片段。报告每段从后端到真实 DOM 的延迟与实际更新次数，产物归 `desktop-latency-*`；不以固定帧率作为业务门槛。Go 收流顺序由 `python/test_go.py::test_text_delivered_before_next_network_chunk_with_frame_limits` 覆盖。这两项不调用真实模型，不能证明外网速度。

`models/request_trace_live.py` 是显式授权后的**单次上下文复查**入口，仅支持最后一次普通、未归属任务的请求：`.venv/Scripts/python.exe -X utf8 tests/models/request_trace_live.py --enable-real-models --source-data-dir <原数据根绝对路径> --source-session <会话ID>`。它只读原会话，向同一 OpenCode Go 模型发送上下文一次、沿用原单请求时限；不执行返回工具、不写原会话、不保存模型正文或原生思考，时序与结果保存在 `.artifacts/tests/request-trace-live-*/report.json`。此检查会再次发送该会话的代码 / 对话，不加入默认 CI 或普通诊断；执行前需有针对该上下文复查的授权，一次授权不能扩展成多次尝试。

`python/test_connections.py` 覆盖诊断共用生产池、无密钥目录探测、按模型真实请求构建 / SSE 解析、独立进度与结果、超时 / 取消 / 缺凭据、活动回答期间释放 / 切换、保存失败与重启持久化。定向命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_connections.py tests/python/test_model_http.py -q`。不调用外网或真实模型。桌面 `settings.spec.ts` 的 `model settings persist` 场景覆盖复用开关 / 超时保存、GLM 成功和 DeepSeek 失败的独立展示、明确的模型传参、目录探测与释放入口；网络结果在 IPC 层模拟。截图、模拟说明与隔离配置进入该次 `desktop-settings-*` 目录。仅需此场景时执行 `npm.cmd --prefix apps/desktop run test:desktop -- settings.spec.ts --grep 'model settings persist'`。

`desktop/chat.spec.ts` 使用 `support/desktop_peer.cjs` / `agent_peer.py` 测试装配替换模型，保留真实 Electron、preload、RPC、运行核心、只读文件工具和存储；覆盖超过 8 秒等待、窗口重载不重发、停止、错误、历史重启和预算保存。测试入口不会进入产品启动流程，也不会发网络请求。

该场景同时核对最后观测、收包间隔与首字指标显示，确认 8 秒无新数据及窗口重载后仍显示等待间隔；思考阶段用模型替身模拟，不能当作真实服务首字成绩。实际显示链路的计时仍使用上面的 `desktop/latency.mjs`，不把两种指标相加后宣称已做真实端到端测速。

`desktop/runtime.ts` 复用桌面 package-lock 锁定的 Playwright；不另建一套测试依赖。桌面测试实际运行本机 / 开发 / 写入诊断，网络 UI 用例仅验证显式选项传递；Python 的网络测试独立覆盖响应分类和请求边界。模拟通过不代表服务可达、认证成功或真实工具回合通过。

Python 配置组包含白名单顺序调整、成员完整性与保存检查；诊断组包含从其他 cwd 定位后端开发文件，以及安装布局缺少开发文件时的明确报告。这两处修正可按 pytest 用例节点单独验证，无需为了注释补齐运行全量回归。

M2 B 的必要检查集中在 `python/test_file_changes.py`，覆盖真实文件创建 / 精确替换、BOM / CRLF、Plan 授权、基线与唯一匹配、链接 / 路径、保存失败和取消清理；`test_tasks.py::test_scope_change_stops_pending_writes_and_keeps_history_paired` 覆盖任务约束改变后停止写入及明确跳过事实。按改动选择节点运行，不要求每次全跑。`desktop/files.spec.ts` 通过同一模型替身装配驱动真实 Electron / RPC / 文件工具，验证空目录、Plan 拒绝与文档授权、创建 / 编辑、右侧 diff 和重启。构建后运行 `npm.cmd --prefix apps/desktop run test:desktop -- files.spec.ts`；不开外网、不使用真实 Go 凭据。新增共享样本覆盖模式与成果身份边界。

`python/test_file_changes.py::test_successive_edits_need_no_model_hash` 覆盖简化后的接口：schema 只提供路径 / 原文 / 新文，读取 / 搜索 / 写入结果不返回 hash，不传 hash 可创建后编辑和连续编辑，保留 BOM / CRLF 与其他位置的修改，旧 hash 输入可兼容接收。`::test_create_edit_preserve_and_reopen` 另核对旧快照摘要不一致也能从正文读取 diff。现有冲突 / 保存失败用例仍验证多重匹配、准备后实际文件变化及真实保存失败，不以假成功掩盖错误。

`python/test_goal_controller.py::test_goal_continues_after_file_conflict_and_unreadable_change` 使用真实应用 / 文件 / 成果存储、模型替身：准备后注入一次外部编辑 → 收到 FILE_CHANGED → 重新读取并成功编辑且保留外部修改 → 一条历史记录损坏 → 收到 CHANGE_DAMAGED → 列表保留不可用计数 → 继续创建文件并完成同一个 Goal / Run。两次错误都保存在工具历史，未调用真实模型，未自动重放。`test_collaboration.py::test_user_handoff_and_readonly_review` 同时核对模型的 `list_changes / read_change` 不再返回摘要字段。命令按上述 pytest 节点选择，不为这次简化跑全量回归。

`python/test_goal_controller.py::test_goal_continues_after_missing_file_in_empty_project` 覆盖空项目读取不存在的 README → `FILE_NOT_FOUND` → 模型自行创建 → 同一 Goal 完成，区分可修正路径与真正 I/O 故障；不运行真实模型。已有只读工具检查同步采用该明确错误码。

M2 C 的 `python/test_execution.py` 集中验证真实 Windows Job、显式参数 / 中文路径、输出截断、进程树停止与宿主异常退出、环境引用 / 启动快照、实际 Python / PowerShell、服务监听归属、退出与重启。`::test_environment_reference_failure_and_default_system_snapshot` 验证未绑定项目使用本机默认值、已接纳启动不重复审查、后续选择沙箱不影响已接纳的本机启动，以及继承普通变量而不传凭据 / 应用内部变量。按变更选择场景；服务测试只访问环回 HTTP，使用已有项目 `.venv`，不安装或修改个人环境。Conda / uv 真实本机专项运行尚未包含在这组证据内。

`python/test_execution.py::test_program_tools_json_commands_and_service` 从无环境配置、无预先绑定的项目开始，针对实际 GLM 调用形态，经 `ProjectTools.execute` 执行对象 / JSON 对象字符串两种输入：真实 Node、PowerShell、`Get-Location`，断言不需写入环境配置。再保存含旧 trusted=False 的隔离样本，实际启动、读取、停止环回 HTTP 服务，确认旧字段不再阻断；模型可见环境结果也不带该废弃字段。另核对缺失字段反馈与内部异常不会伪装成输入错误。命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_execution.py::test_program_tools_json_commands_and_service -q --tb=short`。仅使用隔离项目和本机已有 Node / PowerShell / 项目 Python，无模型请求、无外网或个人数据写入。

`desktop/execution.spec.ts` 使用离线模型替身，驱动真实桌面选定空目录后创建会话，未进入设置、没有环境配置文件时直接执行 `Get-Location`；随后按需导入 / 绑定环境、创建代码、执行命令、启动 HTTP 小应用、查看卡片、切换页面保留、退出清理和重启不重放。设置页与重启后均不再出现信任勾选项。构建后执行 `npm.cmd --prefix apps/desktop run test:desktop -- execution.spec.ts`。截图和隔离记录归 `desktop-execution-*`；协议共用样本同时覆盖环境联合、省略旧信任字段及其兼容类型、秘密路径空字符与禁止 PID 控制。未增加独立测试入口或外网模型请求。

M2 D 的 `python/test_goal_records.py` 聚焦会话日志中的 Goal 控制、HITL 精确答复、失败停止、跨 Run 累计预算、未确认耗时与幂等任务同步。`::test_task_report_sync_keeps_history_without_proof_or_graph_gates` 核对可选引用 / 图不再阻断同步、最新进度生效且历史和用户目标保留。使用真实隔离存储和构造的模型事实，不调用模型或运行项目程序；控制器与桌面的验证分别记录。命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_goal_records.py -q`，按改动优先选具体节点。

`python/test_work_reports.py` 使用生产 RPC / 会话 / 文件工具装配，仅替换模型；在空项目真实创建文件、读取事实索引、报告并跳过后续工具。模拟共同进度保存故障后重启，明确发送只补同步已保存结果，断言没有重新写入文件、额外总结模型请求或自动完成 Task。命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_work_reports.py -q`。全部数据归隔离产物目录，不启动外网或项目程序。

报告与参数反馈使用 `python/test_goal_controller.py::test_goal_progress_without_report_gates_or_argument_abort`：参数缺项先返回模型修正，纯正文回合继续 Goal，可选图无法调度时继续原目标，最终不填 criteria / evidence 也能提交完成报告；文件只创建一次，终结报告后的工具不再执行。与旧预期的差异对应 [DSH 对照](../docs/plan/runtime-checks-dsh-review.md)，不再要求补表或显式恢复被误停的 Goal。`python/test_tasks.py::test_task_updates_refresh_next_request_without_per_tool_revision_gate` 覆盖共同信息更新不拒绝待执行工具、下一请求刷新上下文。显式真实验证入口仍为 `.venv/Scripts/python.exe -X utf8 tests/models/goal_report_live.py --enable-real-models`，最多 5 请求 / 8 工具 / 180 秒；产物在 `goal-report-live-*`，不进入默认 CI，本次对照没有执行真实模型入口。

M2 E 优先通过真实链路验证联网能力：`.venv/Scripts/python.exe -X utf8 tests/models/web_tools_live.py --enable-real-models` 在隔离空目录 / 数据根中使用生产 RPC、GLM 主模型、Go DeepSeek 原生搜索及公开网页读取，不替换模型或 HTTP。每轮最多 5 个模型请求 / 5 次工具 / 180 秒，单请求 90 秒；失败保留报告、不自动重试。报告在 `.artifacts/tests/web-live-*/report.json`。修复后可显式添加 `--resume-report <报告路径>`，沿原会话已取得来源继续，避免重复搜索；另存接续报告，不覆盖原失败证据。该入口消耗现有 Go 额度，必须显式启用，不加入默认 CI。

构建后，`node tests/desktop/web-live.mjs <已通过的真实报告路径>` 将该次数据复制到隔离目录，用生产 Electron / 后端检查来源卡片、页正文和源链接 IPC，不再调用模型；仅拦截最终系统浏览器打开。截图 / 报告位于 `.artifacts/tests/desktop-web-live-*/`。这证明真实历史的桌面呈现，不冒充再次从桌面发送的网络请求。

E 的预算、取消和失败边界保留在 `python/test_web_tools.py`，可按相关改动选择 `.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_web_tools.py -q`；它使用 `support/web_model.py` 和模拟 HTTP、真实 RPC / 存储验证辅助请求计量、取消释放及无凭据读取，不证明外网可用，也不是每次联网操作的前置检查。

该文件的 `::test_fetch_dns_preflight_uses_actual_httpx_route` 不发请求，验证直连 / 代理 / NO_PROXY 路由与 DNS 预检一致；`::test_page_redirect_extraction_and_output_limit` 使用 HTTP 替身验证实际状态（含 404）、空正文、结构化文本类型、重定向和截断。Python / Ajv 共用的 `web-page-*` 两项契约核对旧历史缺省状态及新增 HTTP 状态，不需要重跑整组契约。

F 的并发直接检查：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_goal_controller.py::test_independent_goals_and_run_cancel_by_owner -q` 在同项目启动两个 Goal 和一个普通运行，验证活动归属、独立取消与退出 / 重启；复用等待模型替身，实际 RPC / 存储。桌面构建后可运行 `npm.cmd --prefix apps/desktop run test:desktop -- concurrency.spec.ts`，从界面创建第二会话并发送、停止第一会话、重载保留第二个 Run ID；复用原模型替身和实际文件读取，不访问网络。截图归 `.artifacts/tests/desktop-concurrency-*/`。这些场景只验证并发与归属，不代替真实模型应用任务，也不默认重复运行其他阶段回归。

F 的协作入口检查：`.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_collaboration.py -q` 使用真实 RPC / 工具 / 存储与可控模型。普通协作场景覆盖定向历史访问、原生状态不外泄、只读约定、实际发送 / 本地等待、忙时排队、精确结果来源、接收方失败传播、暂停 Goal 与重启暂存。新增 `::test_user_handoff_and_readonly_review` 定向覆盖来源简报、真实差异读取、只读 Review、精确移交、其他工作保留及重复安排不重跑。只在相关逻辑变化时选择相应用例，不代表真实模型协作已验收。

M2 收尾复用该文件中的三条定向检查：`::test_bidirectional_delivery_only_breaks_actual_wait_cycle` 验证双向投递与真实互等的区别；`::test_goal_question_yields_collaboration_wait_and_resumes` 验证等待时先回答插话再接续；`::test_long_collaboration_result_and_history_are_readable_in_pages` 验证长中文结果 / 单条历史完整分页和精简请求列表。均使用隔离项目、真实控制器和模型替身，不调用外网模型。

`npm.cmd --prefix apps/desktop run test:desktop -- collaboration.spec.ts` 在构建后用实际 Electron 界面保存约定、读取历史、发送请求、看到结果，并确认窗口重载保留相同 Run / 水位且不重发。模型复用已有替身，项目文件实际读取，不联网。产物为 `.artifacts/tests/desktop-collaboration-*/`；最后的小范围样式 / 历史折叠修正没有单独扩展回归。

`node tests/desktop/counter-live.mjs --enable-real-models` 是显式联网的完整小体验：生产桌面 / Go / 环境 / 文件 / 进程，从空目录 Plan 到 GLM Goal 创建计数器，实际浏览器点击 / 刷新和服务重启，DeepSeek 接手改标题，GLM 独立 Review，再核对退出 / 重启。只替换原生目录选择结果与测试退出确认；页面操作使用隔离 Electron 浏览器窗口，不代表产品新增浏览器自动化。沿用 E 的真实检索证据，不重复搜索。Goal 最多 20 请求 / 40 工具 / 540 活跃秒，其余每次运行沿用明确的产品预算；故障停止且保留逐步报告，不自动重试。产物在 `desktop-counter-live-*`，使用现有 `OPENCODE_API_KEY`，不进入普通 CI。实际执行结果以 progress 为准。

真实计数器中断后可显式添加 `--resume-report <该次报告路径>`，复用已通过步骤、项目和会话，另存 `report-resume-*.json` 保留原失败；没有后台重试。应用退出会停止预览，接续浏览器步骤会明确请求在原地址启动服务。相关修复检查 `python/test_execution.py::test_cwd_accepts_absolute_project_path_without_escape` 只核对绝对 / 相对 cwd 和真实目录边界，不启动程序。`python/test_work_reports.py` 直接使用模型所收结果的 `_evidence`，同时验证历史恢复引用一致和同步不重放。

## 数据与产物

### 用户指南截图（显式运行，不纳入回归）

`node tests/desktop/guide-capture.mjs <core|resources|workbench|team|learning>` 使用已构建的实际 Electron 页面、既有离线模型和隔离示例数据，输出到新的 `.artifacts/tests/guide-<分组>-*/`，包含 PNG 和 `capture.json`。首次使用或产品改动后先 `npm.cmd --prefix apps/desktop run build`。不读取个人会话、不请求真实模型、不修改系统网络；workbench 组仅在隔离项目初始化本地 Git 并启动终端，resources 组只连接本地 MCP 样本，沙箱只展示配置。逐张检查后将选用 PNG 复制到 `docs/guide/images/` 并更新[截图说明](../docs/guide/screenshots.md)；不将演示状态记成真实模型验收。

### Skill 在线发现增量

- `.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_skills.py -q`：覆盖九项预装资源来源 / 许可证、旧方法身份与版本、按需正文、用户覆盖、归档及完整附件复制，不访问网络。桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- bundled-skills.spec.ts` 验证预装来源、复制后编辑、附件导入与原版保持不变，产物在 `.artifacts/tests/desktop-bundled-skills-*/`。
- `.venv/Scripts/python.exe -X utf8 -m pytest tests/python/test_online_skills.py -q`：本地场景使用 HTTP 替身、真实 RPC / 存储，覆盖搜索、快照预览、附属文件、同名保留、项目导入 / 加载 / 重启、取消和 ZIP 目标边界；另覆盖 SkillHub 标准与无 YAML 头的根目录包，预览和项目导入内容一致。公开联网用例默认跳过。
- 显式 `$env:MY_AGENT_TEST_SKILL_ONLINE='1'` 后选择 `::test_online_skill_public_live`：skills.sh 真实搜索和 codeload 下载，在 pytest 隔离数据根安装公开 Skill、导入隔离项目并验证重启恢复，生成 `report.json`，不读取 API key 或调用模型。不是普通 CI 的前置条件。
- 同一开关下选择 `::test_skillhub_public_live`：SkillHub 官方详情 / 下载 API 获取标准包和无头用户上传包，从真实预览直接导入隔离项目并在重启后读取；只访问公开资源，生成 `report.json`，不调用模型。
- 桌面构建后 `npm.cmd --prefix apps/desktop run test:desktop -- online-skills.spec.ts`：测试入口仅将网站 HTTP 替换为 `support/online_skill_fixture.py`，保留生产 RPC / 文件写入；检查在线搜索、预览关闭 / 恢复、安装、项目导入和取消。产物归 `.artifacts/tests/desktop-online-skills-*/`。测试开关只由测试 peer 转发，不改变生产后端环境规则。
- `fixtures/contracts.json` 的 `skill-online-*` 两项共用样本：Python `test_diagnostics_contracts.py -k skill-online` 与 `node --test --test-name-pattern=skill-online tests/contracts/schema.test.mjs`，检查显式来源参数与数值类型一致性。
- `npm.cmd --prefix apps/desktop run test:desktop -- skill-sites.spec.ts`：真实原生网页视图访问本地站点，验证站内搜索、翻页、后退、来源到预览、离页隐藏，以及页面无应用 preload；不依赖外网。
- `node tests/desktop/skill-sites-live.mjs --enable-network`：生产桌面在隔离数据根访问腾讯 SkillHub 和 skills.sh，使用原站搜索、继续加载、详情来源与公开下载预览；SkillHub 用户上传项直接导入隔离项目，skills.sh 项安装到隔离资源库。保留逐站结果 / 截图，不登录、不写个人目录、不调用模型。属于显式网络验收，网站改版或网络失败保留真实失败，不进入普通 CI。产物位于 `.artifacts/tests/skill-sites-live-*/`。

- 自动化只使用 `.artifacts/tests/` 下的独立目录。pytest 默认创建 `python-<id>/`，显式 `--basetemp` 也必须是该根内的独立子目录。集中配置保证直接运行 pytest 不落到系统临时目录。
- 启动、网关和桌面组分别创建 `启动 路径-*`、`gateway-*`、`desktop-*`；其中保存隔离项目、数据根、截图与导出文件。设置验收把真实桌面构建资源复制到隔离工作区，并通过 junction 复用项目 `.venv`；本机启动文件也位于隔离工作区，不修改真实的 `agent.paths.local.json`。
- Playwright 结果和失败 trace 放在 `desktop-results/<id>/`；CI 上传此目录。pytest、Ruff、mypy 缓存分别集中放在 `pytest-cache/`、`ruff-cache/`、`mypy-cache/`，缓存可以跨次复用，业务测试数据不可共用。
- 聚合入口在 `checks-*/` 中验证示例副本和 wheel，结束后清理该临时目录；需要保留的桌面证据仍位于独立桌面产物目录。产物受 Git 忽略。
- `examples/timeout-config/` 是故意保留缺陷的被测项目，它自带的测试可以留在示例中；执行统一由聚合入口在副本中完成。生产 schema 和生成类型继续放在 `schemas/` 与桌面生成目录。

历史 `.artifacts/` 根下的调试脚本与截图作为已有验收历史保留。新的可复用测试源码必须进入本目录，不能继续在产物目录增加脚本。手工原生窗口验收如需保留自动化步骤，也按职责整理到本目录并增加清单，人工结果写入阶段进度。

`python -X utf8 -m tests.models.m5_space_demo` 使用项目 `.venv` 准备隔离的两成员计数器演示；脚本本身不调用模型。输出的 `demo.json` 记录数据根，桌面以该根启动后可实际发送合作请求。演示过程与真实请求结果另记于 M5 进度。

用户明确选择官方直连时，关闭占用此演示数据根的桌面后，用 `.venv/Scripts/python.exe -X utf8 -m tests.models.m5_space_direct --root <演示根绝对路径> --enable-real-models` 运行。只读取 `DEEPSEEK_API_KEY`，请求官方 `deepseek-flash`，复用真实文件、群聊与协作服务；默认最多 24 请求 / 600 秒，可通过参数调整。报告 `direct-report.json` 标注实际 provider 与 API 模型名；不修改产品默认 Go 配置。结束后桌面可查看持久历史，桌面新请求仍沿用 Go，并非增加了完整 provider 设置。已有报告不会自动重放。

## M7 自进化定向验证

M8 的后续维护与新增入口见本文末尾，不将协议 v12 的历史说明当作当前协议。

- 十二项审查修复：`pytest tests/python/test_evolution_review_fixes.py -q` 使用真实服务和离线模型，覆盖指定资源纠错、独立候选冲突、重启接续、历史分页、准备取消／时间预算／跨项目接纳、现场反馈冻结、记忆正文检索／派生纠错、独立证据失效，以及历史改进检索→经验采用→版本变化后的召回。桌面 `evolution.spec.ts -g 'investigates cross-project'` 追加勾选导航保留、原调查再次生成、超过一页的作业／按 ID 打开历史和经验提炼入口；产物仍归 `.artifacts/tests/desktop-m7-investigation-*/`。不发真实模型请求，不修改个人数据。

- 选择性筛选与现场入口：`pytest tests/python/test_evolution_screening.py -q` 覆盖长正文检索、重复归组、准确阅读计量、任务／项目完整分页、冻结接续及模型工具与桌面同一作业。桌面 `evolution.spec.ts -g 'contextual entry'` 检查三种现场范围、启动与原地进度、跳转同一作业、线索／实际阅读及清除继承范围。离线模型，产物 `.artifacts/tests/desktop-m7-contextual-*/`。指定资源与普通调查现在共用筛选／按需读取，预览不再默认铺入 Trace 全文。

- `.venv/Scripts/python.exe -m pytest tests/python/test_evolution_reliability.py tests/python/test_evolution_investigation_evidence.py tests/python/test_evolution_investigation.py -q`：在途采用取消后收回、自动记忆多 Trace 来源失效、候选正文版本比较；索引搜索／后段正文分页／冻结范围与恢复；跨项目调查→多候选→分别采用、外部修改后保留读取基线、活动作业去重与反馈关联。真实服务与存储，模型离线，不读个人历史。
- 桌面 `evolution.spec.ts -g 'investigates cross-project'`：首屏输入／“开始改进”可见且无需保存反馈、同入口查看进度；业务项目证据与 Harness 写入项目分离、两发现两候选、按需材料／最终返回、导航和候选切换草稿、采用与恢复、自动作业关联；调查结束工具的缺项反馈由离线模型修正后继续，不把参数错误当作业务故障。原资源场景另覆盖实验后继续编辑及旧版本效果标记。
- `tests/models/m7_investigation_live.py --enable-real-models`：显式联网的调查／多候选闭环，使用人工 Trace、独立业务与源码目录、生产 Go 客户端；不发送个人历史。可用脚本帮助调整本次实验总预算、选模型或接续先前隔离报告，预算不是产品限制。报告及公开模型结果保存在 `.artifacts/tests/m7-investigation-live-*/`，原失败与补测分别保留。

- `.venv/Scripts/python.exe -m pytest tests/python/test_evolution.py -q`：真实服务、隔离数据，候选／规范／Skill／偏好采用与恢复、外部修改保留、诊断不保存原始秘密、Plan 草稿、工具说明装配、即时取消、代码原版／候选运行和独立恢复。选材专项可用 `-k review_evidence`：覆盖单轮超过 40 条事件时的运行分页／全历史搜索、整个会话／整轮／单事件、截止范围、合并 Trace／去重／预算、实际模型输入与持久快照一致。包括 Windows PowerShell / Python 进程，模型使用离线替身。
- `.venv/Scripts/python.exe -m pytest tests/python/test_diagnostics_contracts.py -q -k m7` 与 `node --test --test-name-pattern=m7 tests/contracts/schema.test.mjs`：共用正反 DTO 样本，检查 v12 新入口。
- 构建后 `npm.cmd --prefix apps/desktop run test:desktop -- evolution.spec.ts`：实际 Electron / RPC，规范及偏好编辑、采用／恢复、反馈、实验详情关闭与重启；选材场景可用 `-g 'selects a named run'`：离线模型生成 22 轮真实运行，翻页保留旧轮、多选、切换整个会话／单事件、预览、跳转 Trace、生成并回查实际材料。证据浮层检查完整位于视窗、材料→Trace→材料、关闭后页面滚动与焦点保持，以及窄窗口直接查看和 Esc 关闭。实际启动本机 Python 检查，产物 `.artifacts/tests/desktop-m7-*/`、`.artifacts/tests/desktop-m7-evidence-*/`；不调用外部模型。
- `.venv/Scripts/python.exe tests/models/m7_evolution_live.py --enable-real-models`：明确启用网络后使用生产 OpenCode Go 客户端。GLM 和 DeepSeek 各生成规范／代码候选并接续一次，通常共 6 请求；隔离试验上限 8 请求／600 秒、单请求 90 秒，不写产品预算。真实代码检查及采用／恢复，报告 `.artifacts/tests/m7-live-*/report.json`。只发送隔离样本，不读取个人会话；不是每次开发必跑项。

## M8 稳定性与体验定向验证

- `pytest tests/python/test_m8_recovery.py tests/python/test_delegation.py tests/python/test_mcp_http.py -q`：离线故障模型、真实运行／文件／持久化及本地 MCP；四 worker 超过旧累计限额、父子账本、取消部分输出、默认不重试、已写文件后模型重试不重放工具、退避取消、有限预算与 MCP 只读重连。
- `test_capability_discovery.py` 中 M8 组合查询用实际服务定义确认 worker 可发现；`test_go.py -k empty_completed` 核对空回答的 usage 与 phase 保留。回退继续复用 `test_checkpoints.py`。
- 构建后 `node --test --test-name-pattern=M8 tests/gateway/backend.test.mjs`：真实测试子进程的读取超时／迟到响应和实际退出后的单次恢复；不发模型请求。
- 构建后 `npm.cmd --prefix apps/desktop run test:desktop -- m8-experience.spec.ts`：真实 Electron 和生产 RPC，模型为隔离样本；五主题、主色持久、侧栏、子任务阅读、Trace 筛选、记忆草稿／反馈、长 Markdown 输入和 125% 缩放。输出 `.artifacts/tests/m8-experience-*/` 的截图与 `metrics.json`。原生缩放截图采用 `webContents.capturePage`，避免 CDP 的视口坐标裁切。测试专用 RPC 计量只记录方法与时间，不记录参数。
- `knowledge.spec.ts` 保留历史查询／压缩／记忆与失败子任务接续回归；新版覆盖面板先关闭再切换入口。
- `.venv/Scripts/python.exe tests/models/m8_collaboration_live.py --enable-real-models`：GLM／DeepSeek 各一次隔离 worker 读取→主任务写文件→最终回答；使用真实 Go，默认 24 请求／600 秒总预算，各 Run 12 请求／16 工具／240 秒。可用 `--model glm-5.3-flash` 单独复测、`--retry-attempts 1` 显式测试临时重试；这些仅属验收设置，不改用户默认。报告 `.artifacts/tests/m8-live-*/report.json` 逐请求记录用量与失败，不进普通 CI。
