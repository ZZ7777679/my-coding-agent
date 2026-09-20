# 证据、时效与覆盖台账

> 统一访问日与检索截止：**2026-09-16**。本文件用于核对十一篇专题的研究依据，不能替代专题正文。第二轮补查见第 9–10 节及[复查记录](00-review-2026-09-16.md)。所有结论均需结合来源的对象、版本、实验条件与公开深度理解。

## 1. 怎样阅读本台账

“发布”是资料出现的日期，“更新”是后续修订，“访问”是本轮查看日期。三者不同。没有可靠发布日期的产品文档标为动态文档，不把搜索引擎抓取时间当成发布日期。

证据类型也不构成简单高低排名：规范能说明协议要求，源码能说明一条实现路径，实验能说明特定条件下的表现，企业案例能说明公开采用方式，社区讨论能说明真实疑问。任何一种都不能自动替代其他类型。

| 标识 | 本轮阅读达到的程度 | 可支持与不可支持的结论 |
| --- | --- | --- |
| 规范 / 文档 | 查看对应正文与相关接口说明 | 支持公开契约；不等于客户端真实兼容通过 |
| 关键源码 | 阅读具体文件或方法，结合文档解释 | 支持该路径的机制；不等于全仓安全审计或运行验证 |
| 论文方法 | 阅读设计、算法或实验条件中的相关部分 | 支持机制与原作者实验解释；未复现结果 |
| 论文摘要 / 元数据 | 核对标题、日期、摘要或限制 | 用于方向、沿革与范围；不能宣称通读全文 |
| 企业自报 | 厂商工程文章、客户材料或产品更新 | 支持公开实践与自报结果；不等于独立因果评价 |
| 社区意见 | 原始帖子、评论、维护者讨论 | 支持存在该意见；不能按点赞数推导正确性 |
| 访问受限 | 正文失败、只取得片段或入口 | 只使用能确认的信息，相关细节留空 |

本轮没有统一下载和冻结所有上游源码快照。标注 `main` / `master` 的链接均是移动版本；采用源码时需要另行固定提交。这里没有“运行通过”这一证据等级，因为本轮没有进行第三方项目实测。

## 2. 记忆与能力组织

