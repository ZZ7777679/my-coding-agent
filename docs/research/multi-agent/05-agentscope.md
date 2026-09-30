# AgentScope 2.0：团队身份、成员会话与服务端消息运行时

> 2026-09-22 固定源码 `226daf0193a9e5b336289051adb4bd01531303eb`，包内版本 `2.0.8`，Apache-2.0。分析对象为该主线快照，不声称它与 PyPI 发布包逐文件一致。静态核查了团队工具、成员 middleware、消息总线和会话服务，未部署集群。

## 1. 先认识当前版本，而不是停留在 MsgHub 教程

AgentScope 早期以多 Agent 消息交换、角色和 pipeline 著称。2025 年的 1.0 论文进一步强调工具与环境交互；本次核查的 2.0 已把完整 Agent 循环、上下文、工具 / MCP / Skill、workspace 和应用服务组织在一起。当前 README 的 8–9 月更新还包括 Pipeline、渠道接入、A2A 等。旧版 `MsgHub` 示例可以解释历史思路，却不能代表这份 2.0 主线的团队服务实现。[当前概览][readme] [1.0 论文][paper]

它值得重点研究，因为它同时提供两种组合层：SDK 层可把多个 Agent 串成统一事件流；应用服务层则真正管理团队、独立成员会话、成员消息、唤醒与存储。后者比“调用几个异步函数”更接近可持续协作的产品。

