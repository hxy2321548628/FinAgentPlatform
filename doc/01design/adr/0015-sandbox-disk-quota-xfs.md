# ADR-0015：沙箱磁盘配额用 XFS project quota

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-31 |
| 决策人 | hxy |
| 主文档关联 | §7.3.2 加固清单、§7.3.5 磁盘与 tmpfs 配额 |

## 背景

§7.3.2 的加固清单中 `--read-only` 只保护 rootfs。`/workspace` 是可写 bind mount（§5.5），LLM 生成的代码可以往里写满宿主机磁盘 —— 这是 §7.1 威胁表「写满磁盘」那一格唯一没堵上的缺口。

同时 `--read-only` 意味着 `/tmp` 只能挂 tmpfs，而 **tmpfs 吃的是宿主机内存，不是磁盘**。

## 决策

| 目标 | 限额 | 机制 |
|---|---|---|
| `/workspace` | **5 GB / thread** | XFS project quota |
| `/tmp` | **512 MB** | tmpfs `size=`，计入单沙箱 2GB 内存预算**之内** |

`projid` 由 sandbox-broker 维护 `thread_id → 数字 id` 的映射（`sandboxes` 表加一列）。

## 理由

XFS project quota 是**唯一能对 bind mount 目录做配额、且支持动态创建**的机制。per-thread 场景下容器数以十计、创建频繁，需要轻量。

**tmpfs 限容比磁盘配额更急**：不限容的话，一句 `dd if=/dev/zero of=/tmp/x` 就能写满宿主机内存、触发 OOM killer —— 而 §4.4 特意把沙箱上限从 24 压到 20、留 4 个余量防的正是 OOM killer 误杀 Postgres。**不限 tmpfs 等于那份余量白留了。**

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **Docker `--storage-opt size=`** | **它限制的是容器可写层，不是 bind mount**，对 `/workspace` 完全无效。这个误解很常见 |
| **每 thread 一个 LVM 卷** | 创建慢、数量受限、需特权操作，不适合 per-thread 动态创建 |
| **每 thread 一个 loop 设备 + ext4 镜像** | 同上，且 loop 设备数量有上限 |
| **不做配额，靠监控告警** | 磁盘写满是瞬时的，告警来不及。§7.1 把「代码失控」判为高频常态而非异常 |

## 后果

**正面**：
- 堵上加固清单最后一个缺口
- 配额调整不需要重建容器

**代价**：
- **要求承载 `/data/sandbox` 的文件系统是 XFS 且以 `prjquota` 挂载** —— 这是一条部署前提，已写入 §8.5 运维清单
- broker 要维护 `projid` 映射，多一份状态
- **配额不等于总量有界**：workspace 在容器销毁后仍留在卷里（§5.5），总占用是「历史 thread 数 × 最多 5GB」而非「活跃沙箱数 × 5GB」。需要 §6.5 的归档回收策略，**扩容只是推迟撞墙**
- 5GB 中 `pip` 装的科学计算栈就占 1–2 GB（rootfs 只读，装不进 site-packages）。建议把常用栈**预装进沙箱镜像**

## 重新评估的触发条件

- 文件系统无法使用 XFS（届时退到 loop 设备方案）
- 5GB 在实际使用中不够（先考虑预装基础包，再考虑提额）
- workspace 总量撞到磁盘上限而归档策略仍未落地
