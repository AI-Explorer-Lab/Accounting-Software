# 同一任务的第 {{turn_number}} 次处理
任务编号：{{task_id}}
原始需求：{{requirement}}

# 上一轮验证失败
{{redacted_failure_summary}}

# 当前变更
变更文件：{{changed_files}}
当前 diff SHA-256：{{diff_sha256}}

# 修复要求
- 只处理上述失败及其直接原因，不扩大需求范围。
- 保留已经正确的实现，不删除或弱化测试来制造通过结果。
- 继续遵守独立 worktree、无网络、无生产访问、无权限提升的边界。
- 完成后说明修复内容和建议重新运行的验证；具体验证命令仍由 orchestrator 决定。
