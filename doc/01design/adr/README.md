# 架构决策记录（ADR）

本目录存放金融学院智能体平台的架构决策记录。上游文档：[总体架构](../01architecture.md)；各项参数与契约见总体架构的[文档地图](../01architecture.md)。

## 这个目录是干什么的

主架构文档回答**「系统是什么样」**，ADR 回答**「为什么是这样，以及当初否掉了什么」**。

分开存放的原因：主文档描述的是当前状态，会被不断改写；而决策是历史事实，**只增不改**。一个决策一旦被推翻，做法是新增一条 ADR 说明推翻的理由，并把旧的标为「已废弃」，而不是把旧记录删掉 —— 否则半年后没人记得当初为什么没选 K8s，于是又要重新讨论一遍。

## 索引

| 编号 | 决策 | 状态 | 关联设计 |
|---|---|---|---|
| [0001](./0001-single-host-compose.md) | 单机 Docker Compose，不引入 K8s | 已接受 | [总体架构 §2–§3](../01architecture.md)、[运维设计](../08operation-design.md) |
| [0002](./0002-sandbox-isolation-gvisor.md) | 沙箱隔离用 Docker + gVisor，不用 Firecracker | 已接受 | [安全设计 §7.3](../07security-design.md) |
| [0003](./0003-sandbox-per-thread-lifecycle.md) | 沙箱按 thread 长驻，不做 per-call | 已接受 | [运行时设计 §5.5](../05runtime-design.md) |
| [0004](./0004-sandbox-broker-docker-sock.md) | `docker.sock` 由独立 sandbox-broker 持有 | 已接受 | [总体架构 §3](../01architecture.md)、[安全设计 §7.3](../07security-design.md) |
| [0005](./0005-task-queue-redis-streams.md) | 任务队列用 Redis Streams / ARQ，不用 Celery | 已接受 | [总体架构 §4](../01architecture.md)、[运行时设计](../05runtime-design.md) |
| [0006](./0006-event-channel-streams-not-pubsub.md) | 事件通道用 Redis Streams，不用 Pub/Sub | 已接受 | [运行时设计 §5.2](../05runtime-design.md) |
| [0007](./0007-sse-over-websocket.md) | 实时推送用 SSE，不用 WebSocket | 已接受 | [总体架构 §4](../01architecture.md)、[运行时设计 §5.2](../05runtime-design.md) |
| [0008](./0008-langgraph-checkpointer.md) | 中断恢复复用 LangGraph Checkpointer，不自建 | 已接受 | [运行时设计 §5.3](../05runtime-design.md) |
| [0009](./0009-default-model-selection.md) | 默认模型 deepseek-v4-pro + 辅助模型下沉 | 已接受 | [总体架构 §2–§3](../01architecture.md) |
| [0010](./0010-self-hosted-accounts-rbac.md) | 自建账号体系与三角色 RBAC | 已接受 | [安全设计 §7.2](../07security-design.md)、[数据设计 §6.2](../06data-design.md) |
| [0011](./0011-cookie-session-not-oauth2.md) | 认证用 Cookie + Redis Session，不用 OAuth2 / JWT | 已接受 | [安全设计 §7.2.2](../07security-design.md) |
| [0012](./0012-plain-http-intranet.md) | 内网走 HTTP，不启用 TLS | 已接受 | [安全设计 §7.4](../07security-design.md)、[运维设计](../08operation-design.md) |
| [0013](./0013-event-anticorruption-layer-v2-stream.md) | 事件契约做防腐层，worker 消费 v2 `astream` | 已接受 | [运行时设计 §5.2](../05runtime-design.md) |
| [0014](./0014-tool-idempotency-key.md) | 工具幂等键，broker 侧去重（键为 `thread_id` + `checkpoint_ns`） | 已接受 | [总体架构 §2.3](../01architecture.md)、[运行时设计 §5.6](../05runtime-design.md) |
| [0015](./0015-sandbox-disk-quota-xfs.md) | 沙箱磁盘配额用 XFS project quota | 已接受 | [安全设计 §7.3.5](../07security-design.md) |
| [0016](./0016-sandbox-filesystem-backend.md) | 自实现 DeepAgents 沙箱后端，不用内置 StateBackend | 已接受 | [运行时设计 §5.5–§5.6](../05runtime-design.md) |
| [0017](./0017-sandbox-network-and-package-install.md) | 沙箱开放出网，agent 自己装 Python 包 | 已接受 | [安全设计 §7.3.3、§7.3.4](../07security-design.md) |

