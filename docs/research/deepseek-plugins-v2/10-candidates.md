# 候选筛选记录：话题 Star 前 100 与近期机制补充

> API 快照：2026-09-23 06:19:44 UTC（北京时间 14:19:44）。本表逐项说明处置，**不是 100 个项目的源码审计报告**。筛选方法见 [01-selection.md](01-selection.md)。

## 1. 怎样读这张表

- **主线**：正文有固定源码的路径与机制分析，编号对应本目录文档。
- **比较**：用于同类取舍或局部机制对照，阅读范围小于完整主线。
- **候选**：有潜在价值，但本轮未充分精读 / 验证；暂缓不表示质量较差。
- **发现入口 / 范围外 / 官方边界**：分别是目录资料、与当前目标距离较大的产品、官方参考。

Star / Fork 属于整个仓库，不是 DSH 适配的用户数。最后 push 采用 API 的 `pushed_at`，以 UTC 日期显示，可能来自非发布改动；它不能证明 DSH 子目录当天更新、发布稳定或生产采用。没有对增长率、安装量、活跃用户和 Star 真实性作统计推断。搜索结果总量 15,879 不是经过验证的插件数量。

## 2. 逐项处置

| 排名 | 仓库 | Star / Fork | 最后 push（UTC） | 处置 | 理由 / 边界 |
| --- | --- | --- | --- | --- | --- |
| 1 | [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | 233,745 / 28,090 | 2026-09-22 | 官方边界 | 原生 Harness，只核对扩展契约；不计入非官方推荐。 |
| 2 | [nexu-io/open-design](https://github.com/nexu-io/open-design) | 97,699 / 11,336 | 2026-09-23 | 主线·02 | 成果驱动工作台；分析 daemon、CLI 桥、会话和文件交付。 |
| 3 | [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | 73,096 / 8,676 | 2026-09-22 | 候选 | 关注度极高，但已读入口属于其他生态；未验证完整 DSH 集成，不把 swarm 宣称直接归给插件。 |
| 4 | [tt-a1i/archify](https://github.com/tt-a1i/archify) | 70,122 / 4,713 | 2026-09-23 | 主线·05 | 明确图示成果与确定性工具链，能比较 Skill 从说明到交付的完整路径。 |
| 5 | [reactive-resume/reactive-resume](https://github.com/reactive-resume/reactive-resume) | 43,348 / 4,786 | 2026-09-22 | 范围外 | 通用简历产品；本轮不因话题标签就把整个产品认定为 DSH 插件。 |
| 6 | [volcengine/OpenViking](https://github.com/volcengine/OpenViking) | 38,498 / 2,998 | 2026-09-23 | 主线·04 | 高关注上下文服务；重点检查 DSH 适配的 recall、capture 与 pending 写入。 |
| 7 | [esengine/DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) | 35,688 / 2,417 | 2026-09-23 | 候选 | 独立 coding agent，更适合 Agent 核心对比；本轮未做完整运行时审计。 |
| 8 | [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) | 33,319 / 3,208 | 2026-09-11 | 候选 | 图像提示与模板库；成果内容可参考，宿主架构相关性低于本轮主线。 |
| 9 | [Tencent/WeKnora](https://github.com/Tencent/WeKnora) | 29,092 / 3,921 | 2026-09-23 | 主线·04 | 组织知识平台的实际 DSH 工具入口；区分检索证据与生成答案。 |
| 10 | [anywhere-labs/dsh-desktop](https://github.com/anywhere-labs/dsh-desktop) | 28,591 / 1,358 | 2026-09-23 | 主线·02 | 原生桌面产品；Windows 启动、profile、Host 和恢复与本项目高度相关。 |
| 11 | [Molunerfinn/PicGo](https://github.com/Molunerfinn/PicGo) | 27,235 / 2,327 | 2026-09-01 | 范围外 | 通用图片上传器；不能把全仓用户规模当 DSH 接入的使用规模。 |
| 12 | [titanwings/distilly](https://github.com/titanwings/distilly) | 24,978 / 2,171 | 2026-09-22 | 主线·05 | 人物材料到工作方法 / persona 的资料生命周期，有版本与纠错实现。 |
| 13 | [nocobase/nocobase](https://github.com/nocobase/nocobase) | 24,325 / 2,889 | 2026-09-23 | 候选 | 通用业务系统平台；如研究企业应用编排再深入，本轮不展开全后端。 |
| 14 | [Nagi-ovo/voyager](https://github.com/Nagi-ovo/voyager) | 20,148 / 668 | 2026-09-21 | 候选 | 多网站增强和提示管理；与本项目独立执行核心的距离较大。 |
| 15 | [awesome-dsh-plugin/awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) | 16,654 / 3,217 | 2026-09-23 | 发现入口 | 用于发现，不作为可安装插件或效果证据。 |
| 16 | [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) | 15,765 / 1,591 | 2026-08-26 | 发现入口 | Harness 教程；用作学习线索，不按插件落地统计。 |
| 17 | [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) | 13,149 / 921 | 2026-09-22 | 主线·04 | Markdown 事实层、索引协调和独立适配仓库，覆盖用户可编辑记忆路线。 |
| 18 | [MemTensor/MemOS](https://github.com/MemTensor/MemOS) | 11,542 / 1,056 | 2026-09-23 | 主线·04 | 本地 MemoryCore 与 DSH adapter；区分 Python 主产品及具体接入。 |
| 19 | [dataelement/dsh-desktop](https://github.com/dataelement/dsh-desktop) | 8,521 / 355 | 2026-09-23 | 候选 | 另一桌面组织；与 Anywhere 重叠，不再平均分配多个启动壳的篇幅。 |
| 20 | [YaoApp/yao](https://github.com/YaoApp/yao) | 7,994 / 716 | 2026-09-22 | 候选 | 自托管多设备工作台；产品路线值得后续比较，未深读实际 DSH 链。 |
| 21 | [zhu1090093659/dsh-web](https://github.com/zhu1090093659/dsh-web) | 7,944 / 543 | 2026-09-23 | 候选 | 原生 Web 聚合与任务面板；保留为任务 UI / Host 账本方向，未列为本轮完整主线。 |
| 22 | [plastic-labs/honcho](https://github.com/plastic-labs/honcho) | 7,306 / 902 | 2026-09-22 | 候选 | 有关注的记忆系统；本轮以三种不同记忆架构控制深读范围，不判断其质量更差。 |
| 23 | [yjh051108/dsh-routing-suite](https://github.com/yjh051108/dsh-routing-suite) | 7,206 / 177 | 2026-09-18 | 候选 | 任务推理路由；已有材料偏预设和作者测评，完整编程收益仍需同任务验证。 |
| 24 | [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) | 7,179 / 1,202 | 2026-09-22 | 范围外 | 小说创作垂直场景；方法可参考，当前主要需求不是长篇写作。 |
| 25 | [anbeime/skill](https://github.com/anbeime/skill) | 7,114 / 665 | 2026-09-22 | 候选 | Skill 商店与集合；需先核验来源和质量，避免用集合大小替代有效能力。 |
| 26 | [Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill) | 6,728 / 492 | 2026-09-23 | 主线·06 | CLI、扩展、DSH 工具和真实 Windows 报告形成可核查的完整产品链。 |
| 27 | [Devin-AXIS/iPolloWork](https://github.com/Devin-AXIS/iPolloWork) | 6,591 / 1,267 | 2026-09-22 | 主线·02 | 多引擎工作台与扩展版本投影；许可及局部源码获取范围单独标注。 |
| 28 | [Q00/ouroboros](https://github.com/Q00/ouroboros) | 6,076 / 611 | 2026-09-21 | 候选 | 进化工作流与多运行时；先区分局部反馈和强 RSI，本轮不重复上一轮主线。 |
| 29 | [ZSeven-W/openpencil](https://github.com/ZSeven-W/openpencil) | 6,009 / 522 | 2026-09-22 | 候选 | 设计画布与并发团队有吸引力；本轮成果产品先选 OpenDesign / Archify。 |
| 30 | [loopx-project/loopx](https://github.com/loopx-project/loopx) | 5,933 / 568 | 2026-09-23 | 主线·03 | 持久控制层、会话绑定、额度与恢复，区别于单次子 Agent 扇出。 |
| 31 | [dsh-market/dsh-market](https://github.com/dsh-market/dsh-market) | 4,412 / 223 | 2026-09-23 | 主线·07 | 安装、profile、快照和独立恢复；有明确用户问题与源码修订可对照。 |
| 32 | [crafter-station/petdex](https://github.com/crafter-station/petdex) | 4,144 / 206 | 2026-09-21 | 范围外 | 宠物素材图库；反映陪伴吸引力，当前核心执行 / 协作优化优先度低。 |
| 33 | [liustack/modlens](https://github.com/liustack/modlens) | 4,015 / 123 | 2026-09-22 | 候选 | 图像到结构化证据有价值；涉及额外视觉调用，本轮不扩展既定模型范围。 |
| 34 | [xiaobright/dsh-anchored-standard](https://github.com/xiaobright/dsh-anchored-standard) | 3,799 / 120 | 2026-09-10 | 候选 | 两阶段预设与作者评分；不以预设 benchmark 直接推断本项目效果。 |
| 35 | [omdsh-dev/DSH-better-sidebar](https://github.com/omdsh-dev/DSH-better-sidebar) | 3,721 / 365 | 2026-09-22 | 候选 | 侧边栏扩展底座；UI 组织有参考，但本轮先读生命周期和成果主链。 |
| 36 | [strukto-ai/mirage](https://github.com/strukto-ai/mirage) | 3,649 / 271 | 2026-09-23 | 候选 | 虚拟终端可能改善执行体验；需另核查命令语义与 Windows 兼容，未深读。 |
| 37 | [agentscope-ai/ReMe](https://github.com/agentscope-ai/ReMe) | 3,502 / 301 | 2026-09-23 | 候选 | 经验记忆与反馈方案；保留后续同任务效果比较，不重复扩展全部记忆框架。 |
| 38 | [foryourhealth111-pixel/Vibe-Skills](https://github.com/foryourhealth111-pixel/Vibe-Skills) | 3,412 / 299 | 2026-08-31 | 主线·05 | 能力路由与共享核心；同时检查作者评测的样本和最佳记录筛选规则。 |
| 39 | [whiteguo233/OpenBiliClaw](https://github.com/whiteguo233/OpenBiliClaw) | 3,344 / 178 | 2026-09-22 | 范围外 | 内容发现垂直产品；本轮主要关注编码任务和多会话执行。 |
| 40 | [edison7009/EchoBird](https://github.com/edison7009/EchoBird) | 3,266 / 374 | 2026-09-22 | 范围外 | 账号配额与多模型自动切换，不符合本项目当前固定模型 / 故障规则。 |
| 41 | [chuspeeism/dashi-taskboard](https://github.com/chuspeeism/dashi-taskboard) | 3,188 / 459 | 2026-09-21 | 候选 | 任务面板与多宿主嵌入有价值；未深读任务状态所有权，不作可靠调度结论。 |
| 42 | [ccch1mneyyy/dsh-TUI](https://github.com/ccch1mneyyy/dsh-TUI) | 3,155 / 195 | 2026-09-23 | 候选 | 终端体验插件；桌面优先下暂不作为主线，官方收录宣称未独立复核。 |
| 43 | [sopaco/deepwiki-rs](https://github.com/sopaco/deepwiki-rs) | 3,082 / 297 | 2026-09-14 | 候选 | 代码文档与上下文生成；适合作为成果 Skill 后续样本。 |
| 44 | [Tiger3807861189/J-Space-Cognition-Suite](https://github.com/Tiger3807861189/J-Space-Cognition-Suite) | 3,007 / 223 | 2026-09-14 | 候选 | 推理控制套件；研究宣称与具体宿主实现、受控效果需要分别核验。 |
| 45 | [MeteorNOX/DeepSeek-Balance-Whale-Widget](https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget) | 2,981 / 114 | 2026-09-22 | 范围外 | 余额挂件解决可见性小需求，与本轮核心架构关联有限。 |
| 46 | [zilliztech/memsearch](https://github.com/zilliztech/memsearch) | 2,641 / 257 | 2026-09-22 | 候选 | Markdown + Milvus 记忆路线；有替换后端意义，先不扩大部署组合。 |
| 47 | [dsh-tauri/deepseek-harness-desktop](https://github.com/dsh-tauri/deepseek-harness-desktop) | 2,519 / 169 | 2026-09-23 | 候选 | Tauri 桌面替代；安装体积是作者描述，本轮未验证安装体验。 |
| 48 | [superdesigndev/treg](https://github.com/superdesigndev/treg) | 2,336 / 226 | 2026-09-23 | 候选 | 工具聚合 / 路由；需要单独核查代理调用与身份模型，未据简介推荐。 |
| 49 | [GCWing/OpenBitFun](https://github.com/GCWing/OpenBitFun) | 2,314 / 241 | 2026-09-23 | 候选 | 独立 Rust Agent 桌面；更适合运行时对比专题。 |
| 50 | [Small-tailqwq/dsh-deep-whale](https://github.com/Small-tailqwq/dsh-deep-whale) | 2,183 / 65 | 2026-09-21 | 范围外 | 界面皮肤，用户吸引力存在，但当前核心协作 / 状态设计价值较少。 |
| 51 | [Alisa0808/vox-director](https://github.com/Alisa0808/vox-director) | 2,010 / 306 | 2026-08-11 | 范围外 | 视频生成 Skill 依赖专门服务与 FFmpeg，超出当前编码主线。 |
| 52 | [MemTensor/memmy-agent](https://github.com/MemTensor/memmy-agent) | 1,971 / 183 | 2026-09-23 | 候选 | 共享记忆个人 Agent；与 MemOS 同组织，不能把二者 Star 合并为一份证据。 |
| 53 | [Minglink/dsh-infinite-gen-4](https://github.com/Minglink/dsh-infinite-gen-4) | 1,940 / 159 | 2026-09-22 | 范围外 | 定位于 jailbreak / 红队提示，不服务本轮产品与协作研究目标。 |
| 54 | [YuJunZhiXue/dsh-purge](https://github.com/YuJunZhiXue/dsh-purge) | 1,914 / 203 | 2026-09-23 | 范围外 | 模型 jailbreak 提示；不作为工程落地增强方案。 |
| 55 | [Jesseovo/last30days-skill-cn](https://github.com/Jesseovo/last30days-skill-cn) | 1,807 / 194 | 2026-07-20 | 候选 | 中文近期研究工作流；需核验抓取、来源与时效后再用于研究质量比较。 |
| 56 | [NanmiCoder/dsh-agent-teams](https://github.com/NanmiCoder/dsh-agent-teams) | 1,775 / 154 | 2026-09-17 | 主线·03 | DSH 原生团队；调度、attempt、mailbox 与真实 fork 使用报告可核查。 |
| 57 | [hyhmrright/brooks-lint](https://github.com/hyhmrright/brooks-lint) | 1,489 / 68 | 2026-09-21 | 候选 | 书籍原则驱动代码评审；引用与诊断质量需要真实代码案例验证。 |
| 58 | [bowenliang123/dsh-context](https://github.com/bowenliang123/dsh-context) | 1,488 / 46 | 2026-09-23 | 主线·07 | 上下文事件投影、请求组成及冷历史回填，贴近现有 Trace / 压缩能力。 |
| 59 | [Devin-AXIS/deepseek-design](https://github.com/Devin-AXIS/deepseek-design) | 1,484 / 145 | 2026-09-04 | 候选 | 可编辑设计 / PPT；与同作者 iPolloWork 和 OpenDesign 有范围重叠。 |
| 60 | [AdamPlatin123/dsh-plugin-radar](https://github.com/AdamPlatin123/dsh-plugin-radar) | 1,465 / 152 | 2026-09-23 | 发现入口 | 生态雷达；目录与运行测试数量属于作者声明，不转写为本轮实测。 |
| 61 | [xmanrui/dsh-im](https://github.com/xmanrui/dsh-im) | 1,452 / 170 | 2026-09-23 | 候选 | 多 IM 入口；有渠道价值，但当前桌面多会话优化不以消息平台为优先。 |
| 62 | [Unclecheng-li/AI_Animation](https://github.com/Unclecheng-li/AI_Animation) | 1,357 / 107 | 2026-09-17 | 范围外 | HTML 动画提示库；本轮已有结构化成果工具链样本。 |
| 63 | [shaobeichen/dsh-pocket](https://github.com/shaobeichen/dsh-pocket) | 1,299 / 65 | 2026-09-16 | 候选 | 手机远程访问；需独立研究身份 / 网络 / 任务控制边界。 |
| 64 | [GanyuanRan/Aegis](https://github.com/GanyuanRan/Aegis) | 1,233 / 56 | 2026-09-23 | 候选 | 架构基线与漂移约束；不能未经场景判断转成本项目强制运行门槛。 |
| 65 | [OpenPetsHQ/openpets](https://github.com/OpenPetsHQ/openpets) | 1,225 / 113 | 2026-09-22 | 范围外 | 桌面陪伴与宠物平台；本轮核心协作研究暂缓。 |
| 66 | [mem9-ai/mem9](https://github.com/mem9-ai/mem9) | 1,216 / 125 | 2026-09-16 | 候选 | 独立记忆服务；与前三条记忆主线对照的后续候选。 |
| 67 | [Anionex/agent-vision-toolkit](https://github.com/Anionex/agent-vision-toolkit) | 1,208 / 47 | 2026-08-27 | 候选 | 多宿主视觉工具箱；需独立核验模型服务与工具成本。 |
| 68 | [platonai/Browser4](https://github.com/platonai/Browser4) | 1,143 / 150 | 2026-09-23 | 候选 | 浏览器引擎与规模化采集；本轮先选具备原生 DSH 和 Windows 使用证据的 BrowserSkill。 |
| 69 | [xyTom/coding-tools-mcp](https://github.com/xyTom/coding-tools-mcp) | 1,143 / 193 | 2026-09-15 | 候选 | 编码能力 MCP；需区分远端工具服务与宿主 Agent 本身，未深读。 |
| 70 | [agentrq/agentrq](https://github.com/agentrq/agentrq) | 1,127 / 80 | 2026-09-23 | 候选 | 实时任务与 HITL 控制；值得作为远程多会话管理补充，当前未审计执行协议。 |
| 71 | [TencentCloudBase/CloudBase-AI-Toolkit](https://github.com/TencentCloudBase/CloudBase-AI-Toolkit) | 1,122 / 143 | 2026-09-23 | 候选 | 云后端工具 / Skill / MCP；当前未授权引入云服务，保留业务接入参考。 |
| 72 | [ysr666/dsh-vision-router](https://github.com/ysr666/dsh-vision-router) | 1,115 / 49 | 2026-09-23 | 候选 | 视觉路由与免费链；未验证服务稳定性 / 成本来源，不把无 Key 宣称当可靠性。 |
| 73 | [paean-ai/deeptide](https://github.com/paean-ai/deeptide) | 1,102 / 139 | 2026-08-22 | 范围外 | macOS 原生 Agent；描述中的品牌措辞不证明官方维护，Windows 项目优先度低。 |
| 74 | [0xsline/awesome-deepseek-harness](https://github.com/0xsline/awesome-deepseek-harness) | 1,094 / 402 | 2026-09-21 | 发现入口 | 生态目录，用于追踪来源与遗漏，不作为独立运行时。 |
| 75 | [EthanYoQ/AI-Novel-Writer](https://github.com/EthanYoQ/AI-Novel-Writer) | 1,076 / 136 | 2026-09-22 | 范围外 | 小说桌面应用，属于垂直产品接入示例。 |
| 76 | [tong-io/tongflow](https://github.com/tong-io/tongflow) | 1,027 / 133 | 2026-09-22 | 候选 | 多模态生成平台；本轮不延展到整个生成服务栈。 |
| 77 | [Tiger3807861189/GLM-5.3-Flash-J-Space-Capability-Realization-Report](https://github.com/Tiger3807861189/GLM-5.3-Flash-J-Space-Capability-Realization-Report) | 1,020 / 64 | 2026-09-05 | 候选 | J-Space 能力报告；是评测材料候选，不是第二个独立插件采用案例。 |
| 78 | [mindscale-noah/MindMemOS](https://github.com/mindscale-noah/MindMemOS) | 989 / 98 | 2026-09-22 | 候选 | 元数据无描述，未凭仓库名推断能力；待补入口与 DSH 实现证据。 |
| 79 | [PicGo/PicGo-Core](https://github.com/PicGo/PicGo-Core) | 988 / 103 | 2026-09-22 | 范围外 | 图片上传核心，与 PicGo 主产品相关；不重复按两个 DSH 采用案例计数。 |
| 80 | [freestylefly/wesight](https://github.com/freestylefly/wesight) | 928 / 207 | 2026-09-19 | 候选 | 多 Agent 安装与桌面工作台；本轮同类主线已选三种不同运行组织。 |
| 81 | [vshulcz/deja-vu](https://github.com/vshulcz/deja-vu) | 925 / 90 | 2026-09-22 | 候选 | 从历史日志构建跨 Agent 记忆的路线有价值；无模型 / embedding 是作者描述，未深读验证。 |
| 82 | [vostride/agent-qa](https://github.com/vostride/agent-qa) | 888 / 18 | 2026-08-03 | 候选 | 带记忆的 QA harness；可用于后续网页验收专题，不推定自改进收益已证实。 |
| 83 | [Anionex/dsh-vision-toolkit](https://github.com/Anionex/dsh-vision-toolkit) | 884 / 46 | 2026-09-16 | 候选 | agent-vision-toolkit 的 DSH 原生适配；不把主库与适配热度相加。 |
| 84 | [LivXue/dsh-plugin-shop](https://github.com/LivXue/dsh-plugin-shop) | 874 / 11 | 2026-09-23 | 发现入口 | 插件商店与每日目录；逐条审核质量和数量未独立核验。 |
| 85 | [wecode-ai/Wegent](https://github.com/wecode-ai/Wegent) | 859 / 142 | 2026-09-23 | 候选 | 自托管编码协作平台；本轮优先直接 DSH 二次开发，保留更广框架对照。 |
| 86 | [toby-bridges/api-relay-audit](https://github.com/toby-bridges/api-relay-audit) | 857 / 82 | 2026-09-16 | 候选 | 模型代理审计工具；用于验证特定中继问题，非本轮主执行链。 |
| 87 | [Electricitysheep/dsh-handbook](https://github.com/Electricitysheep/dsh-handbook) | 804 / 45 | 2026-09-07 | 发现入口 | 教程与案例；其中测试结果需按各自条件使用，不视作本轮复现。 |
| 88 | [LiPu-jpg/Openwrite](https://github.com/LiPu-jpg/Openwrite) | 754 / 120 | 2026-09-16 | 范围外 | 小说创作插件；DAG 与工具组织可后续比较，业务领域当前不匹配。 |
| 89 | [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet) | 726 / 54 | 2026-09-23 | 范围外 | 宠物与素材制作，核心编码协作优先度低。 |
| 90 | [omdsh-dev/dsh-browser](https://github.com/omdsh-dev/dsh-browser) | 718 / 52 | 2026-09-22 | 比较·06 | 与 BrowserSkill 比较宿主桥接和页面续接；旧路径 Lum1104/dsh-browser 已转至此。 |
| 91 | [whitelonng/dshcode](https://github.com/whitelonng/dshcode) | 714 / 30 | 2026-09-13 | 候选 | 另一个 Electron 桌面壳；不平均重复研究多个类似 UI。 |
| 92 | [hellowind777/helloagents](https://github.com/hellowind777/helloagents) | 705 / 98 | 2026-09-06 | 候选 | 长期自主伙伴；需深入区分调度、Goal 与提示词，未据简介推荐。 |
| 93 | [ningbainb/deepseek-harness-desktop](https://github.com/ningbainb/deepseek-harness-desktop) | 686 / 21 | 2026-09-22 | 候选 | Windows 桌面集成；可后续针对零安装体验与远程连接作对照。 |
| 94 | [myYangyunfan/dsh_desktop](https://github.com/myYangyunfan/dsh_desktop) | 678 / 37 | 2026-09-21 | 候选 | Node / CLI 捆绑的 Windows 桌面；当前主线已有启动生命周期代表。 |
| 95 | [Aisland-SJL/dsh-worktable](https://github.com/Aisland-SJL/dsh-worktable) | 668 / 79 | 2026-09-06 | 候选 | 项目工作台与实时控制室；适合后续多项目可视化专项。 |
| 96 | [lencx/Minke](https://github.com/lencx/Minke) | 665 / 70 | 2026-09-16 | 候选 | 桌面封装；缺少本轮独立源码比较，不判断其产品质量。 |
| 97 | [EverMind-AI/SkillCorpus](https://github.com/EverMind-AI/SkillCorpus) | 665 / 111 | 2026-09-17 | 主线·05 | 语料治理与真正的 DSH 检索引擎，核对默认按需模式和 bundle 路径。 |
| 98 | [ccch1mneyyy/working-activity](https://github.com/ccch1mneyyy/working-activity) | 659 / 235 | 2026-08-30 | 范围外 | 终端 Working 行体验；当前桌面多会话优化关联有限。 |
| 99 | [yejiming/MuseAI](https://github.com/yejiming/MuseAI) | 658 / 59 | 2026-08-14 | 范围外 | 角色与故事交互垂直场景；不以 persona 关键词机械纳入核心架构。 |
| 100 | [fufankeji/deepseek-harness-studio](https://github.com/fufankeji/deepseek-harness-studio) | 658 / 69 | 2026-09-01 | 候选 | 安装 / 插件推荐桌面；同类候选保留，未验证宣传中的智能推荐效果。 |

## 3. 热度榜之外为什么仍补入少量样本

| 项目 | 发现依据 | 本轮处置与价值 | 热度 / 时效边界 |
| --- | --- | --- | --- |
| EverMind-AI/plugins | 从 EverOS 当前文档的适配链接进入 | [记忆正文](04-memory.md)；主库的 DSH 实现确实位于独立仓库，必须一并读 | 不把 EverOS Star 移给适配仓库 |
| wowyuarm/dsh-agent-team | 社区目录及与 Nanmi 团队的同类比较 | [协作正文](03-collaboration.md)；成员身份、会话绑定和账本先保存再应用 | 36 Star 是 9 月 22 日目录快照，非上述同时点 API 数据 |
| ranxianglei/billion-context | 近期更新页与上下文压缩问题 | [上下文正文](07-context-and-lifecycle.md)；原生 DSH 入口、请求代理和原文回读 | 当日公开页 251 / 29；不能称为大规模采用 |
| zhang-guo-wen/dsh-mcp-manager | 近期更新页 | [生命周期正文](07-context-and-lifecycle.md)；加载模式、过滤与会话连接资源 | 当日精确 Star 未取得；0.1.0 / 当日重命名不等于成熟度证明 |
| zhang-guo-wen/dsh-claude-compat | 近期更新页及 MCP 拆包关联 | [生命周期正文](07-context-and-lifecycle.md)；规则激活、去重与宿主语义兼容 | 当日精确 Star 未取得；固定 0.2.0 源码 |

近期更新页还发现 companion-memory、DSH-Patrol、ANOLISA、dsh-recall-plugin、dsh-starbridge-client、dsh-task-engine、dsh-fish-memory、dsh-plugin-doctor、dsh-exp-ops、dsh-cpa、dsh-skill-manager、dsh-token-meter-panel、agentflow 等。它们留作候选，不因刚更新就自动进入推荐。第二页限流也意味着本轮没有完整覆盖最新发布长尾。

前轮较低关注的 task-coordinator（当日 2 Star）、Odai（当日 119 Star）、memory-evolution（当日公开页 327 Star）和若干 UI / workflow 插件，不再作为本轮主要推荐；已有固定源码仅可用于机制交叉核对。若后续出现明确用户问题，例如历史 Skill 合并或持久工作流接续，可以按问题重新选择，不能因本轮暂缓就判断它们没有价值。

## 4. 本轮筛选留下的真实缺口

本轮按完整产品、协作、记忆、Skill、浏览器及扩展生命周期选出不同架构，而非穷举热门项目。Honcho / ReMe / memsearch 的同任务比较、OpenPencil 的画布并发、IM / 远程控制、Browser4 的批量浏览和虚拟终端仍未充分研究。它们是具体后续方向，不应被正文结论代表。

公开 Star 响应、固定目录候选和源码身份分别保存在忽略的研究缓存；时间与获取限制见 [证据登记](09-evidence.md)。未来重做排序应重新取快照并检查实际接入目录，不能只在本表改日期。
