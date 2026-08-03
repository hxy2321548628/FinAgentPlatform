# 事件映射器的测试样本

`stream_chunk.jsonl` 是 DeepAgents 真实吐出的流式 chunk，用来离线驱动事件防腐层的测试
（[P0 计划 · 步骤一](../../../../doc/03plan/P0-plan.md)）。**离线跑真实数据，不需要调模型、不花 token。**

## 来源

| 项 | 值 |
|---|---|
| 生成命令 | `app/spike/probe2_stream_dump.py --fixture` |
| 日期 | 2026-08-03 |
| 环境 | deepagents 0.7.1 · langgraph 1.2.10 · langchain 1.3.14 · `deepseek-v4-pro` |
| 消费方式 | `astream(stream_mode=["updates","messages","custom"], subgraphs=True)` |
| 规模 | 359 条 chunk，4 轮模型调用，13,039 token |

每行是一个 chunk，形如 `{"ns": [...], "mode": "...", "payload": ...}`，与 `astream` 吐出的
`(namespace, mode, payload)` 三元组一一对应。

## 覆盖了什么

任务是刻意设计的：读一个**不存在**的文件 → 写文件 → 执行，几轮之内走遍映射器需要区分的所有结构分支。

| 结构分支 | 覆盖 |
|---|---|
| `updates` / `PatchToolCallsMiddleware.before_agent`（payload 为 `null`） | ✅ |
| `updates` / `model` —— 带 `tool_calls`（`tool_call` 事件的来源） | ✅ |
| `updates` / `model` —— 无 `tool_calls` 的收尾回答 | ✅ |
| `updates` / `tools` —— `status="success"` | ✅ 2 条 |
| `updates` / `tools` —— `status="error"` | ✅ 1 条（读不存在的文件） |
| `messages` / `AIMessageChunk` —— `content`（`token` 事件） | ✅ |
| `messages` / `AIMessageChunk` —— `additional_kwargs.reasoning_content`（`reasoning` 事件） | ✅ |
| `messages` / `AIMessageChunk` —— `tool_call_chunks`（逐字流式的工具参数） | ✅ |
| `messages` / `AIMessageChunk` —— `usage_metadata`（含 `cache_read`） | ✅ |
| `messages` / `ToolMessage` | ✅ 3 条 |
| 工具名 | `read_file` / `write_file` / `execute` |

**两个已知空缺**，不是遗漏：

- `custom` 模式一条都没有 —— 当时的 backend 没用 `get_stream_writer()`。`sandbox.*` 事件要等排队逻辑实现后才有真实样本。
- `todo.updated` 与 `subagent.*` 没有 —— agent 未调用 `write_todos`，且本期不开子 agent。映射器按契约留分支，但**这两条没有真实数据验证过**。

## 注意

- **顺序有意义。** 这是一条完整未裁剪的流，映射器的「全量回放不漏类型」测试依赖真实时序，不要为省体积抽稀。
- 入库前已扫描，不含 API key、密钥串与宿主机绝对路径。
- 重新生成会得到不同的 id 与措辞（LLM 输出不确定），**测试不要断言具体文本**，只断言结构。
