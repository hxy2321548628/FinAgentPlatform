# ADR-0014：工具幂等键用 `tool_call_id`，broker 侧去重

| 项 | 值 |
|---|---|
| 状态 | 已接受（支点与落点均已验证，**去重键改用 `(thread_id, checkpoint_ns)`**） |
| 日期 | 2026-07-31（2026-08-02 / 08-03 依 P0 探针两次修订） |
| 决策人 | hxy |
| 主文档关联 | §3.2 权衡三、§5.6 工具接口 |

## 背景

§3.2 依据 LangGraph 文档确认了重放边界：checkpointer 的保护粒度是**节点级**（靠 pending writes），但有两种情况节点会整个重跑：

1. 崩溃发生在**工具执行途中**（该节点还没有 pending write）—— 异常路径
2. **HITL 恢复时整节点从头重跑** —— 官方明确 *"any code that ran before the `interrupt()` will execute again"*。**这是正常路径，每次审批都发生**

四个工具中 `read_file` / `list_files` 纯读、`write_file` 全量覆盖写，均已幂等；只有 **`execute_python` 不可控** —— 代码由 LLM 生成，可能追加写、`pip install`、删文件、累加计数。

> **补记一（2026-07-31，[ADR-0016](./0016-sandbox-filesystem-backend.md)）**：工具集已改为 DeepAgents 内置的 8 个，上面这段对工具集的描述不再成立 —— 不幂等的还有 `edit_file` 与 `delete`。**本 ADR 的决策与理由不变，只是适用范围从「`execute_python` 一个工具」扩大到「全部写操作」**。逐工具的分析见[智能体设计 §3.3](../03agent-design.md)。
>
> **补记二（2026-08-02，P0 探针实测）**：上面第 2 条「HITL 恢复时整节点从头重跑，每次审批都发生」**与实测不符**。
>
> 中断实际发生在 `HumanInTheLoopMiddleware.after_model` 节点（`state.next` 实测为 `('HumanInTheLoopMiddleware.after_model',)`），而工具在**另一个节点 `tools`** 里执行。审批通过后重跑的是 after_model 钩子 —— 它只组装审批请求，没有副作用。全程 `backend.write` 只被调用 1 次。
>
> **官方那句 *"any code that ran before the `interrupt()` will execute again"* 仍然成立，但「`interrupt()` 之前的代码」指的是 middleware 钩子内的代码，不是工具本身。**
>
> 后果：本 ADR 的**紧迫性下降** —— 幂等键要防的从「正常路径每次审批必然发生的重复执行」变回「崩溃路径的重复执行」。决策本身不变（崩溃路径仍需要它），但它不再是 P3 HITL 的前置条件，见下方「后果」的修订。

## 决策

worker 调 broker 时带上该次工具调用的 **`tool_call_id`**，**broker 侧去重**：命中已执行记录则直接返回缓存结果，不进沙箱。

存储用 Redis hash，TTL 跟随沙箱生命周期（§5.5）。结果体积大的（artifacts）存引用不存内容。

## 理由

`tool_call_id` 来自 `AIMessage.tool_calls[].id`。重放时这条 AIMessage 是**从 checkpoint 读出来的**，而不是重新调 LLM 生成的，因此同一次工具调用在任何次重放中 id 都相同。

> **已验证**（2026-08-02，P0 探针）。跑一次 `interrupt` → `Command(resume=...)`，中断前的 `AIMessage.tool_calls[0].id`、恢复后的同一字段、以及回填的 `ToolMessage.tool_call_id` 三者完全相同（`call_00_HkfA0hE3SqEjh8XzLwfG8896`）。**支点成立。**

**去重放在 broker 而不是 worker**：broker 是沙箱的唯一入口（[ADR-0004](./0004-sandbox-broker-docker-sock.md)），而 worker 可能有多个副本且会崩溃重启 —— 把去重状态放在 worker 侧起不到跨副本、跨重启的作用。

**`write_file` 保持全量覆盖语义、不提供追加写**，是为了让它天然幂等，避免再为它单独做一套幂等键。

> **已验证**（2026-08-02，P0 探针）：`write_file` 对已存在文件确为**覆盖**（`error=None`，内容被替换），不是此前存疑的 create-only。

## 落地方式：去重键取什么（2026-08-03 定案）

> **结论先行**：**去重键改用 `(thread_id, checkpoint_ns)`，不用 `tool_call_id`。**
> 二者的重放稳定性都已实测通过，选前者只是因为 backend 拿得到它而拿不到后者。
> 本 ADR 标题里的 `tool_call_id` 因此过时，保留标题只为不打断 ADR 编号引用。

### 为什么不能用 `tool_call_id`



P0 探针暴露了一个本 ADR 原先没有考虑的问题：**worker 侧唯一能改的是 `SandboxBackend` 的实现，而它拿不到 `tool_call_id`。**

- `BackendProtocol.write(file_path, content)` / `edit(...)` / `delete(...)` 的签名里没有这个参数；
- middleware 拿得到（`runtime.tool_call_id`），但**不往 backend 传**；
- 在 backend 方法内调 `langgraph.config.get_config()`，`configurable` 只有 `__pregel_*`、`checkpoint_id`、`checkpoint_map`、`checkpoint_ns`、`thread_id` —— **没有 `tool_call_id`**。

