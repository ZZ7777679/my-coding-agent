# M2 上传前代码与提示一致性审查

> 日期：2026-09-18。基线：`dev` / `db31fc3` 之后尚未提交的 M2 工作区。
>
> 结论：本轮确认的 M2 问题已修复，相关验证通过，未留下本轮已知的提交阻塞。此结论针对下面列明的范围，不代表全仓无缺陷、真实模型体验重新验收或安装包已可发布。当前未提交 / 推送。

## 1. 检查范围

- 系统提示、六个内置工作方法、工具描述 / 参数 schema 与实际调用链是否一致。
- 普通 / Plan / Goal 的报告、失败分类、插话、终态历史与可调预算。
- 文件读写、直接本机执行、服务生命周期、联网工具、定向会话协作及结果读取。
- Electron / Python 接入、协作入口、程序卡片、历史恢复与生成协议。
- 与 M2 有关的硬编码和额外门槛；对照此前 [DSH 检查表](runtime-checks-dsh-review.md) 和 [M3 审查](m3-design-review.md) 中已经涉及现有代码的分支。

采用定向静态阅读、既有离线检查和真实桌面 / 本机程序场景。模型为可控替身；不重发用户会话，不修改个人数据和网络配置，不借本轮实施 M3 新模块。

## 2. 已修复问题

| 编号 | 级别 | 触发与原问题 | 本轮修正 |
| --- | --- | --- | --- |
| M2-R1 | P1 | A 请求 B、B 回问 A，即使没有互等也会触发祖先 / 请求图循环拒绝；Goal 真正等待时，用户插话只能等工具返回 | 删除投递前的请求图检查；仅记录正在等待的运行，实际互等时返回现状与原因。状态事件唤醒等待，插话先答后继续，保留原请求 |
| M2-R2 | P1 | 合法长回答超过单次工具预算后，`read_collaboration` 或单条 `read_session` 报错并终止任务 | 长结果按字符偏移读取，历史以固定 `entry_seq` 读取完整 JSON 片段；按实际序列化字节选分页长度。投递与列表只给必要状态 / 来源，正文按需读取 |
| M2-R3 | P1 | 空项目没有 README 等常见文件，模型试读后收到笼统 I/O 错误，整个 Run / Goal 停止 | 把实际不存在明确分类为 `FILE_NOT_FOUND`，保留错误事实并交回模型调整路径或创建；真正访问 / 执行 / 保存故障仍报告实际失败 |
| M2-R4 | P1 | 会话选项按省略号右对齐，宽弹层伸到左侧栏下方，保存协作约定按钮被遮挡而无法点击 | 弹层相对整个输入区定位，宽度受当前输入区约束。真实桌面点击、发送协作及重载回读已通过，没有用强制点击掩盖遮挡 |
| M2-R5 | P2 | 系统提示仍把证据引用写得像必填；Goal 工具描述混入普通请求的 `return`；Plan 的“所有写入禁用”与应用内报告矛盾 | 说明最小报告是 summary / outcome、引用可选；按当前运行生成对应 outcome 描述；区分项目文件 / 程序操作与应用内报告。修正完成条件的旧说明并重新生成协议 |
| M2-R6 | P2 | 程序控制进行中若卡片折叠 / 隐藏导致读取代次改变，操作返回后可能无法释放 busy 状态 | 折叠不重建读取代次，控制结束释放 busy；持续读取仍按程序身份和可见性管理 |
| M2-R7 | P2 | `collaboration.history` 宣称只给已提交历史，却只清理正文实时预览，没有清理实时思考 / 模型阶段 | 公开历史快照一并清空未提交的思考、流模型身份和阶段；不修改持久历史或正文来源 |

主要位置：

- [协作服务](../../src/my_agent/collaboration/service.py)：`submit`、`result`、`history`。
- [协作模型工具](../../src/my_agent/collaboration/tools.py)：`text_page`、读取游标与精简回执。
- [运行提示](../../src/my_agent/runtime/modes.py)、[报告工具](../../src/my_agent/workflow/tools.py)、[错误分类](../../src/my_agent/runtime/loop.py)。
- [文件路径](../../src/my_agent/tools/policy.py)、[读取工具](../../src/my_agent/tools/read_only.py)。
- [程序卡片](../../apps/desktop/src/renderer/src/ProgramCards.tsx)、[弹层布局](../../apps/desktop/src/renderer/src/style.css)。

