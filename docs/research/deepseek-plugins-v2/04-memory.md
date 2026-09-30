# 从对话材料到可复用经验：EverOS、MemOS、OpenViking 与 WeKnora

> 截止 2026-09-23。本篇分别研究本地可编辑记忆、嵌入式记忆加工、独立上下文服务和组织知识检索。它们解决的问题有交集，但事实来源、延迟和运维代价不同，不能只用“支持长期记忆”比较。

## 1. 先建立可以理解实现的概念

一次模型请求能看到的历史是短期上下文。长期记忆则需要在当前窗口之外保存信息，之后检索并重新放回请求。中间至少有五个选择：保存原始事件还是提炼结论；如何区分用户事实、项目事实和做事经验；检索要等待多少时间；新信息多久可见；错误记忆如何纠正或删除。

Skill 表达可复用的任务方法，既能由人编写，也能从执行经历中提炼。后一种方式比保存事实记忆多了方法归纳这一步。产生一个新 Skill 文件，并不能证明 Agent 变得更好。检索、提炼、版本发布与效果评估是不同环节，必须各自检查。

| 对象 | 当日 Star / Fork | 主要事实层 | 本轮最值得学习的机制 |
| --- | --- | --- | --- |
| EverOS | 13,149 / 921 | Markdown；SQLite / LanceDB 是状态与检索层 | 可编辑原文到索引的持续协调，跨会话 flush 与离线整理 |
| MemOS | 11,542 / 1,056 | 本地 MemoryCore 的结构化存储 | 前台召回与后台 capture 分离，带会话路由的辅助模型调用 |
| OpenViking | 38,498 / 2,998 | 独立上下文服务 | profile / recall 并行，事件采集与持久 pending 写队列 |
| WeKnora | 29,092 / 3,921 | 外部组织知识平台，使用前需部署 / 接入 | 检索片段、读取文档与生成回答分成不同工具 |

这些是全仓热度，不是 DSH 插件安装量。尤其 MemOS 的 Python、Cloud 和本地插件不能混为同一部署；EverOS 的 DSH 适配另在 `EverMind-AI/plugins`。

## 2. EverOS：可编辑文件是事实，索引需要持续修复

### 2.1 仓库与部署职责

主仓库快照 `5076683ab88d714390573d8f88ff3c470e51129a`，Python 包 `1.3.1`。`src/everos/entrypoints` 提供 CLI / API，`memory` 组织提取、检索、反思和 cascade，`infra/persistence` 分别实现 Markdown、SQLite 与索引存储，`infra/ome` 提供离线记忆演化的执行基础。算法部分还依赖单独的 everalgo 包，不能把调度层阅读冒充对所有算法的审计。

