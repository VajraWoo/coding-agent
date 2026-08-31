# Capability Map：可用性与权限升级

| Module id | Responsibility | Depends on |
|---|---|---|
| `permission-policy` | 区分只读提问与开发执行；写入和命令需要程序级审批 | `local-tools` |
| `conversation-runtime` | 在多次提问间保存历史；继续使用现有 Agent 循环与终止规则 | `permission-policy`、`agent-runtime` |
| `web-ui` | 本地浏览器界面；选择目录和模式；显示轨迹并处理审批 | `conversation-runtime` |

构建顺序：`permission-policy` → `conversation-runtime` → `web-ui`。

三者可独立验收：权限策略可以脱离界面测试；连续历史可以用假模型测试；网页界面可以使用假后端和本地浏览器验证。