## 3. 提示与实现核对结果

| 对照项 | 核对后的实际行为 |
| --- | --- |
| 常规 / Plan | 常规按请求读写和执行；Plan 无项目命令执行，只有明确的计划文档可写。应用内报告可以保存；未提供的工具不由提示虚构 |
| 工作报告 | 普通 / Plan 的 outcome 为 return / wait；Goal 工作为 continue / complete / wait；普通插话不提供报告工具。引用、逐项验收表和工作图均非完成前置条件 |
| 文件编辑 | path / old_text / new_text，无模型 hash、无强制重复读取。保留唯一匹配及写入期间实际内容变化反馈。旧 hash 参数仅兼容接收，内部摘要只用于历史恢复辨认 |
| 程序执行 | 选定项目没有环境绑定也可直接使用本机环境；旧 trusted 字段不是门槛。支持实际遇到的 command 对象或 JSON 对象字符串；测试非零退出码作为结果报告，不一律当启动故障 |
| Goal | 正常工作连续推进；完整边界处理插话；实际调用故障停止。完成 / 取消的目标作为历史保留，不再冒充当前目标，输入区不占用终态卡片 |
| 协作 | 已有会话与用户安排的角色范围；不自动创建正式会话。投递、当前等待与结果返回分开处理，读取工具本身不请求模型 |
| 搜索与模型 | 主对话仍使用用户选择的 Go 双模型之一；原生搜索辅助调用与主对话选择分开、计入请求使用；本轮不新增真实网络生成请求 |
| 预算 / 路径 | 预算来自集中配置 / 设置快照；E 盘默认路径可覆盖。未增加版本相等判断、哈希凭据、证明表、信任勾选、固定协作轮数或默认 worktree |

## 4. 验证与失败记录

### 后端

使用 `.venv/Scripts/python.exe -X utf8 -m pytest -q`，选择 `tests/python/` 中以下已有组：`test_agent_core.py`、`test_file_changes.py`、`test_execution.py`、`test_goal_controller.py`、`test_goal_records.py`、`test_work_reports.py`、`test_collaboration.py`、`test_tasks.py`、`test_web_tools.py`、`test_go.py`、`test_rpc.py`。

- 首批 **65 通过、1 失败，25.19 秒**。失败为 `test_owned_tree_cleanup_and_owner_death` 的零等待句柄观察；退出发起后立即观察曾返回等待状态。产物：`.artifacts/tests/python-be902ac23d054bd19aeb5b4a206426ff/`。
- Windows 的外部进程终止是异步的；`TerminateJobObject` 对各进程具有 `TerminateProcess` 效果。该用例改为与其“宿主异常退出”分支相同的有界句柄等待，仍必须真实观察到退出，没有删除断言，也没有给产品增加新的清理门槛。[Microsoft TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)、[TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)。
- 新增空项目缺文件场景后，相关 14 项定向复核 **13 通过、1 失败，2.66 秒**；进程清理与新场景均通过，失败只因旧读取测试仍期待 `FILE_UNAVAILABLE`。按新分类更新该预期后，单项 **1 通过，0.28 秒**。产物分别为 `.artifacts/tests/python-e9251fc7abf1479b95fdae95974d22ba/`、`.artifacts/tests/python-69a4266ae44743b98738bb04ae26b960/`。
- 因而本轮覆盖的 **67 个不同后端用例均已有通过证据**；没有为汇总一个全绿数字再次整组重跑。新增协作场景直接覆盖双向投递 / 真实互等、等待中插话接续、长中文结果与历史完整还原；报告用例同时核对当前提示的 outcome 与 schema 一致。
- 最后在既有协作用例中补充“接收方确有实时思考，公开历史仍只含提交内容”的断言，单独复核 **1 通过，0.66 秒**；不增加模型调用或独立测试框架。

初次沙箱执行 pytest 因新建隔离目录访问失败而未运行到业务断言；按已授权的本机测试范围重跑成功。Ruff 初次缓存路径指向工作区外，改用 `--no-cache`；没有修改全局缓存 / 系统权限。

### 协议、类型与桌面

