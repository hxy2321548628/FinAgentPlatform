# ADR-0004：`docker.sock` 由独立 sandbox-broker 持有

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-29 |
| 决策人 | hxy |
| 主文档关联 | §4.1 逻辑架构、§7.3.3 已知陷阱 |

## 背景

worker 需要创建、执行、销毁沙箱容器，这要求访问 Docker daemon。最直接的做法是把 `/var/run/docker.sock` 挂进 worker 容器。

## 决策

**不把 `docker.sock` 挂进 worker。**

引入一个独立的 **sandbox-broker** 服务，它是架构中**唯一持有 `docker.sock` 的组件**，只对内网暴露三个受限 API：

```
create  / exec  / destroy
```

worker 通过 HTTP 调用 broker 间接操作沙箱。

## 理由

**挂载 `docker.sock` 等于授予宿主机 root 权限。** 任何能访问该 socket 的进程都可以启动一个特权容器并挂载宿主机根目录，从而完全接管宿主机 —— 这是一条众所周知的提权路径。

而 worker 恰恰是**最不该拥有这个权限的组件**：它直接处理 LLM 的输出，负责解析和转发 agent 生成的内容，是整条链路上攻击面最大的位置。worker 一旦被 agent 生成的代码或构造的输出影响，就会全线失守。

拆出 broker 后，即使 worker 被攻破，攻击者能做的也只是调用三个受限 API —— 而不是获得宿主机 root。这把「一个组件被攻破」的爆炸半径从「整台服务器」压缩到「沙箱管理能力」。

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **worker 直接挂 `docker.sock`** | 等于给 worker 宿主机 root 权限。**这是本决策要避免的核心风险** |
| **Docker socket proxy**（如 tecnativa/docker-socket-proxy） | 能按 API 端点做白名单，比裸挂安全，但只能过滤 Docker API 的粒度，无法表达「只能操作属于本平台的沙箱容器」这类业务约束。自建 broker 可以 |
| **rootless Docker / Podman** | 能降低宿主机 root 风险，值得叠加使用，但不能替代职责隔离 —— worker 仍不该拥有创建任意容器的能力 |

## 后果

**正面**：
- worker 被攻破不再直接导致宿主机失守
- 沙箱的生命周期管理（LRU 回收、配额、健康检查，见 [ADR-0003](./0003-sandbox-per-thread-lifecycle.md)）集中在一处，不散落在每个 worker 里
- broker 是收敛所有沙箱操作的天然位置，便于统一加审计日志与资源限制

**代价**：
- **多一个服务要部署和维护**
- **broker 本身成为单点** —— 它挂了则所有沙箱操作不可用（见主文档 §8.2）
- broker 持有容器映射表，是有状态的。重启后需要依据容器 label 重新认领已有容器，这段恢复逻辑必须写对，否则会泄漏孤儿容器
- worker 到 broker 多一跳 HTTP 开销（相对于 LLM 调用耗时可忽略）

## 重新评估的触发条件

- 若将来沙箱改为非 Docker 实现（如 Firecracker），broker 的 API 抽象需要重新设计，但**职责隔离这一原则应当保留**
- broker 单点若成为可用性瓶颈，需考虑多实例 + 容器归属分片
