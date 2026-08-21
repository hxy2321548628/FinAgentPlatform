# ADR-0019：记忆存放在 thread workspace 的受保护 memdir

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-08-21 |
| 决策人 | hxy |
| 关联设计 | [总体架构](../01architecture.md) · [数据设计 §6.3–§6.5](../06data-design.md) · [安全设计 §7.3.5](../07security-design.md) |
| 关联计划 | [P15-plan.md](../../03plan/P15-plan.md) |

## 背景

s09 Memory 的核心形状是 `.memory/MEMORY.md` 短索引加上“一条记忆一份 Markdown”。本平台的 workspace 已按 thread 隔离、由 broker 管理，并由 XFS project quota 限制到每 thread 5 GB。P15 需要决定记忆是跟 thread 走，还是另建跨 thread 的用户存储。

本期产品语义确定为：**一个 thread 是一个研究项目；同一 thread 的多个 run 共享记忆；删除 thread 时记忆也删除**。因此不把记忆正文复制到用户级 Postgres namespace，也不让删除 thread 后留下独立的长期记忆。

## 决策

记忆采用 **per-thread workspace memdir**：

```text
受控 memory service 逻辑视角：/workspace/.memory/MEMORY.md
受控 memory service 逻辑视角：/workspace/.memory/<slug>.md
broker / 宿主视角：/data/sandbox/<thread_id>/.memory/...
sandbox execute 视角：同名空目录/不可见遮罩，不暴露上述真实正文
```

- `MEMORY.md` 是可重建的短索引，每条记录是一个带 YAML frontmatter 的 Markdown 文件；文件和索引是记忆正文的唯一真相源。
- `user`、`feedback`、`project`、`reference` 只是记录类型；权限作用域是 `thread`。不同 thread 不继承记忆，课题组与全平台不共享。
- `.memory` 是 broker 管理的保留目录。普通 workspace 文件工具、通用浏览/下载接口和模型生成的 `execute` 不得绕过准入读写或全量扫描；自动抽取、整理和删除只能走受控 memory endpoint。真实 `.memory` 不挂入 sandbox；容器启动前如需保持路径兼容，只能挂同名空目录/不可见遮罩并固定为不可写，正文由 selector 选中后注入。
- `.memory` 与代码、上传文件、`.local`、`outputs/`、整理快照和临时文件共享该 thread 的 **5 GB XFS project quota**，不设第二个隐形容量池。写满统一返回配额错误，不能把主 run 改成 `INTERNAL`。
- P15 可设置 memory cap 作为同一 project quota 内的软保护线；触发时跳过新的抽取/整理写入并记账，不能因此另建不计入 XFS 的存储池。
- 复用 `threads.deleted_at`：API/worker 在调用 broker 前先查到软删状态，立即拒绝记忆 API、召回和抽取；purge 与迟到的 RunTask、skill 对齐、文件请求共用 thread 锁，成功时递归删除整个 workspace，包含 `.memory`，并释放已占字节。purge 失败进入可观测、可重试的最终清理；所有迟到工作都必须使用不创建目录的查找，不得复活已删除 thread。
- P15 必须由 Postgres 保存 `memory_jobs`、`memory_usage` 及不含正文的必要审计元数据；不建立 `memory_records` 作为第二份正文真相源，也不改 LangGraph checkpoint 表。

## 理由

1. 记忆的可见范围与项目文件、产物、代码一致，thread 删除语义单一，不需要跨存储做“删掉用户记忆但保留会话”的特殊判断。
2. workspace 已有 broker 边界、XFS 配额和清理路径；把 `.memory` 放在其中能让索引、正文、快照和临时文件共享同一个容量闸门。
3. 目录形状保留了 Claude Code/s09 的可读、可审计和可重建特性，同时避免引入本期不需要的跨 thread namespace、用户组权限和 StoreBackend 生命周期。

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| `/memories/user/<id>/` 独立用户目录 | 能跨 thread 召回，但与“删除 thread 连带删除记忆”冲突，并新增用户级权限、保留期、孤儿清理和串味风险 |
| Postgres `memory_records` 保存 Markdown 正文 | 会产生第二份真相源；thread 删除不会自然清理正文，且偏离 memdir 文件语义 |
| 让模型用 `write_file`/`edit_file` 直接维护 `.memory` | 绕过敏感信息准入、审计、并发锁和原子回滚；整个 workspace 可写挂载还会允许 `execute` 绕过普通工具保护 |
| 直接把 `.memory` 路由到 StoreBackend | ADR-0016 的预留方案针对未来跨 thread 记忆；本期没有该需求，且 StoreBackend 的读改写不提供本期所需的并发与删除语义 |

## 后果与验收影响

**正面**：同一 thread 的后续 run 能召回；删除 thread 的数据边界直观；记忆占用不会绕过既有 5 GB 配额；无需新增跨租户存储。

**代价**：新 thread 不会自动得到旧 thread 的偏好；`.memory` 会与用户数据、代码和产物竞争 5 GB；需要给 broker 增加保留目录、无创建读取、thread 锁、原子写入和删除竞态保护，并让所有会申请 workspace 的迟到任务复用 `deleted_at` guard；需要验证 sandbox 的空遮罩/不可见隔离，不能只在提示词里声明“不要写”。

P15 必须实际验收：同 thread 跨 run 命中、不同 thread 不命中、`.memory` 写入与快照临时文件计入同一 quota、写满得到 `ENOSPC`、thread 删除后目录不复活且 purge 后空间释放、通用 files API 与 `execute` 均不能绕过 memory admission。

## 重新评估的触发条件

- 教师明确需要跨 thread 的个人偏好或课题组共享记忆；
- `.memory` 长期挤占分析数据导致 5 GB 配额频繁触顶；
- 迁移到多机/对象存储，thread workspace 不再是可靠的长期文件根；
- broker 无法提供受控写入或容器侧不可写隔离。

触发时新增 ADR，重新定义 scope、权限、删除、备份和成本口径；不得在本期偷偷改成 user/global memory。
