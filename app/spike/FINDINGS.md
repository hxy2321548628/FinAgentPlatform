# P0 探针结论

| 项 | 值 |
|---|---|
| 日期 | 2026-08-02 |
| 环境 | deepagents 0.7.1 · langgraph 1.2.10 · langchain 1.3.14 · langchain-deepseek 1.1.0 · Python 3.13 |
| 模型 | `deepseek-v4-pro`（temperature=0） |
| 对应任务 | [架构文档 §11](../../doc/01design/01architecture.md) 的 P0 探针①②③④ + [智能体设计 §7.3](../../doc/01design/03agent-design.md) 的观察项 |

五个探针全部跑完（①–④ 于 2026-08-02，⑤ 于 08-03 补做）。**19 项核对通过，4 项与设计文档不符**，另有 3 项文档没预料到的发现，以及 1 条据此定案的幂等键方案。

**当前无待决事项** —— 探针提出的三个问题（`tool_call_id` 稳定性、幂等键落点、`checkpoint_ns` 稳定性）已全部关闭。

---

## 一、与文档不符的四项

### 1. `async_create_deep_agent()` 不存在 ❌

- **文档写的**：[03agent-design §2.1](../../doc/01design/03agent-design.md) 与 [架构 §5.3](../../doc/01design/01architecture.md)、[§4.3 技术栈表](../../doc/01design/01architecture.md) 都写 `async_create_deep_agent()`，架构 §5.3 还说「`async_create_deep_agent` 的区别是传 `is_async=True`，影响 SubAgentMiddleware 的工具执行与子 agent 调用方式」。
- **实际**：0.7.1 只导出 `create_deep_agent`，且**没有 `is_async` 参数**。异步改由 `AsyncSubAgent` / `AsyncSubAgentMiddleware` 表达；主 agent 直接 `await agent.ainvoke(...)` / `agent.astream(...)` 即可。
- **影响**：小。本期不开子 agent（§2.1），异步能力不受影响 —— 探针 2、4 都是全 async 跑通的。但文档三处措辞要改，且 §5.3 那句关于 `is_async` 的解释整句作废。

### 2. `SandboxBackendProtocol` 没有从 `deepagents.backends` 导出 ⚠️

存在于 `deepagents.backends.protocol`，但 `backends/__init__.py` 不导出它。实现 [ADR-0016](../../doc/01design/adr/0016-sandbox-filesystem-backend.md) 时须写全路径 import。属于实现提示，不影响决策。

### 3. `write_file` 是覆盖，不是 create-only ✅（文档存疑项已解决）

[03agent-design §3.1](../../doc/01design/03agent-design.md) 把 `write_file` 的单次幂等标为「⚠️ 待验证」，§3.3 说「DeepAgents 文档把 `WriteResult` 标注为 create-only」。

**实测（FilesystemBackend 与 DockerSandbox 两个后端结果一致）**：第二次 write 同一路径 `error=None`，内容被覆盖。protocol 的文档字符串也写明 *"creating it or overwriting it if it already exists"*。

→ **`write_file` 单次幂等一栏可从「⚠️ 待验证」改为「✅」**。但它仍在 broker 去重范围内 —— 覆盖写在「重放时内容已被后续步骤改过」的场景下依然会污染数据。

§3.3 对 `edit_file` 与 `delete` 不幂等的判断则**完全正确**，实测：

| 操作 | 首次 | 重放 |
|---|---|---|
| `edit_file` | `occurrences=1` | `Error: String not found in file: '…'` |
| `delete` | `path='/workspace/probe3.txt'` | `Error: '/workspace/probe3.txt' not found` |

### 4. ADR-0014 的支点成立，落点另找（2026-08-03 已定案）

这是本轮最重要的发现，分两半：

**支点成立** ✅ —— `tool_call_id` 在 `interrupt` 恢复前后完全一致：

