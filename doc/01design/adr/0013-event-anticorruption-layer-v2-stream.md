# ADR-0013：事件契约做防腐层，worker 消费 v2 `astream`

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-31 |
| 决策人 | hxy |
| 主文档关联 | §5.2 事件流与断线重放 |

## 背景

worker 需要把 DeepAgents 的执行过程转成前端可消费的事件流。要回答两个问题：**吐什么给前端**，以及**从 DeepAgents 的哪套 API 取**。

DeepAgents 提供两套并存的流式 API：

| API | 产出形态 |
|---|---|
| `astream(version="v2")` | **单条有序序列**，每个 chunk 是 `{"type", "ns", "data"}` 的 `StreamPart` |
| `astream_events(version="v3")` | **多个投影**（`.messages` / `.tool_calls` / `.subagents` / `.values` / `.output`），投影对象带 `.completed` / `.error` / `.output_deltas` 等已组装好的字段 |

## 决策

1. **不透传 DeepAgents 事件。** worker 映射成平台自己的事件词汇再 `XADD`（信封与枚举见 §5.2）
2. **消费 `astream(stream_mode=["updates","messages","custom"], subgraphs=True, version="v2")`**，不用 v3

## 理由

**为什么要防腐层**：

1. DeepAgents 的 `ns` 是 LangGraph 的内部节点路径（形如 `("tools:abc123", "model_request:def456")`），含随机 task id。透传等于让前端耦合 LangGraph 的节点命名
2. 两套 API 并存且都在演进。直接暴露任一套，将来迁移就是前端重写
3. 平台事件（`sandbox.queued`、run 生命周期、配额错误）DeepAgents 根本不知道，本来就得自己发
4. `Last-Event-ID` 重放依赖一个我们自己掌控的单调序号（Redis Stream ID）

**为什么 v2 而不是 v3**：

- **v2 是单条有序序列**，直接对应「往一条 Redis Stream 顺序 `XADD`」。v3 的多投影要靠 `interleave()` 合流，而 `Last-Event-ID` 重放的正确性**完全依赖顺序** —— 在核心恢复路径上引入一个顺序不由我们掌控的合流层，风险不值得
- **`custom` 模式是注入平台事件的通道**：沙箱工具内部用 `get_stream_writer()` 就能把 `sandbox.queued` 推进同一条有序流，排位更新与 token 流之间不会乱序，也不必另开旁路

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **直接透传 DeepAgents 事件** | 前端耦合 LangGraph 的内部节点命名与随机 task id；框架升级即破坏前端 |
| **消费 v3 `astream_events`** | 多投影需 `interleave()` 合流，顺序不由我们掌控，与 `Last-Event-ID` 重放的正确性冲突。它把 tool_call 生命周期组装好确实是真实收益，但不抵这个风险 |

## 后果

**正面**：
- 前端契约与 DeepAgents 解耦，框架升级只需改 worker 的映射层
- 事件顺序完全由我们掌控，`Last-Event-ID` 重放可靠
- 平台事件与 agent 事件在同一条有序流里，不会乱序

**代价**：
- **要自己配对 `tool_call` 与 `tool_result`**（v3 已帮忙组装）。一次性成本，但必须写对
- 映射层是额外的代码与测试面
- **Agent 层事件的 payload 现在定不了** —— 要等 P0 跑出 DeepAgents 实际的 `StreamPart` 结构才能回填（§5.2）
- 若 DeepAgents 将来废弃 v2，需要迁移到 v3 并重新解决顺序保证

## 重新评估的触发条件

- DeepAgents 废弃 v2 `StreamPart`，或 `version` 参数语义变化
- v3 提供有序单流的消费方式
- 出现 v2 表达不了而 v3 能表达的必要信息
