# OpenViking 与 Mem9：把外部记忆系统接入 DSH 的两条路径

> 核查日期：2026-09-23。OpenViking 固定 `563313ebe10a1b33d0ae736ab8b97ca713ff91f9`；Mem9 固定 `3a61b2b9fd1dbbfb84df891c632bcd27b4b665ce`。本文重点核查 DSH 适配层及其队列 / 注入边界，不声称审计整个检索服务或验证召回质量。

许可证按当前固定文件核对：OpenViking 根 LICENSE 为 AGPL-3.0，Mem9 根 LICENSE 为 Apache-2.0；不是对整个生态统一采用 MIT 的假设。本文未复用其实现代码。

## 1. 接入记忆服务，最难的不一定是向量搜索

一个 Agent 会话会产生用户消息、模型回答、工具结果和中断。哪些内容进入长期记忆、何时写、断网后怎么办、召回的文字如何标注来源，决定了一个记忆后端是否能可靠接入实际产品。

这两者将记忆处理放在主 AgentLoop 外部，通过插件消费生命周期事件。它们没有替换 DSH 的会话格式，也不要求把历史全部转成记忆后再继续工作。不同之处是 OpenViking 适配更强调会话 capture / commit、工作区身份和持久待处理队列，Mem9 的 DSH 包主要围绕自动召回、回合 smart ingest 与显式工具。

## 2. OpenViking：捕获日志，分批提交，再按需召回

### 2.1 仓库结构体现跨 Harness 复用

`examples/dsh-memory-plugin/` 拆成入口、配置、HTTP client、capture、lifecycle、runtime、MCP、Skill 和 URI guard。公共记忆逻辑位于 `examples/memory-plugin-shared/lib/`，多个 Harness 复用。DSH 目录中的 shared 关联不是全部独立复制的实现；本次文本缓存不展开符号链接，分析时回到真实共享目录。

这使 DSH 插件只处理宿主事件到记忆协议的翻译。检索算法、层级上下文与服务端记忆生成属于 OpenViking 服务，不应把它们全部说成这个几十个文件的适配包自身实现。[插件入口](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/index.mjs)

### 2.2 会话启动：建立两套身份的映射

Runtime 为每个 DSH session 保存状态：DSH session id、派生的 OpenViking session id、workspace 对应 peer、初始化结果、profile 是否已交付、工具名映射与写入链。

它没有将整个宿主的所有会话塞进一个匿名记忆桶。workspace peer 用于区分知识归属，session 映射用于关联 capture。默认跳过子 Agent 的策略还避免父子视角同时捕获同一工作、重复沉淀记忆；需要共享时应明确选择，而非默认为所有子会话复制个人资料。

### 2.3 请求前：先取最终输入，再并行获取材料

`agent/pre-step` 先等待下游 `next()`，只有 decision 为 enter 且未取消才继续。profile 与 recall 相互独立，使用 Promise.all 并行，最后追加来源明确的消息。

这一设计减少串行等待，但没有消除远程服务延迟：它依然位于模型请求之前。对交互产品应区分必要材料和可选记忆的等待策略，并测量“加入召回前后的首字时间”，不能只测单次搜索速度。

### 2.4 回合运行：capture 与 commit 分离

`session/event` 调用 capture，将需要的消息串行写入服务；`turn/end` 再检查 pending tokens，达到阈值才 commit。capture 是收集事实，commit 才是让后端进一步整理记忆的时点。

失败时若属于可恢复写失败，后续消息进入 pending 队列，置 `hasPendingWrites`，避免新消息越过旧消息先到服务端。插件启动一个单飞 drainer，检查服务健康、重放待处理项，再由剩余队列重新计算 latch；这样无需重启即可从一次临时失败恢复。[Runtime](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/runtime.mjs)

这是比“catch 后打印 warning”更完整的设计，但仍不能直接宣称 exactly-once：网络返回未知时，服务端去重、操作身份和重放协议决定是否重复。flush 等待当前写链，也不等于持久待处理队列已经全部被远端接受。

