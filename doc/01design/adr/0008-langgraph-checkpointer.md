# ADR-0008：中断恢复复用 LangGraph Checkpointer，不自建

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-29 |
| 决策人 | hxy |
| 主文档关联 | §5.3 中断恢复、§5.4 Run 状态机、§8.2 可用性与故障恢复 |

## 背景

平台的核心需求之一是「支持长任务、中断恢复」。一次分析可能跑几十分钟，中途 worker 崩溃、滚动发布、或需要等教师审批，都不能让教师从头再来 —— 既浪费时间，也浪费已经花掉的 token 成本。

需要决定状态持久化与恢复机制自建还是复用框架能力。

## 决策

**直接复用 LangGraph 的 checkpointer**，生产环境使用 `AsyncPostgresSaver`。不自建状态持久化机制。

## 理由

DeepAgents 构建在 LangGraph 之上：`create_deep_agent()` / `async_create_deep_agent()` 返回编译好的 LangGraph graph，并**接受 `checkpointer` 参数**。（`async_create_deep_agent` 的区别是传 `is_async=True`，影响 SubAgentMiddleware 的工具执行与子 agent 调用方式。）

也就是说，**线程级的状态持久化与恢复是框架已经提供的能力**，传一个参数即可启用。自建等于重新实现一遍状态快照、版本管理、恢复语义，而且要跟 DeepAgents 内部的状态结构保持同步 —— 框架一升级就可能失效。

`AsyncPostgresSaver` 会自动建表（`checkpoints` / `checkpoint_writes`），与平台已有的 Postgres 复用同一实例，不引入新存储。

**关键收获：这个决策同时解决了三种不同的中断语义**，而它们本来需要三套机制：

| 类型 | 触发场景 | 机制 |
|---|---|---|
| **崩溃恢复** | worker OOM / 被 kill / 滚动发布 | 队列消息未 ack，pending 超时后重投给其他 worker；LangGraph 从最后一个 checkpoint 继续，已完成的节点不重跑（边界见「代价」一节） |
| **人工介入 (HITL)** | agent 执行敏感操作前暂停等教师确认 | LangGraph `interrupt()` → 状态落盘，run 转 `waiting_approval`，worker 释放；批准后用 `Command(resume=...)` 重新入队 |
| **主动取消 / 暂停** | 教师点击「停止」 | Redis 中打 cancel flag，worker 在 step 边界检查后抛 `CancelledError`；已写入的 checkpoint 保留，可从该点恢复 |

其中 HITL 是长任务平台的核心价值：**任务可以挂起数小时等人，期间不占用任何 worker 资源。** 这一条如果自建，工作量相当可观。

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **自建状态持久化** | 重复造轮子，且要跟 DeepAgents 内部状态结构耦合，框架升级即失效 |
| **不做中断恢复，失败即重跑** | 几十分钟的任务重跑，时间与 token 成本都不可接受；且 HITL 完全无法实现 |
| **`MemorySaver`（内存 checkpointer）** | 进程重启即丢失，无法满足崩溃恢复。仅适合本地开发 |

## 后果

**正面**：
- 崩溃恢复、HITL、主动取消三种语义一次解决
- worker 变成无状态的，可随意增减副本、滚动重启
- 与 §11 的 P2 阶段验收标准直接对应：`kill -9` worker 后任务能续跑

**代价**：
- **强绑定 LangGraph 的状态模型**。若将来更换智能体框架，这一层要重做
- **checkpoint 表会持续膨胀**，需要保留策略与清理机制，否则 Postgres 体积失控（见主文档 §6.5、§10.2）
- **Postgres 成为恢复能力的单点** —— checkpoint 丢失意味着中断的任务无法恢复。这让 Postgres 备份不只是数据保护，也是功能可用性的一部分（§8.5）
- **「已完成的步骤不重跑」成立，但保护不到两种情况**（2026-07-31 依据 LangGraph 文档确认，见主文档 §3.2）：

  保护粒度实际是**节点级**而非超步级 —— 每个节点执行完即写 `checkpoint_writes`（pending writes），同超步内其他节点失败时，已完成节点不重跑。但：

  1. 崩溃发生在**工具执行途中**时，该节点无 pending write，整节点重跑
  2. **HITL 恢复时整个节点从头重跑** —— 官方明确 *"any code that ran before the `interrupt()` will execute again"*。这不是异常路径，**每次审批通过都会发生**

  因此**必须在工具层做幂等键**，不能只依赖 checkpointer。方案见主文档 §5.6，排在 P3 且必须先于 HITL 落地

## 重新评估的触发条件

- ~~P2 实测发现 checkpoint 重放边界与预期不符，需要在工具层补幂等键~~ → **已确认需要幂等键**（2026-07-31），方案见主文档 §5.6。剩余待验证项是 `tool_call_id` 在重放中是否稳定，已并入 P0 探针
- 更换智能体框架
- checkpoint 表膨胀失控且清理策略无法解决
