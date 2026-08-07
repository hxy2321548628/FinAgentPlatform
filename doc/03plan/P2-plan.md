# P2 实施计划

| 项 | 值 |
|---|---|
| 文档状态 | 可开工 |
| 当前版本 | v0.2 |
| 作者 | hxy |
| 日期 | 2026-08-07 |
| 上游文档 | [总体架构设计](../01design/01architecture.md) · [P1 实施计划](./P1-plan.md) |

### 版本历史

| 版本 | 日期 | 修改人 | 说明 |
|---|---|---|---|
| v0.1 | 2026-08-07 | hxy | 初稿。P1 已于同日验收六条全过，本文覆盖「进程重启不丢任务」这一条能力线 |
| v0.2 | 2026-08-07 | hxy | **§7 三项待决全部关闭，可以开工**：幂等键先量后定、建表用 Alembic、worker × 2 + api × 1。§2 三处定案已回填上游文档 |

> **本文档的职责**：回答 **「P2 具体怎么做、做到什么程度算完」**。
>
> **不回答**「为什么队列用 Redis Streams 而不是 Celery」（在 [ADR-0005](../01design/adr/0005-task-queue-redis-streams.md)）、「为什么事件流不用 Pub/Sub」（在 [ADR-0006](../01design/adr/0006-event-channel-streams-not-pubsub.md)）、「为什么复用 LangGraph checkpointer」（在 [ADR-0008](../01design/adr/0008-langgraph-checkpointer.md)）。本文只给相对链接，不复制正文。

---

## 1. P2 的边界

**目标**（[架构 §11](../01design/01architecture.md)）：把「进程重启即丢」这条从平台上摘掉。

一句话概括三期的差别：**P0 回答「agent 好不好用」，P1 回答「不可信代码跑在这台机器上安不安全」，P2 回答「这台机器上的东西挂了会怎样」。**

现在的答案是「全丢」：checkpointer 是 `InMemorySaver`，run 的元数据是执行器里的一个 dict，事件日志是一个 `deque`。三样都在 api 进程的内存里，`docker compose up -d` 一次滚动重启就全没了 —— 而一次分析要跑几十分钟，滚动重启本质上就是一次可控的崩溃（[架构 §8.4](../01design/01architecture.md)）。

**与 P1 的相似之处**：这一期同样**没有未知，只有工作量**。三个组件的选型都已在 ADR 里论证完，要做的是把已定的方案落到代码里并验证生效。

**与 P1 的不同之处**：P1 是**加参数**（在既有的 `DockerContainer` 上补加固项，改完立刻能验），P2 是**换地基**（三处状态从内存搬到外部存储，再把一个进程劈成两个）。因此本文的步骤划分比 P1 更强调「一次只换一样，每换一样都能独立验证」。

### 1.1 做什么

| 范围 | 依据 |
|---|---|
| Postgres：LangGraph `AsyncPostgresSaver` checkpointer | [架构 §5.3 §6.1](../01design/01architecture.md)、[ADR-0008](../01design/adr/0008-langgraph-checkpointer.md) |
| Postgres：`runs` 与 `run_events` 两张表 | [架构 §6.2](../01design/01architecture.md)，**§11 的 P2 一行没提，但拆分后元数据无处可放**，见 §2.2 |
| Redis Streams：事件通道，替换内存事件日志 | [架构 §5.2](../01design/01architecture.md)、[ADR-0006](../01design/adr/0006-event-channel-streams-not-pubsub.md) |
| Redis Streams：任务队列 + consumer group | [架构 §4.2](../01design/01architecture.md)、[ADR-0005](../01design/adr/0005-task-queue-redis-streams.md) |
| worker 进程从 api 中拆出 | [架构 §4.1 §4.4](../01design/01architecture.md) |
| 事件归档与保留策略，关闭 [§6.5](../01design/01architecture.md) 两问 | 见 §2.3 |

### 1.2 P1 已经就位、本期不重做的部分

**事件 id 的格式在 P0 就是照 Redis Stream 的规则发的**（毫秒时间戳 + 同毫秒内序号，见 [`run/log.py`](../../app/run/log.py) 的 `_next_id`）。因此换成真的 Redis Stream 时，**对外契约一个字都不用改** —— 变的只是发号的人。`Last-Event-ID` 的语义、前端的解析、[架构 §5.2](../01design/01architecture.md) 的信封定义全部原样成立。这是 P0 刻意留的接口。