- Ruff `check --no-cache src tests scripts` 通过；format 检查 **130 文件**通过；mypy `src/my_agent` **89 源文件**通过。
- `scripts/export_schemas.py --check`、`npm.cmd --prefix apps/desktop run types:check`、`typecheck`、`build` 通过；受影响前端 / 测试文件 Prettier 通过。schema 与 TypeScript 从源定义生成。
- `npm.cmd --prefix apps/desktop run test:contracts`：**102 通过**。首次沙箱中 Node 子进程 `spawn EPERM`，本机同一检查通过，未改契约预期。
- `test:desktop -- collaboration.spec.ts execution.spec.ts goals.spec.ts`：首次 **1 通过、2 失败**。Goal 通过；协作暴露上述真实弹层遮挡；执行用例在重启后没有展开任务树就找会话。
- 修复弹层后，协作 / 执行用例均按实际左侧项目 → 任务 → 原会话重新进入，不要求产品自动恢复页面；只重跑这两个失败场景，**2 通过，17.7 秒**。重载后实际 Run / 水位、历史卡片和服务已停止状态仍核对，没有放宽持久化断言。
- 已查看最终截图：`.artifacts/tests/desktop-collaboration-cCGRWC/result.png`、`.artifacts/tests/desktop-execution-qHq8v1/program-cards.png`。Goal 首次通过产物为 `.artifacts/tests/desktop-goal-oPHzxk/`。程序卡片的忙碌清理做静态分支核对，未额外制造单独的延迟交互测试。

桌面使用真实 Electron / preload / Python / 文件 / PowerShell / 环回 HTTP，模型替身。原失败 trace 保留于 `.artifacts/tests/desktop-results/`，不把本轮离线检查当成 Go 的延迟或商业模型成功率测量。

## 5. 保留的边界与 M3 接续

- M3 的压缩、长期记忆、临时子 agent、持久协作等待和主动投递后的自动接续仍未实施。当前长等待仍计入 Run 时间；本轮只解决等待中无法响应插话的问题，不宣称完整等待调度已经完成。
- [M3 审查](m3-design-review.md) 的 R2、R5 已在 M2 修复；R1 的插话部分已修复，持久等待 / 计时部分继续保留。其余设计问题不借 M2 上传扩大实现。
- 任意大任务定义、很长单行文件、应用总历史仍受现有可调输入 / 输出容量约束。此次分页针对协作正文和单条公开历史，不冒充统一归档或上下文压缩。
- 没有重跑付费 Go、VPN / 直连、真实模型多人协作或安装包验收；Conda / uv 各种本机配置、Docker / WSL / 沙箱不因本轮检查变成已验收功能。

## 6. Git 上传准备

当前在 `dev`，基线 `db31fc3`；暂存区为空。M2 多数新模块仍是未跟踪文件，上传时不能只提交已有 tracked 文件的 diff。

- M2 实现范围：`src/my_agent/` 的任务、工作方法、Goal、协作、文件修改、运行环境 / 程序、网页工具，以及现有运行 / 会话 / 模型 / RPC 装配；相应桌面模块、协议 v3 与生成脚本、集中测试和 fixtures。
- M2 文档范围：AGENTS、README、初版 / M2 / 运行环境 / DSH / 界面方案，本审查报告及 M2 进度；保留 M0 / M1 原有同步历史。
- 已有 M3 规划、调研与审查文档仍保留，建议与 M2 实现分成文档提交。若同批上传，以实际相对链接依赖收齐文档；不能把 M3 文档存在说成功能已实现。
- `.artifacts/`、虚拟环境、node_modules、out、个人路径文件与环境凭据继续按现有忽略规则排除。没有新依赖、锁文件修改、数据库迁移或 Git 历史重写。
- 下一次执行提交 / 推送前显式核对暂存文件、远端和分支；本轮只准备审查结果，没有执行 commit、merge 或 push。

收尾文件检查：本轮 10 份文档 UTF-8 / LF、代码围栏及 151 个本地链接通过，`git diff --check` 通过。当前 182 个修改 / 未跟踪文件（含既有 M3 文档）已列入忽略提交的 `.artifacts/tests/m2-release-review/git-file-inventory.json`，未出现个人路径文件、环境文件、构建目录或测试产物误入候选清单。清单用于接续盘点，不代替真正提交前的暂存差异检查。
