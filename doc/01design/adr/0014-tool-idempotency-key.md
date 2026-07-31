# ADR-0014：工具幂等键用 `tool_call_id`，broker 侧去重

| 项 | 值 |
|---|---|
| 状态 | 已接受（支点待 P0 验证） |
| 日期 | 2026-07-31 |
| 决策人 | hxy |
| 主文档关联 | §3.2 权衡三、§5.6 工具接口 |

## 背景

§3.2 依据 LangGraph 文档确认了重放边界：checkpointer 的保护粒度是**节点级**（靠 pending writes），但有两种情况节点会整个重跑：

1. 崩溃发生在**工具执行途中**（该节点还没有 pending write）—— 异常路径
2. **HITL 恢复时整节点从头重跑** —— 官方明确 *"any code that ran before the `interrupt()` will execute again"*。**这是正常路径，每次审批都发生**

四个工具中 `read_file` / `list_files` 纯读、`write_file` 全量覆盖写，均已幂等；只有 **`execute_python` 不可控** —— 代码由 LLM 生成，可能追加写、`pip install`、删文件、累加计数。

> **补记（2026-07-31，[ADR-0016](./0016-sandbox-filesystem-backend.md)）**：工具集已改为 DeepAgents 内置的 8 个，上面这段对工具集的描述不再成立 —— 不幂等的还有 `edit_file` 与 `delete`。**本 ADR 的决策与理由不变，只是适用范围从「`execute_python` 一个工具」扩大到「全部写操作」**。逐工具的分析见[智能体设计 §3.3](../03agent-design.md)。

## 决策

worker 调 broker 时带上该次工具调用的 **`tool_call_id`**，**broker 侧去重**：命中已执行记录则直接返回缓存结果，不进沙箱。

存储用 Redis hash，TTL 跟随沙箱生命周期（§5.5）。结果体积大的（artifacts）存引用不存内容。

## 理由

`tool_call_id` 来自 `AIMessage.tool_calls[].id`。重放时这条 AIMessage 是**从 checkpoint 读出来的**，而不是重新调 LLM 生成的，因此同一次工具调用在任何次重放中 id 都相同。

**去重放在 broker 而不是 worker**：broker 是沙箱的唯一入口（[ADR-0004](./0004-sandbox-broker-docker-sock.md)），而 worker 可能有多个副本且会崩溃重启 —— 把去重状态放在 worker 侧起不到跨副本、跨重启的作用。

**`write_file` 保持全量覆盖语义、不提供追加写**，是为了让它天然幂等，避免再为它单独做一套幂等键。

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **不做幂等，接受重复执行** | HITL 每次审批都会重跑，等于每审批一次就重复执行一次代码。对重复画图无所谓，对追加写数据是数据污染 |
| **worker 侧去重** | worker 多副本且会重启，去重状态无法跨副本、跨重启生效 |
| **让沙箱执行本身幂等** | 代码由 LLM 生成，不可控 |
| **worker 自构造键** `(thread_id, checkpoint_id, 节点内序号)` | 成本更高。**作为 `tool_call_id` 不稳定时的退路保留** |

## 后果

**正面**：
- HITL 可以安全落地 —— 这是 P3 HITL 的**前置条件**
- §5.4 的 run 级自动重试上限可以从 1 次放开到 3 次
- 去重逻辑集中在 broker 一处

**代价**：
- **支点未经验证** —— LangGraph 文档没有明说 `tool_call_id` 在重放中稳定。已并入 P0 探针（§11），验证成本几分钟；若不稳定则走退路方案
- broker 需要维护缓存，多一份状态
- **残留风险**：崩溃发生在执行途中时没有缓存结果（只在完成时写），仍会重跑，且部分副作用已落盘。本方案解决不了，需额外记 `started` 标记才能识别 —— P0 不做
- 缓存结果占用 Redis 内存，需配 TTL 与大小上限

## 重新评估的触发条件

- P0 探针发现 `tool_call_id` 在重放中不稳定 → 转退路方案
- 出现「执行到一半」造成实际数据损坏 → 补 `started` 标记与人工提示
- DeepAgents 改变工具调用的 id 生成方式