**`EventLog` 已经是一层可替换的抽象**：`append` / `read` / `follow` 三个方法，执行器与路由都只认这三个。Redis 实现要做的是把 `deque` 换成 `XADD` / `XRANGE` / `XREAD BLOCK`，调用方不动。

**跨进程租约已有兜底**（2026-08-07，[`sandbox/pool.py`](../../app/sandbox/pool.py) 的 `_expire_lease`）。本期把它做精确：worker 有了身份之后，租约可以记名，崩溃时按名回收，不必再等 30 分钟超时。

### 1.3 明确不做

**不是遗漏，是分期。**延续 [P1 §1.3](./P1-plan.md) 的登记方式，每条写明由哪一期偿还。

| 不做 | 后果 | 由哪期偿还 |
|---|---|---|
| MinIO 产物存储 | 产物仍从 workspace 直接读；workspace 仍不回收 | **本期定案移到 P3**，见 §2.1 |
| 认证、RBAC、多用户隔离 | 仍是固定假 `user_id`，`runs` 表的 `user_id` 列先留空 | P3 |
| 配额与限流 | token 计量有了口径但没有闸门 | P3 |
| HITL 审批、主动取消 | run 仍只有四态，`waiting_approval` 与 `cancelled` 不实现 | P3 |
| 工具幂等键去重 | 至少一次投递会带来重复执行的窗口 | **先量后定**（§7 已关闭）：步骤四量出重复次数再决定当期做还是留 P3 |
| `users` / `groups` / `threads` / `artifacts` / `sandboxes` 五张表 | 会话仍等同于 workspace 目录，产物仍靠扫目录 | P3（前四张依赖用户模型或 MinIO）／`sandboxes` 可能永远不需要，见 §2.2 |
| Postgres 主从 | 仍是单点，挂了全局不可用且中断任务无法恢复 | [架构 §8.2](../01design/01architecture.md) 待定，本期只做备份 |
| 可观测性指标、链路追踪、成本看板 | 只有结构化日志与 token 数 | P4 |
| 前端 | 仍只能 curl / Postman 验收 | **仍未排期** —— [P0 §4](./P0-plan.md) 的遗留问题至今未关闭，且它设的前置条件（事件契约经真实流量验证）已于 2026-08-07 满足。本期主动不做，但这条不该继续无主地挂着 |

---

## 2. 三处与上游文档不一致，本期定案

按[项目约定](../../CLAUDE.md)先确认再写。三处结论已于 2026-08-07 回填到对应的上游文档。

### 2.1 MinIO 移到 P3

**冲突**：[P1 §1.3](./P1-plan.md) 把「MinIO 产物存储」登记为 P2 偿还；而[架构 §11](../01design/01architecture.md) 的 P4 一行写的是「产物存储完善」。同一件事被排进了两期。

**定案：P2 不做 MinIO，移到 P3。**

理由：

- **它不是 worker 拆分的前置**。拆分后产物的读取路径完全不变 —— api → broker → workspace 文件。broker 仍持有宿主目录（[ADR-0004](../01design/adr/0004-sandbox-broker-docker-sock.md)），这条路不经过 worker，拆不拆都一样。
- **它的隔离设计依赖 P3 的用户模型**。[架构 §6.1](../01design/01architecture.md) 写明 MinIO「路径按租户前缀隔离」，而租户是什么在 P3 才定。现在建的 key 结构，P3 多半要推翻重来。
- **P2 已经是最大的一期**：三处状态迁移 + 一次进程拆分。往里再塞一个存储组件，只会让「哪一层出的问题」更难分辨 —— 这正是 [P1 §6](./P1-plan.md) 坚持分三次回归要避免的事。

**代价**：[§6.5](../01design/01architecture.md) 的 workspace 归档回收随之推到 P3。按 2026-08-07 的实测（典型会话 ~350KB，约 2.5GB/年），这段等待是安全的，且已有[体检脚本](../../deploy/workspace-report.sh)盯着水位。

**已回填**（2026-08-07）：[P1 §1.3](./P1-plan.md) 的 MinIO 一行已改期次；[架构 §6.5](../01design/01architecture.md) 与 [§4.4](../01design/01architecture.md) 已改成 P3。

### 2.2 P2 要落两张表，不只是 checkpointer

**冲突**：[架构 §11](../01design/01architecture.md) 的 P2 一行只写了「Redis Streams + Postgres checkpointer」。照字面做，run 的元数据无处可放。

