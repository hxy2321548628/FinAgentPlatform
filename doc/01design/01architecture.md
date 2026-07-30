# 金融学院智能体平台 — 总体架构设计

> 状态：设计草案
> 日期：2026-07-29

---

## 1. 背景与已确定的约束

搭建面向金融学院教师的多用户智能体平台，核心能力是"与 AI 智能体对话，通过工具完成分析任务"。

技术栈方向已定：

- 前端 React
- 后端接口层 FastAPI
- 智能体 worker 使用 DeepAgents 框架，要求支持异步并发
- 事件驱动的异步 Agent 架构，支持长任务、中断恢复

已确认的三个前提（决定了下面很多选型）：

| 前提 | 取值 | 影响 |
|---|---|---|
| 规模 | 一个学院，几十到几百名教师 | 单机部署即可，不上 K8s / 队列分片 |
| 部署环境 | 学院/学校内网服务器 | 自建 Postgres/Redis/MinIO；LLM 出网通道需专门确认 |
| 代码执行 | 需要，agent 要能写并运行分析代码 | **必须自建沙箱**，这是架构中最重的一块 |

---

## 2. 规模判断与设计取舍

按一个学院几十到几百名教师估算，**同时在跑的 agent 任务大概率是个位数到几十**。在这个量级下，真正的瓶颈是 LLM API 的 rate limit、token 成本，以及沙箱容器占用的宿主机内存，**不是架构吞吐**。

因此本设计的取舍是：

- **架构按事件驱动设计** —— 这是必须的。长任务（一次分析可能跑几分钟到几十分钟）不能走 HTTP 请求-响应模型，必须异步提交 + 事件订阅。
- **但不提前上分布式** —— 不上 K8s、不做队列分片、不引入服务网格。单机 Docker Compose + 一个 Postgres + 一个 Redis 足够。
- **每一层保持无状态或可水平扩** —— 真撞到瓶颈时，加副本即可，不需要重构。

---

## 3. 总体分层 

```
                    React 前端
                        │
        HTTPS: REST(提交/查询/审批)  +  SSE(事件流)
                        │
                        ▼
        ┌───────────────────────────────────┐
        │   FastAPI 网关（无状态 · 多副本）     │
        │   认证 · 鉴权 · 限流配额 · 事件回放   │
        └───────────────────────────────────┘
             │            │              ▲
             │            │              │
        ┌────▼────┐  ┌────▼──────────┐   │
        │Postgres │  │Redis Streams  │   │
        │元数据 +  │  │ 任务队列        │   │
        │checkpoint│ │ + 事件日志 ────┼───┘
        └────▲────┘  └────┬──────────┘
             │            │ consumer group
             │            ▼
        ┌────┴───────────────────────────────┐
        │  Agent Worker 池（asyncio · 多副本）│
        │  DeepAgents / LangGraph CompiledGraph│
        └────┬───────────────────┬────────────┘
             │                   │
    ┌────────▼────────┐   ┌──────▼──────────┐
    │ sandbox-broker  │   │ LLM API         │
    │  ↓ docker.sock  │   │ (走出网代理)     │
    │ 沙箱容器池       │    └─────────────────┘
    └────────┬────────┘
             │ bind mount
        ┌────▼─────┐
        │ MinIO/S3 │  产物、文件归档
        └──────────┘
```

### 三条独立通道

| 通道 | 载体 | 职责 |
|---|---|---|
| **控制通道** | HTTP REST | 提交任务、取消、审批、查历史 |
| **任务通道** | Redis Streams + consumer group | 分发任务，至少一次投递，ack + pending 重投 |
| **事件通道** | 每个 run 一条 Redis Stream | Worker `XADD` 写入，网关 `XREAD` 转 SSE 推给前端 |

**关键设计：事件流必须持久化，不能用 Redis Pub/Sub。**

Pub/Sub 不持久，用户刷新页面或网络抖动，中间过程就永久丢失了。改用 Stream 做 per-run 的事件日志：前端 SSE 天然携带 `Last-Event-ID` 请求头，断线重连时从上次的 event id 继续读，中间产生的事件全部补齐。Stream 设 `MAXLEN` 或 TTL 控制内存，同时异步归档到 Postgres 做长期存储。

---

## 4. 沙箱层

