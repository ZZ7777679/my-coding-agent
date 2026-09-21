# 压缩后保留什么：DSH、Pi、OpenCode、Claude Code 与 Codex 对照

> **后续决策已收敛并实施：** 最终采用“按需工具减量 + 完整切点摘要 + 绝对 token 配置”，详见 [定稿方案](../plan/context-compaction-v2.md) 与 [M3 进度](../progress/m3.md)。前八节关于草案待收敛 / 尚未实施的表述保留为当次研究的历史状态；第九节为评价争议的补充核对。

> 核对：2026-09-21。仅源码 / 官方说明研究，未运行第三方产品或调用模型。
>
> 回答用户对“近期原文为什么必须保留”和第二版压缩方案的质疑。此前 4K / 2K / 8K / 128K 为自拟参数，不是上游最佳实践。相关方案见 [第二版草案](../plan/context-compaction-v2.md)，本次纠正具有优先性；运行代码未改。

## 1. 比较结论

保留近期材料是常见实现，不是所有产品都只发送一段摘要。不同实现保留的材料形态、计量、切点和手动行为不同。不能把“摘要 + 近期材料”推导为必须保留 20%，也不能从用户嫌保留太多直接改成默认零原文。

| 对象 / 证据 | 自动整理后的材料 | 保留策略 | 手动行为 |
| --- | --- | --- | --- |
| DSH，固定提交源码 | 摘要替换旧区间，近期消息原文保留 | 默认模型窗口 16%，也可配置绝对 token；切点保持工具配对 | `compactNow` 传入保留预算 0，更积极压缩；实际仍留最后节点及配对所需前缀 |
| Pi，固定提交源码 / 文档 | 摘要 + 从 firstKeptEntryId 开始的消息 | 默认约 20K token，倒序累计估计量选合法切点，可在长回合内切分 | 使用同一有效 keepRecentTokens 配置，并非手动默认清空尾部 |
| OpenCode V2，当前官方文档 | 本地摘要 + 近期序列化材料；原生模式按 provider checkpoint 处理 | 默认 keep.tokens=15K；本地尾部不是保证逐字完整的原文，大工具输出缩短 | 手动在步骤边界执行，不要求达到自动阈值；没有另一套公开的手动保留默认 |
| Claude Code，当前官方文档 | 先清旧工具输出，必要时总结；保留请求与关键代码信息 | 官方未公开统一的尾部 token 数或精确切点算法 | `/compact` 可附重点；不能据此断言手动只留摘要 |
| Codex / OpenAI 原生路线，官方文档 | 原生压缩返回不透明续接项；独立接口还可返回保留项 | 官方未给出统一可读尾部 token 数，不能映射成 4K / 20K | Codex 提供手动压缩入口；API 独立 compact 返回的整个窗口须按契约续传 |

下面逐项说明事实和不能推断的部分。

## 2. DSH：自动与手动确实不同

版本为 `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`，不是声称最新发布版本。

[官方 README](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/README.md) 的自动默认是达到模型窗口 80% 开始处理，保留量按 16% 或显式 retainTokens。摘要不替换固定 system / tools。不能据此认定 16% 对 1M 模型或本项目最合适。

