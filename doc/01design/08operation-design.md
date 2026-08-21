# 运行与运维设计

| 项 | 值 |
|---|---|
| 上游 | [总体架构](./01architecture.md) |
| 相关设计 | [运行时与接口设计](./05runtime-design.md) · [数据设计](./06data-design.md) · [安全设计](./07security-design.md) |

本文记录容量模型、恢复策略、可观测性和部署前提。章节继续使用拆分前的 §8.x 编号，便于追溯历史引用；可执行命令以仓库根目录的 `AGENTS.md` 和 [`script/`](../../script/) 脚本为准。

---

## 部署拓扑与容量输入（承接原架构 §4.4）

平台以单机 Docker Compose 部署。常驻服务是 Nginx、API、Worker、Sandbox Broker、Postgres、Redis，**六个**。沙箱由 Broker 动态创建，不在 Compose 中静态声明。

> **2026-08-13 撤除七个服务**：OTel Collector、Tempo、Loki、Prometheus、Grafana 五个可观测性服务，以及 MinIO 与它的建桶任务。MinIO 是连带的 —— 产物存储在 `0009` 迁移就搬走了，此后它只剩 Tempo 与 Loki 两个用户。理由见 §8.3。

`pypi-mirror` 曾列在部署骨架中，始终未部署。P12 开放沙箱出网后也不需要它 —— 直接走公网镜像源（`SANDBOX_INDEX_URL`，默认清华源）。常用科学计算库和中文字体仍预装进沙箱镜像，省掉每会话重装。原因见[安全设计 §7.3.3](./07security-design.md)。

目标服务器的容量输入如下：

| 项 | 当前值 | 影响 |
|---|---|---|
| CPU | 32 核 | 单沙箱上限 1 核，CPU 与内存共同约束并发 |
| 内存 | 64 GB | 沙箱并发上限的主要输入 |
| 磁盘 | 容量充裕 | 不免除每 Thread 5 GB 配额与总量监控 |
| 网络 | 校园内网，Worker 可访问模型 API | 沙箱亦需出网装包（P12 起） |
| 访问 | 内网 IP，无域名 | 当前使用 HTTP，见 [ADR-0012](./adr/0012-plain-http-intranet.md) |

容量基线：

```text
64 GB 总内存
 − 约 14 GB 基础服务
 − 约  2 GB 宿主机
 = 约 48 GB 可分配给沙箱
 ÷     2 GB 单沙箱内存上限
 = 理论上限 24 个沙箱
```

24 个沙箱同时也消耗约 24 核，CPU 与内存的结论吻合。实际配置上限为 **20**，保留 4 个名额的余量，避免 OOM Killer 误杀 Postgres。

~~P4 新增的五个可观测性服务实测共占约 0.41 GB，落在上述基础服务估算的取整误差内，不改变结论。~~ 那五个服务与 MinIO 已于 2026-08-13 撤除，**基础服务的占用只减不增，结论同样不变** —— 沙箱上限仍是 20，不因此上调。腾出的约 0.5 GB 留作余量，而不是换成一个沙箱名额：上限本来就是按内存与 CPU 双约束取的整，多出半个 G 不足以让第 21 个沙箱站得住。

这组数值是当前部署输入，不是架构常量。服务器规格或真实负载变化时，按同一公式重算，并通过配置调整上限。

---

## 8.1 并发模型与容量

Agent run 是 **IO 密集**的 —— 绝大部分时间在等 LLM 返回。

因为所有 CPU 密集的计算（pandas / numpy / statsmodels）都跑在沙箱容器里，worker 只负责发起调用和等待结果，**worker 侧是纯 IO，不会阻塞 event loop**。这是引入沙箱带来的一个额外收益：worker 不需要 `ProcessPoolExecutor`，一个 asyncio 进程可以轻松管理几十个并发 run。

因此容量约束不在 worker，而在**沙箱容器数**：

```
最大并发活跃 thread 数 ≈ 宿主机可用内存 / 单沙箱内存上限(2GB)
```

