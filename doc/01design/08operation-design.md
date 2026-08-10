# 运行与运维设计

| 项 | 值 |
|---|---|
| 上游 | [总体架构](./01architecture.md) |
| 相关设计 | [运行时与接口设计](./05runtime-design.md) · [数据设计](./06data-design.md) · [安全设计](./07security-design.md) |

本文记录容量模型、恢复策略、可观测性和部署前提。章节继续使用拆分前的 §8.x 编号，便于追溯历史引用；可执行命令以仓库根目录的 `AGENTS.md` 和 [`deploy/`](../../deploy/) 脚本为准。

---

## 部署拓扑与容量输入（承接原架构 §4.4）

平台以单机 Docker Compose 部署。常驻服务包括 Nginx、API、Worker、Sandbox Broker、Postgres、Redis、MinIO，以及 OTel Collector、Tempo、Loki、Prometheus、Grafana。沙箱由 Broker 动态创建，不在 Compose 中静态声明。

`pypi-mirror` 曾列在部署骨架中，但本期未部署：沙箱保持 `--network=none`，常用科学计算库和中文字体预装进沙箱镜像。原因见[安全设计 §7.3.3](./07security-design.md)。

目标服务器的容量输入如下：

| 项 | 当前值 | 影响 |
|---|---|---|
| CPU | 32 核 | 单沙箱上限 1 核，CPU 与内存共同约束并发 |
| 内存 | 64 GB | 沙箱并发上限的主要输入 |
| 磁盘 | 容量充裕 | 不免除每 Thread 5 GB 配额与总量监控 |
| 网络 | 校园内网，Worker 可访问模型 API | 沙箱仍然零出网 |
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

24 个沙箱同时也消耗约 24 核，CPU 与内存的结论吻合。实际配置上限为 **20**，保留 4 个名额的余量，避免 OOM Killer 误杀 Postgres。P4 新增的五个可观测性服务实测共占约 0.41 GB，落在上述基础服务估算的取整误差内，不改变结论。

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
| worker 崩溃 | 该 worker 上的 run 中断 | 任务未 ack，pending 超时后重投；从 checkpoint 续跑（§5.3） |
| 网关崩溃 | SSE 连接断开 | 多副本 + 前端自动重连 + `Last-Event-ID` 补齐（§5.2） |
| sandbox-broker 崩溃 | 无法创建 / 执行沙箱 | 重启后需重建容器映射表；已有容器可依 label 恢复认领 |
| 沙箱容器崩溃 | 单个 thread 的执行失败 | 重建容器，workspace 从卷恢复（§5.5） |
| Postgres 故障 | **全局不可用**，且 checkpoint 丢失意味着中断任务无法恢复 | 无冗余。依赖备份恢复（§8.5）。**这是架构中最大的单点** |
| Redis 故障 | 任务与事件流中断 | 无冗余。重启后未 ack 任务可恢复，事件流丢失部分（已归档的除外） |

> **TODO** ｜ 待回答：Postgres 单点是否可接受？最低成本的改善是开启 WAL 归档 + 定期全备，能把 RPO 压到分钟级。是否需要做主从？
> 建议在 [总体架构的质量属性](./01architecture.md) 的可用性指标确定后再决定，不要提前投入。

## 8.3 可观测性

> ~~**TODO** ｜ 待回答：本节整体待设计，规划在 P4 落地（[实施计划基线](../03plan/CLAUDE.md)）~~
> **已于 2026-08-10 全部关闭**（[P4 计划](../03plan/P4-plan.md)，验收八条全过）。四项分两批落地：日志与 token 计量按当初的优先级判断前移到了 P1，其余三项在 P4。

**先落地的两项**（2026-08-06，P1）：

- **结构化日志**：进程日志输出成 JSON 行，`run_id` / `thread_id` 走 `contextvars` 自动带上，一次 run 的全部日志可按 `run_id` 过滤（[`app/log.py`](../../app/log.py)）。异常塞进同一行的 `exception` 字段 —— traceback 换行输出会把一条日志拆成十几行，逐行解析的工具在这里全部失败。
- **token 计量**：按 cache 命中拆分，口径见 §6.4；契约见 §5.2 的 `run.finished`。

