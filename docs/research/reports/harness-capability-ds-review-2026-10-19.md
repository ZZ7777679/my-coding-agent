# DS 综合能力评价：当前实现核对

日期：2026-10-19。基线：当前 dev 工作区，包含未提交的 M5 和刚完成的协作修复。范围仅为用户提供的能力清单及 16 项缺口；本轮只读检查源码、协议、桌面入口、既有测试和进度，不修改产品、不发模型请求、不重新跑全量测试、不提交或推送。

## 总体结论

这份评价有价值，但混用了四个层次：应用已有能力、模型可直接调用的专用工具、所选项目的当前配置、该次会话实际验证过的能力。由“工具清单没有”推到“整个 Harness 没有”，造成 Git、恢复、环境、凭据、后台执行等多项误判；由“存在 schema”推到“场景已经跑通”也不成立。

真正值得补强的是搜索表达能力、已有 Git / 恢复能力的模型入口、项目执行的专用凭据引用、项目诊断聚合与能力说明。沙箱、项目索引、主题定位等确实尚未实现完整产品，但不都构成当前编码的 P0，也不自动授权新增强制测试、自动修复、逐项确认或另一套运行时。

## 逐项核对

| 原编号与结论 | 当前事实 | 判断 |
| --- | --- | --- |
| 1 无 Git 集成 | 编码工作台已有真实本地 status、工作区 diff、暂存区 diff、stage / unstage、初始化、commit、log。模型没有专用 Git 工具，可用命令执行。当前两区差异分别是工作区对暂存区、暂存区对 HEAD，没有合并的工作区对 HEAD 选项，也没有 branch / blame / 冲突工作台 / PR 专用入口。 | **部分成立**。专用模型接口与部分操作缺失，不能称没有 Git 集成。远端 / PR 按用户既定范围后置，不是本地编码前置条件。 |
| 2 无按次撤销 | 文件工作台已有选定 change 的 diff / restore，后端 `documents.restore` 反转该次变更，并对后续重叠内容返回冲突。模型没有同名一等恢复工具。 | **应用层不成立，模型入口缺口成立**。不是 Git commit revert；也不保证任何有后续改动的历史都可自动回滚。 |
| 3 仅字面搜索、无行号 | `search` 的确只有 query、单个 glob 和 limit，没有 regex、before / after、多 include / exclude。结果明确返回 path、line、text；发现已有全局忽略 / exclude_globs。 | **大部分成立，但“没有行号”错误**。缺前后文与每次查询的排除组合，不是完全没有排除。 |
| 4 没有测试 / 诊断闭环 | 没有通用结构化测试报告适配、项目诊断汇总或编辑后自动 lint 钩子；LSP diagnostics 是单文档。已有命令输出 / 退出码和通用 Run / Goal，能够按用户授权执行检查与修复。 | **专用报告能力缺失；不能据此说无法自验证**。用户已规定按需测试、未获修复授权先报告；不应机械补自动检查或失败即自修。 |
| 5 环境管理为零 | 设置已有 Python / venv、Conda prefix、uv + 已有 Python 的登记、探测与项目默认绑定。模型工具只读执行环境，不能专门登记 / 绑定；创建和安装可以在授权任务中用命令完成。没有统一包管理器 / 工具链版本面板。 | **“为零”不成立，自动发现与模型接口有限成立**。空 environments 只说明未登记；探测到 3.9.2 是目标项目实际选到的解释器，不能推断 Harness 自身基线变为 3.9。 |
| 6 无非 HTTP 后台任务 | `run_command` 默认 300 秒可由设置及 timeout_seconds 覆盖，并非固定上限；`start_service` 确实要求本地 HTTP ready_url。ConPTY `start_terminal` 可立即返回，承载非 HTTP 常驻程序，跨回复保留，读取 / 中断 / 关闭并清理进程树。 | **“无法管理非 HTTP”不成立**。缺的是独立于 PTY 的后台作业类型、通用 readiness、定时与重启策略；终端中的 shell 存活不等于每个内部命令成功。 |
| 7 无可用执行沙箱 | `sandbox` 目前是公开配置选项，真正启动返回 SANDBOX_UNAVAILABLE，没有有效本机 / 容器隔离后端。direct 为已确认默认。 | **成立，但属于已知未实现能力**。Job Objects、文件工具路径范围和变量筛选都不是进程级沙箱。用户可自己用 Docker 命令，不等于 Harness 已提供沙箱产品。 |
| 8 无密钥管理，只能参数 / 文件 | 模型凭据有专用环境变量解析；MCP 有环境变量引用、HTTP header 引用、加密令牌 / OAuth 存储，Windows 使用 DPAPI。项目执行环境会筛除敏感变量，目前没有可显式选择并注入任意业务秘密的项目 vault / secret_refs。 | **前半结论错误，项目运行凭据缺口成立**。不能建议把秘密明文放参数作为标准路径，也不能将 MCP 凭据能力说成已覆盖所有项目程序。 |
| 9 无项目级索引 | 没有自建全库符号索引、调用 / 依赖图或影响面分析；LSP 接口没有 workspace/symbol / callHierarchy。definition / references 可以返回跨文件位置，范围由服务实际能力决定。 | **专用索引 / 图能力缺失成立**。说只剩目录树和字面搜索忽略了已有跨文件 LSP。 |
| 10 无协作发现 / 端到端 / 跨会话来源 | 既有 DeepSeek 真实双成员闭环记录；最新修复已提供同任务候选、原因 / 开关 / 接入说明、按任务 / 文件的 list_changes 与 read_change。 | **对当前版本已过时**。原会话 links 为空并不证明系统没有能力；shell / 外部修改仍可能没有可识别的来源。 |
| 11 记忆仅词法且没有纠错 / 去重 | 没有向量语义检索；已有词法 + 分类 / 主体等结构过滤、可选关系召回、有效期、supersedes、停用 / 遗忘。后台按相关候选纠错、按原 ID 更新、唯一同名复用，并保护用户编辑 / 固定条目。自动产物不是先进入人工候选审批箱。 | **语义检索和人工候选箱缺失成立，“没有纠错 / 去重”错误**。模型提取仍会犯错，提示不能保证旧错误全部被清除。用户引用的 cab355cb 本轮未读取其当前条目，不断言仍启用或已删除。 |
| 12 摘要无主题到 seq 的盲区索引 | checkpoint 是 text + through_seq 等元数据，摘要提示要求少量 source_seq 和未知片段说明；read_history 已支持关键词、seq 和归档回读。 | **稳定结构化主题索引缺失成立**。不是完全没有来源引用 / 盲区说明；自然语言摘要中的引用也不等于完整主题索引。 |
| 13 manifest 34 与工具 52 不同 | RequestStarted 的 tool_names 从该次 definitions 生成，模型调用也传同一个 definitions；每轮刷新。get_context_status 返回最近 RequestStarted 及关联 message_id / 时间的清单，不是整个应用永久工具目录。模式、worker、MCP 发现和版本会影响实际定义。 | **历史数字差异待证实，当前源码未发现固定漏记这些 M5 工具的分支**。要判 bug 必须比较同 session / run / message 的请求事实；不能凭 34 / 52 宣布是硬编码。 |
| 14 list_files 无 size / mtime | 当前输出是路径数组、截断和跳过数量，没有 size / mtime。文件工具仍做唯一原文匹配和写入前内容比较，人工编辑有 base_content 冲突处理。 | **元数据缺口成立，“无法发现覆盖冲突”不成立**。mtime 只能辅助观察，不能替代内容冲突检查。 |
| 15 无统一 diff 应用 | patch_files 接受 edits 列表，逐项 old_text / new_text；没有原生 unified diff 解析器。 | **专用工具缺失成立**。可按任务用 git apply 等已有命令，不是 `.patch` 完全无法落地。 |
| 16 无通用 HTTP 请求工具 | web_fetch 面向公开网页文本 GET，无任意 method / body / headers 接口；命令和终端可用 curl.exe / PowerShell / Python 测试本地 API。 | **专用 HTTP 工具缺失成立，“POST / PUT 做不了”错误**。私有 API 的凭据传递与第 8 项应一并设计。 |