```
中断前 AIMessage.tool_calls[0].id = call_00_HkfA0hE3SqEjh8XzLwfG8896
恢复后 AIMessage.tool_calls[0].id = call_00_HkfA0hE3SqEjh8XzLwfG8896   ← 相同
恢复后 ToolMessage.tool_call_id    = call_00_HkfA0hE3SqEjh8XzLwfG8896   ← 相同
```

[架构 §5.6](../../doc/01design/01architecture.md) 与 [§10.2 风险表](../../doc/01design/01architecture.md) 里「`tool_call_id` 重放稳定性未经验证」这条风险**可以关闭**。

**落点不成立** ❌ —— **backend 方法内部拿不到 `tool_call_id`**：

- `BackendProtocol.write(file_path, content)` / `edit(...)` / `delete(...)` 的签名里没有 `tool_call_id`；
- middleware 拿得到（`runtime.tool_call_id`），但**不往 backend 传**；
- 在 backend 方法里调 `langgraph.config.get_config()`，`configurable` 只有 `['__pregel_call', '__pregel_checkpointer', '__pregel_read', '__pregel_replay_state', '__pregel_runtime', '__pregel_scratchpad', '__pregel_send', '__pregel_task_id', 'checkpoint_id', 'checkpoint_map', 'checkpoint_ns', 'thread_id']` —— **没有 `tool_call_id`**。

ADR-0014 的机制是「worker 传 `tool_call_id`，broker 对全部写操作去重」，而 worker 侧唯一能改的就是 backend 实现，它恰好看不到这个 id。

**已由探针⑤解决（2026-08-03）：去重键改用 `(thread_id, checkpoint_ns)`，见下方第五节。**

---

## 二、文档没预料到的三项

### 5. HITL 审批恢复**不会**导致工具重复执行 ★

[架构 §3.2](../../doc/01design/01architecture.md) 那张重放表把「HITL 审批恢复 → 整节点从头重跑」标为**每次审批必然发生**，并据此得出「必须在工具层做幂等键」和「run 级自动重试上限压到 1 次」两个结论。

**实测不是这样**：中断发生在 `HumanInTheLoopMiddleware.after_model`（`state.next` 实测为 `('HumanInTheLoopMiddleware.after_model',)`），而工具在**另一个节点** `tools` 里执行。全程 `backend.write` 只被调用 **1 次**（中断前 0 次，批准后 1 次）。

即：重跑的是 middleware 的 after_model 钩子，那里只是组装审批请求，没有副作用。**工具本身不重复执行。**

→ 这不推翻幂等键方案（崩溃路径仍需要它），但把它从「正常路径每次必然发生」降级为「异常路径才发生」。**§3.2 那张表的最后一行、§10.2 的「写操作重复执行」风险等级、以及 §5.4「run 级重试上限压到 1 次」的理由都需要按此重估。**

### 6. DeepSeek 有 prompt cache，配额不能按 input_tokens 直接算 ★

`usage_metadata.input_token_details.cache_read` 显示了大量缓存命中：

| 运行 | 模型调用 | input | 其中 cache_read | 未命中 | output | 其中 reasoning |
|---|---|---|---|---|---|---|
| 完整分析 | 17 次 | 304,640 | 189,312（**62.1%**） | 115,328 | 8,701 | 1,670 |
| 廉价任务 | 2 次 | 5,918 | 5,760（97.3%） | 158 | 90 | 36 |

**对 [§6.4 配额](../../doc/01design/01architecture.md) 的直接影响**：cache_read 的计费单价远低于未命中部分，按 `input_tokens` 总数设配额会高估成本约 1.6 倍，且会惩罚长会话（会话越长缓存命中率越高、边际成本越低，却被扣得越多）。配额口径应至少把 `cache_read` 与未命中分开记，`usage_metadata` 里两个数都现成。

### 7. `reasoning_content` 与正文分开流式输出，§5.2 缺一个事件类型 ★

