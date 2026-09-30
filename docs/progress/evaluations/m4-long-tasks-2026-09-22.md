# 长任务与多会话协作用户体验评估

日期：2026-09-22。状态：本轮体验完成，未修改产品。视角：长期项目负责人，需要保存共同约定、按阶段安排现有角色会话、交接工作并在重启后接续。

本轮仅测试与评价，不修改产品、个人项目或个人数据，不调用真实模型 / 外部账户，不提交或推送。当前工作区含既有 M4 未提交修改；使用当前桌面构建，复用真实 Electron、生产 RPC / 存储 / 工具和 `tests/support/desktop_peer.cjs` 中的模型替身。替身摘要、召回答复与 token 数值不代表真实模型质量。

实际执行两条隔离用户路径：

1. 创建长期任务，保存共同事实，手动建立角色会话与七阶段关联，发送普通协作消息和 handoff，重启核对持久化及不重复执行。
2. 保存并纠正项目记忆，检查跨会话的实际请求材料、历史折叠与压缩入口，启动局部 Goal 后主动停止 / 取消并重启。

数据与截图统一保存在本仓库 `.artifacts/tests/persona-long-tasks-*`；测试源码为 [persona-long-tasks.spec.ts](../../../tests/desktop/persona-long-tasks.spec.ts)。以下结论基于实际点击、生产 API 返回和已查看的截图；没有进行全量回归或模型质量评比。

## 结论

两条路径都形成了可用的接续闭环。任务共同事实、角色和阶段覆盖可以持久化；handoff 有来源简报和目标会话结果；纠正后的记忆进入新会话的实际请求材料；主动停止 Goal 在重启后仍为暂停，取消后普通问答不重新激活它。本轮未发现 P1 / P2 实测缺陷。

长期负责人主要要付出的操作成本是寻找分工身份与既有协作约定入口。下面两项为 P3 体验摩擦；不将保存协作约定、主动停止或不自动创建会话视为错误设计。

## P3-L1：新角色会话在任务树和阶段关联处缺少角色名称

- **类别**：实测体验摩擦，数据未丢失。
- **用户目标**：先手动建立“实现”“文档”等长寿命会话，再为它们分配不同阶段，之后按角色找回。
- **步骤**：新建任务 → 创建新的工作会话 → 角色填“文档接续”并填写范围 → 返回任务流程，为该会话选择“交接”。
- **预期**：阶段选择行与左侧树能直接辨认已经填写的角色；尚未发消息也能识别。
- **实际**：角色已保存，协作目标下拉能显示“文档接续”；任务树与阶段行仍只显示“新会话”。发送首条消息后改成消息标题，阶段行仍不显示角色。当前场景仅两个会话尚能凭位置区分；多个新会话时更难判断哪个阶段属于哪个角色，这是根据已见呈现方式的影响推断，本轮未堆建大量会话。
- **证据**：[阶段行截图](../../../.artifacts/tests/persona-long-tasks-workflow-5nL9gc/02-role-stage.png)（已查看）；[协作目标与持久角色](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/facts-before-restart.json) 中 `before.data.summary.role` 为“文档接续”；[交接结果截图](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/03-handoff-result.png) 明确使用该角色。
- **源码定位**：`apps/desktop/src/renderer/src/TaskNavigation.tsx:139` / `:145` 的 tooltip 与正文都只用 `session.title`；`apps/desktop/src/renderer/src/Workflows.tsx:424` / `:426` 的行标题和阶段标签只用 `m.title`。
- **最小建议**：在现有树节点和阶段关联行加角色副标题，或采用“角色 · 标题”；保留原会话身份和用户标题，不增加创建表单或自动创建会话。

## P3-L2：普通协作消息的发送入口未就近说明需先保存约定

- **类别**：实测体验摩擦，后端按既定设计返回错误，草稿保留。
- **用户目标**：向同任务已存在的“文档接续”会话发送端口变更补充，暂不唤醒它工作。
- **步骤**：会话选项 → 会话协作 → 选择该会话 → 展开普通协作消息 → 填内容 → 点击“发送给所选会话”，此前尚未保存双方约定。
- **预期**：发送处能看到尚未保存协作约定，并能就近进入已有分工保存操作。
- **实际**：发送按钮可点击，点击后面板顶部才显示“尚未设置这两个会话的协作约定”。发送区在协作目标 / 分工表单之前，窄浮层内需要继续滚动寻找保存入口。输入仍在；按现有设计填写分工并保存后，同一消息成功保存待接收，目标会话空闲时没有启动模型，随后 handoff 请求实际带入消息。
- **证据**：[首次错误截图](../../../.artifacts/tests/persona-long-tasks-workflow-2dO2dv/failure.png)（已查看）；[最终场景同一入口证据](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/03-message-needs-agreement.txt)；[交接后消息状态](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/03-handoff-result.txt) 为“已纳入模型输入”。
- **源码定位**：`apps/desktop/src/renderer/src/Collaboration.tsx:287` 发送按钮只检查目标和消息；`src/my_agent/collaboration/service.py:486` 在普通消息投递时读取既有约定，`:107` 返回 `COLLABORATION_NOT_LINKED`。
- **最小建议**：在消息发送区就近提示“先保存与此会话的分工约定”，提供滚动到已有分工表单的入口。保留用户显式保存约定的设计，不自动绕过或新增授权步骤。

