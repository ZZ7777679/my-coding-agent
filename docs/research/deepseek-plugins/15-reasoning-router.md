# dsh-routing-suite：从 persona 实验到阶段化工具和热重载

> 核查日期：2026-09-23。社区项目 `yjh051108/dsh-routing-suite`，固定提交 `195273352f23bff7f9023ebe2ec0cdbdf9c98f10`。根包自报 0.3.3，内部 router / graded 各有版本和实验沿革；本文以实际 preset 装配路径为准。未运行作者实验、安装注入器或修改宿主权限。

## 1. 它解决的不是“再接一个模型”

该项目试图通过 persona、任务分类、近距离提示、工具呈现和阶段协议改变 Agent 行为。仓库包含三部分：injector 提供运行时注入 / 重载；preset 定义每会话的组合与推理风格；graded 管结构化任务阶段与审阅流程。

这里的 react、spec、weak 是作者给提示行为带起的名称，不应直接等同于学术 ReAct、OpenSpec，或模型 API 的 reasoning effort。代码里的 `RL_PERSONA` 也是提示词标识，不能根据变量名宣称插件对模型进行了强化学习训练。

## 2. 仓库和版本为什么特别容易读错

根 README 仍介绍按模型分类 persona、P1–P23 实验和旧路由方式，但 `preset/router-standard/agent.cordis.yml` 实际指向 `router-bootstrap-v34.mjs?v=88`；同目录还有无版本文件和早期快照。只读 `router-core.mjs` 会看到分类函数，却不一定知道当前运行链还在哪些地方采用它。

本次沿 YAML → versioned bootstrap → versioned core 阅读，确认当前主路径已经更强调固定 persona 与阶段化工具。历史核心里的 mode / persona 函数仍有研究价值，但不能把它们描述为每次 system prompt 都会完整执行的当前路由算法。[真实 preset](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/preset/router-standard/agent.cordis.yml)、[当前 bootstrap](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/preset/router-standard/router-bootstrap-v34.mjs)

这也暴露一个维护问题：文件名版本、package version、README 功能和实际 YAML 引用并非同一事实源。若复用其设计，应该把活动策略版本和入口记录到每次运行，而不是让使用者猜当前生效的是哪段实验。

## 3. 安装与运行时注入：改变的不只是 prompt

injector 暴露 dev_* 工具，用 junction / Loader entry 挂载本地包；持久安装还会更新 profile 依赖，使重启后的 bundle 接管。reload 需要清理模块缓存、重新 import、重建 fiber；watch 检测构建产物变化后触发重载。

真正困难的是注入器重载自己：旧 context 已 inactive，不能继续用旧 context 装配新实例。源码因此通过 root context 恢复，还优先刷新官方 bundle；直接 `loader.create` 可能制造与正式 entry 并存的“幽灵 entry”，之后又要仲裁哪个实例有效。[注入器实现](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/injector/src/index.ts)

这条路线提供快速二次开发体验，也依赖 `loader.internal.loadCache` 等内部面，兼容性比公开服务更脆弱。失败自愈和定时重试属于作者策略；我们不应为了插件开发便利把这些内部操作、自动重试或运行时自修改默认引入产品。

## 4. 新会话建立：host plane 与 agent plane 分开

preset 放在单个 Agent 的 scope 中；persona、plan state 和每会话提示可独立，底层 tools registry、会话存储、Goal 服务和执行边界继续属于 Host。需要提供服务的组使用 entry-local isolate realm，避免第二个会话装载时将自己的服务发布到全局并冲突。

这也是为什么不能机械把所有依赖都隔离：如果背景 jobs 或 shell 服务的生产者仍在 Host，而消费工具移入互不可见的 realm，工具会报告服务不可用。源码注释对这些真实装配问题给出了明确区分。

Windows 路径中，它还注册私有 Git Bash shell seam，让 bash 名称对应实际 Git Bash，而不是被宿主 Windows 默认 shell 解释；这与“工具叫 bash”不等于“确实运行 bash”的问题相关。本文没有运行该执行器，也没有验证其受限令牌兼容性。

## 5. 第一个请求：当前实现主动缩小呈现面

当前 bootstrap 监听 `system-prompt/assemble`，先拿到宿主装配结果；跳过子 Agent，对主会话检查是否已经发生工具调用。未 promoted 时只保留 persona、可能存在的 plan section，以及 `phase_begin` 工具，同时返回空 contexts。

