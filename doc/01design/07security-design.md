# 安全设计

| 项 | 值 |
|---|---|
| 上游 | [总体架构](./01architecture.md) |
| 相关决策 | [ADR-0002](./adr/0002-sandbox-isolation-gvisor.md) · [ADR-0004](./adr/0004-sandbox-broker-docker-sock.md) · [ADR-0010](./adr/0010-self-hosted-accounts-rbac.md) · [ADR-0011](./adr/0011-cookie-session-not-oauth2.md) · [ADR-0012](./adr/0012-plain-http-intranet.md) · [ADR-0015](./adr/0015-sandbox-disk-quota-xfs.md) |

本文从威胁模型出发，定义认证授权、沙箱隔离、数据保护和防滥用措施。章节继续使用拆分前的 §7.x 编号，便于追溯历史引用。

---

## 7.1 威胁模型

明确「防谁」，否则安全设计会失焦：

| 威胁 | 可能性 | 后果 | 本设计的应对 |
|---|---|---|---|
| **LLM 生成的代码失控**（死循环、fork 炸弹、写满磁盘、误删文件） | **高** —— 这是常态，不是攻击 | 宿主机资源耗尽，影响全体用户 | §7.3.2 资源限制 + 超时、§7.3.5 磁盘与 tmpfs 配额 |
| **沙箱逃逸**（代码利用内核漏洞突破容器） | 中 | 宿主机失守 | §7.3 gVisor + 加固清单 |
| **越权访问他人数据** | 中 | 教师看到别人的研究数据 | §6.3 数据层隔离 |
| **配额滥用** | 中 | LLM 费用失控 | §6.4、§7.5 |
| **外部定向攻击** | **低** —— 内网部署，用户是实名师生 | — | 不作为主要驱动因素 |

**关键判断**：用户是学院的实名师生而非匿名公网用户，威胁模型主要是**「agent 生成的代码写错了或失控」**，而不是定向攻击。这一判断直接支撑了 [ADR-0002](./adr/0002-sandbox-isolation-gvisor.md) 中「gVisor 足够、不需要 Firecracker」的结论。

> §7.2.1 引入 `student` 角色后这一判断**基本不变** —— 学生同样是校内实名用户。但需注意学生的**主动探测意愿**通常高于教师（好奇心驱动的沙箱逃逸尝试），这提高了 [实施计划基线](../03plan/CLAUDE.md) 中 P1 沙箱加固的必要性，不宜再往后拖。

## 7.2 认证与授权

**账号自建，不对接学校统一身份认证。** 论证见 [ADR-0010](./adr/0010-self-hosted-accounts-rbac.md)。

### 7.2.1 角色与课题组

| 角色 | 会话与数据 | 课题组共享资源 | 管理能力 |
|---|---|---|---|
| **管理员 `admin`** | 仅自己的 | — | 创建 / 禁用账号、管理课题组与成员、查看与调整任意用户配额、查看全局用量与审计日志 |
| **教师 `teacher`** | 仅自己的 | 所属组**可读可写** | — |
| **学生 `student`** | 仅自己的 | 所属组**可读可写**，与教师同权 | — |

- **管理员不能查看他人的会话内容与上传数据。** 这条边界落在数据访问层，见 §6.3
- **一个用户可同属多个课题组**，可见性走**并集**（`user_groups` 关联表，§6.2）
- **不引入组内角色**（组长 / 成员），读写权限只由全局 `role` 决定
- 组内共享**仅限配置类资源**（skill、智能体提示词）；**不共享**会话、数据文件、产物
- `teacher` 与 `student` 权限完全相同，**区别只在配额档位**（§6.4）

> 组内共享的 skill、自定义系统提示词、MCP 接入**本期均不实现**（[总体架构的系统范围](./01architecture.md)）。此处先定角色模型与共享边界，是为了让 §6.2 的表结构将来不必推倒重来。
>
> **P3 定案（2026-08-08）：角色模型照建，`groups` / `user_groups` 两张表不建。** 上面那句「让表结构将来不必推倒重来」在这两张表上不成立 —— 它们各只有三列与两列，没什么可推倒的，理由见 §6.2 与 [P3 计划 §7.6](../03plan/P3-plan.md)。**本节其余内容（三种角色、管理员不能看他人会话、`teacher` 与 `student` 只差配额）P3 全部落地。**

