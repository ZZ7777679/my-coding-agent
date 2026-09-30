# DeepSeek Harness 非官方插件与二次开发源码调研

> **历史稿，已撤回作为当前推荐清单。** 用户于 2026-09-23 要求重新调研。本文及同目录正文仅保留来源与历史分析，不再代表筛选后的优先项目或当前建议；新一轮入口为 [重新筛选与调研](../deepseek-plugins-v2/README.md)。

> 截止核查日期：**2026-09-23**。从官方链接的 [GitHub `dsh-plugin` 话题](https://github.com/topics/dsh-plugin) 和社区目录发现项目，沿真实入口分析关键实现。本轮共 16 份 Markdown，固定 28 个仓库快照：22 个第三方项目的代表接入 / 核心链、2 个边界筛查样本、3 个目录及 1 个官方对照基线。固定快照数不等于完整审计数。

## 1. 这轮重点是什么

主体是社区和第三方如何利用 DSH 进行二次开发：增强上下文、沉淀记忆、持续多 Agent 协作、执行工作流、构建桌面 / Web 工作台，以及安装和恢复。每篇先解释要解决的问题，再从仓库组织进入装配、输入、运行和持久化流程，说明具体机制、实际价值及未覆盖部分。

官方代码仅用于核对插件依赖的契约。标了 dsh-plugin 不代表就是原生插件；MCP 接入、Skill、独立产品和同名模型适配都单独区分。未将作者的测试 / 效果数字冒充本次实测。

## 2. 建议按使用流程阅读

| 使用位置 | 正文 | 主要分析的非官方项目与问题 |
| --- | --- | --- |
| 发现、安装与更新 | [市场与生态](11-market-and-ecosystem.md) | dsh-market、社区目录：来源身份、profile、兼容、热挂载、恢复 |
| 打开桌面与工作环境 | [两套社区 Desktop](02-desktop-products.md) | Anywhere Labs、DataElement：资源代际、进程、配置和救援界面 |
| 将 DSH 组合成完整产品 | [话题页产品补查](14-topic-products.md) | Open Design、dsh-web：运行时桥、会话冷恢复、Host 任务调度 |
| 构建请求和检查上下文 | [dsh-context](03-context-inspection.md) | 事件投影、压缩 / shadow、归因、冷历史回填和版本适配 |
| 本地记忆与技能维护 | [dsh-memory-evolve](04-memory-evolve.md) | 记忆快照、候选审查、Skill 改动、协作扩展与 RSI 边界 |
| 对接独立记忆后端 | [OpenViking / Mem9](05-memory-backends.md) | 身份映射、召回、capture / commit、持久与内存队列 |
| 选择行为策略与工具呈现 | [dsh-routing-suite](15-reasoning-router.md) | persona 实验、真实 preset、阶段限制、热重载及过度约束 |
| 持续多人协作 | [NanmiCoder Agent Teams](06-agent-teams.md) | captain / members、DAG、attempt、mailbox、改派和空闲恢复 |
| 工作流和正式会话分工 | [workflow / coordinator](07-workflow-and-coordinator.md) | QuickJS、effect 回放、任务会话、消息、等待及结果边界 |
| 评价、策略演化和职责路由 | [Ouroboros / Odai](08-ouroboros-and-odai.md) | host dispatch、反馈循环、Skill generation、记忆来源与回退 |
| 多模态与外部交互 | [Modlens / Qwen / Browser](09-multimodal-and-browser.md) | 请求转换、MCP carrier、共享取消、真实 tab 绑定 |
| 看成果、操作和恢复 | [Sidebar / GenUI / Rewind](10-workbench-and-rewind.md) | 会话工作台、有限 UI schema、动作回传、恢复计划和 rescue |

如果先关心“我们能用什么”，直接看 [本项目参考总结](12-project-implications.md)。需要复核日期、版本、阅读范围和不足时看 [证据登记](13-evidence-register.md)。[官方宿主契约附录](01-plugin-contract.md) 供遇到 Cordis / scope / bundle 等概念时回查。

## 3. 对我们最有价值的几个发现

1. **上下文应该能解释到来源。** dsh-context 的事件投影与 Modlens 的请求期转换说明：原始历史、当前可见材料和实际发出请求不完全相同，需要可回查的关联。
2. **协作的关键是身份和生命周期。** Agent Teams 的 attempt、Ouroboros 的 dispatch、task-coordinator 的正式会话和浏览器的 tab 绑定，分别避免旧结果、旧资源误落到新工作上。
3. **自进化首先要有可追踪的变化。** 记忆维护、Skill generation 和多代执行是不同层次；候选、激活、回退及独立效果证据比“evolve”命名更重要。
4. **产品化会迫使插件处理恢复。** 两套 Desktop、dsh-market 和 ChangeLedger 都说明：宿主坏掉、恢复一半、关闭 UI 但后台还在运行，需要准确状态和可操作入口。
5. **不能仅跟着 README 判断当前架构。** Qwen carrier 已变薄，Ouroboros 的默认运行方向变了，router preset 的真实入口与旧介绍有差异；这些已在正文中纠正。

## 4. 覆盖范围和时效性如何理解

本轮围绕核心模块选择代表实现，没有逐个穷举话题中的所有条目，也没有按星数宣称某个项目最好。独立企业 / 社区项目有实际代码和产品入口，不等于已核实企业生产采用规模。远程服务、商业套餐、闭源内部架构与性能，本轮没有独立实测证据。

每个主要仓库固定完整 SHA，正文源码链接指向该快照；package version、作者验证的宿主版本和当日官方主线分开记录。旧 peer 范围并未被自动解释成不兼容，也未假装已经验证最新版组合。

源代码只保存为研究缓存并静态阅读；没有运行第三方 Agent、安装依赖、改变个人配置或调用真实模型。正式写入仅限本专题和独立研究进度，保留其他任务对 docs 与实现的修改。