`tool_result` 与 `tool.completed` 也不能仅因名字不同判不一致：前者是模型可读来源分类，后者是事件日志类型；`runtime/messages.py` 明确完成投影。它们不是同一个字段的两种枚举值。展示应解释层次，工具总数也应标注当次请求和模式，不设置永久“52 / 25”真值。

## 主要源码依据

- Git：[服务](../../../src/my_agent/local_git/service.py)、[桌面](../../../apps/desktop/src/renderer/src/LocalGitPanel.tsx)、[RPC](../../../src/my_agent/rpc/m5_routes.py)。恢复：[DocumentService.restore](../../../src/my_agent/documents/service.py)、[编辑器](../../../apps/desktop/src/renderer/src/WorkspaceEditor.tsx)。它们没有作为专用模型工具加入 [装配入口](../../../src/my_agent/bootstrap.py)。
- 文件 / 搜索：[ReadTools](../../../src/my_agent/tools/read_only.py)、[忽略策略](../../../src/my_agent/tools/policy.py)、[补丁契约](../../../src/my_agent/tools/file_types.py)。搜索 match 明确含 line。
- 环境 / 运行：[类型及可调超时](../../../src/my_agent/execution/types.py)、[环境登记、变量处理及沙箱不可用反馈](../../../src/my_agent/execution/environments.py)、[桌面](../../../apps/desktop/src/renderer/src/EnvironmentSettings.tsx)、[终端工具](../../../src/my_agent/terminals/tools.py)、[终端生命周期](../../../src/my_agent/terminals/service.py)。
- 凭据：[模型解析](../../../src/my_agent/credentials.py)、[MCP 加密存储](../../../src/my_agent/mcp_client/credentials.py)、[引用与连接装配](../../../src/my_agent/mcp_client/service.py)。本轮未读取任何真实凭据值。
- LSP：[查询契约](../../../src/my_agent/intelligence/types.py)、[服务实现](../../../src/my_agent/intelligence/service.py)。记忆：[召回 / 保存](../../../src/my_agent/memory/store.py)、[维护纠错](../../../src/my_agent/memory/service.py)、[独立开关](../../../src/my_agent/memory/types.py)。
- 上下文：[请求清单与实际模型调用](../../../src/my_agent/runtime/loop.py)（128 / 167 行共享 definitions）、[get_context_status](../../../src/my_agent/context/tools.py)、[摘要与回读](../../../src/my_agent/context/service.py)、[结果预览与切点装配](../../../src/my_agent/context/window.py)、[来源分类投影](../../../src/my_agent/runtime/messages.py)。
- 最新协作事实：[本轮修复方案](../../plan/collaboration-usability-fixes.md) 与 [M5 进度](../../progress/m5.md)。