### 实测：`checkpoint_ns` 满足去重键的两个必要条件

模拟真实场景 —— 让 backend 在第一次 `write` 时抛异常（崩溃在工具执行途中），再用同一 thread 恢复重跑，比对两次调用看到的上下文：

| 条件 | 结果 |
|---|---|
| **① 重放稳定** | `thread_id` / `checkpoint_ns` / `checkpoint_id` / `__pregel_task_id` **四项全部一致**，工具入参也一致 |
| **② 能区分同一轮的不同调用** | ✅ 成立。见下 |

条件②原先我判断会不成立 —— `checkpoint_ns` 的形态是 `tools:<uuid>`，其中的 uuid 就是 `__pregel_task_id`，看起来是按**节点**生成的，那么同一个 `AIMessage` 里的多个 `tool_calls` 会共享同一个 ns 而撞键。

**实测推翻了这个推断**：让模型一次吐出两个并行 `write_file`，两次调用拿到的是**不同**的 ns：

```
/workspace/a.txt → tools:fd422cb9-d8b8-c0ae-510d-64ed2e099a1c
/workspace/b.txt → tools:3ad455cb-c5f8-4f8d-5ade-b005f0a631a7
```

**LangGraph 把每个工具调用扇出成独立 task**，因此 `checkpoint_ns` 实际是**按工具调用**唯一的。

### 决策

**去重键 = `(thread_id, checkpoint_ns)`。** 两项都能在 backend 方法内从 `langgraph.config.get_config()["configurable"]` 直接读到。

不需要再拼「操作名 + 路径 + 内容 hash」—— 那是在怀疑条件②时准备的补强，既然 ns 本身已按调用唯一，加进去只是让键变长、让「同一调用重放」在参数被上游改动时误判成新调用。

被放弃的另两条：

| 方案 | 放弃理由 |
|---|---|
| **A. contextvar 中转** `runtime.tool_call_id` | 依赖 middleware 执行顺序这一框架内部细节，且异步并发下 contextvar 隔离要额外论证。`checkpoint_ns` 是 LangGraph 自己维护的公开配置，更稳 |
| **C. 不做工具层去重** | HITL 路径确实不需要（见「补记二」），但崩溃在工具执行途中仍会重复执行。实测已确认该路径真实存在（本节的模拟就是它） |

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **不做幂等，接受重复执行** | ~~HITL 每次审批都会重跑，等于每审批一次就重复执行一次代码。~~ **依「补记二」此理由不成立** —— HITL 不导致工具重复执行。仅余崩溃路径的数据污染风险，故此备选**重新进入候选**（上方方案 C） |
| **worker 侧去重** | worker 多副本且会重启，去重状态无法跨副本、跨重启生效 |
| **让沙箱执行本身幂等** | 代码由 LLM 生成，不可控 |
| ~~**worker 自构造键**~~ | ~~成本更高，作为退路保留~~ → **因落点问题转为主选**，见上方方案 B |

## 后果

**正面**：
- ~~HITL 可以安全落地 —— 这是 P3 HITL 的**前置条件**~~ → 依「补记二」，HITL 不导致工具重复执行，**本 ADR 不再是 HITL 的前置条件**，两者可解耦排期
- §5.4 的 run 级自动重试上限可以从 1 次放开到 3 次
- 去重逻辑集中在 broker 一处

**代价**：
- ~~**支点未经验证**~~ → **已验证成立**（2026-08-02）
- ~~**落点未定**~~ → **已定案**（2026-08-03）。改用 `(thread_id, checkpoint_ns)`，见上方「落地方式」
- **键改成了框架内部概念**。`checkpoint_ns` 是 LangGraph 的编排细节而非本平台的领域概念，broker 的去重表因此与 LangGraph 的任务扇出方式耦合。若框架改变扇出粒度（例如把同一轮的多个工具调用合成一个 task），条件②会失效而**不报错，只是静默误判**。已列入下方重估触发条件
- broker 需要维护缓存，多一份状态
- **残留风险**：崩溃发生在执行途中时没有缓存结果（只在完成时写），仍会重跑，且部分副作用已落盘。本方案解决不了，需额外记 `started` 标记才能识别 —— P0 不做
- 缓存结果占用 Redis 内存，需配 TTL 与大小上限

## 重新评估的触发条件

- ~~P0 探针发现 `tool_call_id` 在重放中不稳定 → 转退路方案~~（2026-08-02 已验证稳定）
- ~~验证 `checkpoint_ns` 是否稳定~~（2026-08-03 已验证稳定且按调用唯一）
- **LangGraph 改变工具调用的任务扇出粒度** —— 若同一轮的多个工具调用不再各占一个 task，`checkpoint_ns` 将不再按调用唯一，去重会静默误判。**升级 langgraph 时须重跑并行场景复验**：探针已随 `app/spike/` 删除，从 git 取回后即可跑 —— `git show 30b0fa6:app/spike/probe5_replay_key_stability.py`（同目录 `_common.py` 一并取回，不依赖 Docker）
- 出现「执行到一半」造成实际数据损坏 → 补 `started` 标记与人工提示
- DeepAgents 开始把 `tool_call_id` 透传给 backend → 届时可换回语义更清晰的键