Agent 要写并运行分析代码，内网部署又意味着数据不能交给外部托管的 code execution 服务，因此必须自建沙箱。

### 4.1 隔离方案选型

| 方案 | 隔离强度 | 运维成本 | 结论 |
|---|---|---|---|
| 裸 Docker | 弱（共享内核） | 低 | 仅作起步，必须配合加固 |
| **Docker + gVisor (runsc)** | 强（用户态内核拦截 syscall） | 低，基本是 `--runtime=runsc` 一行 | **推荐** |
| Firecracker microVM | 最强 | 高，需要 KVM + 镜像流水线 | 对本规模属于过度设计 |

用户是学院教师而非匿名公网用户，威胁模型主要是"agent 生成的代码写错了或失控"，而不是定向攻击。gVisor 的隔离强度绰绰有余，且几乎是 Docker 的 drop-in 替换 —— 先用裸 Docker 跑通流程，加固清单做完后再切 `runsc` runtime，改动量很小。

### 4.2 生命周期：per-thread 长驻，而非 per-call

Agent 会分多步执行代码（先 `pip install`，再读数据，再计算，再画图）。如果每次调用都开新容器，前一步装的包和写的文件全部丢失。

```
thread 首次需要执行代码 → 分配沙箱容器
    ↓
同一 thread 的后续代码调用复用该容器（包、文件、中间结果都在）
    ↓
idle 30 min 无调用 → 回收容器
    ↓
下次需要时重新创建，workspace 文件从卷恢复
```

### 4.3 文件持久化

让容器可以随时销毁重建，状态留在卷里：

```
沙箱容器 /workspace
    ↕ bind mount
宿主机 /data/sandbox/{thread_id}/
    ↕ 异步同步
MinIO tenant/{user_id}/thread/{thread_id}/
```

DeepAgents 的虚拟文件系统直接映射到这个 workspace。容器本身是无状态可抛弃的。

### 4.4 安全加固清单

逐条落到容器创建参数：

```
--runtime=runsc                  # gVisor
--network=none                   # 或自定义 bridge + iptables 白名单（见下）
--read-only                      # rootfs 只读，/tmp 挂 tmpfs
--cap-drop=ALL
--user=1000:1000                 # 非 root
--memory=2g --cpus=1
--pids-limit=128
--security-opt=no-new-privileges
+ 单次执行 wall-clock 超时（如 120s）
+ stdout/stderr 输出大小上限（防止把网关 OOM）
```

### 4.5 两个实际会踩的坑

**坑一：`--network=none` 会让 `pip install` 全部失败。**

Agent 一定会想装包。必须给沙箱配一个内网 pypi 镜像（清华/阿里源，或自建 devpi），网络策略从 `none` 改成"只允许访问镜像源 + 内网数据源"的白名单 bridge。

**坑二：不要把 `docker.sock` 挂进 worker 容器。**

那等于给 worker 宿主机 root 权限，worker 一旦被 agent 生成的代码影响就全线失守。改成一个独立的 **sandbox-broker** 服务持有 `docker.sock`，只暴露 `create / exec / destroy` 三个内部 API，worker 通过它间接操作。

### 4.6 Agent 侧的工具接口

```
execute_python(code)      → {stdout, stderr, artifacts[], exit_code}
read_file(path)
write_file(path, content)
list_files(path)
```

这些工具在 worker 进程里全部是 `async`，内部通过 HTTP 调用 sandbox-broker，**worker 只是在等 IO**。

---

## 5. 中断恢复

DeepAgents 构建在 LangGraph 之上：`create_deep_agent()` / `async_create_deep_agent()` 返回编译好的 LangGraph graph，并接受 `checkpointer` 参数（`async_create_deep_agent` 的区别是传 `is_async=True`，影响 SubAgentMiddleware 的工具执行与子 agent 调用方式）。

**因此中断恢复不需要自己造轮子** —— LangGraph 的 checkpointer（生产使用 `AsyncPostgresSaver`）已提供线程级的状态持久化与恢复。

但"中断恢复"实际上是三种不同语义，设计上必须分开处理：