`deepseek-v4-pro` 的思考过程走 `AIMessageChunk.additional_kwargs.reasoning_content`，与 `content` 是两个字段，交替流出：

```json
{"__type__": "AIMessageChunk", "content": "", "additional_kwargs": {"reasoning_content": "The"}}
```

[§5.2 的事件类型表](../../doc/01design/01architecture.md) 只有一个 `token`。若把两者都映射成 `token`，前端会把思考过程和正式答复混在一起渲染。**建议加一个 `reasoning` 事件类型**（或给 `token` 的 `data` 加 `channel: "content" | "reasoning"` 字段）。

---

## 三、可以回填 §5.2 的实测结构

`astream(stream_mode=["updates","messages","custom"], subgraphs=True)` 的 chunk 形状为 `(namespace, mode, payload)`。全量样本见 `out/probe2_quick/stream_chunks.jsonl`（67 条，保真）与 `out/probe2/stream_chunks.jsonl`（8213 条，完整分析）。

**观测到的 `updates` 节点名**（注意：不是按工具名分节点，全部工具共用一个 `tools` 节点）：

| 节点 | 出现次数（完整分析） | payload |
|---|---|---|
| `PatchToolCallsMiddleware.before_agent` | 1 | `null` |
| `model` | 17 | `{"messages": [AIMessage]}` |
| `tools` | 16 | `{"messages": [ToolMessage]}` |

**据此修正 [§5.2 的映射表](../../doc/01design/01architecture.md)**：

| 平台事件 | 实测来源 | 关键字段 |
|---|---|---|
| `token` | `messages` 模式的 `AIMessageChunk.content` | `content` |
| `reasoning`（**新增**） | `messages` 模式的 `AIMessageChunk.additional_kwargs.reasoning_content` | 同上 |
| `tool_call` | `updates` 模式 **`model`** 节点的 `AIMessage.tool_calls` | `{name, args, id, type:"tool_call"}` |
| `tool_result` | `updates` 模式 **`tools`** 节点的 `ToolMessage` | `{name, content, tool_call_id, status:"success"\|"error"}` |
| `todo.updated` | 未观测到 —— 本次运行 agent 一次都没调 `write_todos` | 待补 |
| `subagent.*` | 未观测到 —— 未开子 agent，`ns` 全程为 `()` | 契约可保留 |

文档 §5.2 映射表原写「`type="updates"`, `data={<工具节点>: …}` → `tool_call` / `tool_result`」，**实际是 `model` 节点出 `tool_call`、`tools` 节点出 `tool_result`，两者不在同一个节点**，这行要改。

补充：`tool_call` 也能从 `messages` 模式的 `AIMessageChunk.tool_call_chunks` 增量拿到（`{name, args:"", id, index, type:"tool_call_chunk"}`），若要做「工具参数逐字流式渲染」就用它；只要一次性拿完整调用则用 `updates`。

`custom` 模式全程 0 条 —— 符合预期，本次 backend 没用 `get_stream_writer()`。[§8.1 的 `sandbox.queued` 排队事件](../../doc/01design/01architecture.md)靠它，等排队逻辑实现后才能观测。

---

## 五、探针⑤：幂等键定案（2026-08-03 补做）

`probe5_replay_key_stability.py`。目的是给上面第 4 条找落点。

**模拟真实场景**：让 backend 在第一次 `write` 时抛异常（崩溃在工具执行途中 —— 由发现 5，HITL 路径不需要验），再用同一 thread 恢复重跑，比对两次调用看到的上下文。

**条件① 重放稳定** ✅ —— 四个候选字段全部一致：

```
thread_id         probe5-thread              → probe5-thread
checkpoint_ns     tools:aba4ce70-…           → tools:aba4ce70-…
checkpoint_id     None                       → None
__pregel_task_id  aba4ce70-…                 → aba4ce70-…
```

工具入参（路径 + 内容 hash）也一致。顺带复核 `tool_call_id` 在崩溃重放前后同样一致（发现 4 验的是 HITL 路径，这里补了崩溃路径）。