**状态取值**：`提议中` → `已接受` / `已否决` → （后续可能）`已废弃`（被某条新 ADR 取代）

## 已评估但当前不采用

下表是重评导航，不代替正式 ADR。已有 ADR 的方案以 ADR 为准；尚未单列 ADR 的范围裁剪，以对应专题文档为准。若其中一项要改变，应先新增 ADR，而不是直接改总体架构。

| 方案 | 当前结论 | 重新评估的触发条件 | 记录位置 |
|---|---|---|---|
| K8s、服务网格 | 单机 Compose 足够 | 需要跨机部署，或应用副本长期超过 10 个 | [ADR-0001](./0001-single-host-compose.md) |
| 分库分表、读写分离 | 单库单表 | 单表超过千万行，或读负载压垮主库 | [数据设计](../06data-design.md) |
| 异地/同城多活 | 不采用，以快速恢复为主 | 学院提出明确 SLA | [运维设计 §8.2](../08operation-design.md) |
| 灰度、蓝绿、金丝雀发布 | 不采用，允许协调停机窗口 | 用户量或可用性要求上升到不可停机 | [运维设计 §8.4](../08operation-design.md) |
| Celery | 不采用 | Redis Streams 方案不再满足任务语义 | [ADR-0005](./0005-task-queue-redis-streams.md) |
| WebSocket | 不采用 | 出现高频双向实时交互 | [ADR-0007](./0007-sse-over-websocket.md) |
| Firecracker | 不采用 | 平台对校外开放，或用户不再可信 | [ADR-0002](./0002-sandbox-isolation-gvisor.md) |
| 外部托管代码执行服务 | 不采用 | 合规放开且部署边界转向公网 | [安全设计](../07security-design.md) |
| 前端图表库 | 不采用，直接展示沙箱生成的产物 | 需要可交互图表 | [前端技术选型](../02frontend-selection.md) |
| 用户自定义提示词、Skill、MCP | 已满足重评条件，等待排期决定 | 接入进入实施前先确定准入、共享与计量 | [第三方接入规范](../04extension-integration.md) |
| 面向全院学生开放 | 不采用 | 学院明确要求扩大范围 | [总体架构 §7](../01architecture.md) |
| 静态加密、服务间 mTLS、发往 LLM 的数据脱敏 | 当前不采用 | 合规要求变化，或开始承载敏感数据 | [安全设计 §7.4](../07security-design.md) |

## 写作规范

- 文件名：`NNNN-英文短横线描述.md`，编号连续递增，**不复用已删除的编号**
- 一条 ADR 只记一个决策。若发现在写两个决策，拆成两条
- 必须写清**被放弃的备选及放弃理由** —— 这是 ADR 最有价值的部分，也是最常被省略的部分
- 必须写**代价**。只有好处没有代价的决策，说明还没想清楚
- 必须写**重新评估的触发条件**，让将来的人知道什么情况下该回来重看这条

## 模板

```markdown
# ADR-NNNN：<一句话决策>

| 项 | 值 |
|---|---|
| 状态 | 提议中 / 已接受 / 已否决 / 已废弃 |
| 日期 | YYYY-MM-DD |
| 决策人 | |
| 主文档关联 | §x.y |

## 背景
<面临什么问题？有什么约束？>

## 决策
<决定做什么。一两句话说清。>

## 理由
<为什么这样选。>

## 被放弃的备选
| 备选 | 放弃理由 |

## 后果
**正面**：
**代价**：

## 重新评估的触发条件
<什么情况下应该回来重新审视这条决策>
```
