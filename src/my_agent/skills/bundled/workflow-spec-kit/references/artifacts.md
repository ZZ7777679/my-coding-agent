# 功能产物示例 / Feature artifact examples

根据项目已有约定选定一次功能的目录，后续阶段复用该路径。示例可缩短，不强制为了模板完整性新建全部文件。

`spec.md`：

```markdown
# Counter increment
## User scenario
As a visitor, I can increase the visible count without reloading.
## Behavior
REQ-1: One click adds one; the initial value is zero.
## Acceptance examples
From 0, two clicks display 2.
## Out of scope
Persistence between browser visits.
```

`plan.md` 记录对应模块、状态处理、真实运行环境和验证方式。例如复用现有单页和按钮事件，无需新增服务或依赖。

`tasks.md`：

```markdown
- [ ] T1 [REQ-1] Add state and increment action in the existing page.
- [ ] T2 [REQ-1] Run the page and check two clicks display 2.
```

收敛时记录每个有关场景的实际结果、未验证项和剩余差距。没有行为变化的小任务可以直接引用现有规范，避免重新写一套功能定义。编号只是帮助引用，不成为固定语法或执行门槛。
