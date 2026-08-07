# P3 实施计划

| 项 | 值 |
|---|---|
| 文档状态 | **草稿，§7 待决未关闭，不可开工** |
| 当前版本 | v0.1 |
| 作者 | hxy |
| 日期 | 2026-08-08 |
| 上游文档 | [总体架构设计](../01design/01architecture.md) · [P2 实施计划](./P2-plan.md) |

### 版本历史

| 版本 | 日期 | 修改人 | 说明 |
|---|---|---|---|
| v0.1 | 2026-08-08 | hxy | 初稿。P2 已于同日验收六条全过，本文覆盖「谁在用、能用多少、人能不能插手」这条能力线 |

> **本文档的职责**：回答 **「P3 具体怎么做、做到什么程度算完」**。
>
> **不回答**「为什么账号自建而不接学校统一认证」（在 [ADR-0010](../01design/adr/0010-self-hosted-accounts-rbac.md)）、「为什么用 Cookie Session 而不是 JWT」（在 [ADR-0011](../01design/adr/0011-cookie-session-not-oauth2.md)）、「幂等键为什么用 `(thread_id, checkpoint_ns)`」（在 [ADR-0014](../01design/adr/0014-tool-idempotency-key.md)）。本文只给相对链接，不复制正文。

---

## 1. P3 的边界

**目标**（[架构 §11](../01design/01architecture.md)）：HITL 审批 + 取消 + 多用户隔离 + 配额限流 + 工具幂等键。

四期一句话：**P0 回答「agent 好不好用」，P1 回答「不可信代码跑在这台机器上安不安全」，P2 回答「这台机器上的东西挂了会怎样」，P3 回答「谁在用、能用多少、人能不能插手」。**

现在的答案是三个「没有」：没有用户（`runs.user_id` 是一列空值，谁都能读谁的 run），没有闸门（token 有计量口径但没有上限），没有插手的余地（run 一旦提交就只能等它自己跑完或失败）。

### 1.1 与前三期最大的不同：这一期有真正的未知

[P1 §1](./P1-plan.md) 与 [P2 §1](./P2-plan.md) 都写着同一句话 ——「**没有未知，只有工作量**」：选型在 ADR 里论证完了，要做的是把已定的方案落到代码里。

**P3 不是。** 架构文档里有四个 `TODO` 至今悬着，全都落在本期范围内：

| 悬着的问题 | 位置 | 为什么还没定 |
|---|---|---|
| 到底哪些操作需要审批 | [§5.3](../01design/01architecture.md) | 全量拦 `execute` 会让平台没法用（P0 实测一次分析要点十几次确认）；条件拦截的谓词写什么，要看真实行为模式 |
| 配额数值、超额行为、重置周期 | [§6.4](../01design/01architecture.md) | 只有一个样本（31 万 token 的单次分析），推不出日配额 |
| 限流阈值与算法 | [§7.5](../01design/01architecture.md) | 同上，没有真实请求分布 |
| 组内共享的 skill / 提示词表要不要预留 | [§6.2](../01design/01architecture.md) | 架构自己倾向不预留 |

**四个问题的输入是同一样东西：真实使用数据。而平台至今没有真实用户** —— 没有前端，只能 curl，所有实测样本都是验收脚本跑出来的同一个 case。

这构成本期最大的结构性风险，处理办法写在 §7.2：**把「机制」与「数值」分开做**，机制本期落地并可配置，数值留空并标注来源。

### 1.2 做什么

