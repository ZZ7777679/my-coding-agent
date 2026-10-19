# 来源、版本与证据边界

> 访问日期：2026-10-19。优先官方发布页、官方产品 / API 文档及固定版本 changelog。不将搜索排序、社区转述或宣传效果当作本项目验证。

## 1. 上次基线

- [四个 Agent 专题](../agents/README.md)：2026-09-21 源码快照。
- [协作专题](../multi-agent/README.md)：保留当时机制与比较。
- [DSH 生态第二轮](../deepseek-plugins-v2/README.md)：2026-09-23 截止，包含第三方产品；本轮没有重新审计所有候选。
- [当前 M5 实际进度](../../progress/m5.md)和[10-19 回顾](../../progress/project-status-and-roadmap-2026-10-19.md)：判断“已有能力”的依据。

此前 Claude `2.1.88` 材料包含非官方历史源码镜像；本轮不将其用作当前 Claude Code 内部实现证据。产品机制只按当前官方公开契约说明。

## 2. 官方来源登记

| 编号 | 来源 | 日期 / 固定版本 | 本轮用途 |
| --- | --- | --- | --- |
| D1 | [DSH 0.2.0-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.0-rc.1) | 2026-09-28 12:36 UTC | 版本变化基线 |
| D2 | [DSH 0.2.1-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.1) | 2026-10-17 05:22 UTC | 团队投递、等待、扩展与轨迹生命周期 |
| D3 | [DSH 0.2.1-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.2) | 2026-10-17 | 1017 模型 / 搜索接入的后续发布 |
| P1 | [Pi 1.0.0](https://github.com/earendil-works/pi/releases/tag/v1.0.0) | 2026-10-01 19:20 UTC | 1.x 发布基线 |
| P2 | [Pi 1.3.0](https://github.com/earendil-works/pi/releases/tag/v1.3.0) | 2026-10-15 19:17 UTC | 切模型、恢复工具和适配修复 |
| P3 | [Pi 固定 changelog](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/coding-agent/CHANGELOG.md) | `71023aec1546d6d677a65669c5665c0927ce0dd0` | 0.99–1.3 的工具搜索、CodeMode 与请求链路增量 |
| H1 | [Hermes 0.22.0](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.0) | 说明标 10-13；发布 10-14 03:21 UTC | 记忆集成边界、子任务、维护失败处理 |
| H2 | [Hermes 0.22.2](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.2) | 2026-10-15 08:21 UTC | 最新补丁状态；不将大版本发布当作无已知问题 |
| A1 | [Claude Mods 公告](https://claude.com/resources/articles/claude-code-mods) | 2026-10-01 | 已确定首发日期的宿主扩展能力 |
| A2 | [Mods 当前文档](https://code.claude.com/docs/en/plugins/mods) | 当前滚动文档 | 区分扩展、Skill 与 MCP；不视为新首发日期 |
| A3 | [动态工作流](https://code.claude.com/docs/en/workflows) | 当前滚动文档 | 完整 Agent 编排、保存结果与恢复语义 |
| A4 | [Claude 2.1.299](https://github.com/anthropics/claude-code/releases/tag/v2.1.299) | 2026-10-14，页面标 02:49 | 空闲压缩与配置能力 |
| A5 | [Claude changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) | 当日读取到 `2.1.303`；`main` 非固定 SHA | 辅助核对后续修复；未逐版本核实发布时间 |
| A6 | [API 压缩总览](https://platform.claude.com/docs/en/build-with-claude/compaction) | 当前 beta 文档 | 区分服务端协议与客户端通用机制 |
| A7 | [后台压缩](https://platform.claude.com/docs/en/build-with-claude/compaction-background) | `compact-2026-09-04` beta；本轮补读 | 固定前缀、保留新增消息、请求边界采用 |
| O1 | [Codex 官方 changelog](https://learn.chatgpt.com/docs/changelog) | `0.163.0`，2026-10-15 | 用户可见变更；PR 清单只作开发进展 |
| C1 | [Cursor token 效率](https://cursor.com/blog/improved-token-efficiency) | 2026-09-23 | 上游生产实践，收益不外推 |
| G1 | [OpenCode Go](https://opencode.ai/v2/docs/console/go/) | 当前文档 | 模型端点、session header 与客户端要求 |
| G2 | [OpenCode Web Search](https://opencode.ai/v2/docs/console/websearch/) | 当前文档 | 避免把托管搜索误当 Go key 通用接口 |
| G3 | [OpenCode 1.x changelog](https://dev.opencode.ai/changelog/) | 核对至 1.19.3，10-16 | CLI 版本与 Go 服务契约分开，不要求本项目迁移 CLI |
| S1 | [DeepSeek 1017 公告](https://api-docs.deepseek.com/news/news261017/) | 2026-10-17 | 模型更新及 Search / Fetch 开放 |
| S2 | [DeepSeek 搜索指南](https://api-docs.deepseek.com/guides/search/) | 当前文档 | 直接工具接口及认证 |
| S3 | [Search API](https://api-docs.deepseek.com/api/search/) / [Fetch API](https://api-docs.deepseek.com/api/fetch/) | 当前 API 文档 | 端点与请求形式 |

用于固定快照的发布 commit：

| 对象 | Commit |
| --- | --- |
| DSH 0.2.0-rc.1 | `4878cdabd87d4041bdaff61d04c966883b9fd07a` |
| DSH 0.2.1-rc.1 | `1600d8a1e140dcde43a1a0941940a0480712c011` |
| Pi 1.0.0 | `a13d35a742c6ef8462812a28fbe1d8c8b7431c32` |
| Pi 1.3.0 | `71023aec1546d6d677a65669c5665c0927ce0dd0` |
| Hermes 0.22.0 | `e06df9c2eae6901f4c88f464e0ae6e753c0428b8` |

这些身份用于资料追溯，不代表下载和审计了相应版本全部源码。未复制上游代码，也未引入新的许可证依赖。

## 3. 取得方式与限制

研究缓存位于 Git 忽略的 `.artifacts/research/release-update-20261019/`，保存公开 changelog、发布 HTML / 提取文本及 `fetch-manifest.json`。该目录没有用户 key 或个人会话。

- GitHub 匿名 Releases API 请求遇到 403 限流，改从公开发布 HTML 与固定 raw 文件获取；没有使用账户 token。发布页中的 UTC 时间和 tag commit 用于版本表。
- OpenAI 官方文档检索成功，单次 Markdown fetch 返回 404，随后通过官方网页读取 changelog；没有用第三方转载补造功能。
- Pi 一个猜测的 harness README 路径返回 404。它不能证明上游模块被删除，未据此提出架构迁移结论。
- 部分资料只有滚动文档，无法证明首发日期；在正文按“当前机制 / 本轮补读”处理。
- 另查 Letta 官方文章和 Anthropic 工程文章，搜索结果主要落在本轮之前；没有将旧记忆方案或社区最近转发冒充本月新发布。

本轮执行了网页 / 公开文件读取、本地相关代码阅读和文档定向检查。**未运行上游 Agent，未测试旧 / 新 Go 地址，未调用真实模型，未验证缓存收益、后台压缩质量、Search / Fetch 效果或百万 token 负载。** 没有修改产品、系统网络、依赖或 Git 分支状态。

## 4. 解释规则

官方发布声明证明上游声称交付了什么，不证明其没有缺陷；源码入口证明本地目前如何组装，不等同于运行复现。厂商效果数字、实验开关、API beta、预发布 tag 和正式默认能力分别处理。

产品建议均标明为我们基于资料和本地结构的判断。尤其不能从“某个上游删除 invariant 插件”推断所有校验都无意义，也不能从其新增重试 / 限制推断我们必须照搬。取舍继续遵守用户要求：结构简单、正常任务能推进、真实失败可解释、没有额外审批和报告门槛。
