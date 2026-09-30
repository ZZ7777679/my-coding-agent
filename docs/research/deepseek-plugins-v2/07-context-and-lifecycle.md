# 上下文与扩展生命周期：请求、能力和配置何时真正生效

> 2026-09-23。主线为 dsh-context、billion-context、dsh-market，补充两个当日更新的 zhang-guo-wen 插件。固定版本见 [证据登记](09-evidence.md)。低热度样本用于验证具体机制，不被包装成生产成熟度排名。

## 1. 这些插件共同解决什么问题

一个 Agent 界面可能显示了很长的聊天历史、几十个已安装插件和刚保存的设置，但模型下一次真正看到什么、正在调用哪个版本、退出后哪些资源仍在运行，未必与界面直觉一致。

可以把链路拆为：用户选择配置 → 宿主装配能力 → 会话准备请求材料 → 模型调用 → 工具副作用 → 事件保存与显示 → 更新 / 恢复。dsh-context 主要解释已发生的请求；billion-context 直接改写发送到模型的上下文；MCP manager 管能力加载与连接；Claude compat 管规则进入请求；market 管安装配置与宿主重新启动。把它们都称作“增强插件”会掩盖完全不同的责任。

## 2. dsh-context：从持久事件重建“当时模型看到了什么”

### 2.1 仓库组织和版本核实

本篇使用当日再次取得的完整文本快照 `2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7`，package 仍为 `0.54.4`，Apache-2.0。它较当天早些时候的快照又有日志解码计数等改动，因此 package 版本相同也不能代替提交身份。1,488 Star / 46 Fork 表明它有独立关注，但没有安装量资料。

