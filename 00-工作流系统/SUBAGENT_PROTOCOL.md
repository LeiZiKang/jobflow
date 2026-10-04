# Subagent 执行协议

subagent 是可替换执行器，不是第二个 Decider。

## 必须收到的任务信封

```json
{
  "task_id": "稳定唯一 ID",
  "role": "collector | researcher | operator | auditor | builder",
  "objective": "单一、可验证的目标",
  "inputs": ["允许读取的路径或 URL"],
  "allowed_actions": ["read", "browse_read_only"],
  "forbidden_actions": ["send_message", "submit", "login"],
  "output_path": "唯一输出路径",
  "stop_conditions": ["credential", "captcha", "ownership_lost"],
  "acceptance": ["完成所需证据"]
}
```

## 执行规则

- 只做任务信封里的目标，不擅自追加公司、岗位、文字或外部动作。
- 不读取整个仓库，只读取 `inputs` 和完成任务所必需的文件。
- 不使用 `SendMessage` 或代理名字联系其他会话；结果只通过最终返回或指定文件交付。
- 浏览器遇到凭据、验证码、账号注册、控制权丢失时立即停止并报告。
- 查不到就写查不到；推测必须标记，不能为了完整度补事实。
- 不提交 Git，除非任务信封明确授权；默认由 Decider 统一合并和提交。

## 最终返回格式

```text
task_id:
status: completed | partial | blocked | failed
completed:
evidence:
files_changed:
not_done:
blockers:
recommended_next_step:
```