现在 `GET /api/runs/{id}` 读的是执行器内存里的一个 dict（[`run/executor.py`](../../app/run/executor.py) 的 `get`）。**worker 拆出去之后，那个 dict 在 worker 进程里，而查询请求打在 api 进程上** —— 这条端点会直接失效。

**定案：P2 落 `runs` 与 `run_events` 两张表**，字段照 [架构 §6.2](../01design/01architecture.md) 的草案，其中 `user_id` 先留空（P3 才有用户）。

`users` / `groups` / `user_groups` / `threads` / `artifacts` 五张表不建：前三张是用户模型（P3），`threads` 现在等同于 workspace 目录且存在性判断已有现成端点，`artifacts` 的 `s3_key` 依赖 MinIO（按 §2.1 也是 P3）。

**`sandboxes` 表可能永远不需要**：[架构 §6.2](../01design/01architecture.md) 设计它是为了存容器映射，而 P1 已改用容器 label 认领（[P1 §7](./P1-plan.md)），`projid` 也改成从 `thread_id` 派生而不查表。这张表的两个用途都已被更简单的方案取代。**本期不建，并建议在架构里标注其现状**，而不是留着让人以为还要建。

**已回填**（2026-08-07）：[架构 §11](../01design/01architecture.md) 的 P2 一行已补上元数据表；[§6.2](../01design/01architecture.md) 已给 `sandboxes` 标注现状。

### 2.3 §6.5 四问只能关两问，不是四问

**冲突**：[架构 §6.5](../01design/01architecture.md) 在 2026-08-06 写下「**P2 规划时必须把这四项一并关闭**，不要再往后滚」。写这句时没核对四项各自的依赖。

**定案：P2 关两问，另两问随 P3。**

| §6.5 的问题 | 本期能不能答 |
|---|---|
| `run_events` 与 checkpoint 的保留期 | ✅ **P2 关闭**。两者都在本期落到 Postgres，保留期是它们自己的属性 |
| Postgres 备份频率与保留份数 | ✅ **P2 关闭**。[架构 §8.5](../01design/01architecture.md) 已把它列为上线前必须落实的运维项，且 checkpoint 一丢中断任务就无法恢复 —— 备份在这里不只是数据保护 |
| 归档降冷 / 导出 | ❌ 依赖 MinIO，按 §2.1 在 P3 |
| 教师离职 / 毕业后的数据处置 | ❌ 依赖 P3 的用户模型 —— 现在连「谁的数据」都表达不了 |

**这是对 2026-08-06 那句话的修正，不是推翻它的用意**：不许无限往后滚仍然成立，只是「一并关闭」的期次分成了两半。

**已回填**（2026-08-07）：[架构 §6.5](../01design/01architecture.md) 已改成上表的分工。

---

## 3. 环境前提

与 P1 不同，**P2 的环境依赖全部是容器，没有宿主机改造**（P1 要装 gVisor、要重挂文件系统，那些是一次性的机器改造）。Postgres / Redis 直接进 [`deploy/compose.yml`](../../deploy/compose.yml)，`docker compose up` 即得。

**但开发机的内存要重算。**[架构 §4.4](../01design/01architecture.md) 的容量公式是按目标服务器 64GB 推的；开发机 31GB，本期又要多起两个常驻服务：

```
31 GB 总内存
 −  2 GB Postgres + Redis（开发机负载下够用，生产按 §4.4 的 4+2 配）
 −  2 GB 宿主机 OS 与开发工具
 = 约 27 GB，够跑十几个沙箱
```

`SANDBOX_MAX_CONTAINER` 在开发机上仍按 P1 的做法调低即可，**不影响本期任何一条验收** —— P2 验的是「挂了能不能恢复」，不是「能同时跑多少个」。

> **本期新增一条运维前提**（已写进 [架构 §8.5](../01design/01architecture.md)）：Postgres 的数据卷必须落在**宿主机的持久化卷**上，不能用匿名卷。否则 `docker compose down -v` 一次就把 checkpoint 全清了 —— 而那正是本期要保住的东西。

---

## 4. 验收标准

与 [P1 §4](./P1-plan.md) 同样的口径，**一条命令能跑完**。脚本沿用 P1 的分工：本期新增的判据进 `deploy/test/p2.sh`，P0 / P1 的回归由既有脚本转调。

```bash
make all                                     # 门禁全绿
docker compose -f deploy/compose.yml up -d   # nginx + api + worker×2 + broker + postgres + redis

bash deploy/test/p2.sh                       # 本期六条，转调 p1.sh 做回归
```