`src/host` 把状态折叠、时间线、活动、归因、定价估算、回填和详情通道分开；`src/shared` 放前后端共用类型 / 估算规则；`src/client` 消费投影并提供面板。核心不是前端读整段日志后临时算几个 token 数，而是 Host 把事件变成可缓存的请求视图。[Host 装配](https://github.com/bowenliang123/dsh-context/blob/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7/src/host/index.ts)

### 2.2 请求怎样进入投影

插件注册 session projection，宿主在已提交的会话事件上驱动 reducer。`fold.ts` 维护模型可见 surface、系统材料、工具 schema、请求记录、成本与时间等状态。没有变化的事件返回原对象，实际变化再产生新状态；投影保持可序列化 JSON，且按完整用户回合保留有限历史，避免截断一个回合的中间步骤。

压缩和剪枝尤其需要区分“历史仍存在”与“当前请求已经替换”。源码先记录会被遮蔽的具体事件 seq，再在对应替换到来时更新 surface 与净释放量。若只用摘要声明的范围推算，可能把已经由先前替换产生的节点算错；若只记录被移除 token，不扣除新摘要成本，趋势图也会夸大收益。[状态折叠](https://github.com/bowenliang123/dsh-context/blob/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7/src/host/fold.ts)

这直接说明为什么上下文可视化不能只是聊天 UI 的另一种配色。聊天记录回答“发生过什么”，模型请求视图回答“这一调用实际带了哪些材料”，两者必须能关联，但不能互相冒充。

### 2.3 历史、详情与成本怎样控制

新投影加入后，旧会话可能没有相应缓存。`backfill.ts` 等到仪表盘第一次打开才启动后台回填，逐个读取冷会话并刷新投影；正在运行的会话跳过，由正常事件驱动维护，避免冷回填与活跃写入争抢。单个旧日志读不了只影响自身，不阻止用户打开其他会话。[历史回填](https://github.com/bowenliang123/dsh-context/blob/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7/src/host/backfill.ts)

详情通过可选通道加载，概览无需总携带大块内容。文本 token 计算使用启发式密度，图片有额外规则并依赖尺寸信息；这些估算不应与模型返回的真实 usage、账单成本混写。最新日志解码也分别记录 reasoning / text / tool arguments 的块与时间，说明性能显示要跟随实际流格式演化，不能一直假定所有 chunk 都是回答正文。[估算](https://github.com/bowenliang123/dsh-context/blob/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7/src/host/pricing.ts)、[流式日志解码](https://github.com/bowenliang123/dsh-context/blob/2ae7cfa7f8f1e4b0ff0b31c9abdfa12ac803a9f7/src/host/logShapes.ts)

### 2.4 本项目参考

我们已实现上下文预览、压缩 / 回读和 Trace。可借鉴的是在同一请求上关联来源、替换关系、估算与真实 usage，并让历史概览使用可重建的轻量投影；不是再建一个完全平行的日志系统。面板或历史读取失败不应升级为正常 Goal 的执行前置条件。

## 3. billion-context：在模型 API 前增加一层可回读的上下文处理

### 3.1 为什么纳入低热度样本

该项目当日公开页为 251 Star / 29 Fork，明显低于主线产品。入选理由是它实际介入了请求转发、压缩工具、会话归属和原文回读，能用于对照我们自己的压缩系统。固定提交 `b2f28c6a4a854d88382509eb4f5531465c989793`，package `0.1.139`，依赖 `acp-kernel` `0.0.82`，MIT。内核在独立依赖中，本轮未深入审计该依赖的全部压缩算法。

当前 DSH 核心入口是 `src/agent/dsh-native.ts`，旧 `dsh-acp.ts` 不能代表完整接入。`src/agent` 管宿主适配和请求拦截；代理入口处理模型协议；`session.ts` 管压缩会话与原文缓存；`decompress-shared.ts` 管回读；部分历史工具与循环模块已变为共享内核的薄转发。只按文件名挑一个旧 compress 文件，会把入口迁移误判为功能缺失。

### 3.2 从 DSH 请求到代理

原生插件尝试连接指定代理，或启动自身代理；拦截 `globalThis.fetch` 中符合模型 API 形状的请求，转向代理路径。它使用 DSH 的当前发起者信息给请求附加会话身份，并只在本地压缩工具完成注册后标记 plugin mode。否则代理一旦误以为工具已由宿主注册，停止自行注入，就可能产生一份根本没有压缩工具的请求。[DSH 入口](https://github.com/ranxianglei/billion-context/blob/b2f28c6a4a854d88382509eb4f5531465c989793/src/agent/dsh-native.ts)

这个分支解释了集成的核心风险：可用的工具、发送的协议标记和会话归属必须在同一请求上保持一致。URL 相同也不能推导所有请求都是主 Agent；同进程的辅助插件可能调用同一模型地址，所以拦截器还支持 attribution gate，将不属于接管范围的请求放行。[原生拦截](https://github.com/ranxianglei/billion-context/blob/b2f28c6a4a854d88382509eb4f5531465c989793/src/agent/native-intercept.ts)

本项目已经掌握自己的请求装配与 provider client，通常没有必要再从全局 fetch 层接管。学习其归属问题，比移植这一兼容性很重的代理方案更直接。上游的代理重启、有限等待后直连及部分重试策略，也与我们固定的模型 / 故障处理规则不同。

### 3.3 压缩、原文与回读是不同操作

模型提供要压缩的范围及摘要，内核负责结构化状态；代理保存压缩块原文。`BlockContent` 包含 full 和 one 两种视图：前者保留完整原消息，后者保留一层内容及嵌套摘要；二者字节相同时 one 为 null，避免存两份。会话同时保存 token 来源是模型 usage 还是本地 estimate，防止一个估算值无声变成实际用量证据。[会话状态](https://github.com/ranxianglei/billion-context/blob/b2f28c6a4a854d88382509eb4f5531465c989793/src/session.ts)

`decompress` 在已检查实现中是无状态取回，不会把压缩块重新展开进未来全部请求。它先找压缩时保存的原文，再按参数选择 full / one；无法使用缓存时尝试未折叠历史，仍不可得时可能仅返回摘要。宿主原生压缩前的已归档块则明确拒绝称作可恢复原文。大内容写入临时文件供文件工具读取，避免一次返回再次撑大上下文。[回读实现](https://github.com/ranxianglei/billion-context/blob/b2f28c6a4a854d88382509eb4f5531465c989793/src/decompress-shared.ts)

所以“可逆压缩”应谨慎解释：有原文存档时能按需回读，不表示模型摘要无损，也不表示任何模式切换之后所有原文都永远可得。安装 / launcher 还会关闭 DSH 原生自动压缩，以免两套系统交叠；手动 compact 的边界由后续 ingest 差异识别，这也是额外兼容成本。

### 3.4 作者规模数字与结论边界

README 宣称数月、多个宿主、大量调用的长期运行，同时当前仓库其他段落保留早期 / mock 验证表述，材料口径需要进一步对齐。主仓库有论文与测试材料，但本轮没有独立复核原始纵向轨迹，也没有重跑。不能把标题中的 token 节省和长会话规模写成已确认的企业采用或本项目收益。[作者材料入口](https://github.com/ranxianglei/billion-context)

对我们更可靠的参考是摘要与原文分开、回读不自动永久扩张请求、压缩状态与真实 usage 关联，以及避免两套压缩同时拥有同一份上下文。自有系统已有其中一部分，后续只补真实缺口。

## 4. dsh-mcp-manager：连接、工具可见性与加载模式不是同一个开关

### 4.1 独立模块与当前版本

`zhang-guo-wen/dsh-mcp-manager` 的固定提交为 `7f5675fda2fac4fc2dabc1554b85a1e71a54f703`，package `0.1.0`，Apache-2.0，当日有重命名提交。没有取得统一时点的精确 Star，不填零。它从兼容相关能力拆出 MCP 管理，说明规模不大的插件也会因生命周期职责不同而拆包。

入口管理加载模式、已装配服务和实时设置；`lazy-mcp.ts` 管按需工具与 agent 对应的连接；配置 / spec / gate 模块分别负责协议数据与装配许可。不是读取一个 MCP JSON 然后把全部工具一次塞进系统提示。[入口](https://github.com/zhang-guo-wen/dsh-mcp-manager/blob/7f5675fda2fac4fc2dabc1554b85a1e71a54f703/src/index.ts)

### 4.2 请求怎样取得工具

首先由 composition 决定哪些服务允许使用，再由 loading mode 决定是否预加载。eager 直接通过原生 MCP client 发布工具；dynamic 可以在模型请求后挂载原生工具；lazy 或有工具过滤的服务使用 SDK 连接，并经通用 `mcp_call` 转发。

为什么过滤会改变连接方式？原生 carrier 自己掌握工具注册，插件不能假设能在旁边悄悄隐藏一部分；代理 carrier 则保存筛选后的工具列表，并在真正调用时再次确认目标位于该会话可调用集合。eager 下配置过滤没有效果，源码明确给警告，而非显示一个已经生效的开关。[按需加载与调用](https://github.com/zhang-guo-wen/dsh-mcp-manager/blob/7f5675fda2fac4fc2dabc1554b85a1e71a54f703/src/lazy-mcp.ts)

### 4.3 设置变更与清理

已加载服务按 agent ID、serverName 两层登记。原生连接挂在 agent context，SDK 代理连接由插件主动关闭；会话结束与插件卸载都需要释放自己启动的资源。过滤规则更新作用于下一次加载，已加载连接保留接纳时工具集。这是一种明确的版本 / 生命周期策略，不能解释为“修改配置后全体正在运行会话立刻更新”。

本项目的 MCP 服务、项目启用、按需 schema 和会话选择已实现。可参考的是界面区分配置保存、连接建立、schema 激活和下一请求生效，明确设置变更对在途工作的影响。是否采用通用 mcp_call 还要权衡：schema 更少，但具体参数约束和工具可辨认性会转移到另一层，不能只看 token 数。

## 5. dsh-claude-compat：兼容的重点是规则语义和材料来源

固定提交 `0f9253a5fbb80c97660eee95e0ce56facdc6a886`，package `0.2.0`，Apache-2.0。该插件分别处理 Skill provider、CLAUDE 指令与 rules，当前 MCP 管理已拆到上一节的独立包。Skill 格式能读取，不等于已复刻另一个 Agent 的所有生命周期与优先级。

规则层在会话首次需要时加载，并按会话对象保存 activated / injected 状态。无路径限制的规则与按路径匹配的规则分开；成功读取文件后才激活匹配规则，下一次 pre-step 加入请求。恢复会话时检查已有来源消息，避免把常驻规则重复注入；指令层仅处理自己负责的 CLAUDE 段落，不能任意删除项目其他指令。[规则实现](https://github.com/zhang-guo-wen/dsh-claude-compat/blob/0f9253a5fbb80c97660eee95e0ce56facdc6a886/src/rules.ts)、[指令处理](https://github.com/zhang-guo-wen/dsh-claude-compat/blob/0f9253a5fbb80c97660eee95e0ce56facdc6a886/src/instructions.ts)

这种设计节省初始上下文，但依赖对读取工具名称和路径参数的识别；换了工具别名、由 shell 读取或仓库结构发生变化时，不应默认仍有完全等价的激活语义。WeakMap 会话缓存也不意味着外部规则文件每次更改都被立即发现。

我们已能载入根 AGENTS 与分层指令，参考价值是把“发现”“被路径激活”“已进入本次请求”作为可解释的不同事实。是否兼容更多文件名应由实际项目需要决定，不凭生态兼容口号增加一套可能相互覆盖的规则。

## 6. dsh-market：把安装、配置恢复和宿主恢复分开

### 6.1 发现与安装的事实来源

固定提交 `90a31aed5a65d5f5ddaa6cb99432b047c4923581`，package `1.58.0`，MIT，本轮 4,412 Star / 223 Fork。仓库把 registry、profile 文件读取、安装编排、patch、snapshot、restart 和 recovery 分为独立模块。市场目录说明有哪些候选，profile manifest / lockfile / 已安装包说明当前有什么，两者不是一份事实。

`profile.ts` 还区分用户选择的插件与插件引入的依赖，避免 pnpm 自动安装的 peer 被错误显示为用户主动安装的另一插件。恢复时必须保存原始依赖集合，不能拿隐藏了宿主基础包的 UI 列表去覆盖 manifest。[Profile 读取](https://github.com/dsh-market/dsh-market/blob/90a31aed5a65d5f5ddaa6cb99432b047c4923581/src/profile.ts)

安装编排处理集合仓库定位、包管理器兼容、构建和安装后状态检查。它存在对明确失败类型的自动修复 / 重试，并非单次调用外部命令。我们不能直接搬入这些策略；当安装确实失败时，具体失败阶段和受影响文件比一次笼统重试更重要。[安装编排](https://github.com/dsh-market/dsh-market/blob/90a31aed5a65d5f5ddaa6cb99432b047c4923581/src/install.ts)

### 6.2 更新前的快照能恢复什么

snapshot 保存 `package.json`、用户 patch 和市场 state，显式记录可选文件原本不存在的情况。恢复前读取各目标当前状态，依序写入或删除；后续动作失败时逆序补偿已完成部分，并保留补偿错误。单个写入可以采用临时文件 / rename，多文件之间仍可能发生部分失败。[快照与恢复](https://github.com/dsh-market/dsh-market/blob/90a31aed5a65d5f5ddaa6cb99432b047c4923581/src/snapshot.ts)

这不是 node_modules、锁文件、原生模块以及全部外部副作用的完整事务。恢复配置并不自动意味着运行依赖已回到完全相同状态，界面应告诉用户到底恢复了什么。

### 6.3 宿主起不来时，恢复入口不能依赖宿主成功加载

`recovery.ts` 是由独立重启 helper 启动的恢复服务。新宿主在限定时间内没有绑定端口，它才接管原页面正在等待的本机地址，允许用户修改被限定的插件启用项，再让出端口。它不靠坏掉的 DSH 插件树才能工作，也不承担完整包重装。[独立恢复](https://github.com/dsh-market/dsh-market/blob/90a31aed5a65d5f5ddaa6cb99432b047c4923581/src/recovery.ts)

限制也很明确：端口绑定只是某个启动阶段的证据，不能保证所有插件、模型和工具都健康。我们已有 Python 后端生命周期管理，将来若引入能影响启动的扩展，也应让禁用 / 恢复入口位于更外层；目前不能为了一个 Skill 文本导入，就先建设整套宿主救援系统。

### 6.4 用户报告怎样反向检验当前代码

#639 报告旧版市场在官方桌面宿主中错误操作 web profile：该启动方式没有 CLI `--profile`，也没有第三方桌面特有服务，回退默认值便指向别处。本次固定代码已读取官方 `profileContext`，并把宿主报告的名称与真实目录一起传递。因此它是已反映到当前实现的演化案例，不能继续当作新版尚未处理的同一问题。[旧版使用报告](https://github.com/dsh-market/dsh-market/issues/639)、[当前身份解析](https://github.com/dsh-market/dsh-market/blob/90a31aed5a65d5f5ddaa6cb99432b047c4923581/src/index.ts)

这对本项目非常直接：项目、数据根、Skill 资源库和运行环境应继续由明确所有者传入。不能因为没有找到参数，就悄悄推导一个看似合理的目录并执行写操作。

## 7. 可迁移的演化规律

这些项目的当前源码共同呈现出三种变化。第一，从一份全局状态走向会话 / 请求 / 资源分别有身份；第二，从启动时一次性装配走向按请求或按需加载，但必须说明何时生效；第三，从界面显示成功走向保存、执行、结果确认和恢复分别有证据。

对本项目的建议不是同时安装五个插件。优先补足已有链路中的来源与生效状态，按实际规模考虑投影和检索，只有明确的宿主故障场景才建设扩展救援。低 Star 不妨碍某个机制值得学习，高 Star 也不免除版本、兼容和失败处理的核查；没有生产部署证据的部分仍属于设计参考。