| 来源 | 原始时间 / 状态 | 本轮证据与影响 |
| --- | --- | --- |
| [Generative Agents](https://arxiv.org/abs/2304.03442)、[MemGPT](https://arxiv.org/abs/2310.08560) | 2023-04、2023-10 | 原论文概念与设计；模拟环境、分层内存不能直接等同企业验收 |
| [Letta Context Repositories](https://www.letta.com/blog/context-repositories/) | 2026-02-12 | 企业自报与产品设计；文件版本化、渐进读取，不代表冲突自动正确解决 |
| [Mem0 平台迁移](https://docs.mem0.ai/migration/platform-v2-to-v3) | 动态平台文档 | 正文；ADD-only、异步写入与多信号检索需要区别于旧论文和 OSS |
| [Graphiti nodes](https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/nodes.py)、[edges](https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/edges.py) | 访问日主分支 | 关键源码；节点、证据、有效与失效时间字段，未验证所有存储后端 |
| [Hindsight 0.9.0](https://hindsight.vectorize.io/blog/2026/08/06/hindsight-0-9-0) | 2026-08-06 | 官方版本说明；Knowledge Pages 与 coding 使用场景，未复现性能主张 |
| [LLM Wiki 原始 gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | 2026-04-04 起；持续评论 | 原文与讨论；idea file、ingest / query / lint，非统一产品或标准 |
| [Persona](https://github.com/saxenauts/persona) | 访问日仓库 | README、结构与作者复盘；后续方向 Syke，比较口径有条件差异 |
| [PersonaTree](https://arxiv.org/abs/2606.04780) | 2026-06-03 | 论文设计与摘要；人物知识生命周期，不泛化为所有用户画像系统 |
| [LongMemEval-V2](https://arxiv.org/abs/2605.12493) | 2026-05-12，work in progress | 论文方向与实验说明；环境经验评价，未复现完整协议 |
| [GitHub Agentic Memory](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/) | 2026-01-15 | 企业工程与 A/B 自报；使用时核验、PR 合并比例，非本项目成功率 |
| [Agent Skills](https://agentskills.io/specification) | 动态规范；2025 年开放标准沿革 | 规范正文；渐进加载、元数据，实验字段不保证全部宿主支持 |
| [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog) | 2026-07-28 版本 | 规范正文与变更；新版交互不能用早期会话教程代替 |
| [MCP Roadmap](https://modelcontextprotocol.io/development/roadmap) | 动态路线图 | 区分计划与已进入规范的能力；未把路线图目标作为交付事实 |

Skill、Code Mode、Webflow MCP2.0 与 Skills over MCP 的具体原始链接和状态在[02 专题](02-skills-tools-mcp.md)相应段落；“MCP2.0”必须指明说的是厂商产品、讨论用语还是正式协议版本。

## 3. 自进化、RSI 与推理模式

| 来源 | 原始时间 / 状态 | 本轮证据与影响 |
| --- | --- | --- |
| [Reflexion](https://arxiv.org/abs/2303.11366)、[Voyager](https://arxiv.org/abs/2305.16291) | 2023 年 | 原始机制；语言经验与程序技能不必改权重，环境范围有限 |
| [GEPA](https://arxiv.org/abs/2507.19457)、[实现](https://github.com/gepa-ai/gepa) | 2025-07；动态实现 | 论文机制与实现接口；反思、候选保留、评价器不是同一角色 |
| [gskill](https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/) | 2026-02-18 | 方法与实验文章；仓库生成任务，部分数字口径不完全一致，不复制排名 |
| [ACE](https://arxiv.org/abs/2510.04618)、[实现](https://github.com/ace-agent/ace) | 2025-10；动态实现 | 论文与 playbook 结构；稳定 ID、增量更新及反馈归因 |
| [Hermes 优化项目](https://github.com/NousResearch/hermes-agent-self-evolution) | 访问日状态表 | 项目文档；已实现 skill 阶段与 Planned 阶段明确分开 |
| [DGM](https://arxiv.org/abs/2505.22954) | 2025-05-29 | 原始方法；候选档案与经验搜索，未取得数学改进保证 |
| [AHE v4](https://arxiv.org/abs/2604.25850v4) | 2026-04 首版、05 修订 | 论文方法与条件；组件、经验和决策可观测性 |
| [autoresearch](https://github.com/karpathy/autoresearch) | 访问日主分支 | 仓库与任务指令；受限训练实验，硬件与预算影响比较 |
| [Harness-of-Harness](https://arxiv.org/abs/2609.01481) | 2026-09-01 | 新预印本；持续软件开发循环与作者实验，未作为成熟部署 |
| [STOP](https://arxiv.org/abs/2310.02304) | 2023-10 首版，2024 发表 | 方法、元数据与作者限定；改进程序应用于自身，冻结模型 |
| [SICA](https://arxiv.org/abs/2504.15228) | 2025-04 首版 | 论文方法与实验；子集结果不能写成完整 SWE-bench 成绩 |
| [MetaSkill-Evolve](https://arxiv.org/html/2607.05297v1) | 2026-07-06 | 方法与附录相关部分；任务 skill / meta-skill 双层更新，有界递归 |
| [Beagle / DarwinX](https://github.com/SalesforceAIResearch/Beagle) | 2026-09-02 开源记录 | 仓库架构与许可；演化实验设施，未本机运行 |
| [AI4AI-Bench](https://arxiv.org/abs/2608.20318) | 2026-08 | 任务设定与摘要；改善训练算法的评价，不等同完整 RSI |
| [RSI 综述](https://arxiv.org/abs/2607.07663) | 2026-07 | 摘要、分类与元数据；未通读综述所收录的全部论文 |
| [Self-Ask](https://arxiv.org/abs/2210.03350)、[作者实现](https://github.com/ofirpress/self-ask) | 2022-10 | 原论文与示例入口；子问题分解、外部信息，不是不断询问用户 |
| [Plan–Execute](https://www.langchain.com/blog/plan-and-execute-agents)、[Planning Agents](https://www.langchain.com/blog/planning-agents) | 2023、2024 | 官方架构说明；研究中区分静态计划、执行与重规划 |
| [LLMCompiler](https://arxiv.org/html/2312.04511v3) | 2023 首版、后续修订 | 方法正文；DAG、结果绑定、调度、动态重规划 |
| [ADaPT](https://arxiv.org/html/2311.05772v2)、[ReCAP](https://arxiv.org/html/2510.23822v1) | 2023、2025 | 方法与算法；按需分解和父计划接续是不同机制 |
| [RLM](https://arxiv.org/abs/2512.24601)、[实现](https://github.com/alexzhang13/rlm) | 2025-12 首版、2026-05 修订 | 论文机制与运行环境说明；LocalREPL 不等于沙箱 |
| [动态子 Agent](https://www.langchain.com/blog/introducing-dynamic-subagents-in-deep-agents) | 2026-06-29 | 官方实现文章；程序编排完整子 Agent，预算与汇合仍要设计 |

ReAct、ReWOO、ToT、GoT、LATS、Self-Refine、CRITIC、PAL、PoT、CodeAct、S* 的论文分别链接在[07 专题](07-reasoning-modes.md)，正文解释其状态、控制方式与限制。历史论文用于原理，2026 模型 API 的能力以访问日官方文档为准；未直接验证 OpenCode Go 对全部上游字段的转发行为。

## 4. 工作流、Coding Agent、Harness 与上下文

| 来源 | 原始时间 / 状态 | 本轮证据与影响 |
| --- | --- | --- |
| [OpenSpec concepts](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)、[customization](https://github.com/Fission-AI/OpenSpec/blob/main/docs/customization.md) | 访问日主分支 | 产物、schema 与工作流文档；artifact 依赖与执行图分开 |
| [Spec Kit](https://github.com/github/spec-kit) | 访问日主分支 | 当前入口与流程；未沿用所有任务都走同一瀑布的旧描述 |
| [Superpowers skill](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md) | 访问日主分支 | 实际技能文本；审查与修复循环。调研其内容不等于在本任务执行它 |
| [旧 GSD](https://github.com/gsd-build/get-shit-done)、[GSD Core](https://github.com/open-gsd/gsd-core) | 旧仓库 2026-06-26 归档 | 仓库维护状态与后继说明；两者不能混作同一不变实现 |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 动态文档 | thread 内检查点与跨 thread store，不等于外部世界事务 |
| [Temporal](https://docs.temporal.io/workflow-execution)、[Activities](https://docs.temporal.io/activities) | 动态文档 | 持久执行、历史、重试与幂等；未运行服务 |
| [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/) | 动态文档 | 当前产品边界与语言差异；不混淆 AutoGen / Semantic Kernel 的历史定位 |
| [GitHub Agentic Workflows](https://docs.github.com/en/copilot/concepts/agents/about-github-agentic-workflows) | 动态文档 | Markdown 编译、Actions 与 safe outputs；未部署工作流 |
| [mini-swe-agent default.py](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) | 当前 v2 主线 | 关键源码；查询、预算、格式错误与轨迹保存，不宣称完整容错 |
| [Pi](https://github.com/earendil-works/pi/tree/main/packages/coding-agent) | 当前仓库入口 | 包说明与扩展文档相关段落；未全读全部扩展源码 |
| [OpenHands SDK](https://docs.openhands.dev/sdk/arch/overview) | 动态架构文档 | Agent / Conversation / Workspace 与工具分层；托管产品另有边界 |
| [Codex App Server](https://learn.chatgpt.com/docs/app-server) | 动态官方文档 | thread / turn / item、steer、interrupt、transport；实验能力单列 |
| [Claude Code](https://code.claude.com/docs/en/how-claude-code-works)、[OpenCode Server](https://opencode.ai/docs/server/) | 动态产品文档 | 循环与公开 API；文件 checkpoint、服务接口不能推出任意外部撤销能力 |
| [Roo Code](https://github.com/RooCodeInc/Roo-Code) | 2026-05-15 归档 | 当前维护状态；作为历史实现，不承诺继续维护 |
| [Gemini CLI core](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/package.json) | 访问日主分支 | 架构与包清单；分包与许可，未验证全部安全策略 |
| [Fusion](https://cognition.com/blog/devin-fusion)、[Local Fusion](https://cognition.com/blog/local-fusion) | 2026-06-29、2026-09-11 | 厂商架构与更新；lead / sidekick、持续上下文、成本口径有条件 |
| [Cursor Scaling Agents](https://cursor.com/blog/scaling-agents) | 2026-01 | 企业实验；角色、共享锁与扩展瓶颈，不将代码量等同质量 |
| [Cognition HIL / SIL](https://cognition.com/blog/how-to-automate-failure-triages-and-10x-test-generation-what-weve-learned-deploying-ai-across-hilsil-workflows) | 2026-05 | 客户案例；分诊、领域 playbook、测试生成，自报且非随机对照 |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md) | Developer preview；动态主分支 | 架构正文与关键调用边界；未将流事件全部视为已持久化事实 |
| [Anthropic 长任务](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)、[后续 Harness](https://www.anthropic.com/engineering/harness-design-long-running-apps) | 2025-11-26、2026-03-24 | 企业实验；交接、完成契约、独立验收，不给出普遍成本优胜结论 |
| [Aider repomap.py](https://raw.githubusercontent.com/Aider-AI/aider/main/aider/repomap.py) | 访问日主分支 | 关键源码；语法标签、关系排名与预算，不称精确编译器调用图 |
| [GraphRAG 查询](https://microsoft.github.io/graphrag/query/overview/) | 动态文档 | Local / Global / DRIFT / Basic 区分；未验证特定项目检索收益 |
| [SWE-grep](https://cognition.com/blog/swe-grep) | 2025-10-16 | 企业研究文章；专用代码检索与返回定位，演示与严格基准分开 |

## 5. 评测、可观测性、安全与恢复

| 来源 | 原始时间 / 状态 | 本轮证据与影响 |
| --- | --- | --- |
| [SWE-bench](https://www.swebench.com/) | 动态官方站 | 基准范围与相同 mini Agent 视图，未复制动态榜单排名 |
| [Terminal-Bench 版本](https://www.tbench.ai/benchmarks)、[4.0](https://www.tbench.ai/news/terminal-bench-4-0) | 4.0：2026-08-28 | 任务、资源与评分版本变化；不能与旧分数直接比较 |
| [Harbor 核心](https://docs.harborframework.com/core-concepts)、[独立评分](https://docs.harborframework.com/core-concepts/tasks/separate-verifier)、[重评](https://docs.harborframework.com/core-concepts/jobs/regrade) | 动态新文档域名 | 正文；运行与评分分离，重评需要旧产物完整存在 |
| [Harbor 产物收集](https://docs.harborframework.com/core-concepts/jobs/artifact-collection) | 动态文档 | best-effort 不自动使 Trial 失败；必须检查证据完整度 |
| [OTel GenAI 迁移](https://opentelemetry.io/docs/specs/semconv/gen-ai/)、[新仓库](https://github.com/open-telemetry/semantic-conventions-genai) | 访问日迁移状态 | 旧文档不再维护；Agent spans 仍为 Development |
| [LangSmith 观测](https://docs.langchain.com/langsmith/observability-concepts)、[评测](https://docs.langchain.com/langsmith/evaluation-concepts) | 动态正文 | run / trace / thread / trajectory 与在线 / 离线目标；搜索旧摘要与现正文已有差异，以正文为准 |
| [LangSmith 标注](https://docs.langchain.com/langsmith/annotation-queues)、[OTel](https://docs.langchain.com/langsmith/trace-with-opentelemetry) | 动态文档 | 人工队列与非 LangChain 接入；观测身份不替代业务身份 |
| [SmithDB](https://www.langchain.com/blog/introducing-smithdb) | 2026-05-13 | 企业架构自报；对象存储、元数据与服务分层，未实测性能 |
| [LangSmith LLM Gateway](https://www.langchain.com/blog/langsmith-llm-gateway-runtime-controls-for-production-agents) | 2026-07-30 公测 | 运行请求控制与追踪结合；不构成本项目更换网关或静默 fallback 的建议 |
| [Tuned Evaluators](https://www.langchain.com/blog/introducing-langsmith-tuned-evaluators-starting-with-perceived-error) | 2026-08-18 | 产品与 Vanta 自报；异步感知错误评价，不等同事实验证 |
| [LangSmith 自托管](https://docs.langchain.com/langsmith/self-hosted) | 动态商业条件 | Enterprise 附加能力；公开 SDK 不等于整个服务端开源 |
| [Langfuse 实验模型](https://langfuse.com/docs/evaluation/experiments/data-model)、[政策](https://langfuse.com/handbook/chapters/open-source) | 动态文档 | 实验关联、重复样本限制、核心与企业治理边界 |
| [Phoenix](https://arize.com/docs/phoenix)、[LICENSE](https://github.com/Arize-ai/phoenix/blob/main/LICENSE) | 访问日主分支 | 文档与许可文件；当前 ELv2，不能写成 MIT 类许可 |
| [METR 更新](https://metr.org/blog/2026-02-24-uplift-update/) | 2026-02-24 | 原文与限制；新实验选择偏差，不将点估计写成普遍速度结论 |
| [Claude Code 使用研究](https://www.anthropic.com/research/claude-code-expertise) | 2026-06-16 | 观察性研究；样本发生于 2025-10 至 2026-04，非现实结果的全面追踪 |
| [CaMeL](https://arxiv.org/html/2503.18813v2) | 2025 年研究 | 设计与限制相关章节；控制流、数据流、策略维护，不声称注入已解决 |
| [Chrome Agent 安全](https://blog.google/security/architecting-security-for-agentic/) | 2025-12-08 | 产品架构；Critic 与 Origin Sets，初始实现与完整设计分开 |
| [带外防御评估](https://arxiv.org/abs/2606.26479) | 2026-06-25 | 摘要与限制；小规模自适应实验，未阅读全部实现 |
| [配置漏洞披露](https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/) | 2026 年披露；发布前已修复 | 研究者原文；加载顺序与授权边界，不写成当前仍受影响 |
| [Anthropic 隔离总结](https://www.anthropic.com/engineering/how-we-contain-claude) | 2026-05-25 | 企业工程自报；内容、模型、环境多层防御，未独立审计 |
| [Sandbox Runtime](https://github.com/anthropic-experimental/sandbox-runtime) | 访问日 Windows alpha | 当前 README；账户、WFP、ACL 与限制。搜索缓存曾含旧细节，以正文为准 |
| [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) | 官方页更新 2025-07-14 | 系统文档；进程组、例外、终止与资源，不等同完整沙箱 |
| [OWASP Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)、[Skills](https://owasp.org/projects/agentic-skills-top-10) | 前者 2025-12 发布；后者 Incubator | 两个项目成熟度分开，不把风险目录当作合规认证 |

## 6. 社区、访问失败与不能推出的结论

社区原始材料包括 LLM Wiki gist 评论、Hermes 用户反馈和维护者 AMA、LangChain 普通 / deep agent 讨论、METR 更新解读、sandbox-runtime 讨论。正文注明其意见属性，没有用社区自报数字代替论文或正式版本状态。[记忆讨论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)、[Hermes 反馈](https://www.reddit.com/r/hermesagent/comments/1upvfe7/hermes_agents_selfimprovement_does_it_actually/)、[LangChain 讨论](https://forum.langchain.com/t/what-are-the-differences-between-ordinary-intelligent-agents-and-deep-intelligent-agents/3095)

以下保留首次访问与第二轮补查的区别，没有用二手转述补成“已经读过原文”：

| 材料 | 访问或证据限制 | 正文处理 |
| --- | --- | --- |
| Stripe Minions 两篇 | 首次正文提取不完整；第二轮已读取文章，part 2 用浏览器核查完整正文 | 04 已补 Blueprint、完整 Agent 节点、工具选择与企业环境前提；不推断全部内部源码 |
| Manus 上下文工程文章 | 首次正文失败；第二轮已取得原文 | 08 已补缓存、文件与错误保留；2025 年经验不作为 2026 年全部接口约束 |
| ProgramBench | 独立站首次失败；第二轮通过 arXiv 读取任务构建与评价方法 | 09 已补程序行为重建与测试边界，未复现结果 |
| 2026 年部分 RSI 新材料 | 预印本、公开时间很近；少数只核对摘要 | 标明成熟度与读取深度，不宣称部署有效 |
| 商业系统内部实现 | 只有公开文档、SDK、工程文章 | 不猜测未公开调度、存储与模型权重 |
| 全部第三方项目 | 未安装与运行；未做性能、兼容和攻击实测 | 所有选型建议均为待验证判断 |

## 7. 完整度检查应检查什么

本轮按问题轴检查覆盖，而不以链接数量代表完整：记忆是否有写入、读取、冲突、遗忘与版本；能力是否区分发现、组合和执行；演化是否覆盖改进器自身；推理是否覆盖分解、行动、重规划、搜索与反馈；工作流是否区分产物依赖和运行状态；评测是否同时包含公共基准、平台和业务收益；安全是否覆盖执行前、执行中及恢复后。

LangSmith 在早期评测草稿中的遗漏已经纠正：现有正文按数据对象、线上到离线评价、标注、Studio、SmithDB、Gateway、Tuned Evaluators、自托管条件展开，并与 Langfuse、Phoenix 使用相同维度比较。这个遗漏也说明不能以“看过若干知名项目”宣称市场完整，代表方案的选取必须与问题轴对应。

第二轮已补 Agents SDK、ADK 2.0、CrewAI Flows、Braintrust、Weave、Step-Back / Self-Discover 和独立协议专题，但仍未对全部 SDK、平台和推理变体做同等深度分析。十一篇专题是按问题轴组织的资料研究与工程解析，不是全行业穷尽检索、系统综述元分析或实测选型报告。

## 8. 下一次更新的具体核查顺序

1. 核对正式协议、仓库归档 / 迁移、预览转正式、许可证等会改变采用条件的事实。
2. 对准备采用的实现固定 commit / release，重新阅读关键路径与依赖边界。
3. 补齐本轮访问受限的原始材料，再决定是否扩大其分析篇幅。
4. 用本项目代表任务进行同模型、同预算的小规模验证，区分资料分析与实测证据。
5. 对记忆与自进化观察更新后是否持续有益，而不是只看一次演示成功。

这是后续维护建议，未创建定时任务，也不意味着本轮已获自动安装、付费评测或系统权限变更授权。

## 9. 第二轮补查：新增证据与版本校正

下表只记录本轮新增或加深的材料；已有专题来源仍保留在前文和对应正文。日期未知的动态页面不编造发布日期，链接也不表示整个站点均已读完。

| 来源 | 日期 / 版本 | 阅读深度与具体用途 |
| --- | --- | --- |
| [A-MEM](https://arxiv.org/html/2502.12110v11) | 首发 2025-02；核查 v11，2025-10 | 方法：note 构造、连接与旧记忆演化；01 补原始事实与派生解释的区别 |
| [SimpleMem](https://arxiv.org/html/2601.02553v3)、[仓库](https://github.com/aiming-lab/SimpleMem) | v3，2026-01-29；访问日仓库 | 方法与 README；v1 异步递归合并不能代表 v3 在线合成，论文与新增模块分开 |
| [SAGE](https://arxiv.org/html/2605.30711v1) | 2026-05-29 | 方法 3.1–3.4；密度与自适应路由，不把节省决策调用写成零写入成本 |
| [MemGate](https://arxiv.org/html/2606.06054v1) | 2026-06-04 | 方法 IV-A / IV-B；连续向量门控与候选重排，不误写为原文删词或访问控制 |
| [MIPROv2](https://dspy.ai/api/optimizers/MIPROv2/)、[Flex](https://dspy.ai/diving-deeper/flex/) | 动态文档；Flex experimental | 候选生成、搜索与模块代码优化；结构、参数和 RSI 的不同对象 |
| [TextGrad](https://arxiv.org/abs/2406.07496)、[官方示例](https://github.com/zou-group/textgrad) | 2024-06 首发；当前 README | 论文摘要与 Variable / loss / TGD 示例；未逐模块审计源码 |
| [Agent Lightning v1 报告](https://arxiv.org/html/2608.17528v1)、[仓库](https://github.com/microsoft/agent-lightning) | 2026-08-19；当前 v1 主线 | Trainer / Gateway / Rollout Controller 与真实调用采样；旧版结构不可混用 |
| [ADK 2.0](https://adk.dev/2.0/)、[Graph](https://adk.dev/graphs/) | Python GA 05-19、Go GA 06-30、TS GA 08-21，均为 2026 年 | 官方正文；新图运行时、类型化节点数据与事件迁移 |
| [CrewAI Flows](https://docs.crewai.com/v1.15.21/en/concepts/flows) | 页面版本 1.15.21 | 持久状态、恢复 / 分叉与缺失恢复源行为；不等同外部副作用恢复 |
| [Agents SDK](https://developers.openai.com/api/docs/guides/agents/running-agents) | 动态官方文档 | Runner、历史管理、暂停续接；与托管 Agents API 分开 |
| [Agents API 架构](https://developers.openai.com/api/docs/guides/agents-api/architecture)、[环境生命周期](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle) | 访问日官方文档；未核定首发日 | harness / executor / 应用分工，断连、空闲与资源清理；未真实调用 |
| [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)、[backends](https://docs.langchain.com/oss/python/deepagents/backends) | 动态文档；固定源码见下节 | 状态、文件后端、装配与持久化边界 |
| [DeerFlow 2 公告](https://github.com/bytedance/deer-flow/discussions/3795)、[当前 README](https://github.com/bytedance/deer-flow/blob/main/README.md)、[RFC](https://github.com/bytedance/deer-flow/issues/4308) | 公告 2026-06-25；README / RFC 为访问日状态 | 当前跨 Worker 取消与租约；旧 409 行为已不能概括现状；RFC 不视为已合入 |
| [SWE-agent ACI](https://github.com/SWE-agent/SWE-agent/blob/main/docs/background/aci.md)、[Goose](https://block.github.io/goose/) | 经典机制 / 当前产品入口 | 工具交互设计、企业分叉与公开核心的区别；未运行 |
| [Step-Back](https://arxiv.org/html/2310.06117v1)、[Self-Discover](https://arxiv.org/html/2402.03620v1) | 2023-10、2024-02 的原始方法版本 | 阅读抽象机制与 SELECT / ADAPT / IMPLEMENT，不将旧实验数值套给当前模型 |
| [Least-to-Most](https://arxiv.org/abs/2205.10625)、[Self-Consistency](https://arxiv.org/abs/2203.11171) | 2022 年首发 | 论文摘要与机制定位；本文工程示例为独立推演 |
| [Test-Time Scaling](https://arxiv.org/html/2608.04001v1) | 2026-08-04 | 分类与评价框架；整体系统、候选集合与复现条件分开 |
| [OpenViking 架构](https://github.com/volcengine/OpenViking/blob/main/docs/en/concepts/01-architecture.md)、[API](https://github.com/volcengine/OpenViking/blob/main/docs/en/api/06-retrieval.md) | 访问日 main 文档 | 分层上下文、服务端组装、URI 与版本；未审计完整固定源码 |
| [Braintrust](https://www.braintrust.dev/docs/evaluate)、[高级实验](https://www.braintrust.dev/docs/evaluate/advanced-evaluations) | 动态文档 | task / scorer / experiment、逐样本 trials 和记录层级 |
| [Weave 对象](https://docs.wandb.ai/weave/guides/tracking/objects)、[Evaluation](https://docs.wandb.ai/weave/tutorial-eval) | 动态文档 | 调用与对象版本、数据集及评分器；不推断全栈许可或语言功能对齐 |
| [ProgramBench](https://arxiv.org/html/2605.03546v1) | 2026-05 | 任务构建与测试方法，补足首次访问缺口 |
| [A2A](https://a2a-protocol.org/latest/specification/) | 当前正式 1.0.0 | 任务 / 产物 / 状态、协议绑定和版本协商；未运行兼容测试 |
| [Agent Client Protocol](https://agentclientprotocol.com/protocol/v1/prompt-turn)、[原 Communication Protocol](https://agentcommunicationprotocol.dev/introduction/welcome) | 当前 v1 文档 / 已并入 A2A 的公告 | 两个 ACP 不混用，回合停止与取消确认分开 |
| [AG-UI](https://docs.ag-ui.com/concepts/events) | 访问日事件规范 | 快照 / JSON Patch / 消息等不同状态，草案与正式事件不混列 |

### 距检索日较近的材料

| 日期 | 原始来源 | 影响的具体判断 |
| --- | --- | --- |
| 2026-09-03 | [MCP in LangChain](https://www.langchain.com/blog/mcp-in-langchain-stateless-protocol-elicitation-and-more) | SDK 接口迁移、beta 状态与协议可用性分开 |
| 2026-09-08 | [子 Agent 上下文](https://www.langchain.com/blog/organizing-context-in-a-multi-agent-harness) | fork 与 isolated 按职责选择，不能笼统认为子 Agent 一律不继承历史 |
| 2026-09-08 | [SWE-Bench Pro Verified](https://arxiv.org/abs/2609.08149) | 新预印本；执行时泄漏、任务与测试质量；未获得本研究独立复现 |
| 2026-09-09 | [Connections](https://www.langchain.com/blog/connections-managed-credentials-and-per-caller-identity-for-managed-deep-agents) | 连接所有者与凭据类型分开，能力目录应结合调用者 |
| 2026-09-10 | [Credit Genie / OpenWiki](https://www.langchain.com/blog/how-credit-genie-uses-openwiki-to-keep-codebase-knowledge-fresh-searchable-and-automated) | 客户使用代码驱动 Wiki 更新；跨仓库增强仍为后续方向 |

## 10. 源码固定程度与核查边界

本轮通过 `git ls-remote` 记录以下 HEAD。**记录 HEAD 不等于阅读该提交的源码**，更不等于运行通过。

| 仓库 | 2026-09-16 观察到的 HEAD | 本轮实际核查 |
| --- | --- | --- |
| langchain-ai/deepagents | `7f9e8ed3a555933902045792da9bb184950ee7b2` | 已读取此提交的 `libs/deepagents/deepagents/graph.py`，支持装配与权限继承分析 |
| bytedance/deer-flow | `a58ab484a641fd5928ae512ad21c5c7fd7a18c18` | 当前 README、changelog 和讨论；未将 main 内容伪称固定源码审计 |
| volcengine/OpenViking | `25a17fa228f7625b38b3733ab1e8a2194a478fe1` | 当前架构、URI 与检索文档；未审计全部实现 |
| microsoft/agent-lightning | `736dc6ab6867c3a720942c43c3d8d39bff299a9a` | 当前 README、基础文档与 v1 论文；未运行训练 |

部分 GitHub API 的命令行访问被当前网络环境拒绝，未为此更改代理、TLS 或系统配置；改用官方网页、原始文本和公开文档完成不依赖该访问方式的核查。正文提取失败也不直接判定资源已经删除。

本轮没有逐个验证全部历史外链的可达性。对决定本次新增结论的来源读取原文，对未完成固定源码或独立验证的部分保留范围；后续选型时应先固定准备采用的实现，而不是依据整个仓库的星数或“最新”标签批准部署。

## 11. 2026-09-18 M3 联合调研补充

本次新增来源与逐项链接集中在 [专题 13](13-m3-context-memory-collaboration.md)，未将以上 9 月 16 日台账日期整体更新。该专题分别记录公开产品行为、源码机制与本项目推导，主要增量为：

| 来源 | 本次核对基线 / 深度 | 不据此宣称 |
| --- | --- | --- |
| Claude Projects | 2026-09-17 官方发布正文；与当前 Agent Teams / subagents 文档比较 | 已公开云端记忆算法，或本机多会话冲突已自动解决 |
| Codex | 官方本地 memories、subagents 与 Responses compaction 文档 | 全部服务端源码已审计，或原生压缩适用于 Go 双模型 |
| DeepSeek Harness | `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720` 的 summarizer、协作来源类型、subagent 说明、MCP memory 示例 | 参考 memory 配置等于核心默认长期记忆，或整个仓库已运行 |
| Pi | `71dca871bc80b6bc97be37f0ca3189399d651fff`，提交页为 2026-09-11；读取压缩源码 / 设计与 README | 该快照就是查询日最新 HEAD；扩展能力就是核心默认行为 |
| OpenCode / Gemini / OpenHands / Cline | 当前官方 compaction、memory、subagent 文档 | 所有版本行为相同，或已逐产品实测 |
| Cursor / Copilot / Devin / Cascade / Letta / Factory | 当前官方页面及注明日期的工程文章 | 厂商结果可以跨模型直接排名；旧 Cascade memory 适用于新 Devin Local |

公共 GitHub API 的本机访问未成功，未修改代理 / VPN；通过官方网页固定 Pi 提交并读取目标文件。未安装、复用源码或进行效果实验。本项目方案见 [M3 总体方案](../plan/m3-implementation-plan.md)，状态见 [M3 进度](../progress/m3.md)。

同日用户要求进一步吸收前期技术后，定向重读 SimpleMem v3、A-MEM v11、ACE v3、RLM v3，以及 OpenViking 架构、Deep Agents 子上下文、Hindsight、SWE-grep 官方资料；具体来源和采用差异保存在 [M3 技术吸收](../plan/m3-technology-adoption.md)。OpenViking 前期固定提交的文档本次抓取失败，改读官方 main，未把动态页面描述为固定源码核查。Graphiti、LLM Wiki、SAGE / MemGate、GEPA 等仍沿用前期已注明范围，没有重新声明全篇验证或实际效果。