**通过条件**（六条全中才算完）：

1. **`kill -9` worker 后任务从 checkpoint 续跑** —— 这是[架构 §11](../01design/01architecture.md) 给 P2 定的原文标准。**要验的是「续跑」而不是「重跑」**：比对崩溃前后的工具调用次数与 token 消耗，已完成的步骤不应再花一次 token。只看「run 最终成功了」不算通过 —— 从头重来一遍也会成功。
2. **三个进程全部重启后，三样东西都还在** —— 会话历史（追问能接上上下文）、run 的终态（`GET /runs/{id}` 仍答得出）、事件流（`Last-Event-ID` 仍能补齐）。这三样正是本期要从内存里搬走的三样。
3. **两个 worker 副本并行时，任务不重复消费也不丢** —— consumer group 的 ack 与 pending 重投是自写的 200 行（[ADR-0005](../01design/adr/0005-task-queue-redis-streams.md) 明确了这笔债），必须实测。
4. **[P0 的验收四条](./P0-plan.md)经新架构全过** —— 事件流完整、agent 自写代码并执行、断线重连不重不漏、产物可取回。
5. **[P1 的六条](./P1-plan.md)不回归** —— 沙箱加固、broker 边界、SSE 心跳、结构化日志都不能因为多了两个存储和一次拆分而失效。
6. **事件 id 契约不变** —— 换成真 Redis Stream 之后，id 仍是 `{毫秒}-{序号}` 形状，前端解析与 `Last-Event-ID` 语义一个字不改（§1.2）。

> **一条要测量、不设门槛的观察项**：崩溃恢复时**工具有没有重复执行**。[ADR-0008](../01design/adr/0008-langgraph-checkpointer.md) 明确崩溃在工具执行途中会导致整节点重跑，而幂等键排在 P3。本期先把这个次数量出来，它是 §7 那项待决的输入 —— 不实测就定，是在猜。

---

## 5. 任务分解

六个步骤，**每步有独立的验证标准，未通过不进下一步**（[技术章程第四条](../../.claude/python-constitution.md)）。

```mermaid
flowchart LR
    S0["步骤零<br/>起 Postgres 与 Redis"] --> S1["步骤一<br/>checkpointer 落库"]
    S1 --> S2["步骤二<br/>run 元数据落库"]
    S2 --> S3["步骤三<br/>事件通道换 Streams"]
    S3 --> S4["步骤四<br/>拆 worker + 任务队列"]
    S4 --> S5["步骤五<br/>归档与保留策略"]
```

**先换存储、后拆进程**，理由与 [P1 的「先加固后拆分」](./P1-plan.md)完全一致：步骤一到三都在**现有的单进程里**完成，改完立刻能用 P0 的验收 case 验；步骤四才把已经验证过的东西劈成两个进程。反过来先拆再换，等于在跨进程环境里调试三种存储的接入，每次验证多一层间接。

### 步骤零：起 Postgres 与 Redis

| 项 | 内容 |
|---|---|
| 产出 | [`deploy/compose.yml`](../../deploy/compose.yml) 加两个服务（数据卷落宿主机持久化目录）；依赖用 `uv add` 记进 [`pyproject.toml`](../../app/pyproject.toml)；连接配置进 [`Settings`](../../app/config.py) |
| 依据 | 本文 §3、[架构 §4.4](../01design/01architecture.md) |
| 验证 | ① 两个服务起得来且数据卷在宿主机上看得到；② **连不上时进程启动即失败**，不是等到第一次查询才炸；③ `docker compose down && up` 后数据仍在 |

验证标准②不是形式主义：[`Settings`](../../app/config.py) 现在就是这个规矩（缺 `DEEPSEEK_API_KEY` 构造即抛），连接也该照办。一个「能启动但一查就 500」的进程，会让后面每一步的失败都多一个候选原因。

### 步骤一：checkpointer 落库

| 项 | 内容 |
|---|---|
| 产出 | `InMemorySaver` 换成 `AsyncPostgresSaver`，见 [`api/platform.py`](../../app/api/platform.py) 里那行标了「这笔债登记在 P2」的注释 |
| 依据 | [ADR-0008](../01design/adr/0008-langgraph-checkpointer.md)、[架构 §5.3](../01design/01architecture.md) |
| 验证 | ① 进程重启后，同一 thread 追问能接上上文（问「刚才那张图用的是哪几个行业」应答得出）；② `checkpoints` / `checkpoint_writes` 两张表由框架自动建出；③ P0 验收四条不回归 |

