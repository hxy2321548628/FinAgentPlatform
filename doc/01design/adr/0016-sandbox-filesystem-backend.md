# ADR-0016：自实现 DeepAgents 沙箱后端，不用内置 StateBackend

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-31 |
| 决策人 | hxy |
| 主文档关联 | §5.5 沙箱生命周期、§5.6 工具接口；[智能体设计 §4](../03agent-design.md) |

## 背景

DeepAgents 的文件工具（`ls` / `read_file` / `write_file` / `edit_file` / `delete` / `glob` / `grep`）由一个可插拔的 **backend** 驱动，默认是 `StateBackend` —— 文件存在 LangGraph state 里。

而本平台有一个真实的沙箱容器（§7.3），代码在 `/workspace` 里跑，文件落在宿主机 `/data/sandbox/{thread_id}/`（§5.5）。

主文档 §5.5 原先只写了一句「DeepAgents 的虚拟文件系统直接映射到这个 workspace」，**没有说明怎么映射**。这句话有两种读法，后果完全不同，必须定死。

DeepAgents 官方内置的后端有 `StateBackend` / `FilesystemBackend` / `LocalShellBackend` / `StoreBackend` / `ContextHubBackend` / `CompositeBackend`，**没有 Docker / 容器后端**。

## 决策

**自实现 `SandboxBackend`，实现官方的 `SandboxBackendProtocol`**（即 `BackendProtocol` 七个文件方法 + `execute`），通过 HTTP 调用 sandbox-broker。

分工是：**七个文件方法由 broker 直接操作宿主机 bind-mount 目录，只有 `execute` 进容器。**

工具层不动 —— 不自定义工具，仍用框架内置的那 8 个。

> **实现方式补充（2026-08-02，P0 探针）**：框架另提供一个基类 `BaseSandbox`，只要求实现 `execute` / `upload_files` / `download_files` / `id` 四个成员，其余文件方法它会**转成 shell 命令进容器执行**。这比直接实现协议省事得多。
>
> **但本 ADR 明确不用它** —— 走 `BaseSandbox` 就等于放弃了上面那条分工，「文件操作不依赖容器存活」这条理由随之作废。**要直接实现 `SandboxBackendProtocol`。**
>
> 另注：`SandboxBackendProtocol` 位于 `deepagents.backends.protocol`，**没有从 `deepagents.backends` 导出**，须写全路径 import。

> **实现方式补充（2026-08-03，P0 步骤二）**：`SandboxBackend` 内部把九个文件方法委托给 `FilesystemBackend`（`root_dir` 设为该 thread 的 workspace，`virtual_mode=True`），只有 `execute` 与产物判定自己写。
>
> **这不等于「改用 `FilesystemBackend`」** —— 下表排除它，针对的是「把它直接挂给 agent 当 backend」。本决策的四条分工全部保持：仍自实现 `SandboxBackend`、仍实现 `SandboxBackendProtocol`、文件操作走宿主 bind-mount 目录、只有 `execute` 进容器。变的只是磁盘操作由谁落笔。
>
> 成立的前提是 **P0 不拆 broker**（[P0 计划 §1.2](../../03plan/P0-plan.md) 已登记为 P1 欠债）：worker 进程直接持有 bind-mount 目录，因此「它操作的是 worker 的文件系统，不是沙箱的」这条排除理由不成立 —— P0 形态下两者是同一个目录。**P1 拆出 broker 时本补充随之失效**，届时文件操作改走 HTTP，需重新评估。
>
> 包装层必须补三件它不做的事，缺一条就违反[智能体设计 §3.4](../03agent-design.md)或让 agent 白跑：
>
> - **越界时它抛 `ValueError` 而非返回 `error` 字段** —— 不捕获就会让整个 run 失败
> - 它的虚拟根是 `/`，agent 视角的 `/workspace/x` 须先剥掉前缀
> - **`ls` / `glob` / `grep` 结果里的路径要翻译回去**（2026-08-03 步骤三实跑发现）。只做入向翻译的话，`ls('/workspace')` 会返回 `['/holdings.csv']`，而 agent 只能照抄这个路径 —— 下一步 `read_file('/holdings.csv')` 就被判越界，它没有别的办法知道该补前缀。**翻译必须是双向的**
>
> 其 `virtual_mode` 的防护已实测：`..`、workspace 外的绝对路径、**指向外部的符号链接**（规范化后校验，含符号链接目录）均被拦下，且穿越写入不落盘。

## 理由