### 2.5 工具、Skill 和 URI 必须一起交付

插件另外挂载 MCP 和 bundled Skill，并在工具前后识别 `viking://`。这个 URI 属于知识系统命名空间，不是本机文件路径；把它交给通用 read_file 会找不到文件或误导模型。

MCP 挂载放在核心生命周期注册之后，且不等待首次 tools/list 完成，避免一个接受连接却不返回目录的服务卡住其他 hook。由此可见，“外部工具已配置”与“记忆 capture 已装配”不是一个状态。

## 3. Mem9：在回合边界做小而明确的集成

### 3.1 一个适配入口承载完整闭环

`dsh-plugin/src/index.ts` 包含配置解析、Gateway、工具注册、recall 和 ingest 生命周期；测试按失败、召回、摄取、配额与真实 Loader 组合拆分。包范围较集中，便于沿一条请求追踪，而后端服务仍是另一层。[完整适配实现](https://github.com/mem9-ai/mem9/blob/3a61b2b9fd1dbbfb84df891c632bcd27b4b665ce/dsh-plugin/src/index.ts)

默认连接托管 API，也允许更改地址使用自托管。每次操作通过宿主 credentials 解析凭据名称。是否使用托管服务，关系到会话内容发往哪里，不能仅凭插件本地安装就称为本地记忆。

### 3.2 首步召回，而非每个工具往返都搜索

pre-step 仅在 `step === 1`、召回启用、Agent 符合条件且 query 足够长时发起查询。它限制条数和每条字符，将结果作为 plugin / recall 来源的 user message 追加。默认仅 root Agent，子 Agent 需显式配置加入。

收益是避免每个工具往返都重复查询、重复注入；代价是在一个很长回合中，后续发现的新问题不会自动触发同一条首步召回路径，模型仍可使用显式记忆工具补查。

### 3.3 完整回合结束后异步摄取

监听器只接受 `turn/end` 且 reason 为 completed 的回合；从本回合抽取有界消息，并要求包含 assistant 内容。WeakMap 记录本进程已经调度的 turn，Map 按 session id 串行化 ingest Promise；不同会话可独立推进。

这一点值得仔细区分：它减少同一进程内重复安排，并保证本会话顺序，但队列没有在适配层持久化。进程崩溃时，尚未送达的后台摄取不能据此保证自动恢复。不能把 WeakMap 去重写成跨重启 exactly-once。

### 3.4 卸载和配额失败不是普通成功

卸载先停止接受新任务，再等待现有队列；超时触发 abort，最终清理句柄。配额拒绝可向会话注入一次解释，其他自动路径失败则记录 warning 并保留主决策。

这是外部可选记忆的产品选择，不是本项目故障策略的默认替代。本项目已确定实际调用 / 保存故障停止当前运行，若以后采用后台记忆，需要先明确它属于独立作业还是当前 Run，不能靠放进后台就绕过停止规则。

## 4. 两者可以怎样帮助我们做决定

| 需求 | OpenViking 适配的启示 | Mem9 适配的启示 |
| --- | --- | --- |
| 多项目记忆身份 | DSH session 与服务 session / peer 明确映射 | 检查服务端 scope，不能只传 agent 名称 |
| 低额外调用量 | profile / recall 并行，capture 与 commit 分开 | 回合首步召回，完整回合后批量摄取 |
| 断网恢复 | 持久 pending、顺序 latch、drainer | 明确进程内队列的边界，避免虚报恢复能力 |
| 不污染主会话格式 | 通过外部服务和来源消息接入 | 通过标准事件与工具接入 |
| 质量验证 | 应验证 scope、去重、错误事实和延迟 | 应验证召回价值、摄取丢失窗口和费用 |

本项目已有本地记忆，不需要先引入远程后端才能改进。可以先借鉴“候选来源 + 提炼作业身份 + 输入边界 + 可观测的失败”，再根据跨设备或大规模检索需求决定是否采用其中一种服务。