| 类型 | 触发场景 | 机制 |
|---|---|---|
| **崩溃恢复** | worker OOM / 被 kill / 滚动发布 | 队列消息未 ack，pending 超时后重投给其他 worker；LangGraph 从最后一个 checkpoint 继续，已完成的步骤不重跑 |
| **人工介入 (HITL)** | agent 执行敏感操作前暂停等教师确认 | LangGraph `interrupt()` → 状态落盘，run 转 `waiting_approval`，worker 释放；批准后用 `Command(resume=...)` 重新入队 |
| **主动取消/暂停** | 教师点击"停止" | Redis 中打 cancel flag，worker 在 step 边界检查后抛 `CancelledError`；已写入的 checkpoint 保留，可从该点恢复 |

第二种是长任务平台的核心价值：**任务可以挂起数小时等人，期间不占用任何 worker 资源**。

### Run 状态机

```
                 ┌──────────────────┐
                 ▼                  │ resume
  queued ──→ running ⇄ waiting_approval
     ▲          │  ↘
     │          ▼    ↘
     │       succeeded  failed ──→ (retry) ──┐
     │                                        │
     └────────────────────────────────────────┘
                    │
                cancelled
```

---

## 6. 并发模型与容量

Agent run 是 **IO 密集**的 —— 绝大部分时间在等 LLM 返回。

因为所有 CPU 密集的计算（pandas / numpy / statsmodels）都跑在沙箱容器里，worker 只负责发起调用和等待结果，**worker 侧是纯 IO，不会阻塞 event loop**。这是引入沙箱带来的一个额外收益：worker 不需要 `ProcessPoolExecutor`，一个 asyncio 进程可以轻松管理几十个并发 run。

新的容量约束变成了沙箱容器数：

```
最大并发活跃 thread 数 ≈ 宿主机可用内存 / 单沙箱内存上限(2GB)
```

64GB 内存的服务器约支持 25-30 个同时活跃的沙箱。对"几十到几百名教师，同时在跑个位数到几十"的量级，单机完全够用。

**SandboxManager 需要实现**：容器数上限、LRU 回收、超限时排队等待、健康检查。

---

## 7. 技术选型与权衡

### 7.1 任务队列：Redis Streams（自写 consumer）或 ARQ

**不建议 Celery。** Celery 5 仍以 prefork 为主，对 asyncio 的支持很别扭，与"异步并发 agent worker"的需求正面冲突。

推荐 Redis Streams + consumer group 自写消费循环（约 200 行；Redis 本来就要用于事件流，不引入新组件），或使用 ARQ（Redis + asyncio 原生，更轻量）。

**理由**：真正的状态在 LangGraph checkpointer 中，队列只负责"分发 + 至少一次投递 + 失败重投"，职责很轻，选型压力小。将来若需要更强的可靠性保证或跨机房，再换 NATS JetStream / RabbitMQ 也不困难。

### 7.2 实时通信：SSE 而非 WebSocket

Agent 场景约 95% 是服务端单向推流（token、工具调用、中间步骤），客户端交互（中断、审批、追问）频率极低，走普通 POST 即可。

SSE 的优势：协议简单、自带断线重连与 `Last-Event-ID`、走标准 HTTP 对 Nginx 与校园网代理友好。WebSocket 只有在需要高频双向通信时才值得那份复杂度。

### 7.3 存储

| 组件 | 用途 |
|---|---|
| **Postgres** | 用户、会话、run 元数据、事件归档，以及 LangGraph checkpoint 表（`AsyncPostgresSaver` 自动建表） |
| **Redis** | 任务队列、事件流、取消标志、分布式限流 |
| **MinIO** | 沙箱 workspace 归档、分析产物（图表、Excel、报告）。路径按租户前缀隔离 |

### 7.4 模型

默认 **deepseek-v4-pro**，开启 thinking，`effort` 先设 `high` 再按实际路由压测调整。金融分析这类多步推理任务，effort 的收益比换用小模型明显。意图分类等辅助调用可下沉到 `deepseek-v4-flush` 以控制成本。

模型接入层需做成可替换：若后续因保密要求转为内网私有化部署，只替换该层，不影响上层设计。

---

## 8. 数据模型草案