| 范围 | 依据 |
|---|---|
| `users` / `groups` / `user_groups` / `threads` 四张表 | [架构 §6.2](../01design/01architecture.md) |
| 认证：HttpOnly Cookie + Redis Session，`/auth/login`、`/auth/logout`、`/auth/me` | [架构 §7.2.2](../01design/01architecture.md)、[ADR-0011](../01design/adr/0011-cookie-session-not-oauth2.md) |
| 授权与隔离：**在数据访问层注入 `user_id` 过滤**，越权返 404 | [架构 §6.3 §5.7](../01design/01architecture.md) |
| 配额：token 日配额（按未命中加权）+ 并发 run 上限，**按角色分级** | [架构 §6.4](../01design/01architecture.md) |
| 限流：接口层 Redis 分布式计数，三个 429 用 `code` 区分 | [架构 §7.5 §5.7](../01design/01architecture.md) |
| 主动取消：Redis cancel flag + `cancelled` 态 + `run.cancelled` 事件 | [架构 §5.3 §5.4](../01design/01architecture.md) |
| HITL 审批：`interrupt` → `waiting_approval` → `Command(resume=…)` | [架构 §5.3 §5.7](../01design/01architecture.md) |
| 工具幂等键：broker 按 `(thread_id, checkpoint_ns)` 去重 | [架构 §5.6](../01design/01architecture.md)、[ADR-0014](../01design/adr/0014-tool-idempotency-key.md) |
| 沙箱租约记名（P1 遗债） | [P1 §1.3](./P1-plan.md)、[P2 §8.2](./P2-plan.md) |

### 1.3 前几期已经就位、本期不重做的部分

**事件契约早就留好了位置。**[`event/model.py`](../../app/event/model.py) 的 `EventType` 里 `run.cancelled` 与 `interrupt` 两个名字**从 P0 起就在清单里**，那段 docstring 明写「枚举列全清单是为了让前端有一份完整的类型表，但不是每种都已有对应的事件模型 —— 模型随各步骤落地时才添加」。`RunStatus` 的 docstring 也点名了「`cancelled` 与 `waiting_approval` 要等那两项落地」。**本期是填实现，不是改契约** —— 与 P2 处理事件 id 的原则一致。

`interrupt` 的 payload 已按 P0 探针实测在[架构 §5.2](../01design/01architecture.md) 定死，本期照抄即可，不需要再探。

**`runs.user_id` 列已经建好**（[`migration/version/0001_runs.py`](../../app/migration/version/0001_runs.py)），连 `ix_runs_user_started` 索引都在。P2 建表时刻意留的空列，本期只填值，不加列不改索引。

**token 按 cache 拆分的口径 P1 就落地了**，`runs` 表的三列一直在记数。配额要做的是加一道闸，不是重做计量。

**Alembic 在 P2 就引入了**，[P2 §7](./P2-plan.md) 定案时给的理由原文就是「P3 要加五张表并给 `runs` 补 `user_id`，那时再引入就得给已有数据补写第一版迁移」。这笔预付款本期兑现。

**broker 已经拆出来了**，幂等键的落点就位 —— [P1 §1.3](./P1-plan.md) 登记这笔债时写的是「broker 拆分后落点已就位」。

### 1.4 明确不做

**不是遗漏，是分期。**延续 [P2 §1.3](./P2-plan.md) 的登记方式，每条写明由哪一期偿还。

| 不做 | 后果 | 由哪期偿还 |
|---|---|---|
| MinIO 产物存储、`artifacts` 表、workspace 归档回收 | 产物仍从 workspace 直接读，workspace 仍只增不减 | **本期建议退回 P4，见 §7.1**（P2 §2.1 曾定案移到 P3，与架构 §11 的 P4「产物存储完善」冲突） |
| 组内共享的 skill、自定义系统提示词、MCP 接入 | `groups` 表建了但组内共享无内容 | [架构 §1.2](../01design/01architecture.md) 本就不在范围内。**本期只建组织结构，不建共享资源** |
| 提示词工程、子 agent 划分、效果评测 | 智能体好不好用仍只有一个 case 的证据 | **仍无期次** —— [架构 §10.3](../01design/01architecture.md) 明写「平台的价值完全取决于智能体好不好用，这块债只是被安排了，不是被还了」 |
| 前端 | 仍只能 curl 验收；而本期的审批、配额提示、越权提示全是给人看的 | **仍未排期**。[P2 §1.3](./P2-plan.md) 已经点名「这条不该继续无主地挂着」，本期它变得更刺眼，见 §7.3 |
| `sandboxes` 表 | — | **大概率永远不需要**，[架构 §6.2](../01design/01architecture.md) 已说明理由 |
| Postgres 主从 | 仍是单点 | [架构 §8.2](../01design/01architecture.md) 待定 |
| 可观测性指标、链路追踪、成本看板 | 只有结构化日志与 token 数 | P4 |
| 测试与业务共用同一个 Postgres 库 | 测试数据混进业务表 | [P2 §8.3](./P2-plan.md) 登记，本期顺手做掉（步骤零要动迁移，成本最低） |

