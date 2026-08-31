项目地址：https://github.com/VajraWoo/coding-agent

这是一个用 Python 从零实现的命令行编程智能体，没有使用 Agent 框架。千问负责提出下一步工具调用，本地 Harness 自己保存对话历史、解析模型输出、校验并执行工具、反馈结果，并用最大轮数控制终止。

运行环境：Python 3.11+。进入仓库后执行：
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

将百炼 API Key 和创建 Key 时显示的 OpenAI 兼容地址分别设置到 DASHSCOPE_API_KEY、DASHSCOPE_BASE_URL 环境变量。运行示例：
coding-agent --workspace .\demo_run "为计算器增加减法和安全除法，并编写测试"

主要功能：列出/读取/写入工作目录内文件；执行本地命令；连续处理多个 Tool Calls；显示每轮执行轨迹；处理路径越界、错误参数、命令超时、HTTP/JSON 异常和轮数耗尽。默认测试不调用 API，执行 python -m pytest 即可。真实测试需设置 RUN_LIVE_API_TESTS=1 后执行 python -m pytest -m live。

注意：run_command 具备当前用户权限，不是操作系统沙箱；不可信项目应在隔离环境运行。API Key 不进入仓库、README 或视频。
