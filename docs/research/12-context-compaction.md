# 上下文压缩：商业 Harness、开源实现与本项目取舍

> 调研截止：2026-09-18。本文核对官方产品文档、API、公开实现和实验报告；没有调用真实模型、重放用户会话或复现论文实验。代码基线为本仓库当前 M2 工作区，实施方案见 [上下文管理方案](../plan/context-management-plan.md)。

## 1. 结论

当前值得采用的方式是：**先用确定性规则减少旧工具输出，再由模型维护增量工作摘要，保留近期完整交互，并允许按需读取原始历史。** 自动触发和手动触发共用这条路径。提前准备摘要、在请求边界替换上下文，减少用户等待。

不同产品的核心差异并不只是摘要提示词：有的使用普通模型生成文本，有的提供服务商专有压缩状态，有的把压缩质量纳入模型训练。它们的可移植性、缓存行为和可检查程度不同。公开资料不足以给出截至本日 Claude Code、Codex、Cursor 的同条件质量排名。

对本项目，优先使用当前选择的 GLM / DeepSeek，通过已有 OpenCode Go 连接生成可读摘要；保持原始日志、用户确认的任务事实与摘要分开。原生 Claude / OpenAI 压缩接口暂不接入，不增加模型、密钥或自动 Review。

## 2. 先区分五种容易混淆的操作

| 操作 | 谁决定内容 | 主要作用 | 代价与边界 |
| --- | --- | --- | --- |
| 旧观察裁剪 / observation masking | 确定性规则 | 把早期大段工具输出替换成结果说明和回读引用 | 无摘要请求；可能增加后续回读 |
| 文本摘要 / compaction | 大模型 + 宿主切分 | 将较早工作转换成可接续说明 | 有模型成本，可能丢失细节或误记结论 |
| 服务商原生压缩 | 服务商 API + 模型 | 返回专用续接状态 | 协议和模型依赖更强，不一定可供其他模型使用 |
| 外部化与检索 | 宿主存储 + Agent 按需读取 | 让完整内容离开常驻输入，但仍可取回 | 需要准确来源、分页和明确的内容完整性 |
| Prompt caching | 服务商缓存 | 减少重复前缀的处理成本与部分延迟 | 没有缩短逻辑上下文，也不替代压缩 |

本文中的“压缩”主要指给后续模型请求准备更小的有效上下文，不是压缩磁盘 JSONL 文件，也不是删除界面中的聊天记录。摘要属于有损表示；保存原件使遗漏可补查，但不会自动保证模型每次都能找回正确细节。

## 3. Claude：产品行为与 API 能力分开看

### 3.1 Claude Code 已公开的行为