## 好用之处与实际覆盖

| 用户路径 | 已完成的实际动作与结果 | 证据 |
| --- | --- | --- |
| 任务 / 七阶段 | 创建任务和首会话；保存目标、进度、端口结论；默认七阶段齐全；当前阶段改为“实现”，目标角色覆盖为“交接”；重启两项关联及共同结论均保留 | [任务重启截图](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/05-restarted-task.png)、[重启事实](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/result.json) |
| 手动协作 / handoff | 新建已有角色会话；普通消息保存后无活动运行；明确点击 handoff 后目标真实读 `main.py`；简报带当前任务版本、端口结论和说明；结果返回；重启目标 run_id / watermark 未增加 | [交接结果截图](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/03-handoff-result.png)、[重启前事实](../../../.artifacts/tests/persona-long-tasks-workflow-KvhVpI/facts-before-restart.json) |
| 记忆查看 / 纠错 / 跨会话召回 | 用户显式保存“端口 8000”，编辑为“8123”并优先召回；新建接续会话实际请求清单带纠正后内容，未带旧的“端口 8000” | [纠错截图](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/01-corrected-memory.png)、[新会话实际材料截图](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/04-new-session-materials.png)、[事实 JSON](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/result.json) |
| 上下文 / 历史 | 历史关键词返回 3 项；展开片段后加入提问；切到任务再回会话时选择仍在；发送后实际材料记录可看；手动压缩得到 checkpoint，并显示“压缩后待计量” | [历史片段](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/02-history-fragment.png)、[压缩入口与状态](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/03-context-compacted.png) |
| 局部 Goal / 停止 / 重启 | 启动替身等待 Goal → 点击“停止运行” → `paused`；退出后重启仍为暂停且无活动 Run；明确取消后普通问答完成，旧 Goal 只留已取消历史卡 | [停止截图](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/05-goal-stopped.png)、[取消后的普通对话](../../../.artifacts/tests/persona-long-tasks-memory-YpKZLz/06-cancelled-goal-history.png) |

已人工查看任务阶段、协作错误、handoff 结果、新会话实际材料、停止 Goal 的截图。其他截图作为同一脚本的补充证据留存，没有把截图生成本身写成全部视觉验收。

## 验证命令与测试适配记录

- `npm.cmd --prefix apps/desktop run test:desktop -- persona-long-tasks.spec.ts`：最初沙箱 `spawn EPERM` 未进入场景；获准在沙箱外用相同隔离命令运行。不是产品启动故障。
- 初次脚本漏传既有 `getSession` 边界必需的 `before_seq: null`，另有 `role=status` 多匹配、保存列表仍折叠的选择器假设，均只调整本轮测试脚本；不列产品问题。
- 普通消息首次未保存约定返回真实错误，改为保留此体验观察，然后经 UI 保存既有约定并继续。
- 批次 `persona-long-tasks-workflow-5nL9gc`：handoff 已开始且 `read_file` 成功，但既有 `DesktopModel` 的 `if "wait" in prompt`（`tests/support/agent_peer.py:120`）匹配了完整简报里来源 Run 的 `waited_seconds`，导致替身无限等待，最终测试 120 秒超时。未修改模型替身或产品；最终场景从尚未运行的来源会话 handoff，准备对话移到目标会话，避开测试标记。这个失败不证明真实 handoff 会挂起，带来源已完成 Run 的完整交接没有在本轮成功验收。
- 上述批次的记忆 / 上下文 / Goal 场景 **1 passed，14.0 秒**，最终产物 `persona-long-tasks-memory-YpKZLz`。
- `npm.cmd --prefix apps/desktop run test:desktop -- persona-long-tasks.spec.ts --grep associates`：仅复跑受替身影响的交接场景，**1 passed，11.8 秒**，最终产物 `persona-long-tasks-workflow-KvhVpI`。两个场景有分别通过的证据，没有为了形成单一绿灯重复跑已通过场景。
- 本轮未重建桌面，使用现有最新 M4 OAuth 构建；未调用真实 Go 模型或外部服务，未使用个人数据根，未更改系统网络；没有提交 / 推送。

## 覆盖限制与下一步

- 当前是短路径的真实 UI / RPC / 持久化验收，模型文本、摘要和报告 token 数均为固定替身。它证明材料走通、状态可接续，不能证明 800K 输入表现、真实摘要保真度、中文召回质量或连续数小时协作质量。
- 未测遗忘后自动提取抑制、跨项目派生记忆纠错、活动 Goal 移交、继承完整有效上下文、同文件并行冲突、真实模型主动协作和异常掉电。本轮不据此宣称通过或失败。
- 没有发现需要立即停止当前开发或回滚的产品问题。建议后续若用户授权调整，先改善角色在导航 / 阶段表的辨识，再改善普通消息处的约定提示；真实长任务质量继续单独观察。
