# 运行检查与 DSH 对照

日期：2026-09-18。依据用户本轮要求，检查运行中的额外校验、重复审查和固定门槛，并直接实施简化。本文记录本次变更，后续相关规则以本文及 AGENTS 为准；旧 progress 中的失败与修复经过保留。

## 1. 基准与结论

基准是官方 `deepseek-ai/deepseek-harness` 的固定提交 [0d1f50007f9bca3f52b06e1c3074fa14d5fb0720](https://github.com/deepseek-ai/deepseek-harness/tree/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720)，与此前网络调研相同。许可证为 [MIT](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/LICENSE)。只参考实现方式，自行修改本项目，没有引入上游运行时。源码及下载记录在 `.artifacts/research/deepseek-harness/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/`；不是对用户当前 DSH 安装或个人配置的验证。

两次实测阻塞都属于本项目实现问题：报告 schema 与执行条件不一致；连续编辑返回新 hash，却只接受旧缓存。前者不应靠模型补表解决，后者也不应靠额外读取绕过。本次进一步移除报告审查、路径写法限制、环境前置登记和无依据的数值估算。

DSH 的 [默认装配][dsh-base] 实际启用了 workspace-write、ask 和文件观察策略。因此“DSH 没有校验”不是源码事实。本次比较的是同类能力的真实触发条件，**不把上游更严格的默认值反向引入本应用**。本产品已有的可信本机执行、可选沙箱、失败停止、手动正式会话及角色协作选择继续按用户决定实现。

## 2. 已移除或简化的门槛

| 位置 | 原行为与问题 | 对照及本次处理 |
| --- | --- | --- |
| 文件编辑参数 | 模型需传 hash，连续编辑还依赖运行内旧缓存 | DSH 在 [编辑工具][dsh-edit] / [观察策略][dsh-observe] 内维护版本。我们移除模型 hash 和 observed 缓存，编辑只需路径、原文、新文；同日进一步按用户确认取消工具返回摘要，写入前的内容变化交回模型调整，不终止整个 Goal。 |
| 历史快照重复校验 | 每次读取历史都重新核对前后摘要，读取失败可使整轮停止 | 按用户确认删除快照摘要校验，diff 直接来自保存的前后内容；无法读取的记录保留局部错误，不影响后续工具执行。摘要只留作宿主中断状态辨认，模型成果工具不返回它。 |
| 路径表达 | 项目内绝对路径被当成非法路径；读取限制在项目内 | DSH [本地文件后端][dsh-fs] 接受绝对 / 相对路径，沙箱写入边界另行处理。读取允许明确的项目外路径及链接，写工具接受项目内绝对路径；默认扫描不顺带遍历项目外目录。 |
| 忽略文件 | .gitignore、dist、build 等用于直接拒绝读取和写入 | DSH 直接 read / edit 不把搜索忽略规则当权限。现在忽略只用于全项目发现，明确文件和子目录可直接访问。 |
| 文件名黑名单 | .env、.npmrc、auth.json、.key 等一律拒绝，包括普通配置或测试样本 | 本次核对的 DSH 文件后端没有这套名称门槛，已移除。应用自身 Go 凭据继续由专用解析器持有，不能主动把真实凭据加入上下文。 |
| 硬链接 | 普通读取因 st_nlink > 1 被拒绝 | DSH 的读取不以链接数拒绝，已移除该条件；本项目编辑采用替换路径的文件写入语义。 |
| .gitignore 大小 | 固定超过 64 KiB 即无法可靠发现源码 | 已删除独立大小门槛；仍解析嵌套忽略规则，指定路径访问完全不依赖它。 |
| 报告引用 | 工具、日志、Goal 结算、任务同步四处重新核验引用 | DSH [Goal 工具][dsh-goal] 不要求提交会话 seq 证据表。删除 verify_reference / verify_report 及调用；宿主仍记录报告真正来自哪个 Run。模型附加引用明确为模型信息。 |
| 报告完整性 | 完成工作必须附引用；每轮 Goal 必须填写全部原始条件，complete 要求逐项 met | DSH 完成动作依赖模型判断与目标身份，不做此类证明。现在最小输入为 summary / outcome，条件、工作项、下一步、引用都可省略。原用户目标仍原样保存。 |
| 模式定义 | 普通请求 schema 暴露 continue / complete，执行时再拒绝 | 普通 / Plan 工具 schema 只暴露 return / wait，Goal 暴露 continue / complete / wait；消除定义与执行的不一致。 |
| 可选工作图 | 缺依赖、环、完成项的前置状态未更新，都能使报告同步失败 | DSH [todo][dsh-todo] 是进度快照，不是强制执行证明。移除报告图审查，保留描述；图不能选出下一项时回到原 Goal，由模型判断下一步或提问。 |
| 共享工作项版本 | 另一个会话更新同一进度项，旧报告会被拒绝并使 Goal 停止 | 参照 DSH 进度快照的最新写入语义，采用最新报告；所有旧任务版本保留，报告不覆盖用户维护的目标 / 约束 / 决策。 |
| 每工具任务版本 | 模型生成期间任务字段变化，随后写工具被全部拒绝 | 移除 scope_key 及逐工具比较。每个模型请求前刷新共同信息；立即停止仍用停止入口，而非把编辑元数据变成隐式审批。 |
| 未执行的参数错误 | schema 错误、原文不匹配等与执行故障一样终止整轮 | DSH [工具调度][dsh-calls] 会把普通工具错误交回模型。现在参数、匹配、写入前的文件变化、已存在目标、类型、未知工具和需要显式 shell 的反馈可修正；历史成果读取问题也仅作用于对应记录。宿主不重放调用，下一次模型选择照常计量。 |
| 缺少 report_work | 一个完整的纯正文回合导致 Goal 以 GOAL_REPORT_MISSING 失败 | DSH [Goal 续跑驱动][dsh-driver] 根据仍活动的目标推进下一轮。现在继续原 Goal；仍须显式 complete / wait 才改变相应目标状态。 |
| 环境必需登记 | 项目运行普通系统命令也必须先导入一个环境 | DSH [PowerShell 执行器][dsh-pwsh] 使用已有本机工具。所选项目未绑定时直接使用本机工具；特定 Python / Conda / uv 环境按需绑定，显式绑定失效不静默切换。 |
| 独立信任开关 | 没有环境配置的项目默认 trusted=False，普通命令仍被 PROJECT_NOT_TRUSTED 阻断 | 原审阅错误地把独立勾选解释为用户要求，预先绑定的测试掩盖了默认路径。按同日用户反馈移除 UI 开关与执行闸门；旧字段仅兼容，不参与判断，模型工具结果不再暴露该字段。 |
| 环境重复核对 | 启动接纳和准备落盘之后再次读取完整配置、核验权限 | 删除第二次 confirm，接纳时取快照，后续设置作用于下一次启动；在途进程可直接停止。 |
| 环境白名单 | 未列入固定列表的正常工具变量被无声丢弃 | 对照 DSH [子进程环境][dsh-env] 的继承后筛除方式，继承普通配置，筛除 KEY / PASSWORD / SECRET / TOKEN 名称及 MY_AGENT_ 应用变量；选定环境再覆盖路径，不打印整份环境。 |
| 命令长度估算 | 按 argv 的 JSON UTF-8 长度 64000 预判 Windows 命令一定不支持 | 删除该估算。真实命令经执行器启动，系统错误按实际原因报告；显式 PowerShell 与参数数组的区别保持。 |
| 上下文估算 | 输入加上 max_output_tokens × 4 后超过字节预算即拒绝 | 移除跨单位推算，只比较实际序列化输入与用户设置的上下文字节预算。 |
| 流封装比例 | 累计 SSE JSON 超过正文预算 × 32 即中止，可能正文很短但分片很多 | 删除倍率条件；实际累计内容及单事件仍使用用户输出预算，接收字节只用于观测。 |
| 工具索引 | index 大于 255 被当成协议错误 | 删除该固定值；索引只需是非负整数，完整参数和调用 ID 配对仍校验。 |
| 历史累计大小 | 会话 / 任务日志累计 64 MiB 后拒绝读写、要求新建会话 | 删除累计生命周期容量上限。单条记录仍遵循传输 / 存储帧容量；历史仍使用现有内存投影，本次没有做大规模历史性能优化。 |
| 网页 DNS | 无论实际连接方式，先要求本机解析目标域名 | DSH [HTTP provider][dsh-http] 在代理路由下交给代理解析。现在根据 HTTPX 实际传输选择，仅直连预检；NO_PROXY 使用同一路由选择，没有添加代理配置或探测。 |
| 网页内容与状态 | 404、空 HTML 正文直接成为工具故障，+json / +xml 文本被拒绝 | DSH [HTTP provider][dsh-http] 返回实际状态与可解码正文，[类型规则][dsh-http-policy] 支持结构化后缀。现在同样返回状态 / 正文，空正文可见，桌面显示 HTTP 状态；网络中断仍是实际故障。 |

## 3. 核对后继续保留的条件

下面是具体职责依据，不是以笼统的“安全”为理由保留所有检查。

| 条件 | 保留依据 / 作用范围 |
| --- | --- |
| 完整 JSON、类型、必需字段、未知字段、工具 ID 配对 | DSH [工具定义 / 分发][dsh-tools] 同样校验完整参数。协议不完整不能解释成另一项动作；参数错误反馈与执行故障已经分开。 |
| 原文唯一匹配、写入期间真实内容变化、create 不覆盖 | 保留精确编辑的必要语义：不能确定位置或准备后内容改变时本次不写入，反馈给模型读取 / 调整。当前直接比较内容，不以 hash 或旧读取记录准入；局部冲突不结束 Run / Goal。 |
| UTF-8 文本 / 二进制区分 | DSH [文件后端][dsh-fsio] 也按文本能力区分。当前工具没有二进制编辑能力，不冒充支持。 |
| 项目写工具的真实路径归属 | DSH [workspace-write 文件后端][dsh-fs-sandbox] 有同类写入边界。读取门槛已放开；项目进程仍按用户选择本机直接运行，不能把文件工具边界当系统隔离。 |
| Plan / Review 模式、正式会话由用户创建、协作角色 | 用户已经明确选择的产品行为，且 DSH 也有模式 / authority。没有新增确认弹窗；模式不符仍不能暗中执行写入。 |
| 真正失败停止、无隐式重试 | 用户此前明确要求。网络、实际执行、保存故障及不确定副作用仍停止；按同日最新确认，输入反馈、未写入的文件冲突和单条历史读取问题不终止任务。 |
| 用户设置的请求 / 工具 / 时间 / 内容预算 | 用户已在界面调整并确认保留，累计 Goal 账本含辅助搜索。移除的是未说明的额外倍率 / 固定索引 / 历史寿命，不是清空用户预算。 |
| 显式环境失效、所选沙箱尚不可用 | 只影响用户明确选择的环境 / 执行方式，不静默换解释器或退回直接运行。没有绑定则使用本机工具；项目信任布尔开关已移除，不再作为保留条件。 |
| 程序所有权、取消清理、HTTP 服务监听归属 | 对应运行卡片“应用启动 / 保留 / 退出时停止”的实际承诺。不能把另一个既有服务显示为新启动成功；仅 start_service 做就绪检查，普通命令不依赖 HTTP 或端口探测。 |
| 公开 URL、无凭据、文本类型、直连 DNS、重定向容量 | DSH HTTP provider 也有这些条件，甚至默认拒绝跨源重定向；本项目不额外照搬更严格的跨源限制。代理 DNS 的额外门槛已修正。 |
| 会话角色访问、忙碌排队、失败状态不自动唤醒、协作等待 | 用户选择的已有会话协作方式。2026-09-18 收尾审查移除了“回到委派祖先 / 在途请求成环就拒绝”的额外门槛；允许正常双向投递，仅在实际互等时返回当前状态与原因，保留请求。Goal 等待期间可先处理插话；不按任务长度 / 文件数设置门槛。自动子 agent 仍未实现。 |
| 日志身份 / 配对、单写者、原子保存、幂等、中断不重放 | 属于应用事实与用户数据的存储契约，DSH 也区分 session、goal revision 和执行记录。移除的是对报告语义重复审查，不修改用户文件或重置损坏记录来伪造成功。 |
| UI 页容量与 JSONL 单帧容量 | 有继续读取入口的传输分页，不是任务数量 / 工作规模上限。单帧与有限 preload / renderer 仍属于桌面通信契约，没有新增审批。 |

## 4. 对用户可见的变化与验证

> **同日实测补正：** 原审阅遗漏了工具参数包装兼容与错误反馈。GLM 四次将有效 command 对象作为 JSON 字符串传入，`ProjectTools` 以通用 schema 错误拒绝；仅有底层执行服务验证不能覆盖此路径。现已在工具边界统一解包，错误具体到字段，并修正联调发现的 PowerShell 对象输出未刷新问题。经工具入口真实执行的结果与保留的首次失败见 [M2 修复记录](../progress/m2.md#run_command-四次参数拒绝排查2026-09-18完成)。此前 24 类审阅完成不等于所有执行入口已无问题。

> **默认路径补正：** 上述修复后的用户调用又被 `PROJECT_NOT_TRUSTED` 拦截：其数据根没有 `environments.json`，并非主动禁用执行。前一组用例预设 trusted=True，未验证选定项目后直接使用的路径。现已取消该额外条件，并用无环境配置的实际工具 / Electron 路径验证 `Get-Location`，另验证历史 trusted=False 不再阻断服务。结果见 [默认执行修复](../progress/m2.md#无环境配置项目被信任开关阻断2026-09-18完成)。

- 简单 Goal 完成文件后可以直接 `report_work(summary=..., outcome="complete")`，无需另外读取证据索引或补全任务图。普通请求 schema 不再提供不可用的 Goal 结果。
- 文件读写不会因为绝对写法、忽略目录、普通配置文件名或硬链接而中断；写入前真实内容冲突明确报告，模型读取后可在原 Goal 内继续调整。模型工具不返回版本 hash；宿主保留的摘要不再作为编辑或历史读取条件。
- 选定项目后无需先打开设置、导入环境或确认信任，即可使用本机工具；普通工具配置不再被固定环境白名单删掉。环境改动与任务共同信息分别在下一次启动 / 模型请求生效。
- 参数、未写入的文件冲突和不可用历史记录由下一次模型请求处理，实际网络 / 程序 / 保存故障继续按原约定停止。网页状态是实际结果，不冒充 404 为正常业务页面。
- 使用集中 tests 与隔离模型 / HTTP 替身验证；没有重新发送用户对话、调用真实模型、修改 VPN / 全局设置、提交或推送。实际命令、失败修正与通过数量以 [本轮 M2 进度](../progress/m2.md#以-dsh-为基准的运行约束全面对照2026-09-18完成) 为准。
- HTTPX 路由查询局部使用锁定依赖的私有传输选择方法，直连 / 代理 / NO_PROXY 已有定向检查；升级 HTTPX 时应复查此适配。没有声称直连预检形成网络沙箱，也没有测量本轮真实外网延迟。

后续遇到新的正常业务阻塞，应直接核对相应调用链及上游同类实现。不要再用给模型追加“请严格遵守”来弥补接口自身的不一致，也不要恢复本次已移除的门槛。

[dsh-base]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/bundle/base/cordis.patch.yml
[dsh-edit]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/fs/tool-fs/src/edit.ts
[dsh-observe]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/fs/fs-observation-policy/src/index.ts
[dsh-fs]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/fs/fs-local/src/index.ts
[dsh-fsio]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/fs/fs-local/src/fsio.ts
[dsh-fs-sandbox]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/fs/fs-sandbox/src/index.ts
[dsh-goal]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/goal/tool-goal/src/index.ts
[dsh-todo]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/todo/tool-todo/src/index.ts
[dsh-calls]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/core/agent-loop/src/tool-calls.ts
[dsh-driver]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/goal/goal-round-driver/src/index.ts
[dsh-pwsh]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/shell/pwsh-local/src/index.ts
[dsh-env]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/subprocess/subprocess/src/index.ts
[dsh-http]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/web/web-fetch-http/src/provider.ts
[dsh-http-policy]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/web/web-fetch-http/src/policy.ts
[dsh-tools]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/core/tools/src/index.ts