**排除 `StateBackend` 的理由是决定性的，不是偏好问题**：文件只存在于 LangGraph state 中，磁盘上没有实体，所以沙箱里的 `pd.read_csv('/workspace/data.csv')` 会 FileNotFound。而「agent 写代码分析文件」正是本平台的全部业务（§1.1），这个组合根本不成立。

其余三点：

- **换后端而不是换工具集**，是因为 backend 正是框架给的扩展点。自定义工具意味着要重写框架自带的工具描述与提示词，还会失去 `edit_file` / `glob` / `grep` 这些白送的能力
- **checkpoint 不再承载文件内容**。`StateBackend` 会把文件写进 state，而 state 每个超步都进 checkpoint —— 一份 50MB 的 CSV 会被反复写进 Postgres。这是 §10.2「checkpoint 表膨胀」风险最直接的来源，换后端即消除
- **文件操作不依赖容器存活**。§5.5 的沙箱 idle 30 分钟后被回收，若文件操作也走容器，翻看历史文件就要冷启动一个容器。走宿主路径则没有这个代价

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **`StateBackend`（默认）** | **沙箱内的代码读不到文件**，业务场景直接不成立；且文件内容进 checkpoint 撑爆 Postgres |
| **`FilesystemBackend`** | 读写 worker 进程所在容器的真实路径。它操作的是 **worker 的文件系统，不是沙箱的** —— 同样读不到，且等于让 LLM 生成的路径直接作用于 worker 容器 |
| **`LocalShellBackend`** | 它的 `execute` 是宿主机上的 `subprocess.run(shell=True)`，**零隔离**，官方标注 development-only。与 §3.1 的 P0 质量属性「安全隔离」正面冲突 |
| **`StoreBackend` / `ContextHubBackend`** | 面向跨 thread 持久化与 LangSmith 托管，与本平台的 per-thread 卷模型（[ADR-0003](./0003-sandbox-per-thread-lifecycle.md)）不匹配，且 ContextHub 依赖外部服务（§2.2 内网部署） |
| **`CompositeBackend` 混合路由** | 本期没有需要分流的第二类路径。将来做跨 thread 记忆时可以用它把 `/memories/` 路由到 `StoreBackend`，那时再引入 |
| **继承 `BaseSandbox` 只补 4 个方法** | 省事，但它把 `ls` / `read` / `glob` / `grep` 全转成进容器的 shell 命令，直接推翻本决策「文件操作不依赖容器存活」那条理由。**代价换来的省事不值** —— 七个方法本就是薄封装 |
| **不用 backend，自定义 4 个工具**（主文档 §5.6 原方案） | 要重写框架的工具描述与配套提示词；失去 `edit_file` / `glob` / `grep`；且 `execute_python(code)` 这种「代码作为参数」的形态不如「先写文件再执行」可复查 —— P3 审批时教师看不到完整脚本 |

## 后果

**正面**：
- agent 写的文件与沙箱里跑的代码在同一命名空间，业务场景成立
- checkpoint 体积与文件大小解耦
- 文件操作不受沙箱回收影响，也不占用 §8.1 的 20 个沙箱名额
- 白得 `edit_file` / `glob` / `grep`

**代价**：
- **要自己写并维护一个 backend**。`BackendProtocol` 有七个方法，随框架升级可能变动 —— 这是版本升级时的固定检查项
- **broker 从「只 exec」扩大到「碰文件」，攻击面变大**。路径由 LLM 生成，属不可信输入，必须规范化后校验前缀，挡住 `../` 穿越
- **多一条部署前提：uid 一致性**。容器内进程写出的文件 broker 要能读写，需固定沙箱运行用户的 uid/gid 并与 broker 对齐，否则会出现「写得进、读不出」。已并入 §8.5
- **工具集变了，主文档 §5.6 的幂等结论随之失效**。`edit_file` / `delete` 也不幂等，broker 去重范围要扩到全部写操作，见[智能体设计 §3.3](../03agent-design.md) 与 [ADR-0014](./0014-tool-idempotency-key.md)
- 文件操作多一跳 HTTP。可接受 —— 都是 async，worker 只是在等 IO（§8.1）

## 重新评估的触发条件

- DeepAgents 官方推出容器 / Docker 后端 —— 届时评估是否切换，重点比对它的隔离方式是否满足 §7.3
- `BackendProtocol` 在框架升级中发生不兼容变更
- 出现跨 thread 共享文件的需求（届时引入 `CompositeBackend` 分流，而非改写本 backend）