---

## 2. 三处与上游文档不一致，本期定案

### 2.1 `threads` 表建起来之后，「会话存不存在」有两个真相源

**冲突**：现在会话**等同于** workspace 目录，存在性判断走 broker 的 `GET /threads/{id}/exists`（[`sandbox/remote.py`](../../app/sandbox/remote.py)）。建了 `threads` 表之后，同一个问题有两个答案，而两者会分叉 —— 目录被误删、或建表成功但建目录失败。

**定案：表是权威，目录是它的副产品。**

- api 侧一律查表，`/exists` 不再被 api 调用；
- broker 的 `/exists` 保留，但降级为 broker 内部判断（它管容器与目录，本来就该有自己的视角）；
- 建会话是**先落表、后建目录**，与 [P2 的 `RunSubmitter`](../../app/run/submitter.py) 同一顺序原则（先落库再产生副作用）。目录建失败则整体失败，不留半个会话。

**理由**：多租户隔离的过滤条件长在表上（§6.3），而目录没有归属信息。让目录当权威，等于把越权检查建在一个不知道谁是主人的东西上。

### 2.2 `runs.user_id` 的一致性由谁保证

**冲突**：[架构 §6.2](../01design/01architecture.md) 写「由创建 run 的唯一入口（`POST /threads/{id}/runs`）保证，不做触发器」。但 P2 之后那个入口的实现 [`RunSubmitter.submit`](../../app/run/submitter.py) 只认 `thread_id` 与 `content`，**它不知道 user 是谁**。

**定案：`user_id` 从 session 取，经端点传进 submitter；`threads.user_id` 是权威，submit 前先校验该 thread 属于当前用户。**

不做触发器的决定不变，但「唯一入口保证」要落到具体的一行校验上 —— 而那行校验本身就是 §6.3 的隔离过滤，不是额外工作：查 thread 时已经注入了 `user_id` 条件，查不到就是 404，走不到 submit。

### 2.3 `waiting_approval` 不占并发配额，但 worker 要不要 ack

**冲突**：[架构 §5.4](../01design/01architecture.md) 说 `waiting_approval` 期间「不占用任何 worker 资源，可挂起数小时」；而 [P2 的 worker](../../app/worker/loop.py) 是**跑完才 ack**，ack 在 `finally` 里。若审批期间不 ack，这条消息会一直挂在 pending 里，被 `XAUTOCLAIM` 当成「worker 死了」重投 —— 教师还没点确认，任务已经被另一个副本重跑了。

**定案：进入 `waiting_approval` 时 ack 并释放沙箱，审批回传时作为一条新任务重新投递。**

- 这与 P2 的 ack 语义一致：ack 表示「这一段执行结束了」，不表示「整个 run 结束了」。失败的 run 也 ack（[`worker/loop.py`](../../app/worker/loop.py) 的模块 docstring 已经写明这个区分）；
- 挂起数小时期间不持有队列消息、不持有沙箱，正是 §5.4 那句「不占用任何 worker 资源」的字面实现；
- 恢复靠 checkpoint，而 checkpoint 在 P2 已经落库 —— 这是本期能这么做的前提。

**代价**：一次 run 在队列里会出现多次（每轮审批一次）。因此 `run.started` 不能再当「这个 run 第一次开跑」用 —— 那是 [P2 验收①](./P2-plan.md) 依赖的判据。本期要给恢复投递一个区别于首次提交的标记，见步骤五。

---

## 3. 环境前提

**本期几乎没有新的环境依赖**，这是四期里最轻的一次：不像 P1 要改宿主机（gVisor、XFS），也不像 P2 要加两个常驻服务（Postgres、Redis）—— 那两样本期直接用。

