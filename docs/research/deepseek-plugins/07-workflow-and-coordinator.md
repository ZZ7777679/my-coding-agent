# dsh_workflow 与 task-coordinator：可执行流程和可见会话分工

> 核查日期：2026-09-23。两者都扩展调度，但管理对象不同。本文分别沿各自完整流程分析，再说明与持续 Agent Teams 的关系。

## 1. dsh_workflow：把一次编排变成可复用制品

固定仓库 `icetomoyo/dsh_workflow`，提交 `44b83c182aa02d1be8a0803e8446cb495f93cd8f`，0.1.2、MIT。peer 仍指向早期 DSH 0.0.1-rc.2，README 安装路径指向 `dsh-external/dsh_workflow`；本次固定的是前者，未将两个仓库认定为完全等同，当前宿主兼容尚未实测。

### 1.1 要保存的不只是提示词

该插件保存 workflow capsule：manifest、source、intent、inputs、requires、provenance。一次运行再产生 snapshot、事件、artifact、用量和任务结果。这样相同流程可以重新输入数据执行，而不必每次让模型从零描述如何拆分与汇总。

`catalog.ts` 发现流程；`author.ts` 协助主 Agent 生成；`capsule.ts` 管格式；`service.ts` 接命令与工具；`engine.ts` 管执行；`runtime.ts` 执行受限脚本；`store.ts` 保存产物。结构明确把“生成流程”和“执行流程”分开。

### 1.2 用户请求进入后，模型与脚本分别做什么

用户发起命名 workflow 或自然语言创建。自然语言请求成为正常用户消息，authoring contract 作为独立插件材料，避免内部协议污染标题。主 Agent 调查 workspace 后提交 source + manifest，再进入 preflight 和启动。

脚本的核心接口是 `async run(wf, args)`。`wf` 暴露 phase、spawnAgent、wait、parallel、pipeline、synthesize、artifact 等能力。模型决定任务描述，脚本组织依赖与数据传递，Host 执行真正的子 Agent 调用。它不同于每一步都再问模型“接下来做什么”。

### 1.3 受限执行真正采用了什么

当前源码使用 **QuickJS / quickjs-emscripten**，不是 Node 的 `vm`。传入脚本的能力经 JSON 编解码桥接，拒绝循环结构和不可序列化值；禁用隐式时间与 Math.random，要求显式输入，减少续跑时的非确定性。

