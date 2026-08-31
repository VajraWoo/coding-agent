# 项目规格：最小编程智能体

## 目标

实现一个小型命令行 Coding Agent。它接收自然语言编程任务，询问千问下一步做什么，在本地执行通过校验的工具，将结果反馈给模型，循环运行，直到模型给出最终答案或程序安全终止。重点是展示自己实现的完整 Agent 循环，而不是包装现成 Agent 框架。

## 已确定假设

1. Python 3.13 命令行程序，不做 GUI。
2. 单 Agent，使用北京地域 `qwen3-coder-plus`。
3. 使用 OpenAI 兼容 HTTP 协议，不使用 Agent 框架/SDK。
4. 一次运行处理一个任务，第一版不做流式输出、多 Agent 或长期记忆。
5. Agent 只能操作命令行指定的工作目录。
6. 最小工具集：`list_files`、`read_file`、`write_file`、`run_command`。
7. 优先级：可理解、可验证、安全，然后才是功能数量。

## 技术栈

- Python 3.13
- `httpx`：HTTP 请求
- `pytest`：自动化测试
- 标准库：`pathlib`、`subprocess`、`json`、`dataclasses`

## 预定命令

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
$env:RUN_LIVE_API_TESTS = "1"
python -m pytest -m live
python -m coding_agent --workspace .\demo_project "为计算器增加减法并编写测试"
```

## 项目结构

```text
src/coding_agent/
  __main__.py       命令行入口
  cli.py            参数解析与进度展示
  agent.py          Agent 循环、历史、终止与错误
  model.py          千问 HTTP 客户端与响应解析
  tools.py          工具定义、校验与本地执行
  errors.py         项目异常
tests/              工具、循环、解析和真实 API 测试
demo_project/       视频演示项目
tasks/              实施计划与任务清单
README.md           公开仓库说明
README.txt          最终提交说明（不超过 1000 汉字）
```

## 核心约定

模型不直接读文件或执行命令，只能返回结构化工具请求。本地运行时校验并执行请求，将结果追加到历史，再调用模型。

```text
用户任务 → 模型 → 工具请求 → 校验/本地执行 → 结果入历史 → 再次调用模型 → 最终答案
```

## 工具约定

- `list_files`：返回限量的相对路径，拒绝工作目录外路径。
- `read_file`：读取限长 UTF-8 文本，拒绝目录、不存在/不可解码文件和越界路径。
- `write_file`：在工作目录内写入完整文本，需要时创建父目录。
- `run_command`：只接受参数数组，例如 `["python", "-m", "pytest"]`；不经过 shell；返回退出码与限长输出。

## 失败与终止规则

- 最多 12 轮模型调用；模型请求超时 60 秒；本地命令超时 30 秒。
- 工具输出超过上限时截断。
- 未知工具、错误 JSON、无效参数、路径越界、超时和命令失败转为结构化错误，不让主程序直接崩溃。
- 模型返回最终文本时结束；达到轮数上限时受控失败。
- API Key 只从环境变量读取，永不记录或提交。

## 代码风格

公开函数使用类型标注；使用小模块和显式数据结构；模型特有解析只放在 `model.py`；本地副作用只通过工具注册表发生。

```python
@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False
```

## 测试策略

1. 单元测试：路径限制、文件操作、超时、输出截断和 API 响应解析。
2. Agent 循环测试：使用脚本化假模型，保证稳定且免费。
3. 可选真实测试：显式开启后调用千问。
4. 最终演示：真实模型修改 `demo_project` 并运行测试。

假模型只是测试替身，演示必须使用真实 API。

## 边界

- 始终：校验工具参数、限制路径、里程碑提交前测试、显示执行过程、解释新设计。
- 先询问：新增运行依赖、放宽命令执行、超出最小范围、创建/发布远程仓库。
- 永不：提交凭据；使用 Agent 框架；使用服务器托管代码/文件工具；改写已推送历史；截止后推送。

## 完成标准

- CLI 接收工作目录和自然语言任务。
- 真实千问能请求本地工具，运行时能连续执行多个工具并保存正确历史。
- 四个工具正常工作并拒绝工作目录外操作。
- 超时、API 失败、错误参数、未知工具和轮数耗尽都可见且受控。
- 确定性测试无需 API 就能全部通过；显式开启的真实 API 测试也能通过。
- 演示中 Agent 真实修改小项目并运行测试。
- 公开仓库有真实里程碑且无凭据。
- 你能用“用途、输入/输出、失败方式、安全边界、验证方法”解释每个模块。

## Git 里程碑

1. `docs: define coding agent scope and architecture`
2. `feat: add workspace-safe local tools`
3. `feat: add qwen model client`
4. `feat: implement agent execution loop`
5. `feat: add command-line interface`
6. `test: cover failures and live integration`
7. `docs: add demo and submission instructions`

每次提交都是真实检查点，不伪造、不倒填日期。

## 待确定

1. Git 历史显示的姓名和邮箱。
2. 公开仓库使用 GitHub 还是 Gitee。
3. 两分钟演示任务在核心循环工作后选定。