按上方容量基线确认的 **32 核 / 64 GB** 实算：**理论上限约 24 个沙箱，建议配置为 20**。CPU 侧与内存侧结论吻合，两边同时到顶，没有一边先成为瓶颈。

对「同时在跑个位数到几十」的量级（[总体架构的用户范围](./01architecture.md)）够用，但**余量不算宽裕**。若实际活跃度高于预期，处置顺序是：先把单沙箱内存上限从 2GB 降到 1GB → 再扩服务器内存 → 最后才考虑多机。

> 这一结论依赖 [总体架构的用户范围](./01architecture.md) 中「学生 = 课题组研究生」的口径。若将来放开到全院学生，需重新评估。

**SandboxManager 需要实现**：容器数上限、LRU 回收、超限时排队等待、健康检查。

### 沙箱排队（2026-07-31 确认：排队，不直接拒绝）

沙箱数达到上限时，新的沙箱创建请求**进入队列等待**，而不是返回失败。设计如下：

| 项 | 取值 | 理由 |
|---|---|---|
| 排队位置 | sandbox-broker 内部，FIFO | broker 是唯一知道容器总数的组件（[总体架构的组件职责](./01architecture.md)），队列放在别处都要同步状态 |
| worker 侧行为 | `create` 调用异步挂起等待，不轮询 | worker 本就是纯 IO 等待模型（§5.6），多等一个 IO 不改变并发模型 |
| 前端反馈 | 事件流推 `sandbox.queued`，带当前排位 | 教师能看到「前面还有 N 个」，而不是界面卡住不动 |
| 等待上限 | 建议 10 分钟，超时则 run → `failed` | 无限等待会让 run 永远挂着，且占着配额 |
| 公平性 | 靠 §6.4 的 per-user 并发 run 上限保证 | 队列本身不做按用户加权 —— 单用户占满队列的问题应该在入口（配额）解决，而不是在队列里做复杂调度 |

**run 状态机不新增状态。** 「等沙箱」期间 run 仍是 `running`，只通过事件表达子状态。理由：这是个短暂的进程内状态，不值得持久化到 `runs` 表；且 worker 崩溃恢复后会从 checkpoint 重新请求沙箱、重新排队，本来就不需要恢复排队位置。

**`sandbox.queued` 在排位每次变化时推送**（2026-07-31 确认），而非只推一次。队列长度最多 20 量级（见上方容量基线），事件量可忽略，换来的是教师能看到队伍在动而不是一个静止的数字。该事件的 payload schema 归入 §5.2 的事件契约一并定义。

## 8.2 可用性与故障恢复

单机部署，不做多活；该边界来自当前用户规模和可用性优先级，见[总体架构 §2](./01architecture.md)与 [ADR-0001](./adr/0001-single-host-compose.md)。可用性依靠**快速恢复**而非**冗余**：

| 故障 | 影响 | 恢复方式 |
|---|---|---|
| worker 崩溃（进程退出） | 它手上的 run 全部中断 | Docker 按 `restart` 拉回；任务未 ack，pending 超时后由重启后的它自己 `XAUTOCLAIM` 认领，从 checkpoint 续跑（§5.3） |
| worker 卡死（进程还在，事件循环不转） | 任务照领但永不推进，且不会触发 `restart` | 进程内看门狗超时后结束进程，转成上一行那种情况（ADR-0018） |
| 网关崩溃 | SSE 连接断开 | 前端自动重连 + `Last-Event-ID` 补齐（§5.2）。**api 是单副本**，重启期间 SSE 全断，这是 P2 明确接受的代价 |
| sandbox-broker 崩溃 | 无法创建 / 执行沙箱 | 重启后需重建容器映射表；已有容器可依 label 恢复认领 |
| 沙箱容器崩溃 | 单个 thread 的执行失败 | 重建容器，workspace 从卷恢复（§5.5） |
| Postgres 故障 | **全局不可用**，且 checkpoint 丢失意味着中断任务无法恢复 | 无冗余。依赖备份恢复（§8.5）。**这是架构中最大的单点** |
| Redis 故障 | 任务与事件流中断 | 无冗余。重启后未 ack 任务可恢复，事件流丢失部分（已归档的除外） |