**其余三项**（2026-08-10，P4）。选型是 OTel Collector + Tempo + Loki + Prometheus + Grafana，**trace 与日志都以 MinIO 为后端**（论证见 [P4 §7.1 §7.2](../03plan/P4-plan.md)：装全套而非轻量方案，实测五个服务共占 **0.41 GB**，见上方容量基线）：

| 项 | 落地形态 | 在哪 |
|---|---|---|
| **指标** | 三个抓取端点，**谁独有的观测位置谁答**：api 答平台状态（run 各态计数、队列积压、当日 token），broker 答沙箱容器数与内存（唯一持有 `docker.sock`），worker 答 LLM 延迟与失败率（唯一调模型） | `deploy/prometheus.yml` |
| **链路追踪** | 一个 run 的 trace 跨 api / worker / broker / LLM 四段。整条链路上**只有 api → worker 那一跳要手接** —— 中间隔着 Redis 队列，没有请求头可放 traceparent | `app/telemetry/` |
| **成本看板** | `GET /admin/usage` 按用户与时间聚合。**账本与闸门分开放**：`report/usage.py` 跨用户聚合，`quota/usage.py` 永远带 `user_id` —— 后者刻意不提供「不带 user 也能查」的入口，多租户最常见的越权来源就是某个接口忘了加 where 条件。**呈现层不在本文登记**：P4 期配过一个 nginx 直接托管的单文件运维页（`deploy/web/usage.html`），现已移除 | `app/report/usage.py` |
| **日志集中收集** | 走 OTLP 从进程直接发，**不扒容器 stdout**（扒 stdout 要给采集器挂 `/var/lib/docker/containers`，等于开一道本不需要的口子）。顺带把 trace 与日志接上了：OTel 的 handler 把当前 span 的 `trace_id` 写进每条日志。stdout 那一路原样保留，Loki 挂了不影响 `docker logs` 排障 | `app/telemetry/log.py` |

**「能定位」落在两个具体页面上**，不是「日志里都有，自己 grep」：Grafana 的「平台概览」（六个指标）与「按 run 查链路」（填一个 `run_id` 得到它各段耗时与 token 三元组），看板定义在 [`deploy/grafana/dashboard/`](../../deploy/grafana/dashboard/)。

**告警走 Grafana Alerting → 飞书自定义机器人**，四条规则，选择标准只有一个：**对应「教师会直接感受到的故障」**（有进程抓不到了 / 模型调用失败率偏高 / 队列积压不消 / 沙箱名额快用完了）。一条没人会因此做任何事的告警，只会训练大家忽略这个群。阈值都是偏松的初值，**攒够真实运行数据再收紧**。

