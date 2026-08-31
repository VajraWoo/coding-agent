# 两分钟视频脚本

## 录制前准备

1. 终端提前进入仓库并激活 `.venv`，API Key 与 Base URL 已放在环境变量中，画面里不要执行查看环境变量的命令。
2. 放大终端字体，隐藏通知，关闭显示 Key 的百炼页面。
3. 创建干净演示目录：`Copy-Item -Recurse .\demo_project .\demo_run`。
4. 先彩排一次并计时。正式录制可剪去 API 等待，成片不得超过2分钟。

## 画面与口播

### 0:00—0:20 题目和结构

画面打开 README 的流程图和项目目录。

口播：

“这是我用 Python 实现的最小编程智能体。它没有使用 Agent 框架。千问只负责决定下一步，本地 Harness 自己管理消息历史、解析工具调用、执行文件和命令工具，再把结果反馈给模型。”

### 0:20—0:35 演示任务

画面依次显示 `demo_run/calculator.py`、现有测试和 `DEMO_TASK.txt`。

口播：

“演示项目目前只有加法。我要求 Agent 增加减法和除法，处理除零，补测试并运行全部测试。”

### 0:35—1:25 真实运行

执行：

```powershell
$task = Get-Content -Raw .\demo_run\DEMO_TASK.txt
coding-agent --workspace .\demo_run $task
```

画面保留 `list_files`、`read_file`、`write_file`、`run_command` 的轨迹。等待部分可加速。

口播：

“终端显示每轮模型请求、工具参数和执行结果。模型不能直接碰本地文件；Harness 先校验请求，再执行。测试失败也会作为观察返回，让模型继续修正。循环最多12轮，避免无限运行。”

### 1:25—1:45 验证结果

执行：

```powershell
Get-Content .\demo_run\calculator.py
python -m pytest .\demo_run -q
```

口播：

“这里可以看到新增实现，全部测试通过。最后这次 pytest 是我在 Agent 之外重新运行的独立验证。”

### 1:45—2:00 设计取舍

画面切到 `src/coding_agent/agent.py` 的循环和测试结果。

口播：

“项目用离线假模型稳定测试历史和边界，也有显式真实 API 测试。文件工具限制在工作目录，Key 不进仓库。命令执行仍有当前用户权限，所以我没有把它称为沙箱；不可信项目需要容器或低权限环境。”

## 必须避免

- 不展示 API Key、环境变量值或创建 Key 的弹窗。
- 不把成片做成纯口头介绍；必须出现真实 Tool Calls、文件变化和测试结果。
- 不声称 `shell=False` 等于沙箱。
- 正式成片控制在1分50秒左右，给片头和操作停顿留余量。
