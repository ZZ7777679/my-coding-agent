# 诊断与实验 / Diagnose and experiment — v1

从可观察现象、触发条件和当前环境建立最小假设。优先读取既有日志和证据，必要时只运行能区分假设的实验；记录真实请求、结果、限制和未确认原因。

Build a minimal hypothesis from observed symptoms, triggers and environment. Prefer existing logs and evidence; run only experiments that distinguish plausible causes. Record real requests, results, limits and unconfirmed causes.

不要为使诊断通过而修改全局环境、代理、权限或隐式安装依赖。诊断请求本身不授权修复。实验失败作为观察记录，实际调用 / 执行故障停止并保存可接续的信息。

Do not alter global environments, proxies, permissions or install dependencies merely to pass diagnostics. A diagnostic request does not itself authorize repairs. Preserve failed experimental outcomes as observations; stop on actual execution faults with enough information to resume.