## 证据与不能推出的结论

1. 本轮执行了 Git 状态和限定文件的 rg / 源码读取，复核现有测试及进度；没有新跑模型、浏览器、终端、Git 或 LSP 验收。因此上表“已有”基于实际实现，旧验证只说明当时场景通过。
2. M5 已保存真实本地 Git、ConPTY、Pyright / TypeScript LSP、桌面编辑恢复及浏览器联合证据，并非全都停留在 schema。对应已有用例是 `test_documents.py`、`test_m5_terminals_git.py`、`test_m5_intelligence.py`、`test_m5_shared_bootstrap.py`；本轮没有重新执行它们。
3. `not_connected` 说明该实例当时未连接，不能推断浏览器实现没验过。M4 / M5 有本地点击、截图、会话隔离及退出清理记录；不据此保证用户当前实例依赖与网络一定可用。
4. 压缩并非只写了 preview / keep_recent 参数；已有工具结果缩短、切点摘要替换和历史回读实现及 M3 验证。对旧会话具体效果仍需对应请求材料，不根据参数存在宣称质量优良。
5. 本轮没有重新检查 `tmp_test.txt`、8123 端口或个人记忆 `cab355cb` 的当前状态，也没有删除文件、终止服务或改记忆。引用中的清理提议不是本轮操作指令。
6. 上轮工作图一次“保存结果与状态”未落盘仍未找到根因，不能用本轮能力核对覆盖这条已记录的观察。

## 后续优先级建议（不是实施授权）

1. 先改善高频搜索：regex、前后文、查询级 include / exclude，保持字面默认；复用已有搜索后端。
2. 接通现有能力的模型侧入口：优先 Git status / diff / log 和明确 change 的恢复，避免复制已有服务。副作用保持用户任务范围；不加入额外 Git / remote 前置条件。
3. 收拢能力说明：区分“模型可调用、桌面设置、项目未配置、功能未实现”和请求快照。给工具总数附正确归属，比扩大一份静态清单更实用。
4. 按实际业务补结构化测试结果 / 项目诊断汇总、项目秘密引用与注入。是否执行测试仍按任务决定；不增加每次编辑自动检查、逐候选确认或失败强制自修。

通用后台作业、沙箱、主题索引和符号图可分别规划；当前持久终端 / LSP / 回读已经承担部分职责，不需要因为评价列为 P0/P1 就全部重建。
