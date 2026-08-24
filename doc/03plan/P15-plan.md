# P15 实施计划：让 agent 记得住、说得准，而且不串味

| 项 | 值 |
|---|---|
| 文档状态 | **开发完成；付费质量评估与真 XFS `ENOSPC` 未验**（2026-08-21） |
| 当前版本 | v0.4 |
| 作者 | hxy |
| 日期 | 2026-08-21 |
| 上游文档 | [P13-decision.md](./P13-decision.md)（v0.8，A3–A6）· [P14-plan.md](./P14-plan.md)（已完成，给出的新基线） |
| 参考设计 | [learn-claude-code：s09 Memory](https://github.com/shareAI-lab/learn-claude-code/blob/main/s09_memory/README.md) |
| 下游文档 | 暂无 |

> **本期的一句话验收标准**：同一批 10 题 × 3 副本，在 P14 基线之上，最终版本的质量差异先按 pairwise、再按确定性指标判定，只有超过本期实测噪声带才算改进；同一 thread 的记忆能跨 run 召回、不会跨 thread 串味，thread purge 成功后 `.memory` 一并清理且占用计入该 thread 配额，所有额外模型调用与成本都可追溯。

> **“memdir”在本计划中的含义**：采用参考设计的 `.memory/MEMORY.md` 索引、逐条 Markdown、选择性召回、回合后抽取、准入过滤与整理回滚这套语义；物理落点就是对应 thread 的 `/workspace/.memory/`，由 broker 受控读写，随成功 workspace purge 删除，并计入该 thread 的 5 GB XFS project quota。普通文件工具不获得绕过准入的记忆写权限。这样既保留 memdir 的可读、可审计形状，又不越过 [ADR-0004](../01design/adr/0004-sandbox-broker-docker-sock.md)、[ADR-0015](../01design/adr/0015-sandbox-disk-quota-xfs.md) 与 [ADR-0019](../01design/adr/0019-thread-workspace-memory.md) 的边界。

### 版本历史

| 版本 | 日期 | 修改人 | 说明 |
|---|---|---|---|
| v0.4 | 2026-08-21 | Codex | 最终审查补齐普通文件/工具与 purge 的生命周期锁；用确定性竞态红测证明且修复“迟到写复活 workspace”，并闭合 execute 取消与文件流 fd 释放路径 |
| v0.3 | 2026-08-21 | Codex | 完成 thread 私有记忆、召回/抽取/整理、用户上下文、成本账本、purge 补偿、教师管理入口与 pairwise 尺子；双端门禁、可执行的免费回归、真 Docker 遮罩与记忆页真浏览器走查均绿，10×3 付费评估明确记“未验” |
| v0.2 | 2026-08-21 | Claude | 根据 P15 定案修正文档漂移：记忆改为 thread workspace 内的 `.memory/`，随 thread 清理并计入 5 GB 配额；跨 thread 的 user/global memory 延后，不再把 Postgres 当记忆正文真相源 |
| v0.1 | 2026-08-21 | Claude | 初稿。冻结 P14 基线，确定记忆隔离与 memdir 流程，并把提示词、用户信息、system-reminder 排成可逐项量化的步骤 |

## 1. 边界

### 1.1 本期做什么

| 块 | 来自 | 内容 |
|---|---|---|
| **评估尺子** | P13 C7、D5 | 先做 pairwise evaluator（A/B 与 B/A 各判一次，不一致记 tie），量出 pairwise 自身噪声，再决定最终用 pairwise 还是确定性判据 |
| **逻辑 memdir 存储** | P13 A4、参考 s09 | 每条记忆一份 Markdown；YAML frontmatter 固定 `name`、`description`、`type`；`MEMORY.md` 只保留一行索引，索引由记录重建，不成为第二真相源 |
| **选择性召回** | 参考 s09 | 用轻量模型从短索引中最多选 5 条；模型超时、输出不是合法 JSON 时退回关键词匹配；选中后才读取正文，并受总正文预算限制 |
| **回合后抽取与准入** | 参考 s09 | 仅在 run 真正 `succeeded` 后提交抽取任务；候选必须是 `persistent`，拒绝 `current_task`、临时限制、重复、猜测、工具原文与凭据 |
| **整理与并发保护** | 参考 s09、平台约束 | 记录达到阈值后合并重复/过时/矛盾记录；合并前做 `.memory` 目录快照，校验失败或写入失败时原子恢复；用 thread 级锁和临时文件 `fsync`/rename 防止并发覆盖 |
| **用户信息** | P13 A5 | 在现有 `TailContextMiddleware` 中增加一节，只放经脱敏的姓名、角色、院系与可选的额度读数，不放邮箱、用户 ID 或凭据 |
| **system-reminder** | P13 A6 | 仍由同一个尾部块承载，只在需要时注入；提醒是背景和操作提示，不替代平台的权限、审批、沙箱与配额闸门 |
| **提示词优化** | P13 A3、P14 §8.3 | 只调整 `prompt.py` 的角色段和分析要求段；补上“数据字段不存在时直说没有、只有口径不确定才提问”的边界；环境契约逐字保留 |
| **教师管理能力** | P13 A4 | 在当前 thread 下提供记忆的列表、详情、删除与审计回读；删除物理移除记录以释放 workspace 配额，模型没有直接写记忆目录的按钮 |

管理 API 的最小形状固定为 `GET /api/threads/{thread_id}/memories`、`GET /api/threads/{thread_id}/memories/{slug}`、`DELETE /api/threads/{thread_id}/memories/{slug}`；`thread_id` 先按当前登录用户鉴权，不接受请求体里的 owner。自动抽取是唯一写入来源，教师端不提供任意正文写入接口。

### 1.2 记忆的隔离定案

首版只做 **thread 私有空间**（产品上一个 thread 对应一个研究项目）。同一 thread 内的多个 run 可以召回同一份 `.memory`，但新建 thread 不继承旧 thread 的记忆。`user`、`feedback`、`project`、`reference` 仍是记录类型，不是共享权限；`persistent` 表示在该 thread 的生命周期内持久，而不是跨用户或跨 thread。

| 层级 | P15 定案 | 原因 |
|---|---|---|
| Run | **不单独持久**；只产生候选和本轮召回 snapshot | run 结束后候选要经过准入；避免把临时上下文当长期事实 |
| 会话（thread） | **唯一的长期记忆 owner**；记忆位于该 thread 的 `/workspace/.memory` | 与 Claude Code 的 project memdir 语义一致；删除 thread 时可连同记忆一起清理 |
| 用户（user） | 只负责 thread 的访问鉴权，不拥有跨 thread 记忆 | 现有 thread/workspace 查询均以 `user_id` 隔离；不额外引入全局存储 |
| 课题组（group） | **本期不共享** | 当前组是配置资源的名册，不是会话/数据权限边界；`ThreadRecord` 也没有冻结的 `group_id` |
| 全平台 | **不做** | 一条污染会影响所有教师，风险与收益不成比例 |

删除语义固定为：thread 软删除后立即禁止记忆读取和召回；broker 的 workspace purge 成功时真删整个目录，包含 `.memory/MEMORY.md` 与所有记录，失败进入补偿清理且不得重建目录。若以后确有跨 thread 的个人偏好需求，另开 user-scope 设计，不在本期偷偷扩大范围。

### 1.3 明确不做

| 不做 | 理由 | 由谁偿还 |
|---|---|---|
| 跨 thread 的 user/global memory namespace | 本期选择删除 thread 即删除记忆；跨 thread 共享会重新引入串味、权限和保留期问题 | 后续 user-scope 期，先新增 ADR |
| 把记忆正文复制进 `memory_records` 或 checkpoint | `.memory` 文件就是 memdir 真相源；workspace 已有 broker/XFS 配额和清理语义 | 不偿还；任务/成本账可留在 Postgres，但不存记忆正文 |
| 直接使用 `create_deep_agent(memory=...)` 作为完整方案 | DeepAgents 0.7.1 的 `MemoryMiddleware` 只会把所有 `AGENTS.md` 全量塞进 system prompt，没有索引选择、抽取、准入、整理或租户隔离 | 不偿还；本期自建受控 middleware/repository |
| 跨用户、跨组自动共享 | 组不是数据权限边界，且容易把一人的提示注入传播给其他人 | 后续组权限期，需先改数据设计 |
| 用记忆替代 checkpoint、事件归档或上下文压缩 | s09 明确记忆是选择性知识，不是 transcript 备份；P13 的压缩仍是另一条链路 | 不偿还 |
| 让模型通过 `write_file`/`edit_file` 任意改记忆 | 记忆写入必须经过准入、审计、并发控制与敏感信息过滤 | 不偿还 |
| 自动提示词搜索、换主模型、内置 `web_search` | 不属于 A3–A6，且会破坏本期逐项归因 | P16 以后按需重估 |
| 把评估集纳入 CI | 每轮都是真实 LLM 费用 | 不偿还，保留按需 runner |

## 2. 开工前实测与本期定案

### 2.1 入口基线必须冻结

P14 收尾的同批数据是 **10 题 × 3 副本、30 次分析合计 4.1403 元**，使用并发 4；它比 P13 第二轮低 43.9%，但 P13 已量出的成本噪声带是 **43.3%**，所以结论是“分辨不出”，不是“已经改进”。并发 4 下成本可比，时延不可比；P15 每次对比必须固定评估账号、并发、轮询间隔和配额覆盖，不能拿 P13 的 1.9463 元直接当基线。

P13 的绝对 judge 分数同题极差平均 **0.40 分（5 分制）**。因此验收顺序固定为：

1. 先用同一 item 的 baseline/candidate 做 A/B 与 B/A 两次 pairwise；
2. 量 pairwise 的翻转率与 tie 率，若 win rate 超过它自己的噪声带，使用 pairwise；
3. pairwise 仍分不出时，退回确定性判据（产物、字段、审批、召回准确性、成本），并如实记录“分辨不出”，不为了让计划变绿而选一个更有利的尺子。

### 2.2 参考设计与平台现状的差异

用户给出的 [s09 Memory README](https://github.com/shareAI-lab/learn-claude-code/blob/main/s09_memory/README.md) 把记忆拆成四段：

1. `.memory/` 下“一条记忆一份 Markdown”，`MEMORY.md` 是短索引；
2. 先用短索引选择相关记录，再按上限读取正文；
3. 回合结束抽取候选，只有 `persistent` 才能在当前 project/thread 的后续 run 中保留；
4. 记录太多时整理重复、矛盾和过时内容，并在失败时恢复快照。

当前 `deepagents==0.7.1` 的内置 `MemoryMiddleware` 只按 `sources` 下载全部 `AGENTS.md`，随后每轮把全部内容追加到 system message；它没有上述四段，也不会替平台做 thread/用户鉴权。**本期不传 `memory=[...]` 作为记忆实现**，只借用其 middleware 的生命周期接口作为自定义实现的挂点。

### 2.3 物理存储定案：thread workspace 内的受控 memdir

平台现有 thread workspace 是 broker 管理的 `/data/sandbox/{thread_id}`，thread purge 成功时删除该目录；worker 既没有 `docker.sock`，也不能直接读宿主路径。P15 把 memdir 直接放在该 workspace 的受保护子目录，由 worker 通过 broker 的受控 memory endpoint 读写，不让 worker 或 agent 绕过 broker 访问宿主路径。

受控 memory service 的逻辑路径与 broker 物理路径如下（真实 `.memory` 不挂入 sandbox；`/workspace` 只是服务接口使用的逻辑前缀）：

```text
/workspace/.memory/MEMORY.md                 # memory service 的当前 thread 短索引
/workspace/.memory/<slug>.md                  # memory service 的当前 thread 记录
# broker 宿主真实目录：/data/sandbox/<thread_id>/.memory/
```

示例中的 `type: user` 只是记录分类，不代表用户级共享；本期的权限和物理作用域始终是当前 thread。

```markdown
---
name: project-preference-tabs
description: 教师偏好使用制表符缩进
type: user
---

教师偏好使用制表符缩进。
```

Markdown 文件和 `MEMORY.md` 是记忆正文与索引的唯一真相源；不建立 `memory_records` 表来复制正文。P15 必建 `memory_jobs`（成功 run 到抽取任务的 outbox）和 `memory_usage`（额外模型调用账本），但它们只保存任务、成本和必要审计元数据。文件写入、索引重建、物理删除和版本检查必须经过受控 memory service/broker endpoint，不能让普通 `write_file`/`edit_file` 直接绕过准入。

`.memory` 与 workspace 其余字节共享同一个 **5 GB XFS project quota**，不设第二个隐形容量池；索引、正文、快照和合并临时文件都计入该 thread 的配额。thread 删除的软删/真删时序沿用现有 workspace 生命周期：复用 `threads.deleted_at` 立即拒绝访问，purge 与所有迟到工作共用 thread 锁，成功时连同 `.memory` 一起删除；失败进入补偿清理，不能宣称已释放空间。跨 thread memory 若以后需要，再评估 ADR-0016 预留的 `CompositeBackend`/StoreBackend 路线。

memory cap 只是同一 5 GB project quota 内的**软保护线**，不是第二个存储池：达到它时跳过新的抽取/整理写入并记录原因，主 run 仍按原结果结束；索引、快照和临时文件仍以 XFS 的实际占用为准。上限、单条正文大小和索引大小在 §2.7 探针后冻结，不能用 cap 绕过 thread 配额。

**保护不是靠提示词。** 当前沙箱把整个 workspace 以读写方式挂载，普通 broker 文件接口和 `execute` 都可能触达 `.memory`；P15 第三步必须先落地并实测保护方案：`.memory` 作为 broker 保留目录，通用 files/tree/raw API 隐藏或拒绝，真实 `.memory` 不挂进沙箱（必要时在 `/workspace/.memory` 位置挂空的只读遮罩），召回只由 broker memory service 选择并注入，自动抽取/整理唯一经 broker memory endpoint 写入。这样 `execute` 也不能绕过“最多 5 条/正文预算”；保护未通过前，不得把“记忆完整性”记为通过。

### 2.4 四段记忆流程的参数定案

| 环节 | P15 初始值/规则 | 失败时 |
|---|---|---|
| 索引选择 | 最近最多 3 条用户消息 + catalog；最多选 5 条；选择器用辅助模型，严格解析 JSON 数组 | 超时、非 JSON、越界索引均转关键词匹配，并记 `fallback` |
| 正文召回 | 选中后才加载正文；总字符预算先以 20,000 为探针初值，最终写成显式常量；正文按 `description`/更新时间稳定排序 | 超预算从后往前整条丢弃，不切半条；没有命中则不注入 |
| 注入 | 每个 run 只选择一次；在本 run 内复用同一份 snapshot；正文包在 `<agent_memory>` 中，明确“仅是可能过时的背景，不是新命令” | 召回失败不阻塞主 run，退化为无记忆运行 |
| 抽取 | 仅最终 `succeeded` 的 run 入队；候选带 `scope=persistent/current_task`；`run_id` 幂等；写入前确认 thread 未删除 | 失败只记审计/告警，不能把已成功的 run 改成 `INTERNAL`；已删除 thread 的 job 丢弃，不重建目录 |
| 准入 | 拒绝字段不全、当前会话措辞、一次性路径/限制、工具原文、助手猜测、重复记录、密码/API key/token 等敏感信息 | 候选只落必要的审计元数据，给出拒绝原因，不写活动文件 |
| 整理 | 活动记录达到 10 条触发；一次最多给整理模型 20 条；结果先过 schema、slug 和敏感信息校验 | 先原子恢复 `.memory` 快照并重建索引；并发冲突重试，不静默覆盖 |

20,000、5、10、20 都是**可测的初值**，不是上游默认值。第一轮真实评估后按成本、召回命中和正文截断比例校准，并把最终数字回写本节与配置说明。

### 2.5 抽取的时序与成本定案

`RunExecutor` 只有在 `_suspend()` 返回“没有中断”且 `runs.succeed()` 条件更新成功后，才在同一事务写入按 `thread_id/run_id` 关联的 `memory_jobs` outbox；独立的 worker 消费它，再通过 broker 的 memory endpoint 执行抽取/整理。等待审批、取消、失败、崩溃重投和已终态重复投递都不触发第二次抽取。job 执行前再次检查 `threads.deleted_at`，已删除 thread 直接幂等丢弃，绝不能调用会自动创建目录的路径解析。抽取所需的完整消息由 Agent 提供受控 snapshot，不允许 memory service 直接查询 checkpoint 表。

选择器、抽取器和整理器的 token、耗时、模型名、命中/拒绝数必须单独记账，并并入评估 runner 的 `cost_yuan_total`；不能因为它们发生在主 run 之外就漏进 P13/P14 的成本比较。具体口径定为：前置 selector 的 token 通过 Agent 的 usage 回调合入当前 run 的 `TokenUsage`，终态之后的 extractor/consolidator 写入按 `thread_id/run_id` 关联的 `memory_usage` 账本，配额与用量查询及评估 runner 都汇总两者。辅助模型不可用时，选择退关键词、抽取/整理跳过，不阻塞教师看到的 `run.finished`。

### 2.6 尾部块与提示词的定案

`TailContextMiddleware` 的 1200 字符预算和持久追加语义不变；记忆正文**不进入**这个预算，也不把整张 catalog 每轮重抄。用户信息不是由 worker 单例临时查出来，而是在 API 提交时生成脱敏的 `UserContext`，随 run 快照传入；额度读数按同一时区冻结。尾部节的优先级由高到低固定为：任务进度、步数、已装包、用户信息、system-reminder；超预算时从最低优先级整节丢弃，日志必须说明丢了哪一节，不能把任务进度静默挤掉。

`prompt.py` 只改 `ROLE_SEGMENT` 与 `ANALYSIS_SEGMENT`。`ENVIRONMENT_SEGMENT` 中关于 `/workspace`、`outputs/`、装包、删除审批、提问工具、中文图表和产物引用的契约逐字保留；`.memory` 的写保护由 broker/挂载实现，不靠提示词。P14 的 `E09-absent-field` 观察转成明确规则：数据里没有字段时直接说明没有并给出限制；只有存在多个合理分析口径、且当前数据无法判定时，才用 `ask_user_question`。

### 2.7 开工前必测（结果为否会改变步骤）

1. **MemoryMiddleware 探针**：确认所有 source 全量进 system prompt，且 checkpoint 复用会跳过重新加载；若上游版本已改变，先重新核对自定义 middleware 的替换方式。
2. **存储并发探针**：两条并发写入同一 thread 的 `.memory`，确认 broker 的 thread 级锁、临时文件 `fsync`/rename 和索引重建能看见冲突；不能把普通文件工具的读—改—写假定为“天然安全”。
3. **选择器/解析探针**：让辅助模型返回非法 JSON、重复索引、越界索引和超时，四种都必须落关键词回退而不是让主 run 失败。
4. **抽取时序探针**：分别跑 succeeded、waiting_approval、cancelled、failed，只有 succeeded 产生幂等 job。
5. **尾部预算探针**：同时填满已有三节和新两节，确认掉的是低优先级整节，任务进度仍在；系统提示词的环境契约逐字不变。
6. **成本探针**：从 Langfuse/事件流核对 selector、extractor、consolidator 的 token 能回到同一个评估结果 JSON；缺任一项就不能开始质量对比。

## 3. 环境前提

| 前提 | 怎么确认 |
|---|---|
| P14 基线文件存在 | [`script/eval/result/p14-baseline.json`](../../script/eval/result/p14-baseline.json)，30 次、4.1403 元；跑法与并发记录一并读取 |
| 六个服务起着 | `make ps`；数据库迁移只由 api 容器执行 |
| workspace 配额可回读 | `data/sandbox` 的 XFS `prjquota` 已生效；`.memory`、索引快照和正文与代码、上传文件、`outputs/` 共用 thread 的 5 GB，不设独立存储池 |
| 评估账号独立 | 使用 P13 的专用评估账号，不混入教师自己的 thread、配额和 `.memory` 文件 |
| 真实费用可记账 | `LANGFUSE_BASE_URL` 与 `LANGFUSE_HOST` 都显式指向宿主可达地址；完整打印 4xx/5xx 响应体 |
| memory job/usage 账已迁移 | `memory_jobs`/`memory_usage` 由 api 的 Alembic head 建表；worker 启动不调用 `setup()` 或任何 DDL；不建立记忆正文表 |
| worker 身份链完整 | `RunTask.user_id`、`thread_id`、`run_id` 与脱敏 `UserContext` 一起进入 Agent；worker 单例不可把上一个并发 run 的 user/thread 放进成员变量；已删除 thread 的 job 必须丢弃 |
| 辅助模型可用 | `model_aux` 能完成选择器/抽取器探针；不可用时按 §2.5 的降级规则走 |
| 评估跑法固定 | 每题 3 副本、并发与轮询间隔固定；成本可比、时延不作为 P15 主判据 |
| 外发边界已知 | 记忆正文若送辅助模型，与 Langfuse/模型外发同属既有风险；敏感信息准入先过滤，日志只记 slug/原因不记正文 |

## 4. 验收标准

> 编号是本计划的判据，不预先假定 `verify.sh` 最终条数。收尾按脚本实际条数回写 [doc/03plan/CLAUDE.md](./CLAUDE.md)；依赖真实 LLM 而未触发到目标场景时记“未验”，不记通过。

### 4.0 验收入口

免费门禁仍从根入口跑：

```bash
SKIP_LLM=1 SKIP_HOSTILE=1 bash script/test/verify.sh
```

评估集沿用 P13/P14 的真实链路；固定并发 4、每题 3 副本，并把记忆额外调用计入同一结果：

```bash
EVAL_USERNAME=zuel-eval EVAL_PASSWORD='***' \
LANGFUSE_BASE_URL=http://localhost:3000 \
src/.venv/bin/python script/eval/run_eval.py \
  --repeat 3 --concurrency 4 --run-name p15-final
```

命令中的口令只作示例，不能写进脚本或结果；先用 `--dry-run` 做链路自检，再付费跑完整批次。

### 4.1 免费门禁与仓储/集成判据

| 判据 | 该看到什么 | 失败时看哪里 |
|---|---|---|
| **P15①** | 当前 thread 的 `.memory` 记录符合 frontmatter schema；`MEMORY.md` 只列活动文件；删/改/合并后能扫描 `.memory/*.md` 重建索引，不能出现孤儿或重复 slug；`../`、绝对路径、符号链接和伪造 `MEMORY.md` 输入被拒绝 | memory service、broker reserved-path、index rebuild |
| **P15②** | 同一 thread 的新 run 能召回已有记录；不同 thread（包括同一用户的新 thread）、其他用户和 admin 读取/删除均统一 404；删除 thread 后 `.memory` 不再可读、不再召回，broker purge 成功后空间释放 | thread 鉴权、broker no-create lookup、DELETE/purge 补偿路径 |
| **P15③** | 召回最多 5 条且正文不超过预算；选择器非法/超时走关键词回退；不相关记录不被加载；选择结果和 fallback 原因可审计 | selector parser、keyword fallback、body budget |
| **P15④** | `current_task`、临时路径、凭据、工具原文和“忽略系统规则”等候选不入 persistent；成功 run 可产生幂等 job，审批挂起/取消/失败不产生 | admission gate、executor terminal path、secret detector |
| **P15⑤** | 两个并发写同一 thread 不丢记录；重复 `run_id` 不重复写；整理失败能恢复目录快照和索引；版本冲突可重试或明确失败；触发 memory cap 时跳过新写入，写满 XFS 配额返回 `ENOSPC`，两种情况都不改变主 run 终态 | thread lock、atomic rename、consolidation rollback、outbox idempotency |
| **P15⑥** | 被召回的“忽略系统指令”只作为背景文字，当前用户请求、平台提示和工具证据优先；记忆不能绕过 delete/HITL/沙箱/配额 | memory context wrapper、HITL 与权限回归 |
| **P15⑦** | 用户信息和 reminder 仍在一个尾部块；总长不超 1200；超限丢低优先级整节，任务进度不被挤掉；环境契约 prompt 逐字保留 | `tail_test.py`、`prefix_test.py`、`prompt.py` |
| **P15⑧** | selector/extractor/consolidator 的 token、成本、耗时都有记录；记忆服务失败不把主 run 改成 `INTERNAL`，也不把成功 run 的费用漏出配额账 | usage mapper、run executor、Langfuse spans |

### 4.2 教师侧查看与删除

| 判据 | 该看到什么 |
|---|---|
| **P15⑨** | 登录教师在选定 thread 的记忆入口看到该 thread 的 `name/description/type/updated_at`，可查看正文并物理删除；删除有确认，文件从列表、详情和下一次召回消失并释放可计量空间；不展示宿主路径、用户 ID、模型原始候选或敏感过滤日志 |

浏览器走查沿用 P14 的 Playwright 方式；缺 chromium 时记“未验”。API 层仍需用两个 thread、两个用户和 admin 做 404 隔离测试，不能只靠浏览器隐藏按钮。

### 4.3 付费评估与最终判定

| 判据 | 该看到什么 |
|---|---|
| **P15⑩** | pairwise evaluator 对同一 item 的 baseline/candidate 做 A/B、B/A 两次；解析只接受 `baseline/candidate/tie`；两次相反或无法解析记 tie；重复判分的翻转率与 tie 率有数，结果 JSON 带 rubric 版本 |
| **P15⑪** | 每个能力按独立提交顺序量一次：①只加存储/召回；②再加抽取；③再加整理；④再加用户信息；⑤再加 reminder；⑥最后改角色/分析提示词。最终组合相对 P14 基线的 pairwise win rate 超过 pairwise 噪声，或确定性指标超过 P13 噪声带，才记改进 |
| **P15⑫** | 主模型、选择器、抽取器、整理器的总成本与主 run 成本分开列出；若总成本超过 P14 基线加 43.3% 噪声带，必须标为成本回归并解释，不能用一次质量分掩盖；任一记忆 probe 命中数为 0，该项记“未验” |

pairwise 仍分不出时，最终结论可以是“质量分辨不出”，但必须保留召回准确率、污染率、确定性业务判据和成本表；“没有红色测试”不等于“质量提升”。多轮题的 judge 输入必须来自同一次 run 的完整提问—答复对，不能把第一轮问题配到最后一轮答案上。

## 5. 任务分解

**每一步先写能使它变红的测试/探针，确认通过后才进入下一步。四类质量改动必须逐项提交、逐项跑同一批评估，不能最后一次把所有变化混在一起。**

| # | 做什么 | 验 |
|---|---|---|
| **一** | 冻结 P14 基线；实现 pairwise evaluator、A/B 与 B/A 双向判定、tie 规则、非法输出解析和本地结果落盘；先量 pairwise 自身噪声 | **P15⑩** 的 parser/position-bias 单测；同题重复判分探针 |
| **二** | 做 §2.7 的六处开工前探针；冻结 `thread` scope、记录 schema、正文/索引/合并初值、memory cap 和成本字段；写入开发记录 | 探针正反两向；不通过时回到本节，不先写 agent middleware |
| **三** | 在 broker/Workspace 增加受保护的 `.memory` 保留目录、thread 级锁、无创建读取、原子写入/索引重建和配额回读；实现容器侧不可见隔离；复用 `threads.deleted_at` 做 deleted-thread guard，令 purge、迟到的 RunTask/SandboxPool、skill 对齐、memory job 和文件请求共用锁并走无创建查找，配套持久补偿/reaper，禁止目录复活；Postgres 只新增 `memory_jobs`/`memory_usage` 等任务账表 | **P15①②⑤** 的文件、broker、配额、删除竞态和补偿单测；api/worker 不直接摸宿主目录，已删除 thread 的任何迟到工作都不会重建目录 |
| **四** | 实现嵌套管理 API（`GET /api/threads/{thread_id}/memories`、`GET /api/threads/{thread_id}/memories/{slug}`、`DELETE /api/threads/{thread_id}/memories/{slug}`）与最小前端入口：列表、详情、物理删除、审计字段脱敏；普通文件树和模型工具不能绕过保留目录 | **P15②⑨**；两个 thread/两个用户/admin 404、删除后回读/配额和 Playwright 走查 |
| **五** | 实现 selector：catalog → 最多 5 个索引 → 正文预算；严格 JSON schema、关键词回退、相关性/顺序稳定；把选择结果与成本写入 run 级结果 | **P15③⑧**；假模型覆盖超时、非法 JSON、越界和无命中 |
| **六** | 实现 `MemoryRecallMiddleware`：每个 run 选择一次，同一 run/HITL resume 复用 snapshot；正文作为不可信 `<agent_memory>` 背景注入，不写进 1200 字符尾部，不全量进 checkpoint 历史；从当前 thread 的 broker catalog 读取；把 selector usage 通过受控回调交给 Executor | `memory_test.py`、HITL resume、prefix/cost 探针；确认同 thread 新 run 会重新选择，不能跨 thread 复用 selection |
| **七** | 在 Agent/Executor 增加受控消息 snapshot 与按 `thread_id` 关联的 `memory_jobs` 成功终态 outbox；实现 extractor、`persistent/current_task` 判定、敏感信息和重复过滤；写入前检查 thread 未删除，`run_id` 幂等 | **P15④⑧**；succeeded/paused/cancelled/failed/已删除 thread 五种路径各跑一次 |
| **八** | 实现 consolidation：达到阈值后加 thread 锁，最多取 20 条，严格校验合并结果，目录快照→临时目录→原子替换→重建索引；失败恢复旧目录，`ENOSPC` 不改变主 run 终态 | **P15⑤**；并发写、重复记录、矛盾记录、故意写失败、配额写满五组探针 |
| **九** | API 在提交时生成脱敏 `UserContext` 并随 run 快照传递；给现有 `TailContextMiddleware` 增加用户信息节，调整节优先级，保证任务进度不被新内容挤掉；额度读数采用同一时区冻结的口径 | **P15⑦**；尾部预算/缓存和用户信息不泄漏单测 |
| **十** | 增加条件式 system-reminder 节：只提醒当前 run 真需要的策略，记忆冲突时明确当前请求优先；不复制环境契约，不把安全规则交给模型记忆 | **P15⑥⑦**；提醒出现/不出现两向探针 |
| **十一** | 只改 `ROLE_SEGMENT`、`ANALYSIS_SEGMENT`；加入缺失字段和提问边界、异常/缺失值说明、结论与证据分离等最小措辞；每次只改一组文字 | `prompt_test.py`、E09 真跑、P0/P12/P14 关键回归 |
| **十二** | 按 ①存储/召回→②抽取→③整理→④用户信息→⑤reminder→⑥提示词的顺序逐项跑 10×3；最后跑组合版本、全量回归、浏览器走查，回写 P13 决策观察项和索引 | **P15⑪⑫**；所有未触发的 probe 标“未验”，不以 skip 冒充通过 |

## 6. 回归关系

| 本期改动 | 可能打穿 |
|---|---|
| `.memory` broker/Workspace 与 thread purge | API 启动、文件树/上传/删除、XFS 5 GB 配额、thread 软删与真删、迟到 RunTask/文件请求、workspace-report；删除失败只能进入可重试清理，不能宣称空间已释放 |
| `memory_jobs`/`memory_usage` migration | api 启动、Alembic schema、worker 看门狗、deleted-thread guard；记忆正文不进 Postgres，**不改 checkpoint 表** |
| `RunTask.user_id/thread_id` 到 Agent 的 scope 传递 | worker 并发身份、Langfuse user attribution、P9 子智能体、P14 提问恢复；不能把 user/thread 放进 Agent 单例成员变量 |
| Agent 增加 selector/recall middleware | P13 prefix/tail/cache/cost、P14 HITL resume、P8 skill 注入、P9 子图装配；新 run 与同 thread 续跑必须区分 |
| 成功后 memory outbox/job | run terminal 顺序、至少一次投递、取消/审批/崩溃恢复、worker 看门狗；抽取失败不得改已写下的 `run.finished` |
| 尾部节新增或重排 | P13 的持久追加断言、P14 任务进度/提问卡片、所有依赖 system-reminder 位置的单测；超预算不能静默丢任务进度 |
| `prompt.py` 文案 | P0 产物、P8 装包、P12 网络/安装、P14 delete 与 ask_user_question、E09 缺失字段判据；环境契约不得被顺手改写 |
| 额外 LLM 调用与成本字段 | quota、`runs.tokens_*`、Langfuse 归因、评估 runner 的 cost aggregation；成本双峰不能用中位数估算总额 |
| 记忆管理前端 | P5 路由、登录与 thread 404 隔离、P7 资源可见性页面、P14 Playwright selector；按钮隐藏不替代后端鉴权 |

P15 会同时改 worker/agent、API/迁移与少量前端，但收尾仍要跑 `make`；完整 `verify.sh` 是否扩充到多少条以实际实现为准。真实费用评估不进 CI，但要在收尾记录运行参数、结果文件和未验项。

## 7. 待决事项

1. **正文预算、整理阈值和 memory cap 的最终数值。** 先用 20,000/10/20 与显式 memory cap 做探针初值；根据召回截断率、额外成本、配额占用和质量结果校准，不能照抄教学代码默认值。
2. **记忆保留期。** P15 采用 thread 文件生命周期：单条删除物理 unlink，thread purge 递归删除；不另设独立 180 天正文保留期。审计/任务账是否随 runs 保留，按现有数据生命周期单独定案。
3. **组级或 user 级 project 记忆。** 本期明确禁用；只有在成员权限、删除语义、存储配额和审计规则先落地后，才重新开 ADR。
4. **辅助模型不可用时的产品提示。** 主 run 继续完成，但教师是否看到“本次未更新记忆”要在第一轮真实走查后决定；不能把内部异常原样放进答复。
5. **抽取是否需要教师确认。** 本期沿用 s09 的隐式候选 + 确定性准入，教师可查看/删除；若真实数据出现误记率，再考虑增加“待确认”状态，而不是先把所有候选都写入。
6. **记忆与自定义 agent 配置的关系。** P15 按 thread 隔离；自定义 agent 的 `system_prompt` 仍按 P7 规则冻结，不能因为配置可共享就自动共享 `.memory`。

## 8. 实施记录

> 每步完成后追加真实日期、提交/文件、判据结果和打穿的历史用例。**没有触发目标场景就写“未验”**；评估集只跑了一部分题也要写清楚覆盖数。

| 步骤 | 日期 | 结果 |
|---|---|---|
| **一** pairwise 尺子 | 2026-08-21 | ✅ 代码与确定性测试完成。只接受 `baseline/candidate/tie`，A/B 与 B/A 不一致或任一方非法一律记 tie；按 item + replica 稳定配对，保留多轮完整题面、双向原始证据、rubric 版本与基线 SHA。未发起付费 judge，故 pairwise 实测噪声仍未验 |
| **二** 定案与红测 | 2026-08-21 | ✅ 固定 thread scope、最多 5 条、正文 20,000 字符、整理阈值 10/最多 20 条、总 soft cap 1 MiB、单条正文 100,000 字符与索引 64 KiB；各项均有先红后绿的边界测试 |
| **三至四** 存储、隔离、purge 与教师入口 | 2026-08-21 | ✅ `.memory` 成为 broker 保留目录；通用文件 API/模型工具均拒绝或隐藏，真 Docker 沙箱用空的只读 tmpfs 遮罩。Workspace 读路径不再隐式建目录；purge 与沙箱、skill、memory、普通文件及 10 个 Agent 工具共用 thread lock，迟到写复活、execute 取消穿透和文件流 fd 泄漏均有先红后绿的回归。迟到 RunTask 守卫、软删除 purge 待办与 reaper 共同防止复活。教师端列表→详情→确认删除→空态已真浏览器走通，删除后 broker 404 |
| **五至八** 召回、outbox、抽取与整理 | 2026-08-21 | ✅ selector 严格 JSON + 超时/非法输出关键词回退；每个平台 run 只选一次，HITL 恢复复用快照、新 run 重选。成功终态与 `memory_jobs` 同事务；准入过滤、敏感信息拒绝、CAS 整理、回滚、最多三次重试、stale job 回收和已删 thread 丢弃均完成 |
| **九至十一** 用户上下文、reminder 与提示词 | 2026-08-21 | ✅ 提交时冻结脱敏 `UserContext`，审批重投仍用原快照；尾部块按任务进度→步数→已安装包→用户信息→reminder 的优先级整节丢弃，不超 1200 字符。仅修改角色/分析段，环境契约有逐字节回归保护 |
| **十二** 总门禁与质量结论 | 2026-08-21 | ✅ 开发门禁完成；⚠️ 付费质量结论未验。根 `make` 后端 1627/前端 293 全过，评估脚本 74 测试全过；免费部署回归 43 过、25 未验。未运行六阶段和最终组合的 10×3 付费评估，不宣称质量改进或成本无回归 |

### 8.1 落地结果

- **真相源与隔离。** 记忆正文只在 thread workspace 的 `.memory/*.md`，`MEMORY.md` 可由正文重建；Postgres 只存 outbox、用量和 purge 待办。写入/整理在同 thread 锁中进行，临时文件仍在 `.memory` 内，因此与工作文件共用 XFS project quota。
- **生命周期。** 创建与查找 workspace 已拆开；沙箱获取、skill 对齐、memory 原语、普通文件与 Agent 工具都和 purge 共用 thread 生命周期锁。请求取消后底层 execute 会结束后才释锁，下载则在锁内打开 fd，purge unlink 后仍可完整读取。删除 thread 时同事务建立 `thread_purge_jobs`，首次清理失败由 `app.thread.reaper` 反复补偿；迟到 run 在发出 `run.started` 前就被丢弃。
- **运行链与账本。** selector 的费用计入主 run，extractor/consolidator 另列；`included_in_run` 防双计。`GET /api/runs/{run_id}/memory-usage` 返回三分项、选中 slug、命中/拒绝数、回退原因与 job 状态；明确零账保留，缺账不伪造。
- **教师产品面。** 聊天页工作区新增“文件 / 记忆”页签，记忆页只提供所属 thread 的查看与物理删除，不暴露宿主路径、用户 ID、模型原始候选或过滤日志。

### 8.2 门禁与原始证据

| 入口 | 结果 | 说明 |
|---|---|---|
| `make` | ✅ | Ruff/format、mypy、Oxlint、TypeScript 全绿；后端 **1627 passed**，前端 **293 passed** |
| 重建后 `alembic current` | ✅ | API 容器已在 **`0017_memory (head)`**，六个服务均在运行；worker 未执行 DDL |
| `PYTHONPATH=script/eval ... pytest script/eval -q` | ✅ | **74 passed**；包含 pairwise 双向/严格 parser/多轮题面、四分项费用、缺账未验、批次记忆率聚合与 Langfuse 4xx/5xx 可读失败 |
| 真 Docker `.memory` 遮罩探针 | ✅ | **1 passed**；宿主真正文在容器内不可见，空目录不可写 |
| P15⑨ 真浏览器走查 | ✅ | 临时 thread 中列表、类型/更新时间、正文、二次确认和删除后空态均可见；broker 回读 **404**，thread 清理 **204** 且 workspace 已移除 |
| `run_eval.py --dry-run --repeat 3 --concurrency 4` | ⚠️ | 未调用模型；在读 Langfuse 数据集时上游返回 **HTTP 502，空响应体**，因而未走到 10 题文件/平台链自检。runner 现已给中文错误与退出码 2，不再泄出 SDK traceback |
| `SKIP_LLM=1 SKIP_HOSTILE=1 bash script/test/verify.sh` | ⚠️ | **43 过、25 未验、0 未过**；脚本按“有未验不宣称通过”的规则退出 2。可执行的隔离、并发、恢复、文件、配额、Playwright、外部 MCP 等历史判据全过 |

### 8.3 未验项（不以单测冒充）

- **P15⑤ 的真 XFS `ENOSPC`。** soft cap、CAS、并发写、marker 前回滚和 marker 后收尾均已验；本轮使用 `SKIP_HOSTILE=1`，没有把宿主 thread project quota 真正写满，该分支记未验。
- **P15⑩–⑫ 付费评估。** 未运行 pairwise 重复判分探针、六阶段逐项 10×3 或 `p15-final` 10×3，因此召回准确率/污染率、pairwise 胜率、噪声、四分项真成本与质量改进均未下结论。

### 8.4 成本判定边界

P14 冻结基线仍是 `script/eval/result/p14-baseline.json`，SHA256 为 `a5b78a53ffe28bfc8a2e15982afac1b70b0afb891fbd3020d8338df45fb301fd`，30 次分析合计 **4.140294 元**。按 43.3% 噪声带，P15 最终组合总成本的回归上限为 **5.933041 元**。本轮没有 P15 付费结果，所以主模型/selector/extractor/consolidator 真成本与是否超限均记“未验”，不用单测中的零账推断“无回归”。