**这一步会暴露一个 P0 从未验过的东西**：会话历史到底存了什么、够不够支撑追问。P0 用 `InMemorySaver` 时同进程内也能追问，但没人验过跨重启。

**不要手工改 checkpointer 的表**（[架构 §6.2](../01design/01architecture.md) 明确写了）。表结构随 LangGraph 版本走，改了就等着下次升级时冲突。

### 步骤二：run 元数据落库

| 项 | 内容 |
|---|---|
| 产出 | `runs` 表 + Alembic 迁移（§7 定案）+ 一层仓储；`RunExecutor` 内存里的 dict 退役 |
| 依据 | [架构 §6.2 §5.4](../01design/01architecture.md)、本文 §2.2 |
| 验证 | ① 进程重启后 `GET /api/runs/{id}` 仍返回正确终态；② 四态流转与 [§5.4 状态机](../01design/01architecture.md)一致，没有多余状态；③ 崩溃时处于 `queued` / `running` 的 run 能被扫出来（[§6.2](../01design/01architecture.md) 的部分索引就是为这个建的） |

**建表走 Alembic**（§7 已定案）。本期只有两张表，用得着迁移工具的地方不多；选它是因为 P3 要加五张表并给 `runs` 补 `user_id`，那时再引入就得给已有数据补写第一版迁移，比现在做贵。

`tokens_cache_read` / `tokens_uncached` / `tokens_output` 三列照 [§6.2](../01design/01architecture.md) 建。P1 已经把这三个数算对了（[P1 §4.1](./P1-plan.md) 记了实测的波动），本期只是给它们一个落脚点。

### 步骤三：事件通道换 Redis Streams

| 项 | 内容 |
|---|---|
| 产出 | `EventLog` 的 Redis 实现：`XADD` 写、`XRANGE` 补历史、`XREAD BLOCK` 跟新的；`MAXLEN` 控内存 |
| 依据 | [ADR-0006](../01design/adr/0006-event-channel-streams-not-pubsub.md)、[架构 §5.2](../01design/01architecture.md) |
| 验证 | ① 事件 id 仍是 `{毫秒}-{序号}`，前端契约不变；② 断线重连不重不漏（P0 验收③）经 Redis 仍成立；③ 进程重启后，已产生的事件仍读得到；④ 超过 `MAXLEN` 后老事件被裁掉，而 `XRANGE` 的行为符合预期 |

**`follow` 的语义要一字不差地搬过去**：先补齐历史、再跟新的，直到终态事件结束流（见 [`run/log.py`](../../app/run/log.py) 的 `follow`）。这段逻辑 P0 已经用 SSE 断线重连验过，Redis 版要接受同一套测试 —— **测试不该因为换了实现而重写**，那正是 `EventLog` 这层抽象存在的意义。

**心跳留在 api 侧不动**（[`api/sse.py`](../../app/api/sse.py)）。它包的是事件流，不关心事件从哪来。

### 步骤四：拆 worker 进程 + 任务队列

**本期最大的一块。**

| 项 | 内容 |
|---|---|
| 产出 | 独立的 worker 入口；Redis Streams consumer group（`XADD` 投递 / `XREADGROUP` 消费 / `XACK` / `XAUTOCLAIM` 认领超时消息）；api 只投递不执行 |
| 依据 | [ADR-0005](../01design/adr/0005-task-queue-redis-streams.md)、[架构 §4.1 §4.2 §8.2](../01design/01architecture.md) |
| 验证 | ① `kill -9` worker 后任务从 checkpoint 续跑，且已完成的步骤不重花 token；② 两个 worker 副本不重复消费也不丢；③ api 重启不影响在跑的 run；④ P0 验收四条全过；⑤ 崩溃恢复时工具重复执行的次数被量出来（不设门槛，见 §4） |

**四个必须想清楚的点**：

- **`RunExecutor` 一分为二**。`submit` 留在 api（写 `runs` 行 + `XADD` 任务），`_drive` 及以下整体搬进 worker。两侧的交界就是那条任务消息，它该带什么字段要一次定清 —— 少一个字段，worker 就得回头查库。
- **ack 的时机**。太早（收到就 ack）等于放弃重投，崩溃即丢；太晚（跑完才 ack）则一次几十分钟的任务会一直占着 pending。[ADR-0005](../01design/adr/0005-task-queue-redis-streams.md) 把这几行点名为「自写的 200 行需要自己保证正确性」，是本步最容易写错的地方。
- **重投必然带来重复执行**。这不是 bug 而是至少一次投递的定义。checkpointer 挡掉了已完成节点的重跑，但挡不住「崩在工具执行途中」那一种（[ADR-0008](../01design/adr/0008-langgraph-checkpointer.md) 的「代价」一节写死了这条）。验收标准⑤要量的就是它。
- **租约记名**。worker 有了身份，broker 侧的租约可以按 worker 记；worker 死了就按名回收，不必等 [`_expire_lease`](../../app/sandbox/pool.py) 那个 30 分钟的超时。这是 [P1 §1.3](./P1-plan.md) 登记的那笔债。

