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

- 自动化只使用 `.artifacts/tests/` 下的独立目录。pytest 默认创建 `python-<id>/`，显式 `--basetemp` 也必须是该根内的独立子目录。集中配置保证直接运行 pytest 不落到系统临时目录。
- 启动、网关和桌面组分别创建 `启动 路径-*`、`gateway-*`、`desktop-*`；其中保存隔离项目、数据根、截图与导出文件。设置验收把真实桌面构建资源复制到隔离工作区，并通过 junction 复用项目 `.venv`；本机启动文件也位于隔离工作区，不修改真实的 `agent.paths.local.json`。
- Playwright 结果和失败 trace 放在 `desktop-results/<id>/`；CI 上传此目录。pytest、Ruff、mypy 缓存分别集中放在 `pytest-cache/`、`ruff-cache/`、`mypy-cache/`，缓存可以跨次复用，业务测试数据不可共用。
- 聚合入口在 `checks-*/` 中验证示例副本和 wheel，结束后清理该临时目录；需要保留的桌面证据仍位于独立桌面产物目录。产物受 Git 忽略。
- `examples/timeout-config/` 是故意保留缺陷的被测项目，它自带的测试可以留在示例中；执行统一由聚合入口在副本中完成。生产 schema 和生成类型继续放在 `schemas/` 与桌面生成目录。

历史 `.artifacts/` 根下的调试脚本与截图作为已有验收历史保留。新的可复用测试源码必须进入本目录，不能继续在产物目录增加脚本。手工原生窗口验收如需保留自动化步骤，也按职责整理到本目录并增加清单，人工结果写入阶段进度。