### 7.2.2 认证方式

**HttpOnly Cookie + 服务端 Session（存 Redis）。不用 OAuth2，不用 JWT。** 论证见 [ADR-0011](./adr/0011-cookie-session-not-oauth2.md)。

| 项 | 取值 |
|---|---|
| 凭据载体 | HttpOnly + `SameSite=Lax` Cookie |
| Session 存储 | Redis |
| 有效期 | 7 天滑动过期 |
| 多端登录 | 允许并存 |

**两个实现上的坑**：

1. **SSE 的凭据携带** —— `@microsoft/fetch-event-source`（§5.2）默认**不带**凭据，须配置 `credentials: 'include'`，否则 SSE 请求 401
2. **Cookie 无 `Secure` 标志** —— [运维设计的部署拓扑与容量输入](./08operation-design.md) 走 HTTP，凭据在内网链路明文。已按 §7.1 接受，记入 [风险登记](./09risk-register.md)

## 7.3 沙箱隔离（核心）

Agent 要写并运行分析代码，内网部署又意味着数据不能交给外部托管的 code execution 服务，因此必须自建沙箱。这是整个架构中最重的一块。

### 7.3.1 隔离方案

采用 **Docker + gVisor (runsc)**。选型论证（含 Firecracker 的对比与放弃理由）见 [ADR-0002](./adr/0002-sandbox-isolation-gvisor.md)。

### 7.3.2 安全加固清单

逐条落到容器创建参数：

```
--runtime=runsc                  # gVisor
--network=none                   # 或自定义 bridge + iptables 白名单（见 7.3.3）
--read-only                      # rootfs 只读
--tmpfs /tmp:rw,noexec,nosuid,size=512m   # /tmp 必须限容，见 7.3.5
--cap-drop=ALL
--user=1000:1000                 # 非 root
--memory=2g --cpus=1
--pids-limit=128
--security-opt=no-new-privileges
+ /workspace 磁盘配额 5GB（XFS project quota，见 7.3.5）
+ 单次执行 wall-clock 超时（如 120s）
+ stdout/stderr 输出大小上限（防止把网关 OOM）
```

### 7.3.3 已知陷阱

**陷阱一：`--network=none` 会让 `pip install` 全部失败。**

Agent 一定会想装包。必须给沙箱配一个内网 pypi 镜像（清华 / 阿里源，或自建 devpi），网络策略从 `none` 改成「只允许访问镜像源 + 内网数据源」的白名单 bridge。

> **P1 定案：不做，沙箱保持 `--network=none`**（2026-08-03，理由见 [P1 计划 §2.2](../03plan/P1-plan.md)）。
> 本条写于 P0 之前，前提是「agent 一定会想装包」，而 P0 实测的前提已经变了：镜像预装了 pandas / numpy / matplotlib 与中文字体，全程没有装包需求。
>
> 更要紧的是**它与加固清单直接冲突**：`--read-only` 使 `pip` 只能装到 `HOME` 下，而 `HOME=/tmp` 是 512MB 且 `noexec` 的 tmpfs —— 装得下的包跑不起来，跑得起来的包装不下。要支持装包，得先给出一条可写且可执行的路径，那是对加固清单的实质放松，不能顺手做。
>
> **代价**：agent 遇到预装栈覆盖不到的分析方法（如 `statsmodels`）会直接卡住，且零出网下它的错误信息不会指向「装不了包」。缓解：把可用库清单写进系统提示词；实测缺哪个就加进镜像重新构建。
> **重新评估的触发条件**：教师的分析需求反复撞到缺库，且加库频率高到无法靠重建镜像跟上。

**陷阱二：不要把 `docker.sock` 挂进 worker 容器。**