只有两项新增：

| 项 | 内容 |
|---|---|
| 密码哈希库 | `uv add` 一个（argon2 或 bcrypt，二选一在 §7.4 定）。**不自己实现哈希** |
| 首个管理员账号 | 空库时没有任何账号，登录接口谁也进不去。需要一条 bootstrap 路径，见 §7.5 |

Redis 本期多两类键：session（`7 天滑动过期`）与 cancel flag。两者都短命且可过期，与[架构 §6.1](../01design/01architecture.md) 选 Redis 的理由一致，不引入新中间件。

> **一条要提前想到的运维项**：session 存 Redis 意味着 **Redis 重启会把所有人踢下线**。[架构 §8.5](../01design/01architecture.md) 要补这一条 —— 它不是故障，但运维要知道「重启 Redis = 全员重新登录」。

---

## 4. 验收标准

与前三期同样的口径，**一条命令能跑完**。本期新增的判据进 `deploy/test/p3.sh`，P0 / P1 / P2 的回归由既有脚本转调。

```bash
make all                                     # 门禁全绿
docker compose -f deploy/compose.yml up -d

bash deploy/test/p3.sh                       # 本期七条，转调 p2.sh 做回归
```

**通过条件**（七条全中才算完）。前三条是[架构 §11](../01design/01architecture.md) 给 P3 定的原文标准：

1. **审批流程走通** —— `interrupt` 事件推给前端 → run 转 `waiting_approval` → **四种决策（`approve` / `reject` / `edit` / `respond`）各走一遍** → run 继续跑到终态。四种都要验：它们在 DeepAgents 侧是四条不同的恢复路径，只验 `approve` 等于没验。

2. **`kill -9` 在工具执行途中，恢复后写操作不重复执行** —— **崩溃点必须是定点注入的，不能靠随机时机**。[P2 §7.1](./P2-plan.md) 量了两轮，两轮的刀都落在两次工具之间，差值都是 0 —— 那证明不了幂等键有效，只证明没砍到。本期要造的是「卡在 `execute` 已经开始、结果还没回来」的那一刀。

3. **30 并发压测不崩溃、不串数据** —— 「不串数据」是这条的重点：并发下每个用户只看得见自己的 thread / run / 事件 / 产物。

4. **越权一律 404，不是 403** —— 拿 A 的 session 去读 B 的 thread / run / 事件 / 产物，四条路径都要返回 404。[架构 §5.7](../01design/01architecture.md) 的理由是不给探测他人资源是否存在的机会，因此**403 也算未过**。同时要验管理员不例外（[架构 §6.3](../01design/01architecture.md) 明确管理员不能看他人会话内容）。

5. **三道闸都关得上，且三个 429 可区分** —— token 日配额耗尽 → `QUOTA_EXCEEDED`；并发 run 超限 → `CONCURRENCY_LIMIT`；接口频率超限 → `RATE_LIMITED`。[架构 §5.7](../01design/01architecture.md) 明确「只给 HTTP 429 的话前端无法区分」，因此**三个 code 各自出现过才算通过**。配额按未命中部分加权计算，不按 input 总数。

6. **主动取消真的停得下来，且 checkpoint 保住** —— 取消一个正在跑的 run：run 转 `cancelled`、推 `run.cancelled` 事件、沙箱释放、**token 不再继续消耗**；随后从该点恢复仍能续跑（[架构 §5.3](../01design/01architecture.md) 明确「已写入的 checkpoint 保留，可从该点恢复」）。

7. **[P2 的六条](./P2-plan.md)不回归** —— 尤其是①「续跑不是重跑」：本期 §2.3 改了 ack 时机与投递次数，那条判据（`run.started` 只有 1 条）会被直接影响。

> **两条要测量、不设门槛的观察项**：
> - **一次真实分析里，条件拦截的谓词命中几次**。这是 §7.2 那个「审批范围」待决的输入 —— 命中 0 次说明谓词太严，命中十几次说明平台没法用。
> - **一次真实分析的未命中 token 数分布**。P0 只有一个样本（[架构 §6.4](../01design/01architecture.md) 自己说「不足以直接推出日配额」），本期每跑一次验收就多一个样本，攒够了再定数值。