```
users          (id, name, role, quota_tokens, quota_concurrent, ...) (RBCA角色)
threads        (id, user_id, title, agent_config, created_at)      -- 会话
runs           (id, thread_id, status, checkpoint_id, error,
                started_at, ended_at)                              -- 一次执行
run_events     (run_id, seq, type, payload, ts)                    -- 事件归档
artifacts      (id, run_id, s3_key, mime, size)                    -- 产物
sandboxes      (thread_id, container_id, status, last_active_at)   -- 沙箱状态
-- checkpoints / checkpoint_writes 由 AsyncPostgresSaver 自建
```

**多租户隔离**：`thread_id` 强绑 `user_id`，所有查询在 repository 层统一注入 `user_id` 过滤（或直接启用 Postgres RLS）。不要指望每个接口都记得加 where 条件。

**配额**：LLM 调用是真实成本。至少需要 per-user 的 token 日配额 + 并发 run 数上限，否则单个用户就能占满整个 worker 池和沙箱池。

---

## 9. 部署形态（内网单机）

```yaml
# docker-compose.yml 骨架
services:
  nginx:            # 反向代理，SSE 配置见下
  api:              # FastAPI × 2
  worker:           # Agent Worker × 2~4
  sandbox-broker:   # 唯一持有 docker.sock 的服务
  postgres:         # 元数据 + LangGraph checkpoint
  redis:            # 任务队列 + 事件流
  minio:            # 产物与文件归档
  pypi-mirror:      # devpi，供沙箱装包（也可指向校内已有镜像）
```

### Nginx 的 SSE 配置必须修改

默认配置会让流式输出全部卡住直到响应结束：

```nginx
location /api/runs/ {
    proxy_buffering off;          # 关键：关闭缓冲
    proxy_cache off;
    proxy_read_timeout 3600s;     # 长任务，不能用默认 60s
    proxy_set_header Connection '';
    proxy_http_version 1.1;
}
```

### 内网部署需提前落实的运维项

- **Postgres 定时备份** —— checkpoint 丢失意味着中断的任务无法恢复
- **MinIO 磁盘容量监控**
- **镜像分发方式** —— 内网可能拉不到 Docker Hub，需要私有 registry 或离线导入

---

## 10. 待确认事项

### 10.1 出网通路开通（阻塞项）

主模型已确定走公有云 API，内网服务器必须能访问 `api.deepseek.com`。这不再是选型问题，而是**平台能否运行的硬前提**：

| 情况 | 影响 |
|---|---|
| **有出网代理** | worker 配 `HTTPS_PROXY` 即可，无额外工作 |
| **需过审批 / 走专线** | 立即启动流程。这类审批耗时通常长于开发本身，拖到最后会直接卡住上线 |
| **完全不能出网** | 当前方案不成立，需回到章程重新评审主模型约束，转为内网私有化部署 |

沙箱的网络策略是独立的：沙箱本身保持零出网，模型调用发生在 worker 侧，不经过沙箱。

### 10.2 内网服务器配置

CPU / 内存 / 磁盘规格未确认。内存直接决定沙箱并发上限

---

## 11. 落地路线

| 阶段 | 内容 | 验证标准 |
|---|---|---|
| **P0** | FastAPI in-process 跑 DeepAgents + **裸 Docker 沙箱**（先跑通，加固后置）+ SSE 流式输出 | 教师能对话；agent 能写 Python 读 CSV、算出结果并返回图表 |
| **P1** | 沙箱加固（gVisor + 完整参数）+ sandbox-broker 拆分 + 生命周期管理 | 沙箱内运行 `while True` / fork 炸弹 / 写满磁盘，宿主机不受影响 |
| **P2** | 拆分 worker：Redis Streams + Postgres checkpointer | `kill -9` worker 后，任务能从 checkpoint 恢复继续 |
| **P3** | HITL 审批 + 取消 + 多用户隔离 + 配额限流 | 审批流程走通；30 并发压测不崩溃、不串数据 |
| **P4** | 可观测性（OpenTelemetry）、产物存储完善、成本看板 | 能定位单个 run 的完整 trace 与 token 花费 |

### 关于 P0 与 P1 的顺序

刻意把安全加固放在 P1 而非 P0：先用裸 Docker 快速验证"agent 能否真的写出有用的分析代码"这个最大的不确定性，再投入时间做加固。若 P0 发现效果不达预期，加固工作就是白做的。

但 **P1 不能省** —— 上线前必须完成。

同样，P0 不要跳过直接做分布式：如果 agent 本身效果不行，队列和 checkpoint 都是无用功。

