# 预装 Skill 精选与内容升级

> 2026-09-22；M4 增量。先记录选择依据，再替换随应用发布的资源。

## 目标与选择依据

现有六项预装方法主要是简短的运行约定，缺少可操作的分析步骤、示例与产出指导。保留讨论、规划、实现、诊断、审查、交接六个稳定身份，以公开成熟方法为基础补齐内容；另预装三个适用范围清晰的专业 Skill。

筛选依据为公开安装量、维护来源、正文实用性、资源完整性和与本应用工作习惯的契合。skills.sh [文档](https://www.skills.sh/docs) 说明榜单来自匿名安装遥测；安装量不等于实际使用人数、好评率或模型效果。此次没有可靠的跨站用户评分，也尚未做模型效果对比，不宣称这些改编稿已经获得上游同等效果。

| 预装身份 | 参考 / 上游 Skill | 2026-09-22 榜单安装量 | 处理方式 |
| --- | --- | --- | --- |
| discuss | Superpowers brainstorming | 371.1K | 适配：目标、约束、问题和方案比较；去掉逐层审批、强制提交 |
| plan | Superpowers writing-plans | 255.1K | 适配：交付切片、文件与接口、完成证据；去掉固定工时、强制 TDD / worktree |
| implement | Superpowers executing-plans | 217.8K | 适配：按交付推进、偏差与接续记录；复用本应用 Goal / 进度语义 |
| diagnose | Superpowers systematic-debugging | 266.6K | 适配：重现、分层定位、单假设验证；不引入强制多层校验、固定失败次数门槛 |
| review | Matt Pocock code-review | 594.1K | 适配：需求与工程质量两个角度；默认本会话审查，不强制派生两个 agent |
| handoff | Matt Pocock handoff | 846.2K | 适配：引用产物、聚焦下一步；保存到项目约定的进度位置，复用已有协作接口 |
| frontend-design | Anthropic frontend-design | 909.1K | 原版正文及许可证；在界面设计任务中按需加载 |
| vercel-react-best-practices | Vercel react-best-practices | 731.3K | 原版正文、规则与示例；只应用当前 React / Next.js 版本相关内容 |
| vercel-composition-patterns | Vercel composition-patterns | 348.3K | 原版正文、规则与示例；针对组件 API / 状态组织，不用于无关后端任务 |

安装量来源：[Superpowers](https://www.skills.sh/obra/superpowers)、[Matt Pocock](https://www.skills.sh/mattpocock/skills)、[Anthropic](https://www.skills.sh/anthropics/skills)、[Vercel](https://www.skills.sh/vercel-labs/agent-skills)。这些计数只记录研究时点，不放入产品运行条件。

## 固定源码与许可证

通过 GitHub codeload 下载公开快照，ZIP 中的 commit 标识如下。读取源码和许可证后选择资源，没有运行上游安装脚本、Hooks 或自动配置。

| 仓库 | 固定提交 | 许可证 |
| --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | `5bf4e78011075bcfc0dc295f0724994cd123ee71` | MIT，根 LICENSE |
| [mattpocock/skills](https://github.com/mattpocock/skills) | `c55ee46073ed923f86ce59a5eb3b6d895095d1b7` | MIT，根 LICENSE |
| [anthropics/skills](https://github.com/anthropics/skills) | `34040c9c568585f6929bedeaad110ad08f079624` | frontend-design 目录 LICENSE.txt：Apache-2.0 |
| [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | `063bee94c3f4df8453406c830b0a7df0f2860278` | 所选两项 SKILL.md 及根 README 声明 MIT；快照无独立 LICENSE 文件 |

每个目录保留 `SOURCE.md`，记录原始路径、提交、许可证和修改范围；复用 `.my-agent-source.json` 给现有界面显示来源。改编资源标明“本应用适配版”，不冒充上游原文。保留上游版权声明；Vercel 附带其原有许可声明和 MIT 标准许可文本，并明确上游无独立许可文件。

没有默认引入：完整 Superpowers 启动框架、TDD / worktree / 自动子 agent 套件；Matt 的 issue-tracker 配置、自动提交等宿主约定；每次必须在线拉规则的 web-design-guidelines；包含固定十项评测流程的 mcp-builder。它们仍可按需从网站导入，此次不把其额外流程变成所有任务的默认要求。

## 落地方式与兼容

- 统一放在 Python 包内 `skills/bundled/<name>/SKILL.md`，附属资源随应用离线发布，不在启动时联网安装。
- 保留 `builtin:discuss/plan/implement/diagnose/review/handoff`；旧方法入口读取同一份资源，移除重复的旧正文。旧 Run 的版本与已归档实际材料不改写。
- 项目 → 用户 → 内置的同名覆盖继续有效。按需正文与目录使用原有请求组装；不会把九份全文默认注入每轮。
- 原版资源保持原文，适配正文按用户语言工作。应用规则仍负责工具身份、授权与失败语义，Skill 不创建第二套执行限制。
- 左侧资源管理展示来源；查看内置资源时先复制成用户 / 项目版本再编辑。项目导入和复制均包含附属文件与来源，避免只复制 SKILL.md 后留下失效链接。
- 不改个人数据、不自动写项目、不新增依赖或运行权限开关，不提交 / 推送。

## 最小验证

复用 Skill 服务场景检查旧身份与覆盖、按需加载和版本归档，补充预装目录 / 附属资源可读及完整复制的检查。涉及的桌面复制交互做一条定向验证和类型检查；检查 Python 分发包包含资源。安装量不能代替功能或模型效果验收，本次不为纯资源替换另做真实模型评测。