---

## 5. 任务分解

八个步骤，**每步有独立的验证标准，未通过不进下一步**（[技术章程第四条](../../.claude/python-constitution.md)）。

```mermaid
flowchart LR
    S0["步骤零<br/>用户模型四张表"] --> S1["步骤一<br/>认证"]
    S1 --> S2["步骤二<br/>数据层隔离"]
    S2 --> S3["步骤三<br/>配额与限流"]
    S2 --> S4["步骤四<br/>主动取消"]
    S4 --> S5["步骤五<br/>HITL 审批"]
    S6["步骤六<br/>工具幂等键"]
    S7["步骤七<br/>租约记名"]
```

**顺序的两条理由**：

- **先地基后闸门**：配额要按 user 算、限流要按 user 分级，没有用户模型就无从做起。步骤零到二是一条必须串行的链。
- **先取消后审批**：两者共用同一套「让一个在跑的 run 停下来并保住 checkpoint」的机制，而取消**没有恢复语义**，是其中简单的那一半。先把停下来验对，审批那步就只剩恢复这一个变量。`waiting_approval → cancelled` 也是状态机上的一条边（[架构 §5.4](../01design/01architecture.md)），取消先落地才画得完整。

步骤六与七**与前面几乎正交**（一个在 broker，一个在 broker + worker 之间），不阻塞任何人，排在最后是因为它们不是本期验收的主线。

### 步骤零：用户模型四张表

| 项 | 内容 |
|---|---|
| 产出 | `users` / `groups` / `user_groups` / `threads` 四张表 + Alembic 迁移；`runs.user_id` 与 `runs.thread_id` 补外键 |
| 依据 | [架构 §6.2](../01design/01architecture.md) 的 ER 图与索引表 |
| 验证 | ① `alembic upgrade head` 与 `downgrade` 都跑得通；② [架构 §6.2](../01design/01architecture.md) 索引表里属于这四张表的索引全部建出；③ 已有的 `runs` 行不被破坏（`user_id` 仍可为空，本步不回填） |

**`agent_config` 用 JSONB 不拆列**，理由在[架构 §6.2](../01design/01architecture.md)，本期照办。

**顺手做掉一件 P2 欠的事**：测试与业务共用同一个 Postgres 库（[P2 §8.3](./P2-plan.md) 登记）。本步本来就要动迁移与 conftest，此时分家成本最低；再往后每加一张表，混进业务表的测试数据就多一批。

### 步骤一：认证

| 项 | 内容 |
|---|---|
| 产出 | `POST /auth/login`、`POST /auth/logout`、`GET /auth/me`；HttpOnly + `SameSite=Lax` Cookie；session 存 Redis，7 天滑动过期 |
| 依据 | [架构 §7.2.2](../01design/01architecture.md)、[ADR-0011](../01design/adr/0011-cookie-session-not-oauth2.md) |
| 验证 | ① 登录拿到 Cookie，`/auth/me` 答得出 role 与所属组；② 登出后同一 Cookie 立刻失效；③ **SSE 带 Cookie 能连上**（[架构 §7.2.2](../01design/01architecture.md) 点名的坑一）；④ 未登录访问任何业务端点得 401 `UNAUTHENTICATED`；⑤ 密码只以哈希形式落库，日志里不出现明文 |

验证③单列出来，是因为它是这一步最容易漏的：SSE 走的是另一套客户端（`@microsoft/fetch-event-source` 默认不带凭据），而本平台的核心交互全在 SSE 上。**没有前端的情况下，用 curl 显式验这条**。

### 步骤二：数据层隔离

| 项 | 内容 |
|---|---|
| 产出 | repository 层统一注入 `user_id` 过滤；越权落 404 |
| 依据 | [架构 §6.3](../01design/01architecture.md) |
| 验证 | ① 拿 A 的 session 读 B 的 thread / run / 事件 / 产物，四条路径全部 404；② **管理员也拿不到**；③ 新增一条测试：repository 的公开查询方法**没有一个**允许不带 user 上下文调用 |