那等于给 worker 宿主机 root 权限，worker 一旦被 agent 生成的代码影响就全线失守。改成一个独立的 **sandbox-broker** 服务持有 `docker.sock`，worker 通过它间接操作。**8 个工具与会话目录的物理访问全部经 broker**（只挡容器不挡数据的话，边界只剩一半），API 清单与理由见 [ADR-0004](./adr/0004-sandbox-broker-docker-sock.md)。P1 已落地，见 [`app/broker/`](../../app/broker/)。

### 7.3.4 沙箱的网络策略

沙箱**不需要访问公网**。模型调用发生在 worker 侧，不经过沙箱。沙箱的出站访问仅限：

- 内网 pypi 镜像（装包）
- 内网数据源（若有）

这条策略与 [风险登记的已解除阻塞](./09risk-register.md) 的出网通路是**两件独立的事** —— worker 需要出网，沙箱不需要。

### 7.3.5 磁盘与 tmpfs 配额

堵的是 §7.1 威胁表里「写满磁盘」那一格 —— 加固清单最后一个缺口。选型论证见 [ADR-0015](./adr/0015-sandbox-disk-quota-xfs.md)。

| 目标 | 限额 | 机制 |
|---|---|---|
| `/workspace` | **5 GB / thread** | XFS project quota（`projid` 由 `thread_id` 派生，不查表，见 §6.2） |
| `/tmp` | **512 MB** | tmpfs `size=`，计入单沙箱 2GB 内存预算**之内** |

```bash
# 前提：承载 /data/sandbox 的文件系统以 XFS + prjquota 挂载（部署前提，见 §8.5）
# 路径原样拼进去，不加引号 —— `-c` 后面那串不经 shell，xfs_quota 自己按空白分词
# 且不做去引号。加了引号它会把引号当成路径的一部分，报 ENOENT 却退出 0
xfs_quota -x -c "project -s -p /data/sandbox/{thread_id} {projid}" /data/sandbox
xfs_quota -x -c "limit -p bhard=5g {projid}" /data/sandbox
```

**设完必须回读，且判据不能取退出码**（2026-08-09，[P4 §8.13](../03plan/P4-plan.md)）。实测发现这套配额**从 P1 起就一直没有生效过**，而三层判据没有一层照得出来 —— 三个真因各自独立，任何一个都足以让配额归零：

| 真因 | 表现 |
|---|---|
| 路径被 `shlex.quote` 加了引号（仓库在 `~/文档/` 下，含非 ASCII） | 目录**一个都没被认领**，`limit` 设上的上限只挂在 projid 上，没有任何目录受它约束 |
| loop 挂载重启后没挂回来 | `data/sandbox` 落回 ext4，配额无从谈起 |
| broker 容器里没有承载 workspace 的**块设备节点** | `xfs_quota` 连挂载点都打不开（`CAP_SYS_ADMIN` 只是必要条件） |

**三种情况下 `xfs_quota` 都是把错误打到 stderr 然后退出 0** —— `subprocess.run(check=True)` 因此一次都不触发。判据改为：认领结果直接用 `FS_IOC_FSGETXATTR` 读目录 inode 上的 projid 与继承标志，硬上限用 `report -p` 回读（[`app/sandbox/quota.py`](../../app/sandbox/quota.py)）。**两样都要查**：`limit` 对没认领的目录照样成功，单看限额会得到「有上限但没人受它约束」的假绿。

**定案 fail-closed：配额设不上就拒绝建会话**，而不是静默地无配额跑下去。对一条安全控制，失败该关不该放。**代价是 XFS 挂载从加固项变成了硬启动依赖**（重启后没挂回来则 `POST /threads` 一律 500），已写进 §8.5。CI 与没挂 XFS 的开发机走 `NoQuota`，不受影响。

**`/tmp` 限容比磁盘配额更急**：`--read-only` 使 `/tmp` 只能挂 tmpfs，而 tmpfs 吃的是**宿主机内存**。不限容则一句 `dd` 就能写满内存触发 OOM killer —— 而 [运维设计的部署拓扑与容量输入](./08operation-design.md) 特意留的 4 个沙箱余量防的正是 OOM killer 误杀 Postgres。