宿主维护 pending guest promises 与 host dispatch 集合；超时关闭桥接、通知上层取消，等待已接纳 dispatch 收敛后再销毁 VM。否则一个已经释放的 VM 可能被晚到结果继续唤醒。[受限运行时](https://github.com/icetomoyo/dsh_workflow/blob/44b83c182aa02d1be8a0803e8446cb495f93cd8f/src/runtime.ts)

QuickJS 限制的是工作流脚本能够直接访问的对象。它调用的子 Agent 仍可能获得文件和 shell 工具，因此不能将这个 VM 称为所有项目执行的 OS sandbox。

### 1.4 并发、用量与结果缓存

engine 维护 task 状态、活跃数量、semaphore、预算预留和真实用量。每个任务开始前解析输入及隔离选项；执行后保存结果和 origin。

续跑通过缓存身份与 occurrence 匹配已完成结果，命中后标为 `replayed-from-cache`，不启动新 Agent。身份计算还考虑运行条件和文件状态相关依据。它是重新执行编排、复用已记录效果的设计，不是恢复一个任意暂停位置的 JavaScript 堆栈。[Engine](https://github.com/icetomoyo/dsh_workflow/blob/44b83c182aa02d1be8a0803e8446cb495f93cd8f/src/engine.ts)

仍需保留结果未知窗口：某个 Agent 已经写文件，但结果尚未保存就崩溃，不能凭缺少缓存认定“从未执行”，再次运行可能重复副作用。缓存也不能说明外部依赖、网站或环境未变化。

### 1.5 价值与适用范围

它适合重复调查、并行候选与汇总、固定评审流程。当前仓库还自带较重的评审协议和结构化输出修复；这些是具体工作流选择，不是所有 coding task 都应经历的前置流程。

本项目已有工作流模板，但模板阶段与依赖还不是可执行 scheduler。该项目提供了从“模板数据”走到“执行器”的清晰增量：版本化定义、一次运行身份、子任务句柄、结果来源、取消和显式续跑。是否允许自动修复 / 重试仍需遵守我们现有规则。

## 2. task-coordinator：把独立会话变成可调度的工作对象

固定仓库 `Kayungko/dsh-plugin-task-coordinator`，提交 `5861812edf762ece99e65171cf14f161f0ff7aa2`，0.26.7、MIT。README 中仍有较早验证徽章，清单对 client connection 的范围止于 0.1.6 之前；应区分老文档的已测版本、当前源码和未知的新宿主兼容。

### 2.1 它创建的是顶层会话

与内部 worker 不同，新任务进入普通侧栏，可被用户直接打开、继续和管理。supervisor 使用 task_list / progress / spawn / send / wait 等工具；消息带 coordinator 来源，目标会话能够知道谁在委派。

这适合几项需要长期独立上下文的工作，不适合把每个短函数分析都拆成侧栏新任务。用户可见身份是产品选择，会带来命名、workspace 归属、归档和权限边界的长期成本。

### 2.2 仓库的 DI 分层值得参考

`index.mjs` 负责 Host import 和装配；`tools.mjs` 与 `commands.mjs` 面向模型和用户；`ops.mjs` 用 `createOps(deps)` 接收 sessionController、agents、registry 等；`registry.mjs` 管派生的持久关联；`family.mjs`、`feedback.mjs` 管族谱与反馈；client 只补充界面。

因此操作逻辑不需要 import 一个完整宿主才能解释，宿主契约变化主要集中在装配 / 适配位置。这种思想与我们现有显式 bootstrap 很接近。[操作实现](https://github.com/Kayungko/dsh-plugin-task-coordinator/blob/5861812edf762ece99e65171cf14f161f0ff7aa2/ops.mjs)

### 2.3 派发怎样留下身份

spawn 先校验请求和路线，计算父会话 / depth、workspace 与可选 externalRef，然后调用 sessionController 创建会话、设置模型并发送首条输入，再记录关联。工具创建成功与整个批次全部成功不是同一回事，部分失败必须返回实际结果。

外部关联号只是存储和回显的身份，不应被解析成执行指令。源码也保留了宿主 selectModel 可能改变全局默认模型的说明，表明一个看似局部的会话操作可能有更广副作用，迁移到本项目时必须保持“当前请求快照、下次请求应用选择”的现有语义。

### 2.4 send、steer、wait 不是一个动作

send 可排入 follow-up 或在 step 边界 steer；返回交付信息和队列状态。wait 监听活跃 Agent 的 `whenIdle()`，与超时 / abort 竞争，不靠模型持续轮询。

但 idle 只表示本轮不运行，不能直接等同任务成功；仍需读取报告与实际输出。协调消息被宿主接受也不意味着目标会话已经消化。跨任务追踪应保留 source session、target session、请求和实际 Run 的关联，而不是只有一段聊天文字。

### 2.5 当前持久化方式的取舍

registry 使用临时文件 + rename，损坏文件保留为 corrupt 副本，并降级为空关联集。这样的容错让插件继续工作，却可能丢失递归深度、父子关系等约束依据。对仅展示的辅助索引可以讨论降级，对承担权限或预算身份的状态就不能直接套用。

它还实现进程内的计划确认凭证和部分可复用授权；重启后凭证消失。我们项目不需要因此加一套重复审批，只应保留“派发依据与具体任务绑定”的思路。[作者架构说明](https://github.com/Kayungko/dsh-plugin-task-coordinator/blob/5861812edf762ece99e65171cf14f161f0ff7aa2/docs/ARCHITECTURE.md)

## 3. 三种模式应如何组合

| 模式 | 持久对象 | 适合的问题 | 主要新增复杂度 |
| --- | --- | --- | --- |
| task-coordinator | 用户可见的顶层会话及关系 | 多条长期工作线的分工和交接 | 会话归属、消息与 Run 对应 |
| Agent Teams | team、持续 member、task attempt | 共享任务池和成员复用 | claim、改派、迟到结果、恢复 |
| dsh_workflow | 可执行 capsule 和 run | 可复用的依赖 / 并行 / 汇总流程 | 确定性、缓存、副作用与取消 |

我们可以先改善现有多会话分工与追踪，再引入一条有实际用途的可执行流程，最后按需求增加持续团队。将三个模式都包装成一个模糊的“多 Agent 工具”，会掩盖它们不同的生命周期。
