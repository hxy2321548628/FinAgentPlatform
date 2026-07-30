# ADR-0005：任务队列用 Redis Streams / ARQ，不用 Celery

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-29 |
| 决策人 | hxy |
| 主文档关联 | §4.2 三条独立通道、§4.3 技术栈全景 |

## 背景

网关接收任务后需要异步分发给 worker 执行。需要一个任务队列，要求：至少一次投递、失败重投、与 asyncio worker 兼容。

Python 生态的默认答案是 Celery。

## 决策

采用 **Redis Streams + consumer group 自写消费循环**（约 200 行），或使用 **ARQ**。

**不使用 Celery。**

## 理由

**第一，Celery 与 asyncio 正面冲突。** Celery 5 仍以 prefork 为主要执行模型，对 asyncio 的支持很别扭。而本平台的 worker 必须是 asyncio 的 —— agent run 是 IO 密集的（等 LLM、等沙箱），单个 asyncio 进程要管理几十个并发 run（见主文档 §8.1）。用 prefork 模型跑这种负载，等于为每个并发 run 开一个进程，浪费巨大。

**第二，队列的职责其实很轻。** 真正的状态在 LangGraph checkpointer 中（见 [ADR-0008](./0008-langgraph-checkpointer.md)），队列只负责「分发 + 至少一次投递 + 失败重投」三件事。职责轻意味着选型压力小，也意味着自写 200 行是可控的。

**第三，Redis 本来就要用。** 事件通道已经决定用 Redis Streams（[ADR-0006](./0006-event-channel-streams-not-pubsub.md)），任务队列复用同一个 Redis 不引入任何新组件。而 Celery 会带来 broker + result backend + beat 一整套需要理解和运维的东西。

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **Celery** | 与 asyncio worker 正面冲突（主因）；引入的运维面远大于本场景需要 |
| **RQ** | 同样是同步模型，不适合 asyncio worker |
| **NATS JetStream / RabbitMQ** | 可靠性与功能更强，但要多运维一个中间件。当前规模用不上，将来需要时再换也不困难 |
| **数据库轮询做队列** | 无需新组件，但轮询延迟与 Postgres 压力都不划算，且 Redis 已在架构中 |

## 后果

**正面**：
- worker 全程 asyncio，一个进程管理几十个并发 run
- 不引入新中间件，运维面最小
- 自写消费循环意味着投递语义完全可控、可调试

**代价**：
- **自写的 200 行需要自己保证正确性**：ack 时机、pending 超时重投、consumer 崩溃后的消息认领（`XAUTOCLAIM`）、死信处理。这些是 Celery 已经解决过的问题，自写要重新踩一遍
- 没有 Celery 生态的现成周边（定时任务、监控面板、任务链编排）
- **至少一次投递意味着可能重复执行**。这依赖 checkpointer 保证幂等，而该假设尚未实测验证 —— 见主文档 §3.2 权衡三，**这是当前设计中最需要动手验证的一点**

## 重新评估的触发条件

- 需要跨机房或更强的投递可靠性保证 → 换 NATS JetStream / RabbitMQ
- 自写消费循环的缺陷反复引发线上问题 → 改用 ARQ 等成熟实现
- 出现复杂的任务编排需求（DAG、任务链）→ 重新评估是否需要专门的编排框架