**「不要指望每个接口都记得加 where 条件」**（[架构 §6.3](../01design/01architecture.md) 原话）—— 验证③是这句话的可执行版本。隔离必须做在数据访问层，而「做在数据访问层」这件事本身要有一条测试盯着，否则半年后新加的一个查询方法就会绕过它。

### 步骤三：配额与限流

| 项 | 内容 |
|---|---|
| 产出 | token 日配额（按未命中加权）+ 并发 run 上限，按角色分级；接口层 Redis 计数；三个 429 的 `code` |
| 依据 | [架构 §6.4 §7.5 §5.7](../01design/01architecture.md) |
| 验证 | ① 三道闸各自触发一次，三个 `code` 都出现过；② 配额按未命中扣，`cache_read` 不计入（造一个高命中的会话，验它扣得少）；③ **`waiting_approval` 的 run 不占并发配额**（[架构 §5.4](../01design/01architecture.md)）；④ 数值全部可配置，不硬编码 |

验证②是这一步的核心。[架构 §6.4](../01design/01architecture.md) 实测 62% 的 input 是 cache 命中，按总数扣会高估 1.6 倍，**且方向性地惩罚长会话** —— 而长会话深度分析正是平台想鼓励的。扣错方向比扣错数值严重得多。

**数值本期留空**，见 §7.2。

### 步骤四：主动取消

| 项 | 内容 |
|---|---|
| 产出 | `POST /runs/{id}/cancel`；Redis cancel flag；worker 在 step 边界检查；`cancelled` 状态与 `run.cancelled` 事件模型 |
| 依据 | [架构 §5.3 §5.4](../01design/01architecture.md) |
| 验证 | ① 取消一个正在跑的 run：转 `cancelled`、推 `run.cancelled`、沙箱释放；② **token 不再继续消耗**（比对取消前后的计数）；③ checkpoint 保住，从该点能续跑；④ 取消一个排队中的 run 同样有效；⑤ 取消一个已终态的 run 是幂等的，不报错 |

验证②不能只看「事件流停了」。事件流停下来只说明没人在推，不说明 worker 那边的模型调用停了 —— 而 LLM 调用是真金白银。

### 步骤五：HITL 审批

| 项 | 内容 |
|---|---|
| 产出 | `interrupt` 事件模型；`waiting_approval` 状态；`POST /runs/{id}/approve`；`interrupt_on` 的条件谓词；24 小时超时转 `cancelled` |
| 依据 | [架构 §5.3 §5.4 §5.7](../01design/01architecture.md) |
| 验证 | ① 四种决策各走一遍，run 都能继续跑到终态；② 决策按显式 `index` 重排，缺失或重复的 index 得 `VALIDATION_ERROR`；③ `waiting_approval` 期间**不持有队列消息也不持有沙箱**（§2.3）；④ 超时转 `cancelled`；⑤ 待审批数上限 5 个，超了拒绝新的 |

**`when` 谓词必须是工具调用的纯函数**（[架构 §5.3](../01design/01architecture.md) 引官方警告：非确定性逻辑会破坏基于索引的匹配）。因此谓词只许看 `args`，**不许掺入时间、外部状态或估算**。这条要有一条测试盯着 —— 它坏掉的方式是静默的：索引错位，恢复时把 A 的决策套到 B 的调用上。

**§2.3 的代价在这一步兑现**：一次 run 会多次入队，`run.started` 不再等于「第一次开跑」。要给恢复投递一个标记，并同步改 [P2 验收①](./P2-plan.md) 的判据。

### 步骤六：工具幂等键

