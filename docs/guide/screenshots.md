# 截图来源与维护说明

[返回指南目录](README.md)

## 本版来源

### M8 增量

2026-10-21，M8／协议 v13 实际 Electron 截图来自 `.artifacts/tests/m8-experience-b8a7L4/`。复制 `workers-graphite.png`、`trace-graphite.png`、`memory-graphite.png`、`chat-经典浅色.png` 和 `workers-125.png` 到本目录 `images/m8-*.png`。子任务错误与正文为离线模型样本；状态、记忆保存、主题设置和 RPC 均真实运行。125% 图使用 Electron 原生截图并核对视口几何，未做后期裁切或拼接。

这些新图用于第 13 篇；其余 26 张仍是下面的 M7 历史采集。M8 真实 Go 验收报告单独留在 progress，不把截图中的错误示例当作线上实测。

### M7 原有图片

- 采集日期：2026-10-21（Asia/Shanghai）。产品源码基线 `008b66c`，M7、协议 v12；本轮未修改产品代码。
- 26 张 PNG 来自实际 Electron / React 页面或可见功能面板。没有用示意图代替应用，没有修改 DOM 文案、伪造连接状态或后期拼接画面。
- 全部使用仓库 `.artifacts/tests/` 下新建的项目和独立数据根。示例项目名 `counter-demo`，不读取个人项目记录、会话或记忆。
- 模型由已有 `DesktopModel` 离线样本提供：回答、思考、token 和调查结论用于演示控件，不代表真实 GLM／DeepSeek 请求或实际提升效果。
- 文件读写、任务／会话／记忆持久化、Git 状态与图配置走真实后端。MCP 连接的是本地两工具示例服务；终端通过真实 PowerShell 启动。沙箱只展示配置，未保存启用；回退只预览，未执行恢复。
- 未进行外网模型请求、在线网站登录、OAuth 授权或浏览器安装。不因这一轮截图宣布这些服务验收通过。既有验收结果另见阶段 progress。

## 图片与原始采集目录

原始目录均位于 `.artifacts/tests/`，每组有 `capture.json` 和自己的示例数据；这部分被 Git 忽略。指南仅复制选用 PNG 到 `images/`，不复制会话、诊断、运行配置或密钥。

| 图片 | 原始目录 | 演示内容 |
| --- | --- | --- |
| project-home.png、task-create.png | guide-core-yjx43j | 项目选择、任务创建 |
| chat.png、session-menu.png、goal.png | guide-core-yjx43j | 完成的离线对话、右键菜单、Goal 启动表单 |
| trace.png、context.png、context-materials.png | guide-core-yjx43j | 真实事件视图、样本请求材料 |
| memory.png、rollback.png | guide-core-yjx43j | 记忆保存与列表、真实文件修改后的回退预览 |
| skills.png、mcp.png、workflows.png | guide-resources-xIS0zF | 内置资源、本地 MCP 已连接、工作流模板 |
| execution-settings.png、sandbox-settings.png、diagnostics.png | guide-resources-xIS0zF | 环境／沙箱配置、尚未运行的诊断入口 |
| editor.png、git.png、terminal.png | guide-workbench-V5SxWC | 隔离文件编辑器、本地 Git 状态、终端控制入口 |
| team-graph.png、team-settings.png、work-graph.png | guide-team-tg3bdR | 两成员关系、可编辑配置、七阶段工作图骨架 |
| review-quick.png、review-findings.png、review-evidence.png、review-budget.png | guide-learning-Jk3vaL | 快捷复盘、离线发现、实际材料范围、独立预算 |

图片中的随机 ID、路径、请求数和时间都是该次样例，不是要求用户输入的值。`files: create`／`files: edit` 是测试样本请求标题，不是应用命令。局部面板图片只展示该区域，不代表窗口全貌。

## 更新截图

使用现有依赖，先构建当前桌面代码，再按功能采集。命令在仓库根目录执行：

```powershell
npm.cmd --prefix apps/desktop run build
node tests/desktop/guide-capture.mjs core
node tests/desktop/guide-capture.mjs resources
node tests/desktop/guide-capture.mjs workbench
node tests/desktop/guide-capture.mjs team
node tests/desktop/guide-capture.mjs learning
```

脚本位于 [tests/desktop/guide-capture.mjs](../../tests/desktop/guide-capture.mjs)。它是显式截图辅助入口，不加入普通回归；每次新建隔离目录，结束关闭自己启动的桌面。重跑前确认当前构建对应欲记录的版本。

采集后逐张检查文字可读、加载已完成、所述按钮实际可见；只复制选定的原始 PNG。同步本表、对应操作步骤及[指南进度](../progress/user-guide.md)。界面入口变化时更新相关篇目，不因为文档变动重跑整仓测试。