> **`/metrics` 不要求登录，挡它的是 nginx 一行 `return 404`。** Prometheus 没有会话，给它发一份长期凭据只是把同一个问题换个地方放；而响应里带着用户名与他今天烧掉的 token，与成本看板同一份数据。Prometheus 在 compose 网络里直连 `api:8000`，走不到 nginx。

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
- **MinIO 磁盘容量监控** —— 产物只增不减，**且 §6.5 定案不设保留期**（2.5 GB/年，删了拉不回来）。因此这条监控是唯一的兜底，不要指望有一个清理任务在后面接着
- **镜像分发方式** —— 内网可能拉不到 Docker Hub，需要私有 registry 或离线导入。**这一条容易被漏到上线当天才发现**
- **`/data/sandbox` 所在文件系统须为 XFS 且以 `prjquota` 挂载** —— §7.3.5 的磁盘配额依赖它，[ADR-0015](./adr/0015-sandbox-disk-quota-xfs.md)。挂载选项改动要重启，事后补代价高。**P4 起这已不是加固项而是硬启动依赖**：配额改成 fail-closed 之后，挂载不在时 broker 直接拒绝建会话（`POST /threads` 一律 500）。用 loop 设备造的挂载**重启后不会自动挂回来**
- **重挂之后必须让 broker 重启一次**（2026-08-10，P4）—— 容器的 bind mount 是在它**启动那一刻**解析的。重启后自动起来的 broker 绑的是「挂载还没回来」时那个被遮住的目录，而 `docker compose up -d` **不会重建它**（服务定义没变，compose 认为无事可做）。**症状与没挂一模一样**：实测宿主机看是 xfs、419 个会话目录，容器里看是 ext4、4 个。之前起来的沙箱容器同样绑着旧目录，一并清掉让 broker 重建
- **compose 部署要把承载 workspace 的块设备映射给 broker**（`SANDBOX_QUOTA_DEVICE`，2026-08-09，P4）—— broker 在容器里调 `xfs_quota`，而它要打开那个块设备；`CAP_SYS_ADMIN` 只是必要条件。loop 挂载每次挂载后可能换号，须现查：`findmnt -no SOURCE --target <workspace 根>`，`setup-xfs.sh` 结尾会直接报出来
- **Prometheus / Grafana / Tempo / Loki 的数据目录须先建好并归运行用户**（2026-08-08，P4）—— Docker 自动创建缺失的 bind mount 目录时属主是 root，而这几个容器以宿主用户跑。不建的话它们会因为写不进去反复重启，**而 `up -d` 那一刻是绿的**
- **沙箱运行用户的 uid/gid 须与 broker 进程对齐** —— 容器内代码写出的文件 broker 要能读写（[ADR-0016](./adr/0016-sandbox-filesystem-backend.md)）。不对齐会表现为「agent 写得进、读不出」，且症状不指向权限。**P0 探针已验证**：容器以 `--user $(id -u):$(id -g)` 运行时宿主侧读写正常
- **沙箱镜像须预装中文字体，容器须设 `HOME` 与 `MPLCONFIGDIR`** —— 见 §7.3.5 的预装清单。漏掉不会报错，只会让 agent 白跑几轮、并把告警混进执行结果
- **Redis 重启 = 全员重新登录**（2026-08-08，P3）—— session 存在 Redis（§7.2.2）。这不是故障，但运维要事先知道，否则一次例行重启会变成一片「怎么突然要重新登录」的报障
- **首个管理员由 `.env` 的 `ADMIN_NAME` / `ADMIN_PASSWORD` 在空库时建一次**（2026-08-08，P3）—— 之后再启动都不看它。**改过管理员口令之后不要把 `.env` 里那两项删掉再重建库**，那会让空库判定再次成立。凭据会出现在进程环境里（`docker inspect` 看得到），这是 §7.1 接受过的同一类判断
- **三个 cron 任务**（前两个 2026-08-08 P3，第三个 2026-08-09）—— `python -m store.retention`（事件与 checkpoint 的保留期，§6.5）、`python -m run.approval`（挂超过 24 小时的待审批转 `cancelled`，§5.4）、`python -m run.reaper`（库里还活着、队列里已没有的 run 转 `failed` 且 `retryable`）。三个都可重跑
- **收割器补的是崩溃恢复盖不住的那一半**（2026-08-09）—— worker 挂了靠 Redis 的 pending 列表接管（§5.3），但 ack 写在 worker 主循环的 `finally` 里、无条件执行，而执行器起跑阶段有几处调用落在它自己那圈 `try/except` 之外。那几处抛异常时消息被 ack 而状态没写终态，**此后没有任何东西会再碰这个 run**。判据是「队列里还有没有它」而不是「跑了多久」—— 后者会误杀一次正常的长分析。**收割成 `failed` 而不是重投**：worker 是多副本，两边同时回扫重投会让第二个 worker 的 `start()` 撞上 `running → running` 拿到 `RESUMED` 而照跑不误，同一个 run 并发跑两遍、共用一个沙箱、写同一份 checkpoint

---