| 项 | 内容 |
|---|---|
| 产出 | worker 侧传 `(thread_id, checkpoint_ns)`；broker 对全部写操作（`write_file` / `edit_file` / `delete` / `execute`）去重，命中则返回缓存结果（**含错误结果**） |
| 依据 | [架构 §5.6](../01design/01architecture.md)、[ADR-0014](../01design/adr/0014-tool-idempotency-key.md) |
| 验证 | ① 验收标准②那条定点注入的崩溃用例通过；② 命中缓存时不进沙箱（看容器里有没有新进程）；③ **纯读工具不去重**（`ls` / `read_file` / `glob` / `grep`） |

**缓存错误结果**是关键：`edit_file` 重放时 `old_string` 已不存在，会返回一个首次执行时没有的错误，使 LLM 的后续行为偏离（[架构 §5.6](../01design/01architecture.md)）。只缓存成功结果等于没解决这个问题。

**一处要盯着的耦合**：`checkpoint_ns` 是 LangGraph 的编排细节，不是本平台的领域概念。[架构 §10.2](../01design/01architecture.md) 已登记「升级 langgraph 时须重跑并行场景复验」，本步落地时要把那条复验做成可重跑的用例，而不是只留一句提醒。

### 步骤七：租约记名（P1 遗债）

| 项 | 内容 |
|---|---|
| 产出 | broker 的沙箱申请带上持有者身份；新增按持有者回收的路径；worker 崩溃后名额立刻回池，不等 30 分钟超时 |
| 依据 | [P1 §1.3](./P1-plan.md)、[P2 §8.2](./P2-plan.md) |
| 验证 | ① `kill -9` 一个持有沙箱的 worker，名额在**秒级**回池（现状是最多 30 分钟）；② 超时兜底 `_expire_lease` 保留，不因为有了精确回收就删掉 |

验证②不是保守：精确回收靠的是「另一方发现你死了」，而那个判断本身也可能失效。兜底是最后一道，删掉它等于把两层防护变成一层。

---

## 6. 与 P0 / P1 / P2 的回归关系

| 已有能力 | 本期是否触碰 | 怎么防回归 |
|---|---|---|
| P0 事件流与断线重连 | **碰**：新增两个事件类型，且 §2.3 改了投递次数 | `acceptance.sh` 四条转调；`interrupt` / `run.cancelled` 进事件契约测试 |
| P1 沙箱加固与 broker 边界 | **碰**：步骤六、七都改 broker | `p1.sh` 六条转调；破坏性测试不因为 broker 多了去重表而失效 |
| P1 结构化日志 | 碰：新增的端点要带上 `user_id` | 日志验收从 `run_id` / `thread_id` 扩到含 `user_id` |
| P2 崩溃恢复与队列语义 | **碰得最重**：§2.3 改了 ack 时机 | `p2.sh` 六条转调，其中①的判据要同步改（见步骤五） |
| P2 事件 id 契约 | 不碰 | `p2.sh` ⑥ 转调 |

**最需要警惕的是 P2 ①**。本期改 ack 时机之后，「`run.started` 只有 1 条」这个判据会自然失效 —— 而它失效的方式是**报红**，不是静默，这算运气好。真正的风险是有人为了让它变绿而放宽判据，那样就把 P2 最核心的一条保证悄悄稀释了。**改判据时要保住原意：已完成的步骤不重跑。**

---

## 7. 待决事项

**六项，全部未关闭。§7.1 与 §7.2 不定就无法开工**，其余可在对应步骤前定。

### 7.1 MinIO 与 workspace 回收：留 P3 还是退回 P4

**冲突**：[P2 §2.1](./P2-plan.md) 定案「P2 不做 MinIO，移到 P3」；而[架构 §11](../01design/01architecture.md) 的 P4 一行写的是「产物存储完善」。同一件事仍然被排在两处 —— P2 只是把它从自己身上挪走了，没有真正落定。

**建议：退回 P4。**

- P2 那次决定的实质是「不在 P2」，P3 是当时顺手指的下一个格子；
- 它的驱动理由是「租户前缀隔离依赖 P3 的用户模型」——那说明它**不能早于** P3，不等于**必须在** P3；
- P3 已经有八个步骤，是四期里最大的一期。再挂一条存储线，「未通过不进下一步」会形同虚设；
- 实测约 2.5GB/年（[架构 §6.5](../01design/01architecture.md)），且已有[体检脚本](../../deploy/workspace-report.sh)盯着水位，不紧迫。