DSH 适配位于另一个固定仓库 `EverMind-AI/plugins@f76f4d06135a0b5d784d15eed133ecdcedc12d47`。`index.ts` 安装 hook；`identity.ts` 映射身份；`recall.ts` 构造检索与上下文；`capture.ts` 读取会话事件；`memory-runtime.ts` 串行处理采集与 flush；`provision.ts` 处理可选服务准备。主库与薄适配分开，使多个 Agent 可共用记忆服务，也使适配兼容性需要单独维护。[主库目录](https://github.com/EverMind-AI/EverOS/tree/5076683ab88d714390573d8f88ff3c470e51129a/src/everos)、[DSH 适配目录](https://github.com/EverMind-AI/plugins/tree/f76f4d06135a0b5d784d15eed133ecdcedc12d47/dsh/src)

### 2.2 用户进入一轮对话时如何召回

适配在 `agent/pre-step` 调用下游 next，若被拒绝、已取消或不是第一 step，就不做本轮召回。检索 query 优先放当前直接用户输入，再把预算剩余部分给最近直接用户消息；插件注入文本不会被当作新的人类问题再次检索。返回材料保留 profile、episode、case 和 Skill 等区别，避免一串没有来源类型的“记忆”。[入口](https://github.com/EverMind-AI/plugins/blob/f76f4d06135a0b5d784d15eed133ecdcedc12d47/dsh/src/index.ts)、[查询与上下文](https://github.com/EverMind-AI/plugins/blob/f76f4d06135a0b5d784d15eed133ecdcedc12d47/dsh/src/recall.ts)

身份映射中，session ID 经过路径安全处理，project 默认由 cwd 的可读部分和摘要组成，user 可来自显式配置或系统用户名。这使独立插件容易落地，但也引出项目移动、路径别名、多机身份一致性的成本。我们已有登记项目 ID，不应退回从用户名和 cwd 推导业务身份。

### 2.3 一轮结束后，采集与提取分两步

`MemoryRuntime.captureNow()` 读取 cursor 后的新消息，分批调用服务 `add`，设置 `defer_extraction: true`。只有请求成功后才推进本地 cursor；每会话 Promise 链保持写入顺序。之后由消息量、估算 token、闲置、最大等待时间等触发 flush，将已收集材料真正提取成记忆。

这种设计减少每轮重复做昂贵整理。但 cursor、timer 和 Promise map 是适配进程内状态；不能仅凭它们就宣称崩溃后端到端 exactly-once。服务保存、消息序号和后续恢复各自承担一部分职责。[采集与 flush](https://github.com/EverMind-AI/plugins/blob/f76f4d06135a0b5d784d15eed133ecdcedc12d47/dsh/src/memory-runtime.ts)

一个特别值得比较的选择是 `flushBeforeRecall`：开启对应配置时，新会话召回前等待同项目其他会话的 pending flush。这样切换会话后更可能读到刚产生的事实，但也将后台提取延迟带到新请求前台。它与下面 MemOS 的“只读当前已提交状态、不等待前轮加工”形成直接取舍：一致性更及时，还是响应更快，需要按用户场景决定。

### 2.4 Markdown 到索引：watcher 不是唯一保障

可编辑 Markdown 的优势是用户能检查、修改、diff 和迁移自己的记忆；代价是不能再把向量库当作唯一真实状态。EverOS 的 cascade 将 watcher、周期 scanner、SQLite 变化队列和 worker 组合起来：

```mermaid
flowchart LR
    A[Markdown 新增 / 修改 / 删除] --> B[Watcher 或周期扫描]
    B --> C[SQLite 变化状态]
    C --> D[按类型 Handler]
    D --> E[LanceDB 检索投影]
    E --> F[后续召回]
```

`reconciler.py` 比较磁盘与已记录状态，不假定 mtime 只增不减；文件删除即使漏掉 watcher 事件，也能由 scanner 清理索引孤儿。启动时 `recover_orphan_processing()` 把前一进程留下的 processing 行重新变成待处理。watcher 不可用时仍可保留扫描和 worker，只损失发现速度。[协调器](https://github.com/EverMind-AI/EverOS/blob/5076683ab88d714390573d8f88ff3c470e51129a/src/everos/memory/cascade/orchestrator.py)、[磁盘与状态协调](https://github.com/EverMind-AI/EverOS/blob/5076683ab88d714390573d8f88ff3c470e51129a/src/everos/memory/cascade/reconciler.py)

它还区分管线运行健康与少数文件永久索引失败：不能因为一个坏文件就让整个服务永远显示不健康；也不能把那一个失败文件假装已经可检索。对我们的知识页功能，这是很实用的状态表达参考。

### 2.5 Reflection 的具体对象与 RSI 边界

`ReflectionOrchestrator` 按 owner、app、project 范围选择 episode cluster，合并为新的 episode，写入 Markdown，经 `EpisodeExtracted` 再提取原子事实，并淘汰旧成员。它依赖 embedding、事件等待、持久报告和分区锁，不只是把历史全部拼接后请求“总结一下”。

这里演化的是记忆表示和经验组织。它不等于模型参数训练，也没有在本轮证据中证明“负责改进自身的机制也被改进，并在多轮形成可验证的持续能力提升”的强递归自我改进（RSI）。更准确的术语是离线记忆整理与经验提炼。是否让后续任务变好，需要独立任务集和带版本的对照。[反思协调](https://github.com/EverMind-AI/EverOS/blob/5076683ab88d714390573d8f88ff3c470e51129a/src/everos/memory/reflection/orchestrator.py)

## 3. MemOS：把记忆加工移出交互关键路径

### 3.1 不要读错子系统

固定 `a7367d07e55db61099f7b4e2c1108bc5831a24f3`。此仓库同时存在 Python `src/memos`、Cloud 插件和 TypeScript 本地实现。本篇的 DSH 路径是 `apps/memos-local-plugin/adapters/deepseek-harness`，连接本地 MemoryCore，并复用 `packages/memos-core` 的检索、存储和 Skill 生成模块；不能把 Python 图记忆或 Cloud 能力自动归给这个适配。当前本地 package 为 `2.0.16-beta.1`、声明 MIT，根仓库 LICENSE 为 Apache-2.0；安装说明中的 `2.0.16` 与此源码标记也应区分。

适配 `index.ts` 装配 core、可选 Viewer、system prompt、hook 和显式工具；`bridge.ts` 管理会话 / turn 对齐及后台队列；`host-llm.ts` 借用宿主模型服务；`deadline.ts` 限定前台等待；`tools.ts` 提供主动查记忆等能力。[适配目录](https://github.com/MemTensor/MemOS/tree/a7367d07e55db61099f7b4e2c1108bc5831a24f3/apps/memos-local-plugin/adapters/deepseek-harness)

### 3.2 一次输入只承担本轮召回成本

`beforeStep()` 对接纳的非空直接用户输入执行一次自动召回，并用 session / turn 状态去重。它不把插件生成的上下文当作用户问题。所有前台搜索共享绝对 deadline，适配将有效上限限制为 `min(configured, 3000ms)`；没有等待上一轮 capture、摘要、分类或 embedding 完成。

实现不仅向 provider 传取消信号，还对不能及时响应取消的实现设外层 deadline guard。超时后这一轮继续原 pre-step decision；未按时完成的后台 Promise 仍被观察。**返回前台不等于底层计算在该毫秒已经物理停止**，这两个保证需要分开。[前台接纳与 deadline](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/apps/memos-local-plugin/adapters/deepseek-harness/bridge.ts)、[入口上限](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/apps/memos-local-plugin/adapters/deepseek-harness/index.ts)

召回结果封装为带插件来源的历史数据块，追加在当前查询后面。若本轮开始时前轮加工未提交，本轮就读较旧的已提交状态。这个选择很适合交互响应优先的桌面，但产品需要解释“刚说的话尚未进入长期记忆”，不能将新鲜度空缺误称检索失败。

### 3.3 工具与文本怎样组成可提炼的一次经历

`session/event` 是同步事件流，bridge 先按 turn 聚合直接用户消息、assistant、native tool 和 code-dispatch 事件。工具调用使用 callId / subCallId 配对；turn/end 后将路由、分类和 `onTurnEnd` capture 放进每会话串行后台队列。

它没有把 DSH 的 `session/flush` 当作记忆加工 barrier，session disposed 也不等待全部后台任务；只有插件整体退出时做有界的尽力 drain。这避免保存对话时被长期记忆的辅助模型阻塞，但也意味着不能宣称退出时绝无未加工数据损失窗口。[事件聚合、串行写入与退出](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/apps/memos-local-plugin/adapters/deepseek-harness/bridge.ts)

### 3.4 检索不是一个向量查询

本地 `RecallEngine.search()` 汇集 FTS、向量和 pattern 候选：pattern 补充短字符串无法被 trigram FTS 匹配的问题；RRF 按排序位置融合不同检索结果，避免直接相加不可比较的分数；MMR 再降低重复候选的挤占，之后考虑时间衰减与输出限制。

这条链的价值在于针对真实 query 的异质性：函数名、短错误码、用户偏好与语义近似需求需要不同通路。代价则是参数解释与评测难度上升；一个好看的 recall score 不能证明上下文真的帮到了编码任务。尤其时效衰减不能把长期有效的项目约束错误降权。[本地召回实现](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/packages/memos-core/src/recall/engine.ts)

### 3.5 辅助模型怎样保持会话归属

摘要、分类和经验提炼会触发额外模型请求。`host-llm.ts` 使用异步局部作用域携带当前 turn 的 provider / model 路由，而不是用一个全局“最近选择的模型”。这可以避免两个会话并发时，A 的记忆加工突然使用 B 刚切换的模型。

适配调用 DSH 的公开 llm 服务，凭据仍留在宿主 provider。辅助请求尝试显式关闭推理；遇到明确不支持的 effort 时再按适配规则处理，不能偷偷更改主会话推理级别。对我们而言，最有价值的是统一请求计数、会话路由快照与凭据边界；无需照搬额外 provider fallback。[宿主模型桥](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/apps/memos-local-plugin/adapters/deepseek-harness/host-llm.ts)

### 3.6 Skill 演化有流程，但还缺独立质量闭环

`SkillEvolver` 收到 task completed 后，先做规则筛选，再检索已有相似 Skill；找到相关项则进入升级，否则生成新项。evaluator 用模型判断这次经历是否可重复、可迁移、有技术深度；状态保存 queued / generating 等，并提供孤儿任务恢复入口。

这些实现足以说明它不是只写一个“反思”提示词，但“LLM 判断值得生成”仍不是“新 Skill 在未见任务上提高成功率”。自动恢复、生成和安装也受具体 adapter 配置影响，不能因为共享类有方法就断言 DSH 默认全部自动执行。它属于可检查的经验驱动自改进管线，尚非经本轮验证的强 RSI。[演化器](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/packages/memos-core/src/skill/evolver.ts)、[经验价值判断](https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/packages/memos-core/src/skill/evaluator.ts)

适配 README 的初始端到端目标仍写 DSH 0.1.0-rc.5，编译 / 契约使用 rc.6。主仓库当日更新和较高 Star 都不能代替 0.1.7 的实机验证；本轮没有运行该组合。

## 4. OpenViking：把上下文作为独立服务

### 4.1 接入先解决身份与服务边界

本轮沿 `563313ebe10a1b33d0ae736ab8b97ca713ff91f9` 的 `examples/dsh-memory-plugin` 阅读，并核对当日较新 HEAD `34840c24f92ed04b19dac559dd2a6f13c336742f` 的比较；该段增量没有修改这一 DSH 适配目录。主仓库最新 push 不能假定等于插件改版。

适配把 DSH session 与 workspace / peer 映射到服务侧范围，客户端调用远端上下文能力。原生 DSH 工具、事件和 Skill 仍留在宿主，OpenViking 负责服务侧的记忆、知识与上下文组织。本篇的深入边界是适配层，不将其等同于对服务端所有存储与 ACL 的完整审计。[插件目录](https://github.com/volcengine/OpenViking/tree/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin)

### 4.2 前台并行，后台有序

`index.mjs` 在 pre-step 的 next 之后并行获取 profile 和 recall，再追加到被接纳的消息。profile 更像稳定身份 / 偏好材料，recall 针对当前问题，两者可以并发，减少额外等待。

另一方面，`session/event` 的 capture 和 commit 必须保持顺序；写失败之后 `hasPendingWrites` 会使后续写入进入 pending 队列，避免后面的 commit 越过前面的未完成消息。共享 single-flight drainer 尝试恢复 pending 工作。这里已经超过单纯进程内 Promise 排队，但仍不能推导外部服务与本地事件之间的跨系统事务。[hook 装配](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/index.mjs)、[写入与恢复](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/runtime.mjs)

### 4.3 防止记忆把自己的输出当成新事实

`capture.mjs` 拒绝插件来源的消息进入人类输入采集路径，assistant 与工具结果也各有配置。否则每轮召回的旧记忆会再次被提取，越来越像“用户反复确认过”的事实，形成自我强化污染。

MCP 挂载放在核心 hook 之后且不等待其首次 tools/list，避免一个连接成功却迟迟不返回列表的服务挡住全部能力注册。这是可选外部服务与核心对话生命周期分离的具体例子，不只是“异步更快”。[采集过滤](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/capture.mjs)、[MCP 装配](https://github.com/volcengine/OpenViking/blob/563313ebe10a1b33d0ae736ab8b97ca713ff91f9/examples/dsh-memory-plugin/index.mjs)

其主仓库 LICENSE 为 AGPL-3.0，`examples/dsh-memory-plugin/package.json` 则将适配包 `0.5.0` 标为 Apache-2.0；两者不能合并成同一许可结论，具体复用仍需核对文件声明。技术上，独立服务适合多端共享与集中索引，但也引入服务可用性、认证、版本和网络延迟，对当前单用户 Windows 桌面不应默认成为启动依赖。

## 5. WeKnora：组织知识不应伪装成用户记忆

WeKnora 的 29,092 Star 和完整知识平台形态使其值得纳入，但本轮只审读固定 `e179f4444592929f9e95be98713883d6c14a7677` 的 `packages/dsh-weknora` 适配。主项目根许可正文为 MIT 加第三方组件声明；GitHub 元数据的 `NOASSERTION` 不能自动解释为无许可。[许可正文](https://github.com/Tencent/WeKnora/blob/e179f4444592929f9e95be98713883d6c14a7677/LICENSE)

入口先解析配置并创建 HTTP client，再注册知识库列表、search、文档读取和组合回答等工具。`search` 返回检索到的原始段落，不先让另一个模型改写；需要生成回答时走另一工具。`tools.ts` 还处理按名称命中文档与正文片段去重，并对跨 tenant 范围的名称搜索结果按请求范围投影。

因此一次使用应理解为：模型知道可用知识库 → 根据任务查询 → 得到带文档身份的证据 → 必要时读更多原文 → 由当前模型组织回答。它并不自动学习用户偏好，也不是一项自动 capture 插件。[入口](https://github.com/Tencent/WeKnora/blob/e179f4444592929f9e95be98713883d6c14a7677/packages/dsh-weknora/src/index.ts)、[工具语义与结果范围](https://github.com/Tencent/WeKnora/blob/e179f4444592929f9e95be98713883d6c14a7677/packages/dsh-weknora/src/tools.ts)

对本项目，这更适合未来已有企业知识库的连接需求：保留检索证据与生成答案的区别，通过现有 MCP / 工具边界接入，而非再建一套本地组织知识后台。公司维护和较高 Star 说明资源与关注度；本轮仍未取得该 DSH 插件的命名企业生产部署规模证据。

## 6. 建议怎样吸收，怎样验证价值

最优先的是把我们已经存在的记忆系统表达清楚：原始记录、提炼条目、检索命中和进入某次请求的材料各有来源；用户修改或遗忘之后，后续请求不能继续拿旧投影当当前事实。EverOS 的可重建投影与 MemOS 的前后台分离提供具体参考。

其次才是混合检索或 Skill 自动提炼。验证应围绕实际问题，而非只比较检索命中率：同一项目连续两次任务是否减少重复说明；纠正偏好后旧偏好是否消失；两个项目相似问题会不会串记忆；后台失败是否拖慢首字；提炼经验能否改善后续未见任务。这里列的是后续采纳时需要验证的效果，本轮未执行模型实验。

本项目已有会话摘要、归档回读、记忆与知识页，不应重新引入整套第三方 Memory OS。可以先做可见性、新鲜度和作用域的小范围改进；只有实际容量、检索质量或多端共享需求出现后，再决定是否值得增加向量依赖或独立服务。