> **TODO** ｜ 待回答：Postgres 单点是否可接受？最低成本的改善是开启 WAL 归档 + 定期全备，能把 RPO 压到分钟级。是否需要做主从？
> 建议在 [总体架构的质量属性](./01architecture.md) 的可用性指标确定后再决定，不要提前投入。

## 8.3 可观测性

**现状：只剩结构化日志与账本两项，指标、链路追踪、日志集中收集与告警于 2026-08-13 整体撤除。**

### 8.3.1 还在的两项

- **结构化日志**（2026-08-06，P1）：进程日志输出成 JSON 行，`run_id` / `thread_id` / `user_id` 走 `contextvars` 自动带上，一次 run 的全部日志可按 `run_id` 过滤（[`app/log.py`](../../app/log.py)）。异常塞进同一行的 `exception` 字段 —— traceback 换行输出会把一条日志拆成十几行，逐行解析的工具在这里全部失败。**撤除可观测性没有动它一行**，它现在是唯一的排障入口：

  ```bash
  docker compose -f docker/compose.yml logs worker | jq -c 'select(.run_id == "…")'
  ```

- **token 计量**（2026-08-06，P1）：按 cache 命中拆分，口径见 §6.4，逐条落进 `runs.tokens_*`。**配额闸门读的就是它**（`quota/usage.py`），这条路完全在平台内，不依赖任何外部服务。

  > ~~**成本账本**：`GET /api/admin/usage` 按用户与时间聚合（`app/report/usage.py`）。~~ **同日（2026-08-13）一并撤除**，用量改到 Langfuse 上看，见 §8.3.3。**计量与账本是两件事，撤掉的只是后者** —— 数字仍在逐条落库。

### 8.3.2 撤掉了什么，以及撤掉之后失去了什么

| 撤掉的 | 原来解决什么 | 现在靠什么 | 代价 |
|---|---|---|---|
| **指标**（Prometheus + 三个抓取端点） | run 各态计数、队列积压、沙箱容器数与内存、LLM 延迟与失败率 | 无。查库能算出前两项，后两项**量不到了** | 「一次模型调用有多慢」只有调用发生那一刻测得到，事后查任何一张表都还原不出来 |
| **链路追踪**（OTel + Tempo） | 一个 run 跨 api / worker / broker / LLM 四段的耗时归因 | 日志里的时间戳，**要人工拼** | 跨进程那一跳（api → worker 隔着 Redis 队列）没有任何东西再把两侧串起来 |
| **日志集中收集**（Loki） | 跨容器按 `run_id` 检索 | `docker compose logs \| jq` | 只能查还在 Docker 日志轮转窗口内的；轮转出去就没了 |
| **告警**（Grafana Alerting → 飞书） | 四条规则：进程抓不到 / 模型失败率高 / 队列积压 / 沙箱名额将满 | 无。**故障要靠人发现或用户报障** | 这是撤除中最实的一项损失 |

**撤除的理由是减少在建期的复杂度**，不是这套东西没价值 —— 恰恰相反，[P4 §8.13](../03plan/P4-plan.md) 记着一次不跳任何一条的全量重跑照出三个真因，其中包括「磁盘配额从 P1 起就没生效过」。撤的是**当下**的维护面：五个容器、五个依赖、约 1500 行埋点与 750 行测试，以及每次重启都要先 `chown` 三个数据目录的启动前提。

**重新纳入的时机：上线前。** 上线意味着有真实教师在用、故障要靠人发现就来不及，而告警那一行正是为此存在的。届时要重做的不只是把代码找回来 —— 那时的系统比现在多了子智能体、外部 MCP 与 skill 三条链路，埋点面更大，见 [P6 决策 §12](../03plan/P6-decision.md)。