**若采纳，要回填三处**：[P1 §1.3](./P1-plan.md)、[P2 §1.3 与 §2.1](./P2-plan.md)、[架构 §6.5 与 §4.4](../01design/01architecture.md)。**不采纳则本期加第九、第十两个步骤**，并重估工期。

### 7.2 四个数值：本期定还是留空

[§1.1](#11-与前三期最大的不同这一期有真正的未知) 列的四个 TODO，输入都是真实使用数据，而平台还没有真实用户。

**建议：机制与数值分开 —— 机制本期落地并可配置，数值留空并标注来源。**

| 项 | 机制（本期做） | 数值（本期不定） |
|---|---|---|
| token 日配额 | 按角色分级的扣减与拒绝路径 | 具体额度 |
| 并发 run 上限 | 计数与 `CONCURRENCY_LIMIT` | 具体个数 |
| 接口限流 | Redis 计数 + `RATE_LIMITED` | 阈值与窗口 |
| 审批触发范围 | `when` 谓词的接线 | 谓词判什么 |

**审批范围那条要单独说**：它不像前三条能靠配置留空 —— 谓词写什么直接决定平台能不能用。**建议本期先只全量拦 `delete`**（P0 实测一次分析里 `delete` 一次都没调，属于低频高危，全量拦不影响可用性），`execute` 的条件拦截等 §4 那条观察项攒够样本再加。

**这是 P2「先量后定」的同一套办法**，但有个区别要认清：P2 那次量的是系统行为（工具重跑次数），跑一次验收就有数据；本期要量的是**人的使用行为**，没有真实用户就永远攒不够。所以这条待决**不会因为等待而自行关闭**。

### 7.3 前端还要不要继续挂着

[P0 §4](./P0-plan.md) 的遗留问题至今未关闭，[P2 §1.3](./P2-plan.md) 已经点名「这条不该继续无主地挂着」。

**本期它变得比前三期更刺眼**：审批要人点、配额耗尽要给人看提示、越权要给人看 404 —— 本期做的东西**大半是给人用的，而没有人能用**。用 curl 验收能证明机制对，但证明不了机制可用。

**需要一个决定**：P3 之后排前端，还是与 P3 并行，还是继续挂着。**不建议继续挂着** —— 它已经跨了三期。

### 7.4 密码哈希用 argon2 还是 bcrypt

没有强偏好，需要一次性定死并写进 [ADR-0010](../01design/adr/0010-self-hosted-accounts-rbac.md)。倾向 argon2（`argon2-cffi`），它是当前的推荐默认。**要一并定的是参数**，用库的默认档还是显式指定 —— 显式指定的好处是将来调整时有据可查。

### 7.5 首个管理员账号怎么来

空库时没有任何账号，`/auth/login` 谁也进不去。三个常见做法：环境变量指定初始管理员、一次性 CLI 命令、迁移里插一行固定账号。

**倾向 CLI 命令**（`python -m auth.bootstrap`）：环境变量会把凭据留在 compose 文件与进程环境里；迁移插固定账号则意味着**所有部署的初始密码相同**，且删不干净。**要一并定的是**：这条命令在已有管理员时该拒绝，还是允许再建一个。

### 7.6 `groups` 建了但组内共享不实现，值不值得

[架构 §7.2.1](../01design/01architecture.md) 说「此处先定角色模型与共享边界，是为了让 §6.2 的表结构将来不必推倒重来」。但组内共享的资源（skill、提示词）本期一样不建，`groups` / `user_groups` 两张表建起来之后**没有任何东西挂在上面**。

**需要判断**：现在建两张空表是不是过早。[架构 §6.2](../01design/01architecture.md) 自己在另一处对 skill 表的态度是「倾向不预留 —— 现在猜它的字段，和将来照实际需求建表，成本差不多，但猜错要迁移」。**同一条理由是否适用于 `groups`**，要一次性想清楚，不要两处用两套标准。
