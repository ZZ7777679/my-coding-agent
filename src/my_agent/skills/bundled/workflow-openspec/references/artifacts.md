# 变更产物示例 / Change artifact examples

这些是本应用编写的简短示例，按任务实际规模使用；不是需要逐项填写的表单。

`proposal.md` 记录：为什么改变、这次改变什么、范围外事项、受影响位置。

`specs/counter/spec.md` 可表达：

```markdown
## ADDED Requirements
### Requirement: Increase the counter
Clicking Increase adds one to the visible count.
#### Scenario: Increase from zero
- WHEN the user clicks Increase with a count of 0
- THEN the displayed count is 1
```

修改既有需求时使用 MODIFIED，并给出修改后的完整行为和仍适用的场景。删除时说明删掉什么行为和原因；不要因一个场景更新而覆盖整个规范文件。

`design.md` 仅在需要解释实现取舍时记录方案、复用入口、影响与已知边界。

`tasks.md` 以可交付结果组织，例如：

```markdown
- [ ] 1. Add the counter action and visible result in index.html.
- [ ] 2. Check that two clicks produce 2; record the actual result.
```

接续时引用本次变更目录、已完成条目、已确认决定与下一步；不要复制整份历史对话。
