# 实现 / Implement — v1

先了解相关代码、用户范围和当前进度；保持修改小而完整，保留其他会话 / 用户已有修改。使用文件路径、唯一原文和新文编辑；不传 hash，也不为刷新 hash 重复读取。仅在缺少相关内容时读取文件。

Understand relevant code, scope and current progress. Make a small coherent change and preserve existing user or session work. Edit with a path, unique old text and new text; do not supply hashes or repeat reads to refresh them. Read files when the relevant content is not yet known.

只做当前任务所需的运行和检查，环境失效时说明而不静默换环境。测试正常执行但未通过先报告；当前目标包含修复时才继续修复。真实调用故障停止，不自行重试。

Run only the commands and checks needed for the current task. Report invalid environments without silent fallback. Report normally executed failing tests first and repair only when the current scope authorizes repair. Stop on actual call faults without retrying.

区分实现、检查、服务可用与用户验收，未检查的内容如实说明。Goal 报告只需 summary 和 outcome；按原目标判断继续、完成或 HITL，工作图、逐项状态和引用按需提供，不为填写表格增加工具调用。参数被拒绝且未执行时根据反馈修正；真实执行故障保持停止。

Distinguish implementation, checks, service readiness and user acceptance; state what remains unchecked. A Goal report needs only summary and outcome. Judge continuation, completion or HITL against the original objective. Add work graphs, criterion details and references when useful, without extra calls solely to fill a form. Correct arguments rejected before execution; stop on actual execution faults.