> **P9 的四处「必须实测」不受影响。** 逐条核对过：G6 读的是真跑一次拿到的 `astream` chunk，G7 对的是 `runs` 表与 DeepSeek 后台账单，G8 查的是 `aget_state`，G9 看的是抛出来的是哪一层的 `recursion_limit` —— **四处没有一处依赖 trace 或指标**。撤除不阻塞 P9。
>
> **真正被这次撤除改掉的是 F5（MCP 熔断告警）**，它原定「复用 P4 已接的飞书运维通道」，而那条通道没了。修订见 [P6 决策 F5](../03plan/P6-decision.md)。

### 8.3.3 Langfuse：同日接入，外部服务

**用量与 agent 链路改到 Langfuse 上看**（v4，自托管在同一台机器上，**不由本项目的 compose 编排**）。这与上面撤掉的那一套是两个决定：那套是平台自己的指标与 trace，这一套是 LLM 与 agent 专用的追踪。

| 项 | 取值 |
|---|---|
| 接入点 | 回调挂在**图**上而不是模型上（[`app/agent/trace.py`](../../app/agent/trace.py)）—— 挂模型只看得到「调了几次 LLM」，挂图才看得到节点、工具调用与中断，而 agent 出问题多半在工具那一段 |
| 归属 | `langfuse_session_id` = `thread_id`，`langfuse_user_id` = 提交人。**光对上这两个键还不够** —— 见下方那条 2026-08-16 的更正 |
| 开关 | `LANGFUSE_BASE_URL` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` **任缺其一即整个关掉**，并打一条日志说明。宁可没有追踪，也不要「配了一半、以为在记其实没记」 |
| compose | worker **与 api** 都要经 `host.docker.internal` 才够得着它（compose 里已配 `host-gateway`）。**填 `127.0.0.1` 或 `localhost` 连的是容器自己**，症状是 trace 一条不出现且没有报错，而 api 那侧的用量端点一律回 `available: false` |

> **2026-08-16 更正（P11）：这一节原来漏了一件事，而漏掉的那件让「谁花了多少」整整
> 三天答不出来。**
>
> `metadata` 里的两个键只让**根 span** 带上身份。`CallbackHandler` 确实也调
> `propagate_attributes`，但只在 `on_chain_start` 的 `parent_run_id is None` 那一支 ——
> 而 LangGraph 随后是在别的 async 任务里调模型的，根上进的 OTel 上下文传不进去。
>
> 后果：**token 全部落在没有主人的 `GENERATION` 上**。Langfuse 自己的按用户统计
> （`repositories/events.ts`）逐 event 行按 `e.user_id` 分组并且 `WHERE user_id` 非空，
> 于是那些行被整批滤掉 —— 按用户切出来每人都是 0，而每一步都返回 200。
> 实测：7,118,137 个 token 全记在 `userId = null` 那一行。
>
> **修法**：在 `agent/factory.py` 的 `_astream` 里，把整个 `graph.astream` 再包一层
> `propagate_attributes`。三条路径并排实测过 —— 裸模型调用本来就带得上，走图的带不上，
> 外层包一次之后带上了。**历史数据补不回来**（那个上下文管理器不追溯已存在的 span）。
>
> 另外两件同期查清的事：**v1 metrics 与 traces / sessions 三个端点在 v4 的
> `events_only` 模式下整个 404**（而它们的文档还活着）；**费用恒为 0 的真因是
> Langfuse 内置的 100 个模型价格里一个 deepseek 都没有**，`POST /api/public/models`
> 可以自己注册，脚本见 `script/register-model-price.sh`。

**两个必须知道的后果：**

1. **会话全文离开了平台的权限体系。** Langfuse 记完整 prompt 与 completion，谁能登录它谁就看得见全部会话内容 —— §6.3 那条「管理员看不到会话内容」在平台接口内仍成立，但**已不再是一条有效的保密边界**。详见 [§6.3.1](./06data-design.md) 与[风险登记 §10.2.3](./09risk-register.md)。
2. **它的 redis 与平台的 redis 都想绑 `127.0.0.1:6379`。** 两套栈同时起时后起的那个直接起不来（实测踩过）。**要同时跑就得有一方让开** —— 改哪一边都行，但别改成「每次手工挑一个起」，那种约定活不过两周。

**本项目的验收脚本不断言 Langfuse 收没收到 trace。** 它是外部服务，让门禁的绿依赖另一个项目起没起，是把一条本来可靠的判据变成偶发红的最快方式。要验就手工打开它看。

## 8.4 部署与发布

当前不做灰度、蓝绿或金丝雀发布。用户量小、停机窗口容易协调，直接 `docker compose up -d` 滚动重启即可 —— 前提是 §8.2 的崩溃恢复真的可靠，滚动发布本质上就是一次可控的崩溃。若学院提出不可停机要求，按[总体架构 §7](./01architecture.md)重新评估。

**Nginx 的 SSE 配置必须修改。** 默认配置会让流式输出全部卡住直到响应结束：

```nginx
location /api/runs/ {
    proxy_buffering off;          # 关键：关闭缓冲
    proxy_cache off;
    proxy_read_timeout 3600s;     # 长任务，不能用默认 60s
    proxy_set_header Connection '';
    proxy_http_version 1.1;
}
```

> **TODO** ｜ 待回答：CI/CD 方案。内网环境下代码怎么进来、镜像怎么构建与分发（见 §8.5 第三条）、配置与密钥怎么管理（LLM API key 不能进 git）。

## 8.5 内网部署需提前落实的运维项

- **Postgres 定时备份** —— checkpoint 丢失意味着中断的任务无法恢复。这不只是数据备份，也是功能可用性的一部分
- **Postgres 的数据卷必须落在宿主机的持久化目录，不能用匿名卷** —— 否则 `docker compose down -v` 一次就把 checkpoint 全清了，而那正是 P2 花整期保住的东西。这条在 P2 起 Postgres 的那一刻就要做对，事后迁移数据卷代价高
- ~~**MinIO 磁盘容量监控**~~ —— MinIO 已于 2026-08-13 撤除。**这条要盯的东西没有消失，只是换了地方**：产物与 P15 的 thread-local `.memory` 都在会话 workspace 里。[`script/workspace-report.sh`](../../script/workspace-report.sh) 必须统计整个 workspace，明确包含 `.memory` 的索引、正文、整理快照和临时文件；它们与代码、上传文件和产物共用该 thread 的 5 GB XFS 配额。脚本挂 cron，超水位退出码为 1（见 [ADR-0019](./adr/0019-thread-workspace-memory.md)）
- **已删 thread 的 workspace 要最终清理** —— thread 软删后立即拒绝记忆读写；对 `deleted_at` 超过 grace period 却仍有目录的 thread，清理任务须重试 purge，持续失败时记结构化错误并让 cron 非零退出，供当前巡检或上线后告警通道捕获。迟到的 run、memory job 和文件请求只能做无创建查找，不得在 purge 后重建目录（见 [P15 计划](../03plan/P15-plan.md)）
- **镜像分发方式** —— 内网可能拉不到 Docker Hub，需要私有 registry 或离线导入。**这一条容易被漏到上线当天才发现**
- **`/data/sandbox` 所在文件系统须为 XFS 且以 `prjquota` 挂载** —— §7.3.5 的磁盘配额依赖它，[ADR-0015](./adr/0015-sandbox-disk-quota-xfs.md)。挂载选项改动要重启，事后补代价高。**P4 起这已不是加固项而是硬启动依赖**：配额改成 fail-closed 之后，挂载不在时 broker 直接拒绝建会话（`POST /threads` 一律 500）。用 loop 设备造的挂载**重启后不会自动挂回来**
- **重挂之后必须让 broker 重启一次**（2026-08-10，P4）—— 容器的 bind mount 是在它**启动那一刻**解析的。重启后自动起来的 broker 绑的是「挂载还没回来」时那个被遮住的目录，而 `docker compose up -d` **不会重建它**（服务定义没变，compose 认为无事可做）。**症状与没挂一模一样**：实测宿主机看是 xfs、419 个会话目录，容器里看是 ext4、4 个。之前起来的沙箱容器同样绑着旧目录，一并清掉让 broker 重建
- **compose 部署要把承载 workspace 的块设备映射给 broker**（`SANDBOX_QUOTA_DEVICE`，2026-08-09，P4）—— broker 在容器里调 `xfs_quota`，而它要打开那个块设备；`CAP_SYS_ADMIN` 只是必要条件。loop 挂载每次挂载后可能换号，须现查：`findmnt -no SOURCE --target <workspace 根>`，`setup-xfs.sh` 结尾会直接报出来
- ~~**Prometheus / Grafana / Tempo / Loki 的数据目录须先建好并归运行用户**（2026-08-08，P4）~~ —— 四个服务已于 2026-08-13 撤除，这条启动前提随之消失。**但那个坑本身仍然成立**，将来任何一个以宿主用户跑、往 bind mount 里写的容器都会踩：Docker 自动创建缺失的目录时属主是 root，容器写不进去而反复重启，**`up -d` 那一刻是绿的**
- **沙箱运行用户的 uid/gid 须与 broker 进程对齐** —— 容器内代码写出的文件 broker 要能读写（[ADR-0016](./adr/0016-sandbox-filesystem-backend.md)）。不对齐会表现为「agent 写得进、读不出」，且症状不指向权限。**P0 探针已验证**：容器以 `--user $(id -u):$(id -g)` 运行时宿主侧读写正常
- **沙箱镜像须预装中文字体，容器须设 `HOME` 与 `MPLCONFIGDIR`** —— 见 §7.3.5 的预装清单。漏掉不会报错，只会让 agent 白跑几轮、并把告警混进执行结果
- **Redis 重启 = 全员重新登录**（2026-08-08，P3）—— session 存在 Redis（§7.2.2）。这不是故障，但运维要事先知道，否则一次例行重启会变成一片「怎么突然要重新登录」的报障
- **首个管理员由 `.env` 的 `ADMIN_NAME` / `ADMIN_PASSWORD` 在空库时建一次**（2026-08-08，P3）—— 之后再启动都不看它。**改过管理员口令之后不要把 `.env` 里那两项删掉再重建库**，那会让空库判定再次成立。凭据会出现在进程环境里（`docker inspect` 看得到），这是 §7.1 接受过的同一类判断
- **三个 cron 任务**（前两个 2026-08-08 P3，第三个 2026-08-09）—— `python -m store.retention`（事件与 checkpoint 的保留期，§6.5）、`python -m run.approval`（挂超过 24 小时的待审批转 `cancelled`，§5.4）、`python -m run.reaper`（库里还活着、队列里已没有的 run 转 `failed` 且 `retryable`）。三个都可重跑
- **收割器补的是崩溃恢复盖不住的那一半**（2026-08-09）—— worker 挂了靠 Redis 的 pending 列表接管（§5.3），但 ack 写在 worker 主循环的 `finally` 里、无条件执行，而执行器起跑阶段有几处调用落在它自己那圈 `try/except` 之外。那几处抛异常时消息被 ack 而状态没写终态，**此后没有任何东西会再碰这个 run**。判据是「队列里还有没有它」而不是「跑了多久」—— 后者会误杀一次正常的长分析。**收割成 `failed` 而不是重投**：收割器与 worker 是两个各跑各的进程，重投一条 worker 其实还认领得回来的消息，第二份的 `start()` 会撞上 `running → running` 拿到 `RESUMED` 而照跑不误，同一个 run 并发跑两遍、共用一个沙箱、写同一份 checkpoint

---
