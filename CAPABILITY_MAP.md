# 能力地图：最小编程智能体

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `local-tools` | 在指定工作目录内安全地列出、读取、写入文件和执行子进程 | — |
| `model-client` | 调用千问 API，将回复解析为文本或工具调用 | — |
| `agent-runtime` | 管理历史、执行“模型→工具→结果→模型”循环、错误和终止 | `local-tools`、`model-client` |
| `cli-observability` | 接收任务与工作目录，显示每个执行步骤 | `agent-runtime` |
| `verification-delivery` | 测试系统，准备演示、仓库文档和面试讲解 | 全部模块 |

实现顺序：`local-tools` + `model-client` → `agent-runtime` → `cli-observability` → `verification-delivery`。

