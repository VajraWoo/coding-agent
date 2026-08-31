# Minimal Coding Agent

这是一个从零实现的命令行编程智能体。千问负责判断下一步，本地 Harness 保存对话历史、解析 Tool Calls、校验并执行文件/命令工具，再把结果反馈给模型，直到任务完成或达到轮数上限。

项目没有使用 LangChain、OpenAI Agents SDK 等 Agent 框架，也没有调用服务端托管的代码执行或文件工具。HTTP 请求、历史管理、工具注册与执行、错误处理和终止条件都在仓库中实现。

## 运行流程

```text
用户任务
   ↓
Agent 保存 messages ──→ 千问 Chat Completions API
   ↑                         ↓
工具结果 ← 本地校验与执行 ← tool_calls
   │
   └── 没有工具调用且返回文本时结束
```

核心模块各管一层边界：

- `model.py`：用 `httpx` 调用百炼 OpenAI 兼容接口，解析文本与多个 Tool Calls。
- `tools.py`：提供 `list_files`、`read_file`、`write_file`、`run_command`，限制路径、时间和输出大小。
- `agent.py`：保存完整历史，匹配 `tool_call_id`，执行反馈循环，最多调用模型12轮。
- `cli.py`：解析参数并显示轮次、工具参数、成功/失败和最终回答。

## 环境要求

- Python 3.11 及以上（开发环境为 Python 3.13）
- 阿里云百炼 API Key，以及创建 Key 时显示的 OpenAI 兼容地址

Windows PowerShell 安装：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

把凭据放进当前终端环境，不要写入代码或提交到 Git：

```powershell
$env:DASHSCOPE_API_KEY = "你的 API Key"
$env:DASHSCOPE_BASE_URL = "创建 Key 时显示的 OpenAI 兼容地址"
```

运行 Agent：

```powershell
coding-agent --workspace .\demo_run "为计算器增加减法和安全除法，并编写测试"
```

也可使用：

```powershell
python -m coding_agent --workspace .\demo_run "你的任务"
```

## 测试

默认测试完全离线，不调用模型 API：

```powershell
python -m pytest
```

真实端到端测试会产生一次实际模型调用，需要显式开启：

```powershell
$env:RUN_LIVE_API_TESTS = "1"
python -m pytest -m live
```

离线测试覆盖路径逃逸、读写、命令超时与截断、敏感环境变量清理、HTTP/JSON 错误、多个 Tool Calls、历史顺序、工具错误反馈、轮数耗尽和 CLI 行为。

## 两分钟演示

先从干净样例复制一份运行目录：

```powershell
Copy-Item -Recurse .\demo_project .\demo_run
Get-Content .\demo_project\DEMO_TASK.txt
```

然后把文件中的任务原样交给 Agent。它应先查看文件，再修改 `calculator.py` 和测试，运行 pytest，最后报告结果。`demo_run/` 已被 Git 忽略，可反复删除后重建，不会污染开发历史。

## 安全边界

- 文件路径解析为真实路径后，必须仍属于指定 workspace。
- 命令使用参数数组和 `shell=False`，具有超时与输出上限。
- 子进程不会继承名称中含 Key、Token、Secret、Password 等字样的环境变量。
- 模型服务地址必须使用 HTTPS；异常和终端轨迹不打印 API Key。
- 工具失败作为观察反馈给模型，预期错误不会直接打断主程序。

`run_command` 不是操作系统沙箱。被启动的程序仍拥有当前用户权限，处理不可信仓库时应使用容器、虚拟机或低权限账号。完整审查见 [security_best_practices_report.md](security_best_practices_report.md)。

## 项目资料

- [SPEC.md](SPEC.md)：范围、协议、边界与完成标准
- [CAPABILITY_MAP.md](CAPABILITY_MAP.md)：需求到模块的对应关系
- [LEARNING_NOTES.md](LEARNING_NOTES.md)：按模块整理的设计和答辩笔记
- [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md)：项目总述与常见追问
- [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md)：两分钟视频操作和口播脚本

项目使用 AI 辅助开发，但规格、模块边界、测试场景、安全取舍和每个 Git 里程碑均保留在仓库中，作者需要对最终设计负责。