官方说明的顺序是先清理较早工具输出，必要时再总结对话；`/compact` 可以指定关注点，`/context` 查看占用。`PostCompact` hook 可以取得可读的 `compact_summary`。这证明产品存在文本摘要产物，不代表其全部内部策略已公开。[运行说明](https://code.claude.com/docs/en/how-claude-code-works)、[Hook 契约](https://code.claude.com/docs/en/hooks)

当前 checkpoint 功能支持从选定位置向前或向后总结，并保留相应未压缩部分；操作不修改磁盘代码，原始内容仍在 transcript 中。这体现了“选择上下文视图”与“撤销文件修改”的分离。[Checkpointing](https://code.claude.com/docs/en/checkpointing)

更新日志早在 **2.0.64** 就宣布自动压缩即时化；本次读取的 **2.1.275** 还修复了 compact / resume 后记忆文件附注变化造成的缓存失效。这里的即时是用户体验目标，不能理解为摘要不消耗计算，也不能仅凭日志还原后台算法。[Claude Code changelog](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md)

**本项目可借鉴：** 老工具内容先减量、手动入口、近期窗口、原始历史，以及不打断界面的后台准备。没有证据支持照搬一个固定压缩比例就能取得同样效果。

### 3.2 Claude API 的两代原生压缩

| 接口 | 核对到的机制 | 设计意义 |
| --- | --- | --- |
| `compact-2026-01-12` | 达到阈值后由所选模型生成 compaction block，并可继续回答 | 宿主接入简单，但请求可能承担摘要等待 |
| `compact-2026-09-04` | 独立按需总结，返回带签名的可读摘要块；可后台准备，之后替换已总结前缀并保留新增尾部 | 将“生成摘要”和“采用摘要”分离 |

新版需要按契约保留完整块及其签名；保留尾部思考还涉及相同 system / tools 和连续未编辑消息。它是原生 Claude API 能力，不能推定 Claude Code 全部请求都走此版本，也不能直接放进 Go 的 Chat Completions 请求。签名不是“无损”或“隐藏向量压缩”的证明。[Claude compaction API](https://platform.claude.com/docs/en/build-with-claude/compaction)

后台思路并非九月才出现：Anthropic **2026-01-16** 的 session-memory cookbook 已演示提前更新摘要，达到切换点时接续未总结尾部。示例中的即时体验依赖摘要已经准备好，缓存收益也依赖前缀命中；它是实现示例，不是所有 Claude Code 内部行为的证明。[Session-memory cookbook](https://platform.claude.com/cookbook/misc-session-memory-compaction)

另一个独立能力是 context editing：规则清除旧工具结果或思考块。它与模型摘要不同；修改已缓存前缀也可能产生缓存重建成本。旧客户端 SDK 的 compaction helper 已被弃用，不能继续按早期教程作为最新推荐接口。[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

## 4. Codex：客户端控制 + 模型原生续接状态

Codex 配置公开了 `model_context_window` 和 `model_auto_compact_token_limit`，支持调整自动压缩阈值；App Server 暴露 `thread/compact/start`，以 `contextCompaction` 项目报告生命周期。RPC 立即返回受理，不代表摘要已经完成或对用户没有等待。[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)、[App Server](https://learn.chatgpt.com/docs/app-server#trigger-thread-compaction)

截至 **2026-09-17 的 CLI 0.155.0**，官方更新记录包括支持服务商的流式远端压缩，以及压缩失败时仍保存已接收用户输入。前者说明客户端路径仍在演进，后者提醒我们新输入必须先落盘，不能因为压缩失败而消失。[官方 changelog](https://learn.chatgpt.com/docs/changelog)

OpenAI 将 compaction 描述为与模型协同的能力。Responses API 既支持阈值触发，也支持独立 `/responses/compact`；输出可包含不透明的加密续接项。独立接口返回的是完整规范窗口，应按契约续传整个结果，不能只抽取其中一个加密项。[Codex 模型指南](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide)、[Responses compaction](https://developers.openai.com/api/docs/guides/compaction)

**与普通文本摘要的区别：** 服务商可以保留宿主无法解释的状态；宿主的可读性与跨模型迁移能力较弱。公开契约不足以证明这是 KV-cache、固定潜向量格式或无损编码，也不足以证明所有 Codex provider / 登录路径采用相同机制。

**本项目取舍：** 借鉴持久化边界、流式状态和完整窗口续接契约；不在 Go 上模拟一个假的 OpenAI 原生 compaction 字段。普通摘要与将来可能加入的 provider-native checkpoint 应有不同类型。

## 5. Cursor 与 Factory：质量优化还发生在模型训练和信息组织上

### 5.1 Cursor Composer 的 self-summarization

Cursor 在 **2026-03-17** 介绍将摘要步骤纳入 Composer 强化学习轨迹，以后续任务结果评价压缩质量。报告称其内部困难代码任务上的压缩错误减少约 **50%**，摘要约为原基线的 **1/5**。这是训练与运行协同，不是仅修改摘要提示词；不能把效果直接归给任意模型或本项目双模型。[Self-summarization](https://cursor.com/blog/self-summarization)

Cursor 也公开了另一条通用做法：长工具结果写成文件，模型按需读取；完整会话历史可作为可搜索文件补查。动态发现降低初始输入，减少被迫摘要的次数。文章中的 **46.9%** 指特定 MCP 工具发现实验，不能当作通用会话压缩收益。[Dynamic context discovery](https://cursor.com/blog/dynamic-context-discovery)

**本项目可迁移的是外部化与历史检索；模型训练方案只作长期参考。** 两者不能混为“已经拥有 Composer 的摘要质量”。

### 5.2 Factory 的 anchored iterative summarization

Factory 的 **2025-12-16** 报告采用持续更新的结构化摘要，评估涉及 **36,611 条消息**及回忆、产物、接续和决策探针。报告中的总体分数为 Factory **3.70**、Anthropic **3.44**、OpenAI **3.35**，满分 5；产物追踪三者都偏弱。[实验与方法](https://factory.com/news/evaluating-compression)

这些是厂商自测、旧接口与特定模型裁判的结果，不能改写为 2026 年 9 月三种完整产品的排名。其更有用的启示是：摘要质量要看“下一步能否正确工作”，文件 / 命令 / 错误来源最好由宿主单独索引。文字看起来流畅或压缩率很高，都不足以证明接续可靠。

## 6. 开源 Harness 怎样实现可迁移的部分

| 项目 | 核心路线 | 对本项目的启示 |
| --- | --- | --- |
| DeepSeek Harness | 压力触发，按边界保留近期交互，模型总结较早内容；可先清理工具结果 | 参考相同请求前缀与会话身份，避免为摘要重建整套运行时 |
| Pi | 独立摘要请求、旧摘要增量更新、近期尾部和日志中的 compaction entry | 参考持久化切点与文件操作索引；不照搬重试策略 |
| OpenCode V2 | 本地控制的摘要流程，兼容 provider 可选择原生压缩 | “本地压缩”不等于离线；Go 服务与 OpenCode Harness 是两层 |

**DSH 核对基线：** 固定提交 `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`，并对照当前说明。`summarizeWithLlm` 真实调用模型，复用 system / tools / 已有前缀，再附加摘要指令；它并非确定性拼接。默认触发比例与保留比例是可配实现值，没有证据表明它们对所有模型最优。[说明](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/README.md)、[summarizer 源码](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/src/summarizer.ts)

**Pi 核对基线：** 2026-09-18 的 `earendil-works/pi` 移动分支。其摘要使用专门提示与序列化历史，保存切点，原始 JSONL 保留；文件操作由宿主另行收集。源码在有传入 sessionId 时复用它，并非文档概述中的一律创建新 ID；长回合切分也可能产生多次摘要调用。这里以具体源码为准，未声称锁定最新发布版。[设计说明](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md)、[实现](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/compaction/compaction.ts)

**OpenCode 核对基线：** V2 文档。本地摘要仍向所选模型发送请求，并以完成的 checkpoint 重新构造后续窗口；provider-native 路线依服务商能力选择。不能把 V1 的配置项、V2 的行为与 Go 的 API Key 混成一种能力。[OpenCode V2 compaction](https://opencode.ai/v2/docs/compaction)

以上只分析机制，没有复制上游代码。DSH 既有审计保存了固定源码；Pi 移动分支没有取得 commit pin，后续真正复用代码前仍需固定版本和核对许可证。

## 7. 效果证据：什么能比较，什么不能

### 7.1 规则裁剪未必弱于模型摘要

《The Complexity Trap》**v3，2025-10-27** 在 SWE-agent / SWE-bench Verified 上对比旧观察遮蔽与 LLM 摘要。其 Qwen3-Coder 480B 一组结果为：

| 方法 | Solve rate | 每题成本 |
| --- | ---: | ---: |
| 保留原始上下文 | 53.4% | $1.29 |
| 旧观察遮蔽 | 54.8% | $0.61 |
| LLM 摘要 | 53.8% | $0.64 |

这是论文 v3 表格，不与早期版本的数字混用。置信区间重叠，不能据此宣称遮蔽必然提高成功率；它说明在这类工具输出密集任务中，昂贵的语义摘要未稳定优于简单裁剪。部分摘要轨迹变长也提醒我们观察总完成成本。[论文 v3](https://arxiv.org/html/2508.21433v3)

本项目还包含需求讨论、用户纠正和跨回合决策，不能直接套用单次修复基准；这些内容比可重新读取的编译输出更需要语义摘要。

### 7.2 用相同维度比较机制

下表是基于上述机制的工程分析，不是产品实测排名。

| 维度 | 规则裁剪 | 普通模型摘要 | 原生服务商压缩 | 训练过的自摘要 |
| --- | --- | --- | --- | --- |
| 首次整理等待 | 很小，无额外生成 | 有额外请求，可提前准备 | 依接口与调度，不能假定免费或即时 | 仍有生成开销，可与调度配合 |
| 用户纠正 / 决策 | 不负责理解，需要原文或任务事实 | 可归纳，但会遗漏、混淆新旧 | 内部表示难检查 | 有任务训练信号，仍需验证 |
| 文件与长日志细节 | 外部化后按需回读 | 摘要容易漏路径、失败信息 | 不透明，不等于完整保留 | 训练收益不等于细节无损 |
| 双模型迁移 | 通常容易 | 可读文本较容易 | 常受 provider / 模型契约限制 | 依赖实际可用模型 |
| 缓存影响 | 改旧前缀可能失效 | 摘要生成可命中旧前缀，采用后需建立新前缀 | 依 provider 契约 | 依运行实现 |
| 适合本项目 | 先做 | 核心能力 | 暂缓接入 | 暂作参考 |

### 7.3 更少 token 不自动等于更低费用、更快首字

应比较完整成本：

```text
总成本 = 摘要请求 + 后续输入/输出 + 历史回读 + 重复工作
用户等待 = 前台生成摘要等待 + 后续模型首字等待 + 必要回读等待
```

Go 对缓存输入的计价明显低于普通输入，尤其 DeepSeek Flash；同一会话的主请求与辅助请求需要保持 `x-opencode-session`。因此不断改前缀、频繁做小摘要可能抵消节省。连接池复用减少连接建立开销，不能省去摘要模型的生成时间。[Go 接入与计价](https://opencode.ai/docs/go/)

**设计推论：** 小窗口先裁剪，真正积累到有意义的量才总结；摘要提前生成，采用后保持稳定，不按每次新消息重新生成摘要。以总请求数、缓存量与用户等待验证效果，不只看压缩百分比。

## 8. 本仓库当前的真实缺口

以下来自本地代码核对，不是已实现清单：

| 现状 | 问题 | 后续处理 |
| --- | --- | --- |
| `SessionLog.context()` 重放会话事实，运行循环累计历史 | 缺少独立的有效上下文组装器 | 保留完整历史重放，另建请求窗口组装 |
| `max_context_bytes = 600000`，超出返回 `BUDGET_CONTEXT` | 字节预算被当作终点，没有自动压缩路径 | 将其纳入整理压力；不能当成模型 token 容量 |
| 用户任务目标 / 约束和 Goal 已有独立记录 | 摘要可能再次复述并逐渐改写事实 | 当前权威状态独立注入，摘要只提供工作接续 |
| 工具结果已有长度限制，程序日志只有有界尾部 | 历史 JSONL 不等于保存了所有原始输出 | 新内容在裁剪前归档；历史缺失明确标识 |
| Go 适配仅公开输入 / 输出 token | 看不到缓存命中与摘要成本 | 返回存在对应字段时统计，否则显示未知 |
| 已有流式活动、Goal 与模型切换 | 容易把压缩等待显示成“模型思考” | 压缩独立活动类型，关联请求和摘要记录 |

相关源码：[运行循环](../../src/my_agent/runtime/loop.py)、[会话存储](../../src/my_agent/sessions/store.py)、[默认值](../../src/my_agent/defaults.json)、[模型客户端](../../src/my_agent/models/go.py)、[网页工具](../../src/my_agent/tools/web.py)、[执行存储](../../src/my_agent/execution/store.py)。

特别需要纠正一个容易过度承诺的表述：当前不能说“所有原始工具结果已经落盘，随时完整恢复”。被截去的旧进程日志和网页内容无法凭摘要重新创造；重新执行命令也不是读取历史。

## 9. 最终采用方式

建议本项目采用以下固定方向，参数在实现时集中配置：

1. **权威任务事实独立保存。** 用户确认的目标、约束、纠正以及 Goal 状态不由压缩模型改写。
2. **先减少旧观察。** 老的大块工具结果换成简短状态与准确引用；近期交互和在途工具保持完整。
3. **同模型增量摘要。** 使用当前 Go 模型更新“上次摘要 + 新进入较早区间的交互”，记录来源范围；不引入额外便宜模型。
4. **保留近期尾部。** 完整保留用户新消息和工具调用 / 结果配对，不机械截断最后若干条消息。
5. **提前准备，边界采用。** 后台摘要对应不可变切点，完成后只替换它覆盖的前缀；新追加内容自然留在尾部。
6. **原始历史可回读。** 首批使用来源序号和词法检索，不上向量数据库或知识图谱。
7. **过程可看，规则少设。** 输入区提供自动 / 手动入口及占用、摘要、费用和状态；不增加摘要完整性审查、固定标题校验或人工批准门槛。

这不是把所有厂商功能叠在一起：首批核心是一个上下文组装器、一个摘要服务与现有日志的回读入口。具体数据结构、后台边界、失败处理、参数与实施顺序见 [上下文管理方案](../plan/context-management-plan.md)。

## 10. 证据边界与接续

- 本文没有在 GLM / DeepSeek 上取得压缩质量、首字时间或成本的实测数字，不把论文和厂商数据作为本产品承诺。
- 商业产品文档能证明公开行为；模型内部表示、训练细节和默认内部提示没有公开的部分保持未知。
- 历史实验与最新接口分开标日期。Claude 九月 API、Codex 9 月 17 日版本与早期 Factory / 学术实验不能直接横向排名。
- 后续只需用一个简单完整任务做有针对性的接续比较，再确定默认阈值与摘要长度；不把大型评测平台作为业务实现前置条件。
- 本文是研究结论，配套方案是设计产物；上下文压缩尚未实现，也未提交 / 推送 Git。