**条件② 能区分同一轮的不同调用** ✅ —— 这一条我原先判断会**不**成立。`checkpoint_ns` 形如 `tools:<uuid>`，其中的 uuid 就是 `__pregel_task_id`，看着是按**节点**生成的，那么同一个 `AIMessage` 里的多个 `tool_calls` 应该共享同一个 ns 而撞键。

实测推翻了这个推断。让模型一次吐出两个并行 `write_file`：

```
/workspace/a.txt → tools:fd422cb9-d8b8-c0ae-510d-64ed2e099a1c
/workspace/b.txt → tools:3ad455cb-c5f8-4f8d-5ade-b005f0a631a7
```

**LangGraph 把每个工具调用扇出成独立 task**，所以 `checkpoint_ns` 实际按**调用**唯一。

**结论：去重键 = `(thread_id, checkpoint_ns)`。** 不需要再拼「操作名 + 路径 + 内容 hash」—— 那是怀疑条件②时准备的补强，既然 ns 已按调用唯一，加进去只会让「同一调用重放」在参数被上游改动时误判成新调用。

**代价要记住**：`checkpoint_ns` 是 LangGraph 的编排细节，不是本平台的领域概念。**若框架改变扇出粒度，条件②会失效且不报错，只是静默误判。** 升级 langgraph 时须重跑本探针的并行场景复验，已写进 [ADR-0014](../../doc/01design/adr/0014-tool-idempotency-key.md) 的重估触发条件。

---

## 六、其余观察项

| 观察项 | 结果 |
|---|---|
| §7.2 验收 case | ✅ 通过。agent 自行 `write_file` 写 `explore_data.py` 与 `volatility_analysis.py`，`execute` 运行，产出 `outputs/industry_volatility.png` |
| §4.3 产物是否落在 `outputs/` | ✅ 遵守。唯一产物在 `outputs/` 下，无散落 |
| 是否触发 pip install | ⚠️ 1 次。镜像已预装 pandas/numpy/matplotlib，agent 仍试图 `pip install matplotlib --upgrade` 并 `apt-cache search chinese font` 找中文字体 → **[§7.3.5 的预装清单必须含中文字体](../../doc/01design/01architecture.md)**，否则 agent 会在这上面浪费轮次，而沙箱零出网时这些命令还必然失败 |
| §5.2 的 N（截断轮数） | 一次典型分析 17 轮模型调用、16 次工具调用 |
| §6.4 配额输入 | 单次分析 313,341 token（见上方缓存拆分） |
| uid 对齐（§8.5 部署前提） | ✅ 容器以 `--user $(id -u):$(id -g)` 运行，宿主侧读写正常。但非 root 时容器内无可写 HOME，matplotlib/pip 会往 stdout 刷告警混进 `execute` 输出 —— **须设 `HOME` 与 `MPLCONFIGDIR`** |
| ADR-0009 模型 ID | ❌ **`MODEL_AUX` 拼错**：`.env` 与文档三处写 `deepseek-v4-flush`，接口实际返回的是 **`deepseek-v4-flash`** |

### BaseSandbox 与 §4.2 的取舍

`BaseSandbox` 只要求实现 `execute` / `upload_files` / `download_files` / `id` 四个成员，其余文件操作它会转成 shell 命令**进容器**执行。这与 [§4.2](../../doc/01design/03agent-design.md)「7 个文件工具由 broker 直读 bind-mount 目录、不需要容器在跑」相反。

两条路都可行：继承 `BaseSandbox` 省事但绑定容器；直接实现 `SandboxBackendProtocol` 才能拿到 §4.2 说的三条性质。本 spike 用的是前者（`docker_sandbox.py` 里 upload/download 已走宿主侧，ls/read/grep/glob 仍进容器）。**正式实现应选后者**，§4.2 的决策不变，但文档应写明这是「不用 BaseSandbox」的选择。