### 步骤五：事件归档与保留策略

| 项 | 内容 |
|---|---|
| 产出 | Redis Stream 异步归档到 `run_events`；Stream 的 `MAXLEN` / TTL；checkpoint 的清理策略 |
| 依据 | [ADR-0006](../01design/adr/0006-event-channel-streams-not-pubsub.md)、[架构 §6.5](../01design/01architecture.md)、本文 §2.3 |
| 验证 | ① Stream 已被 `MAXLEN` 裁掉的历史，仍能从 Postgres 完整重放；② 保留期到点后旧数据真的被清，且清理任务本身可重跑；③ [§6.5](../01design/01architecture.md) 的两问在架构文档里被关掉，不是留个「已实现」了事 |

验证标准①是这一步的全部意义所在：Stream 裁剪与 Postgres 归档之间**只要有一点缝，教师翻历史就会看到一段空白**，而那段空白不会报错。归档滞后于裁剪的时间窗要算清楚，不能靠「一般来得及」。

---

## 6. 与 P0 / P1 的回归关系

P2 全程**不新增业务功能**，因此 P0 的验收四条与 P1 的六条都是贯穿始终的回归基线。

**回归跑几次、在哪几步跑**，照 [P1 §6](./P1-plan.md) 的教训安排：

| 步骤 | 跑什么 | 为什么这一步要跑 |
|---|---|---|
| 步骤一 | P0 四条 | checkpointer 换实现，会话状态的读写路径全变 |
| 步骤三 | P0 四条（重点验③断线重连） | 事件流的存储换了，`Last-Event-ID` 的语义最容易在这里悄悄变形 |
| 步骤四 | P0 四条 + P1 六条 | 进程拆分会同时打破两边的假设 |

**每次重跑都是真实调用 DeepSeek，有成本**。P1 实测单次约 30 万 token（[P1 §4.1](./P1-plan.md)），三次约 100 万 token 量级，是本期的已知开销。不要为省这笔钱压缩成一次 —— 三个步骤各自会以不同方式打破假设（状态读写、事件存储、进程边界），一次跑不出是哪一层的问题。

> P1 的六条只在步骤四跑一次即可：步骤一到三都不碰沙箱、不碰 broker。

---

## 7. 待决事项

**三项均已于 2026-08-07 关闭，可以开工。**

| 项 | 状态 |
|---|---|
| ~~**工具幂等键要不要提前到本期**~~ | **已关闭：先量后定。** 步骤四把「崩溃恢复后工具重复执行了几次」量出来（验收标准⑤，只测量不设门槛），据实测决定当期做还是留 P3。这是 P0 用探针定 `checkpoint_ns` 的老办法 —— 不实测就定，是在猜。<br>背景：[ADR-0014](../01design/adr/0014-tool-idempotency-key.md) 的去重排在 P3，但本期引入的重投机制正是它要防的场景（[ADR-0008](../01design/adr/0008-langgraph-checkpointer.md) 明确崩在工具执行途中会让整节点重跑），落点已于 P1 就位。<br>**若实测确实重复执行，当期就把它落到 broker** |
| ~~**建表方式：迁移工具还是幂等 DDL**~~ | **已关闭：本期就引入 Alembic。** 两张表时引入的成本最低；「等需要了再引入」意味着要给已有数据补写第一版迁移，那比现在做贵。P3 要加五张表并给 `runs` 补 `user_id`，届时会用上 |
| ~~**worker 副本数与 api 副本数**~~ | **已关闭：worker × 2、api × 1。** 副本数用在真正要验的地方（验收标准③的消费语义）。api 多副本要解决的是 SSE 连接与网关可用性，那是 P3 上认证与限流之后才谈得上的话题。<br>**代价明确接受**：api 重启期间 SSE 全断，靠前端的 `Last-Event-ID` 自动补齐 —— 而那条路径本期验收标准②要验 |
