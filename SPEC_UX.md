# Spec：本地交互界面与权限模式

## Objective

把已经完成的命令行 Harness 升级为普通用户可以直接使用的本地应用。用户不需要编写长命令，也不需要在提示词中声明“不要写文件”。程序必须在权限层区分两种模式：

- **只读提问**：模型可以回答并读取项目，但程序绝不允许写文件或运行命令。
- **开发任务**：模型可以读写和运行命令；每次 `write_file` 或 `run_command` 在网页中展示参数并等待用户允许，除非用户显式开启本次会话的自动批准。

浏览器界面支持同一工作目录中的连续追问，清晰显示聊天内容、执行步骤、审批请求、错误和最终状态。现有 CLI 与测试入口继续可用。

## Tech Stack

- Python 3.13
- 现有 `httpx`、`pytest`
- Python 标准库 `http.server`、`threading`、`webbrowser`：本地 HTTP 服务，不新增 Web 框架
- 原生 HTML、CSS、JavaScript：不使用前端构建工具

## Commands

```powershell
# 安装与离线测试
python -m pip install -e ".[dev]"
python -m pytest

# 启动本地网页（自动打开浏览器）
coding-agent-ui

# 不自动打开浏览器，用于测试或远程终端
coding-agent-ui --no-browser --port 8765

# 旧 CLI 保留
coding-agent --workspace D:\project "修复测试失败"
```

## Project Structure

```text
src/coding_agent/policy.py       权限过滤和审批包装
src/coding_agent/conversation.py 连续历史与会话状态
src/coding_agent/web.py          仅监听本机的 JSON API 与静态资源服务
src/coding_agent/static/         HTML、CSS、JavaScript
tests/test_policy.py             权限不可绕过的单元测试
tests/test_conversation.py       多轮历史与审批状态测试
tests/test_web.py                本地 HTTP API 测试
```

## Code Style

边界使用显式数据结构，不把权限写在提示词里：

```python
policy = PolicyTools(
    workspace_tools,
    mode="ask",
    approve=None,
)
assert {item["function"]["name"] for item in policy.schemas()} == {
    "list_files",
    "read_file",
}
```

## Testing Strategy

1. 权限测试使用假审批器，证明只读模式无法调用写入和命令，即使模型伪造调用也会失败。
2. 连续会话使用脚本化假模型，证明第二条用户消息收到第一轮完整历史。
3. Web API 在随机本地端口启动，验证创建会话、发送消息、轮询状态、批准/拒绝和静态页面。
4. 浏览器手工验证布局、控制台错误、审批流程和窄屏显示。
5. 现有离线和真实 API 测试不得回归。

## Boundaries

- Always：仅监听 `127.0.0.1`；校验 workspace；只读权限由代码强制；审批参数完整可见；API Key 永不发送给浏览器。
- Ask first：写文件、运行命令；选择自动批准后仅对当前开发会话放行。
- Never：网页直接接收或返回 API Key；只读模式执行副作用工具；从网页提供任意服务监听地址；删除用户文件作为“回滚”。

## Success Criteria

- 运行 `coding-agent-ui` 后自动打开清晰的中文本地页面。
- 页面可选择现有目录、只读提问或开发任务，并进行连续两轮对话。
- 只读会话中，前端和后端均不提供写入/命令能力；伪造 API/模型调用也无法绕过。
- 开发会话的写入和命令默认暂停，页面批准后才执行；拒绝结果反馈给模型。
- 默认轨迹只显示工具名、关键参数和结果摘要；可展开查看完整输出。
- 页面刷新后当前进程内的会话仍可读取；重启后不做持久化。
- CLI 旧用法继续通过测试。
- 完整离线测试、真实 API 冒烟测试、凭据扫描和浏览器检查通过。

## Open Questions / Adopted Assumptions

- 第一版只支持单机单用户，不做登录和远程访问。
- 会话只保存在内存；关闭程序即清除，这是为了避免无意保存源码和对话。
- 网页界面不直接编辑文件；所有副作用仍经过 Harness 工具层。
- 不在本次升级中加入多 Agent、联网搜索或数据库。