**配额不等于总量有界。** 按 §5.5，容器销毁后 workspace 仍留在卷里，故总占用是「历史 thread 数 × 最多 5GB」而非「活跃沙箱数 × 5GB」，worst case 是 TB 级。[运维设计的部署拓扑与容量输入](./08operation-design.md) 的「磁盘充裕」**不解除这个问题**，扩容只是推迟撞墙。原本指望的解法是 §6.5 的归档回收，而**它已于 P4 定案不做** —— 实测典型会话仅 ~350KB、推算 2.5 GB/年，worst case 与实际分布差着四个数量级（§6.5.1）。**因此这一条现在靠的是「实测量级远低于上界」，不是靠机制**，重估触发条件见 §6.5。

> **实现提醒**：rootfs 只读使 `pip` 装的包落在 workspace 里，而科学计算栈就要 1–2 GB。建议**把常用栈预装进沙箱镜像**，否则 5GB 里小一半被基础包吃掉，且每个 thread 都要重装一遍。

### 沙箱镜像预装清单（P0 实测得出）

| 项 | 为什么必须预装 |
|---|---|
| pandas / numpy / matplotlib | 见上方实现提醒 |
| **中文字体**（如 `fonts-noto-cjk`）并配好 matplotlib 默认字体 | 实测 agent 画中文标题的图时发现字体缺失，自行执行 `pip install matplotlib --upgrade`、`apt-cache search chinese font` 去找 —— 零出网下这些**必然全部失败**，纯浪费轮次与 token。**同时要在提示词里显式禁止 agent 自己找字体**（[智能体设计 §6](./03agent-design.md)），只预装不改提示词仍会浪费轮次，因为 agent 不知道字体已装好 |

**另需在容器启动时设 `HOME` 与 `MPLCONFIGDIR` 指向可写路径。** `--read-only` + 非 root 运行（§7.3.2）使容器内没有可写的家目录，matplotlib 与 pip 会把告警刷到 stdout，**混进 `execute` 的返回值里干扰 LLM**。这不是美观问题 —— agent 会把告警当成执行出错。

## 7.4 数据安全

[总体架构的合规约束](./01architecture.md) 的合规结论（不含敏感数据、不受等保约束、允许出网）**大幅简化了本节** —— 原本因合规未定而必须保留的脱敏与加密要求现在都不成立：

| 项 | 结论 |
|---|---|
| 发往 LLM 的数据脱敏 | **不需要**。[总体架构的合规约束](./01architecture.md) 已确认教师数据可送公有云 |
| MinIO / Postgres 静态加密 | **不需要**。无涉密内容，落盘加密的收益不抵运维复杂度 |
| 服务间 mTLS（网关 ↔ worker ↔ broker） | **不需要**。全部在 Docker Compose 内部网络，不暴露到宿主机外 |
| 传输加密（浏览器 ↔ Nginx） | **不启用**，走 HTTP。理由与代价见 [运维设计的部署拓扑与容量输入](./08operation-design.md) |

> **TODO** ｜ 待回答：审计日志。哪些操作需要留痕（登录、管理员改配额、管理员禁用账号、数据导出）？留多久？
> 注意这一条**没有**被合规结论解除 —— 它的驱动因素不是合规，而是 §7.2.1 中管理员权限较大，需要可追溯。

## 7.5 限流与防滥用

- **配额层**：per-user token 日配额 + 并发 run 上限（§6.4）
- **接口层**：网关侧的请求频率限制，用 Redis 实现分布式计数
- **沙箱层**：容器数上限 + 单容器资源上限（§7.3.2、§8.1）

> ~~**TODO** ｜ 待回答：具体限流阈值与算法，以及触发限流后返回给前端的提示语~~
> **已关闭（2026-08-08，[P3 计划 §7.2](../03plan/P3-plan.md)）：P3 给一版保守初值，宁松勿紧。**
>
> 这道闸与另外两道的性质不同：**它误伤的是正常用户**（配额与并发超限至少还对应着真实的资源占用，频率限制拦的往往只是手快）。因此初值往松里定，等真实请求分布出来再收紧。算法用滑动窗口（Redis 计数，与 §6.1 选 Redis 的理由一致）。

---