旧 AgentScope Runtime 官网已发布迁移说明：其 sandbox、Agent-as-a-Service 与观测能力纳入 2.0，旧仓库保留参考并计划归档。因此，早期 Runtime 1.0 部署教程属于历史路线，不能与当前 2.0 代码拼成一套未经验证的安装方案。[Runtime 迁移说明](https://runtime.agentscope.io/)

## 2. 仓库组织揭示了两套不同职责

| 模块 | 负责什么 | 为什么这样拆分 |
| --- | --- | --- |
| `agent/_agent.py` | 单个 Agent 的 reply、模型 / 工具循环、上下文与中断 | 团队成员仍复用同一种执行核心 |
| `tool/`、`permission/`、`workspace/` 等 | 能力、权限、实际执行环境 | 团队角色名称不能替代工具与环境约束 |
| `pipeline/` | 将执行者 / 验证者等按流程组合成统一 `reply_stream` | 调用方可像调用一个 Agent 那样调用流程 |
| `app/_tool/` | TeamCreate、AgentCreate、TeamSay 等业务操作 | 工具是模型入口，状态仍由服务与存储持有 |
| `app/storage/` | Agent、Session、Team 等可保存记录 | 角色定义、一次对话和团队关系独立演化 |
| `app/message_bus/` | 队列、事件回放、广播、锁 / 注册表 | 可切换内存或 Redis，不让传输层理解团队业务 |
| `app/_bus_ops.py` | 将总线原语组合成业务投递 / 唤醒 | 避免工具、调度器各自拼接消息键和事件顺序 |
| `app/_service/`、`app/middleware/` | 会话状态、执行触发、团队成员行为 | 前端读取真实服务状态，成员行为进入共同循环 |

它没有把团队逻辑硬塞进 `Agent.reply()`，但 `_agent.py` 仍是很大的执行核心，工具和服务也有耦合。不能因为目录分层就推断实现已高度解耦。做二次开发时，新增团队生命周期应沿 `app` 修改；调整所有 Agent 的上下文压缩则应进入 SDK 层。[单 Agent][agent] [业务总线操作][busops]

## 3. 从一个用户请求建立团队

模型调用 `TeamCreate(name, description)` 时，工具读取当前 session，确认它当前没有所属团队，再创建 `TeamRecord`，把 leader 的 session 与 team 关联。团队描述被用作共同任务背景，而不是将 leader 的全部对话拷贝给所有成员。

这一步的结果是团队实体，不是若干模型进程。接着 `AgentCreate` 才选择 `SubAgentTemplate`，创建成员的 AgentRecord 和独立 session，登记成员关系，并把初始任务投递到成员 inbox，同时发出唤醒。

代码顺序有实际意义：创建工具已经发送第一条工作指令，调用方再立即补发相同的 TeamSay 会造成重复要求，所以工具描述明确提示不要重复发送。它说明 API 设计必须交代“创建时是否自动执行”，否则主模型很容易把初始化和派工做两遍。[建立团队][create-team] [创建成员][create-agent]

## 4. 为什么 Agent、Session、TeamMember 要分开

当前 `TeamMember` 保存 `owner_id / agent_id / session_id / role`。`role` 区分 `created` 与 `invited`：前者由团队创建，解散时连同成员定义清理；后者借用已有用户 Agent，为这次团队建立单独的借用会话，团队解散后原 Agent 定义继续存在。

这里解决了两个真实问题。第一，同一专家定义可以服务多个独立任务，但各任务不能串用一份可变历史。第二，团队拥有一次协作会话，不应因解散团队而删除用户长期维护的专家。旧版只有 `member_ids` 的记录不能表达这些关系，因此当前代码保留迁移入口。

对本项目的启发是：用户创建的长期会话、内部 worker 和可复用角色模板可以共享底层执行能力，却必须拥有不同的创建、展示和删除语义。仅用一个 `is_subagent` 布尔值很快会不够用；但没有“借用专家”需求时，也无需提前照搬跨 owner 模型。[团队存储模型][team-model]

## 5. 能力与上下文怎样进入成员

成员模板提供 system prompt、context 配置、ReAct 配置和权限等信息。AgentCreate 用团队目标、成员职责与 leader 身份填充提示词，并从 leader session 等记录解析必要设置。成员有自己的 `AgentState`，不能把模板对象的可变状态在多个执行间直接复用。

工具、MCP、Skill 和 workspace 是组装成员时的能力材料。README 列出本机与多种 sandbox 后端，但“支持这些后端”不等于团队默认拥有彼此隔离的文件系统；需要看部署选择及 workspace 映射。上下文隔离也不会自动解决成员修改同一源文件的问题。

团队共同背景适合放目标、职责和稳定约定，成员私有上下文适合放工具过程与局部推理。共享知识应有明确来源和作用域，而不是把所有成员整段 transcript 广播给所有人。后者既增加开销，也让一个局部误判污染整个团队。[成员创建][create-agent] [SDK 能力概览][readme]

## 6. 通信不是一个 send 函数：队列、回放和唤醒分工

`TeamSay` 在调用时重新读取成员目录，以适应刚加入的成员；地址最终对应具体 agent / session。定向消息只送给一个成员，未指定接收者则广播给其他成员。借入成员的展示名称加入短身份后缀，解决不同用户 Agent 同名的问题。消息以带来源的 HintBlock 等形式进入接收路径。[通信工具][say]

`_bus_ops.py` 把底层操作组合为业务行为：保存 session event 到 replay log，再发布即时通知；投递 inbox 后触发 wakeup；真正用户输入、HITL 接续与普通 wake 使用不同的触发类型。这避免了所有“来了一条东西”都被解释为同一种新用户请求。[业务投递][busops]

Redis 后端进一步区分三类语义：

| 通道 | 当前实现 | 可以保证什么 | 不能据此保证什么 |
| --- | --- | --- | --- |
| 待消费队列 | Redis Stream；Lua 内执行 XRANGE + XDEL | 同一条在一次 drain 中交给一个消费者 | 消费者取出后崩溃，业务仍必然完成 |
| 回放日志 | Stream，读取不删除；支持游标与裁剪 | 客户端可按保留范围续读事件 | 无限保留或完整业务状态恢复 |
| 即时广播 | Redis Pub/Sub | 在线订阅方及时得到唤醒 | 离线订阅方补收历史消息 |

因此，源码注释中的“一个消费者取走”不能扩写成端到端 exactly-once。队列删除后到业务保存之间仍有失败边界；广播也明确是 best-effort。可靠性分析必须追踪业务记录、队列和执行结果之间的关系，而不是看见 Redis 就认定可靠。[Redis 实现][redis]

## 7. 调度与状态：活跃租约优先于旧快照

服务层 `SessionStatus` 区分 running、idle、等待用户确认、等待外部执行结果。状态判定先查询分布式 session-run 锁，发现某个 worker 正在持有租约，就显示 running；只有没有执行者持有租约时，才根据已保存上下文末尾推断等待或空闲状态。

这样做是因为在途内存状态比上次保存的快照新。若 UI 只根据数据库里旧的“等待确认”字段渲染，用户刚恢复运行时仍可能看到已经过时的状态。租约到期可以让崩溃 worker 的会话脱离 running，但它不能判断该 worker 最后一次外部动作是否成功。状态恢复和副作用核对仍是不同问题。[会话服务][session]

这个集群设计对本项目的直接价值是状态优先级和单一事实来源。我们是单写者桌面应用，可以用现有 ActiveRun 与持久日志表达相同原则，现阶段并不需要 Redis 或分布式租约。

## 8. 结果汇报与 GoalPipeline：能力与代价一起看

团队成员有 `TeamMemberLoopMiddleware`：它检查本轮最后一个工具动作是否成功向 leader 或团队汇报。若成员直接输出正文而没有成功 TeamSay，middleware 会提示其继续汇报；次数受 `max_nudges` 限制，超过后结束为异常结果。它还区分本轮 reply 身份，避免拿以前一次汇报充当当前完成。[成员汇报约束][member]

这比单纯写一句“完成后记得汇报”更强，能够降低 leader 永远等不到消息的概率。但它也把汇报动作变成结束条件，会增加模型调用，并可能把已经完成的业务工作标成失败。本项目已明确完整回合无需强制报告即可继续，因此应借鉴“结果有宿主身份与来源”，而不照搬这条强制补报循环。

SDK 中 `GoalPipeline` 则把 executor 和 verifier 连接起来：执行者输出工作报告，验证者输出 pass / fail / impossible，循环直到完成或达到限制。HITL 接续不重置实例上的迭代计数。它适合有明确验证目标的局部流程，但验证者仍是模型，其结论不自动等于工具事实；当前实例计数也不能在没有持久化适配的情况下解释为跨进程预算保证。[GoalPipeline][goal]

## 9. 落地价值、演化方向与本项目取舍

AgentScope 的演化体现出从研究中的消息协作，走向应用服务中的身份、会话、存储、渠道和运行生命周期。最有价值的不是角色名称，而是把团队真正变成可观察、可停止、有归属的业务对象。

对我们优先有用的是成员定义与执行实例分开、消息与唤醒分开、活跃状态与持久状态分开，以及临时 worker 不挤进用户长期会话列表。对于团队 charter、成员来源、结果来源，可以在现有任务与协作记录上表达。跨 owner 邀请、分布式 Redis 总线、多种 sandbox 编排属于规模和部署需求出现后再考虑的能力。

这份源码本身没有证明“加上 Teams 就提高编码正确率”。真正需要评估的是分解是否减少重复阅读、成员能否独立产出可整合结果、错误消息是否会导致重复执行、以及团队最终完成时间和总成本是否改善。部署可用与任务效果应分别衡量。

[readme]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/README.md
[paper]: https://arxiv.org/abs/2508.16279
[agent]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/agent/_agent.py
[create-team]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/_tool/_team_create.py
[create-agent]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/_tool/_agent_create.py
[team-model]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/storage/_model/_team.py
[say]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/_tool/_team_say.py
[busops]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/_bus_ops.py
[redis]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/message_bus/_redis_message_bus.py
[session]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/_service/_session.py
[member]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/app/middleware/_team_member_middleware.py
[goal]: https://github.com/agentscope-ai/agentscope/blob/226daf0193a9e5b336289051adb4bd01531303eb/src/agentscope/pipeline/_goal_pipeline.py