promoted 之后再回流宿主 sections，替换 persona，按阶段过滤工具引导，加入阶段说明与常驻行为段。这样既能控制第一轮行为，也会改变大量宿主上下文；这不是毫无副作用地“追加一段提示词”。例如 contexts 被置空就需要判断其他插件注入材料会受什么影响，不能只看单插件测试通过。[当前装配分支](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/preset/router-standard/router-bootstrap-v34.mjs#L629)

前几代采用任务分类：`classifyTask()` 对构建 / 修复关键词命中计数，平手返回 weak；weak persona 根据模型 id 是否包含 flash 选择不同文本。这是启发式规则加提示，不是训练出的 router，更不是对任意新模型都适用的能力检测。[核心函数](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/preset/router-standard/router-core-v34.mjs)

## 6. 工具循环：目录、帮助、可调用范围和阶段推进

项目将理解 / 规划 / 开发 / 验证分成阶段；`tools_catalog` 展示摘要与阶段标记，`tools_help` 按需给完整参数。这里要区分两个机制：渐进披露减少 prompt 中的 schema 体积；`tools.restrict` 则真正缩小此 scope 下可见 / 可调工具集合。前者是上下文优化，后者是工作流约束。

restrictions 是交集。若推进阶段时只加一个更宽的新限制而不释放旧限制，工具仍会被旧窄集合锁住。代码保存 per-session disposer，跨热重载 generation 用共享 Map 找到并释放前代限制，再设置新阶段；交付阶段释放限制。这是可撤销注册在真实插件中很具体的价值。

pre-step 根据新事件判断可否推进，维护 consumed 水位，避免毫秒时间相同的旧工具调用反复触发跃迁。默认当前 `windowFor(stage)` 只包含本档及已开放阶段；旧 preset description 还提到预放下一档，不能据说明认定当前代码仍如此。

这些机制可以减少工具目录干扰，但把阶段工具集配置错，也会让正常任务被阻断。宿主的 OS sandbox 与阶段工具 restriction 又是不同层次：只限制注册表不会隔离同进程插件本身的文件 / 网络访问。

## 7. graded：把任务方案变成显式状态机

graded 的当前源码把大类编辑、锁定、小类编辑、锁定和审阅变成工具驱动状态迁移；计划保存在独立 tree，而非从 todo 自由文本里再解析。redteam verdict 记录通过 / 拒绝及问题，角色和模式也有独立字段。[状态机](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/graded/src/mode-state.js)、[工具](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/graded/src/tools.js)

这比“请严格按计划做”更可观测，但也会把流程规定成硬门槛。工具记下 redteam pass，并不证明一定有独立审阅者运行；作者允许的自演审阅与独立 Agent 的评判也不能混为一谈。

它以 session 文件保存状态，读取失败可能返回 null，写入使用直接 `writeFileSync` 并返回布尔状态。这里不能声称具有完善的原子提交或跨进程事务；热重载时状态能重新读取，只证明一种生命周期解耦方式，并不等于所有故障都可无损恢复。

## 8. 作者实验提供了什么，尚不能证明什么

README 与实验文档报告 persona、近距离引导、任务类型对行为和缓存命中的影响，还说明某些组合对 Pro 与 Flash 表现相反。这支持一个值得检验的假设：**同一套冗长的通用提示不一定适合所有模型与任务**。[作者实验材料](https://github.com/yjh051108/dsh-routing-suite/blob/195273352f23bff7f9023ebe2ec0cdbdf9c98f10/preset/docs/experiments.md)

实验文档开头给出的任务只是检查仓库结构并读 README，输出预算为 max_tokens=1024；触发矩阵每格 n=2，部分消融每格 n=3，另有较小的配置复查。minimal-like / standard-like 分类主要依赖 we、let me 等词及开头标记。这能观察措辞和工具表面对输出风格的影响，不能直接充当真实修复任务的完成率或代码质量指标。

因此样本、模型版本、任务定义和统计口径都限制外推；语言风格分类尤其不能解释模型内部真实推理过程。本次未复算原始实验，不引用其百分比作为独立确认的效果，也不据此认定阶段限制提高了编程成功率。

演化路径更可靠的工程证据是：首次真实用户输入何时可见、hook 是否真的进入模型请求、额外 followup 是否多产生了一次付费调用、热重载是否残留旧限制。这些问题需要沿生产装配链和实际请求事实核对，单看纯函数 router 测试不够。

## 9. 对我们的参考：取机制，保留既定工作方式

可参考的是按需工具目录、每轮策略快照、事件身份水位、可撤销 scope 注册，以及“实际请求采用了什么提示”的 Trace。我们的模型也有明确范围，若以后调整策略，应分别核对 GLM 与 DeepSeek 的真实行为，不能只凭型号字符串复制 persona。

不适合直接采用的是首轮强制 phase_begin、所有任务锁定固定步骤、交付前必须填写统一证据表，以及用工具名推断已完成阶段。这些与本项目已确认的按授权直接推进、最小报告、失败停止和避免额外运行门槛冲突。研究其缺点同样有参考价值。

另有复用前需要澄清的版本事实：根 LICENSE / README 写 MIT，根 package.json 写 BSD-3-Clause，graded package.json 写 Apache-2.0。本文不替作者裁定冲突；当前只分析源码，若真要搬用应核对对应文件的适用许可与声明，不能给整个套件一律标成 MIT。