[region.ts 的 selectCompactableRange](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/src/region.ts#L97-L142) 从最新节点倒序累计，达到预算后再向前调整到工具配对完整的切点。retainTokens 在这里是近期目标 / 最低累计量，不是严格硬上限；一个很大的最后单元可能让实际保留超出预算。

[index.ts 的 compactNow](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/src/index.ts#L332-L372) 明确把 0 传给同一选择函数。因为循环先累加最新节点才比较，0 不等于完全不留任何原文；随后仍扩展到合法配对。它会尽量压缩最后必要单元之前的旧内容。这解释了为什么手动操作可能比默认自动策略腾出更多空间。

该版本也会拒绝没有变小的摘要，并可能因没有可处理的完整旧区间而不压缩。它不是“永远成功”的证据。范围选择、摘要收益检查和外围有界策略应一起看，不能把这些简化成一次无效生成后等历史增长。

## 3. Pi：绝对近期预算，保留实际消息尾部

版本为 `71dca871bc80b6bc97be37f0ca3189399d651fff`。

[文档](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/coding-agent/docs/compaction.md) 给出 keepRecentTokens=20000；压缩后使用摘要及保存切点以后的消息。手动、自动、溢出处理使用同一有效配置。因此 1M 模型不会仅因容量大就默认保留 200K 原文；20K 只是该版本工程默认，不是摘要质量证明。

[findCutPoint 源码](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/coding-agent/src/core/compaction/compaction.ts#L361-L429) 按近期 token 估计累计后选择合法消息边界，不能单独从工具结果切开。长用户回合超出近期预算时，可以在回合内切开；早期回合部分生成接续摘要，不将整轮视为必须保留。

这里不是全历史语义打分，也不是严格取最后 N 个字符。保留区实际大小受消息边界影响；“预算 20K”不能解释为精确等于 / 严格不超过 20K。

## 4. OpenCode V2：近期材料不等于全部原文

[当前 V2 官方文档](https://opencode.ai/v2/docs/compaction) 默认 keep.tokens=15000。本地压缩保留近期序列化内容，工具结果可缩为最多 2000 字符，附件以描述表达。因此要区分保留最近操作信息与重放完整工具输出。

本地摘要与原生 provider checkpoint 也不同；原生流式路径保留真实用户输入，独立 endpoint 返回值按原样保存。不能把 V1 的源码行为、V2 本地摘要以及原生路径合成一个算法。手动压缩不要求达到自动阈值，但文档未提供默认清空近期材料的另一套手动配置。

## 5. Claude Code：公开行为足够说明有取舍，不足以给精确数值

[官方工作原理](https://code.claude.com/docs/en/how-claude-code-works#when-context-fills-up) 说明先清理旧工具输出，必要时总结；请求和关键代码信息会保留，但早期细节仍可能丢失。用户可指定压缩重点。

它没有在该文档公开“固定保留几轮 / 多少 token / 全部原文”的统一算法。本轮不采用泄露源码或第三方反编译推断；不能把官方 API 的某一种压缩协议当作所有 Claude Code 版本内部实现。也不能用“请求被保留”推导为全部请求始终逐字保留。

## 6. Codex 与 OpenAI 原生压缩：输出不是普通摘要模板

[Codex 提示指南](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide#compaction) 描述与模型配合的压缩机制；[当前 API 文档](https://developers.openai.com/api/docs/guides/compaction) 区分服务端流式压缩与独立 `/responses/compact`：后者返回的规范窗口可以包含原来的保留项，不能只取不透明 compaction 项再删掉其他返回内容。

[App Server](https://learn.chatgpt.com/docs/app-server#trigger-thread-compaction) 确认手动 `thread/compact/start` 生命周期。本轮未审计各 Codex 客户端版本和 provider 分支的保留实现，不能声称所有 Codex 路径都完全依赖同一原生模式，也不提供未经核对的“保留所有用户消息 / 固定最近 N token”结论。

本项目使用 Go Chat Completions + GLM / DeepSeek，不能通过多写一段提示获得该原生协议能力。当前可直接借鉴的是 DSH / Pi 一类本地文本摘要与保留区组装。

## 7. 对本项目第二版的纠正

1. **近期原文不是错误设计。** 它降低当前操作信息经过摘要后丢失或必须立即回查的概率。时间顺序是简单可解释的选择方法，不能仅因“最近不一定重要”就增加全历史相关性判定模型。
2. **不应从 20% 直接推导出默认零保留。** 本项目此前的 20% 其实是历史 / 字节预算比例，不是模型 token 窗口比例；不同单位必须先纠正。允许更充分的手动压缩不等于正常自动续跑只用摘要。
3. **4K 不是上游证明过的默认，更不是严格切断上限。** 第二版“超过就将最后完成单元全部摘要”的激进策略不能冒充 Pi / DSH 的同款做法。保留应首先遵守实际协议边界，超大单元按结果减量和合法切点处理。
4. **手动与自动需要明确产品语义。** 建议自动处理保留一个可调的近期工作区；手动采用 DSH 式更积极的范围选择，只留下必要的末尾交互及当前输入。不要静默为手动 / 自动共享一个会让短窗口几乎不动的保留预算。
5. **暂不把 B/R/S 多重比例、预计释放一半的分类、自动二次收紧写成最终必须实现。** 这些是上一版自行设计的机制，不是本次资料证明必需。先以统一 token 计量、清楚的手动 / 自动选区、一次有效摘要替换为主；输出控制与有界后备应针对真实失败场景配置，不能又成为复杂策略系统。
6. **不再凭直觉换一组默认数值。** 4K 可作为较小近期区的实验候选，15K / 20K 是上游参考值，各自都有取舍。默认值应在双模型接续与回查开销的最小样本上确定；本轮没有完成该实测。用户反对固定 20% 的方向保留。

推荐的核心结构仍简单：系统 / 当前事实 + 一份接续摘要 + 明确切点之后的必要近期材料。改善重点是切点与触发语义，不是追求压缩率数字越大越好。

## 8. 本轮交付边界

仅完成比较和对草案的纠正；没有修改应用实现、调用模型、操作私人会话或复制上游源码。第二版暂列为待收敛草案；此次对照优先于此前关于必须保留 4K 或默认完全不保留的会话建议。后续先确定手动 / 自动语义，再落实现有服务中的最小改动。

## 9. DeepSeek 评价中的问题，上游是否已经解决（2026-09-21 补充）

本节重新读取固定版本 DSH / Pi 的公开源码、包文档及当前产品官方说明。只确认已公开机制，不把机制存在等同于实测质量领先。未运行第三方程序或调用模型。

### 9.1 先缩短工具结果再摘要：上游也有这种取舍

- [DSH pruner](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-tool-result-pruner/README.md) 是可选组件：达到压力条件后保留头尾，若减量后仍需摘要，摘要模型读取的是已缩短的 surface。原日志保留。文档明确承认裁剪不理解中段语义；不能据此宣称中间错误不会丢失。
- [Pi serializeConversation](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/coding-agent/src/core/compaction/utils.ts) 将摘要输入中的工具结果截为前 2000 字符，并标明省略字符数。这直接否定“成熟 Agent 一定把完整工具原文交给摘要模型”的假设。
- [Claude Code](https://code.claude.com/docs/en/how-claude-code-works#when-context-fills-up) 明确先清理旧工具输出，必要时摘要，但未公开摘要阶段是否会重新读取被清理的原始输出。不能推断其内部一定恢复全文。

本项目上一轮“摘要前原文必需恢复”的建议应降为可比较的改进候选，而非必须修复的架构错误。当前已观察到省略区误推断的真实风险仍成立；恢复原文可能改善取材，但增加摘要输入与延迟，效果未经对照验证。

### 9.2 回查线索：有更具体的上游机制，但并非统一主题索引

[DSH 查询工具](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/session-query/tool-session-query/README.md) 可选提供事件搜索、替换 / 引用关系追踪及完整事件读取；读取可带相邻事件摘要。当前会话事件搜索截止于发起查询的步骤之前。它能回答“摘要替代了什么、原始事件在哪里”，不等于每份摘要默认生成语义主题表，也不是语义向量搜索。

[Pi 压缩文档](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/coding-agent/docs/compaction.md) 使用目标、约束、进展、决定、下一步和关键上下文的摘要结构，并累积已读 / 已改文件路径。这改善继续工作时的定位，但不保证逐项被省略内容都有来源索引。DSH 摘要提示同样明确要求当前工作、待办、错误及精确路径 / 标识符。

对本项目最直接的借鉴是简洁的接续摘要、少量精确来源及调用 / 结果关联；无需复制整个查询框架或要求模型逐项填表。

### 9.3 近期证据：保留窗口缓解，不是语义上的永久保护

Pi 按切点保留约 20K 近期消息；DSH 按近期预算并维护配对边界。它们不能证明每一条“将来仍有用”的证据都不会被处理。[OpenCode V2](https://opencode.ai/v2/docs/compaction#checkpoints) 默认保留约 15K 的近期序列化内容，其中大工具结果仍会缩至 2000 字符；因此“保留近期”不等于“近期工具原文完全不动”。本轮所核对默认机制未提供按证据语义需要自动永久 pin 的保证。

### 9.4 Codex 原生路线的边界

[Codex 指南](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide#compaction) 与 [Responses 压缩契约](https://developers.openai.com/api/docs/guides/compaction) 描述模型配合的不透明压缩项。独立 compact 接口可能同时返回保留项，整个返回窗口须按契约续传。这是另一条实现路线；公开契约没有给出人类可读的主题索引或任意重要细节无损保证，不能把 API 行为扩展成所有客户端 / provider 分支的统一内部实现。本项目现有 Go Chat Completions 路径不能直接照搬该协议。

### 9.5 收敛建议

保留现有按需减量和切点结构；优先改善摘要对当前工作 / 用户纠正 / 精确错误与来源的表达，并补历史调用与结果关联。简短来源线索值得做；全文摘要取材与更强的近期保护需以实际接续收益决定，不立即加入全量主题图、永久 pin、审核模型或格式门槛。以上仅为本轮比较结论，尚未授权或实施新改动。
