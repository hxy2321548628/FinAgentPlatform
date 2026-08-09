# 金融学院智能体平台 — 智能体设计

| 项 | 值 |
|---|---|
| 文档状态 | **草稿**（本期范围内已定稿，下期内容为占位） |
| 当前版本 | v0.2 |
| 作者 | hxy |
| 上游文档 | [总体架构设计](./01architecture.md) |

### 版本历史

| 版本 | 日期 | 修改人 | 说明 |
|---|---|---|---|
| v0.1 | 2026-07-31 | hxy | 初稿。只覆盖「与平台契约耦合、改起来贵」的部分，其余显式推迟 |
| v0.2 | 2026-08-02 | hxy | **依 P0 探针实测回填**：改正 `async_create_deep_agent` 与模型 ID 笔误；`write_file` 存疑项定案为覆盖；回填 §5.2 的 N 与 §7.3 全部观察项；§6 新增中文字体约束 |

> **本文档的分工**：[总体架构](./01architecture.md)写的是**承载智能体的平台**，本文写**智能体本身**。二者的交界面是 §3 工具集与 §4 文件系统 —— 那也是本文的重点。
>
> **TODO 约定**与主文档一致：`> **TODO** ｜ 待回答：……` 表示骨架已就位但内容未定。

---

## 1. 范围与分期

**本期不做完善的智能体，只做端到端跑通**（与 §1.1 平台定位、§11 的 P0 口径一致）。

因此本文的取舍标准不是「重要不重要」，而是 **「改起来贵不贵」**：

| 判据 | 处理 |
|---|---|
| 一旦定下就被平台契约锁住（进事件流、进前端渲染分支、进数据表、进 broker 逻辑），改一次要动多处 | **本期定死** |
| 只在 worker 进程内部生效，不越过任何接口，改了别人无感 | **下期再做** |

### 1.1 本期必须定死的

| 项 | 本文章节 | 不定会怎样 |
|---|---|---|
| 工具清单与工具名 | §3 | 工具名出现在 §5.2 的 `tool_call` 事件、前端渲染分支、HITL 的 `when` 谓词、broker 去重表。改名要动四处，还要处理已落库的历史事件 |
| 文件系统后端 | §4 | 选错则沙箱里的代码**读不到** agent 写的文件，且文件内容进 checkpoint 撑爆 Postgres |
| 产物判定规则 | §4.3 | `artifacts` 表（§6.2）无从写入，前端渲染不出图 |
| 历史截断策略 | §5.2 | P0 跑长会话必然爆 context，然后临时打补丁 |

### 1.2 本期明确不做

| 项 | 为什么能推迟 |
|---|---|
| 提示词工程（措辞打磨、few-shot、金融领域知识注入） | 改一个字符串重启 worker 即可，不越过接口 |
| 子 agent 划分 | 见 §2.1。开启会让事件流出现嵌套（`ns` 变深），但契约（§5.2 映射表）已预留，届时是加实现不是改契约 |
| skill 库 / 用户自定义提示词 / MCP | 平台侧 §1.2 本就不做本期 |
| 效果评测体系 | 见 §7 |
| 摘要式上下文压缩 | 见 §5.2 |

---

## 2. Agent 形态

### 2.1 本期形态：单 agent，无嵌套

用 `create_deep_agent()` 构建**一个** agent，不划分子 agent，直接 `await agent.ainvoke(...)` / `agent.astream(...)` 驱动。

> **v0.1 写的是 `async_create_deep_agent()`，实测不存在**（deepagents 0.7.1 只导出 `create_deep_agent`，也没有 `is_async` 参数）。异步改由 `AsyncSubAgent` / `AsyncSubAgentMiddleware` 表达，只影响子 agent，本期不开子 agent 故不受影响 —— P0 探针已用全 async 路径跑通完整分析。

理由：子 agent 的价值是并行分解与上下文隔离，而本期的目标任务（读一份 CSV、算指标、出图）是线性的，拆了只增加调用轮次与 token。同时它会让事件流出现嵌套渲染需求，前端本期无必要承担。

### 2.2 DeepAgents 内置能力开关

| 能力 | 本期 | 说明 |
|---|---|---|
| 内置文件工具（`ls` / `read_file` / `write_file` / `edit_file` / `delete` / `glob` / `grep`） | **开** | 后端替换为自实现的 `SandboxBackend`，见 §4 |
| `execute`（shell 执行） | **开** | 由 `SandboxBackendProtocol` 提供，是代码执行的唯一入口 |
| `write_todos`（todo 规划） | **开** | 框架自带，且 §5.2 已定义 `todo.updated` 事件 |
| 子 agent | 关 | 见 §2.1 |
| skill | 关 | §1.2 |
| HITL 中断（`interrupt_on`） | P0 关，**P3 开** | 触发范围未定，见主文档 §5.3 的 TODO |

### 2.3 模型

沿用 [ADR-0009](./adr/0009-default-model-selection.md)：主模型 `deepseek-v4-pro`，辅模型 `deepseek-v4-flash`（v0.1 写的 `flush` 是笔误，2026-08-02 经 `GET /models` 核对改正）。

> **需要说明**：**本期辅模型实际上无处可用。** 辅模型的用武之地是子 agent 与上下文摘要压缩，而这两项本期都不做（§2.1、§5.2）。ADR-0009 的「辅助模型下沉」要到下期才真正生效 —— 现在把它写进配置只是占位，不要误以为已在省钱。

---

## 3. 工具集契约

**本期工具集 = DeepAgents 内置的 8 个工具，不自定义新工具。** 工具由 backend 驱动（§4），我们只换后端实现，不换工具层。

### 3.1 清单

| 工具 | 对应 backend 方法 | 单次幂等 | 需要活跃容器 | broker 去重 |
|---|---|---|---|---|
| `ls` | `ls(path)` | ✅ | ❌ | 否 |
| `read_file` | `read(file_path, offset=0, limit=2000)` | ✅ | ❌ | 否 |
| `glob` | `glob(pattern, path=None)` | ✅ | ❌ | 否 |
| `grep` | `grep(pattern, path=None, glob=None)` | ✅ | ❌ | 否 |
| `write_file` | `write(file_path, content)` | ✅ 覆盖写 | ❌ | **是** |
| `edit_file` | `edit(file_path, old_string, new_string, replace_all=False)` | ❌ | ❌ | **是** |
| `delete` | `delete(file_path)` | ❌ | ❌ | **是** |
| `execute` | `execute(command)` | ❌ | ✅ | **是** |

**「需要活跃容器」这一列是 §4.2 映射方式带来的结果** —— 七个文件工具由 broker 直接操作宿主机上的 bind-mount 目录，容器不在跑也能用；只有 `execute` 必须进容器。

### 3.2 工具名冻结

上表的 8 个名字**本期冻结**。它们已经或即将出现在四处：§5.2 的 `tool_call` / `tool_result` 事件 payload、前端的工具渲染分支、HITL `interrupt_on` 的键、broker 的 `tool_call_id` 去重表。

### 3.3 幂等：结论比主文档 §5.6 更强

主文档 §5.6 的结论是「只有 `execute_python` 有问题」。换成真实工具集后这条不再成立：

以下三条均已由 P0 探针实测（2026-08-02，`FilesystemBackend` 与容器后端结果一致）：

| 操作 | 首次 | 重放 | v0.1 的判断 |
|---|---|---|---|
| `edit_file` | `occurrences=1` | `Error: String not found in file: '…'` | ❌ 不幂等 —— **正确** |
| `delete` | `path='/workspace/x.txt'` | `Error: '/workspace/x.txt' not found` | ❌ 不幂等 —— **正确** |
| `write_file` | `error=None` | `error=None`，内容被覆盖 | ⚠️ 存疑 → **定案为覆盖** |

- **`edit_file` / `delete` 不幂等** —— 重放返回一个首次没有的错误。虽不破坏数据，但 **LLM 会看到一个第一次没看到的错误**，行为随之偏离。
- **`write_file` 单次幂等** —— DeepAgents 的 `BackendProtocol.write` 文档字符串写明 *"creating it or overwriting it if it already exists"*，实测确为覆盖，此前「create-only」的读法不成立。

**broker 的去重范围仍是「全部写操作」，`write_file` 不因单次幂等而豁免** —— 它防的是另一种情况：重放时文件内容已被后续步骤改过，此时覆盖写同样污染数据。

这样做的额外好处是：**单个工具是否幂等不再是正确性的前提**。去重命中即返回首次执行的缓存结果，包括错误结果 —— 重放看到的东西与首次完全一致。这比逐个工具论证幂等更稳，也更省心。

去重键与机制见 [ADR-0014](./adr/0014-tool-idempotency-key.md)。

> **2026-08-02 修订**：P0 探针发现 **HITL 审批恢复不会导致工具重复执行**（中断落在 middleware 钩子节点，工具在另一个节点执行，实测全程只调用 1 次）。因此本节要防的场景从「每次审批必然发生」缩回「崩溃路径」，去重仍要做但**不再是 HITL 的前置条件**。同时 ADR-0014 暴露出一个落点问题：**backend 拿不到 `tool_call_id`**，去重键怎么传尚未定案。

### 3.4 错误语义：返回，不抛

`BackendProtocol` 的硬性要求是 *"Always return structured results with error fields; never raise exceptions"*。这不是风格约定，两种做法的行为差异很大：

| 做法 | 后果 |
|---|---|
| **抛异常** | LangGraph 节点失败 → 整个 run 失败 → 触发 §5.4 的 run 级重试（本期上限 1 次）→ 教师看到任务挂了 |
| **返回 error 字段** | LLM 收到工具错误，自己决定改代码重试 / 换路子 / 告知用户 —— 这才是 agent 该有的行为 |

所以 `SandboxBackend` 内部的**一切**异常（broker 不可达、HTTP 超时、容器创建失败、配额超限、排队超时）都必须捕获并转成 `error` 字段。

### 3.5 沙箱排队的表达

`execute` 遇到无空闲沙箱时（§8.1 决定排队而非拒绝）：

```
execute() → 无空闲沙箱 → async 等待，不阻塞事件循环
              ↓ 每次排位变化
         get_stream_writer() 写 custom 事件 → §5.2 映射为 sandbox.queued { position }
              ↓ 拿到沙箱
         sandbox.ready → 进容器执行
```

**等待必须有上限**，超时后按 §3.4 返回 error 而非抛异常。

> **P0 落地方式（2026-08-03 步骤三定案，与上图不同）**：**沙箱在 run 开始时申请、run 结束时归还**，不是每次 `execute` 借还一次。排队因此发生在执行器里而非工具里，`sandbox.queued` / `sandbox.ready` 由执行器直接写事件日志，**不经过 `get_stream_writer()` 与 custom 通道** —— 那条路径至今没有一条实测样本。
>
> 改触发点的理由：沙箱本就按 thread 长驻（[ADR-0003](./adr/0003-sandbox-per-thread-lifecycle.md)，run 结束后还留 30 分钟才回收），提前到 run 开始申请只多占了 agent 推理的那几分钟，对占用时长的影响可以忽略；而懒申请要给 backend 加异步容器抽象与 run 级生命周期，为可忽略的收益换来一层复杂度。
>
> **代价是明确的**：一个从头到尾不执行代码的 run（纯问答）也会占一个沙箱名额。若 P0 观测到这类 run 占比可观，再改回懒申请。
>
> 超时时长取 **600 秒**（[架构 §8.1](./01architecture.md) 的「建议 10 分钟」），超时后 run 转 `failed` 且 `retryable=true`。这仍是拍的数，等 P0 攒够周转率数据再调。

---

## 4. 文件系统语义 ★

本章是智能体与平台耦合最深的地方，也是本期最贵的决策。

### 4.1 决策

**自实现 `SandboxBackend`，实现 DeepAgents 的 `SandboxBackendProtocol`，替换默认的 `StateBackend`。**

DeepAgents 目前没有 Docker 后端（内置的 `LocalShellBackend` 直接 `subprocess.run(shell=True)` 跑在宿主机上，官方标注 development-only，本平台绝不能用）。论证、备选与代价见 [ADR-0016](./adr/0016-sandbox-filesystem-backend.md)。

> **不要用 `BaseSandbox` 抄近路**（2026-08-02，P0 探针）。框架提供的这个基类只要求实现 4 个成员，但其余文件方法它会转成 shell 命令**进容器**执行 —— 那样 §4.2 下面的性质 2「文件工具不需要容器在跑」就不成立了。须直接实现 `SandboxBackendProtocol`（位于 `deepagents.backends.protocol`，未从 `deepagents.backends` 导出）。

### 4.2 路径映射

```
Agent 视角          /workspace/data.csv
                        ↕  SandboxBackend（worker 进程内，全 async）
                        ↕  HTTP
broker              宿主 /data/sandbox/{thread_id}/data.csv   ← 7 个文件工具在这一层完成
                        ↕  bind mount
沙箱容器            /workspace/data.csv                        ← execute 在这一层执行
```

三条由此成立的性质：

1. **`write_file` 写的文件，`execute` 跑的代码能直接 `open()` 读到** —— 二者在同一个命名空间。这正是不能用 `StateBackend` 的原因：那样文件只存在于 LangGraph state 里，沙箱内 `pd.read_csv()` 会 FileNotFound。
2. **文件工具不需要容器在跑。** §5.5 的沙箱 idle 30 分钟被回收后，翻看历史文件不必冷启动一个容器。
3. **checkpoint 只存路径与工具调用记录，不存文件内容** —— 这是替换 `StateBackend` 的直接收益，也是 §10.2「checkpoint 表膨胀」风险的主要缓解手段。

### 4.3 产物判定

约定目录：**`/workspace/outputs/`**。

```
execute 执行完 → broker 列出 outputs/ 下本次调用后 mtime 变化的文件
              → 随执行结果一并返回 artifacts[]
              → worker 上传 MinIO，写 artifacts 表（§6.2）
```

**为什么不 diff 整个 workspace**：workspace 上限 5GB（§7.3.5），每次 `execute` 全量 stat 太贵；且中间文件（下载的原始数据、临时 pickle）会被误判成产物塞进 MinIO。

**风险与退路**：这依赖 §6 的提示词要求 agent 把图存进该目录，而 LLM 不保证遵守。P0 记录实际遵守率；若不可靠，退到「diff 整个 workspace 但按扩展名白名单过滤」。

> **P0 首次观测（2026-08-02）**：遵守。完整验收 case 的唯一产物 `industry_volatility.png` 落在 `outputs/` 下，workspace 根目录只有 agent 自己写的两个 `.py` 与输入 CSV，无散落产物。**样本量只有 1 次，不足以下结论**，退路暂不启用，继续观察。

### 4.4 新增的攻击面

**broker 从「只 exec」变成「要碰文件」**，多出两件事必须做：

- **路径限制在 thread 根目录内** —— 规范化后校验前缀，挡住 `../` 穿越。agent 传来的路径是 LLM 生成的，属于 §7.1 的不可信输入
- **uid 一致性** —— 容器内进程写出的文件，broker 进程要能读写。需固定沙箱内运行用户的 uid/gid 并与 broker 对齐，否则会出现「agent 写得进、读不出」的诡异现象。这是一条部署前提，需并入 §8.5

---

## 5. 上下文管理

### 5.1 what 进上下文

| 内容 | 是否进 LLM 上下文 |
|---|---|
| 系统提示词 | ✅ 常驻 |
| 历史消息（含工具调用与结果） | ✅ 按 §5.2 截断 |
| 文件**内容** | ❌ 只在 `read_file` 显式读取时进入，不预加载 |
| todo 列表 | ✅ 框架维护 |

### 5.2 截断策略

本期用最简单可用的策略：**保留系统提示词 + 最近 N 轮完整对话，超出则整轮丢弃最早的**。

> **必须以「完整的一轮」为单位丢弃**，不能按 token 数从中间切。一个 `AIMessage` 带 `tool_calls` 必须与对应的 `ToolMessage` 同时存在或同时不存在 —— 切出「有调用无结果」的消息序列，LLM API 会直接报错。这是截断实现最常见的坑。

**本期不做摘要压缩。** 摘要每次要多花一次 LLM 调用，且必然丢信息；在「先跑通」的定位下不值得。下期做，届时辅模型（§2.3）才有用武之地。

**N 的取值：先取 20 轮**（2026-08-02，依 P0 探针②回填）。

实测一次典型分析（持仓 CSV → 按行业算年化波动率 → 出图）：**17 次模型调用、16 次工具调用**，即约 17 轮就跑完一个完整任务。N 取 20 能容纳一次完整分析不触发截断，同时挡住多轮追问后的无限增长。

> 这是单次观测得出的起始值，不是定论。真正该盯的是 token 而非轮数 —— 同一次分析里 `input_tokens` 从首轮 2,916 涨到末轮上万，轮数相同而上下文长度差一个量级。**若后续出现单轮上下文过长导致的失败，截断口径应从「最近 N 轮」改为「按 token 预算倒推轮数」。**

---

## 6. 提示词

**本期只写一版能跑通的最小系统提示词，不做工程化**（§1.2）。

但其中有几条**不是文风，而是契约的一部分**，改动会破坏平台行为：

| 硬约束 | 依据 |
|---|---|
| 工作目录是 `/workspace` | §4.2 |
| 图表等产物必须存到 `/workspace/outputs/` | §4.3，否则产物丢失 |
| 沙箱无公网。装包走内网 pypi 镜像，不要用 `requests` 从公网拉数据 | §7.3.4 |
| 代码先 `write_file` 成 `.py` 文件再 `execute` 运行，不要写成 shell 里的长 heredoc | 便于复查与重跑；P3 上 HITL 后，教师审批时需要看到完整脚本 |
| **画图直接用中文，不要自己找字体、不要 `pip install` 或 `apt` 装字体** | 见下方观测。镜像已预装中文字体并配好 matplotlib |

骨架：

```
你是金融学院的数据分析助手，帮助教师完成金融数据分析任务。

工作方式：
- 工作目录是 /workspace，你的文件工具和代码执行都在这里
- 写代码时，先用 write_file 存成 .py 文件，再用 execute 运行它
- 图表、报表等需要交付给用户的产物，一律存到 /workspace/outputs/
- 环境不能访问公网。装包用 pip（已配置内网镜像），不要从网上下载数据
- 画图直接用中文，环境已经装好中文字体并配成 matplotlib 默认。不要自己找字体、
  不要设置 rcParams 的字体、更不要用 pip 或 apt 装字体

分析要求：
- 说明你的分析思路，不要只给结果
- 对数据中的异常值、缺失值要明确指出如何处理的
```

> **P0 观测到的第一个真实失败模式（2026-08-02）**：agent 画中文标题的图时发现字体缺失，自行执行了
> `pip install matplotlib --upgrade; apt-cache search chinese font; apt list --installed | grep -i font`
> 来找中文字体。**这在零出网的沙箱里必然全部失败**，纯浪费轮次与 token。
>
> 两条应对，缺一不可：
> 1. **镜像预装中文字体**并配好 matplotlib 默认字体（记入[主文档 §7.3.5](./01architecture.md) 的预装清单）；
> 2. **提示词显式禁止 agent 自己找字体**（已加入上表硬约束）。
>
> 只做 1 不做 2 仍会浪费轮次 —— agent 不知道字体已装好，还是会先去查。
>
> **两条都做之后的复验（2026-08-03，步骤三实跑）**：同一个 case，**零次 `pip install`、零次找字体**，中文标题与轴标签直接渲染正常。轮次与 token 都降了：13 次工具调用（首轮 16 次）、186,372 token（首轮 313,341）。样本量同样只有 1 次，但这两条应对确实生效了。

> **TODO** ｜ 待回答：提示词工程整体待下期。包括金融领域术语与常用指标口径的注入、few-shot 示例、错误恢复引导。阻塞于 P0 积累真实的失败案例 —— 上面这条是第一个，继续积累。

---

## 7. 效果验证

### 7.1 本期不建评测体系

理由：没有基准数据集、没有标注、没有对照。建一套评测的成本远超收益，且在提示词还没定型时，评测出的数字指导不了任何决策。

### 7.2 P0 的验收就一个 case

与 §11 的 P0 口径一致：

> 给一份持仓 CSV，要求按行业分组计算年化波动率并画图 —— agent 能写出 Python、在沙箱中跑通、返回结果与图表，即通过。

**✅ 已通过**（2026-08-02）。agent 自行 `write_file` 写出 `explore_data.py` 与 `volatility_analysis.py`，`execute` 运行，产出 `outputs/industry_volatility.png`。

### 7.3 同时要记录的观察项

这些**不是通过条件**，是给后续章节回填数据用的。**首轮结果（2026-08-02，单次观测）**：

| 观察项 | 结果 | 回填到 |
|---|---|---|
| 完成一次分析的轮次与 token 分布 | 17 次模型调用、16 次工具调用；共 313,341 token（input 304,640 / output 8,701）。**input 中 62.1% 是 prompt cache 命中** | §5.2 的 N（已回填为 20）、[§6.4 配额](./01architecture.md) |
| agent 实际调用了哪些工具、频率如何 | `ls` / `read_file` / `write_file` / `execute`，未调 `write_todos`、`edit_file`、`delete`、`glob`、`grep` | [§5.3 HITL 触发范围](./01architecture.md) |
| 是否把产物存进了 `outputs/` | ✅ 遵守，无散落产物 | §4.3 的退路是否要启用 → 暂不启用 |
| 是否触发 `pip install`、装了什么 | ⚠️ 1 次。**不是为了装分析库，是为了找中文字体**（见 §6） | [§7.3.5 的镜像预装清单](./01architecture.md) → 须含中文字体 |
| `tool_call_id` 在 `interrupt` 恢复前后是否一致 | ✅ 完全一致 | [ADR-0014](./adr/0014-tool-idempotency-key.md) 的支点 → 已关闭 |

三条需要留意的：

- **本期不做 HITL（§2.2），但顺带发现审批恢复并不会让工具重复执行** —— 这削弱了 [ADR-0014](./adr/0014-tool-idempotency-key.md) 的紧迫性，详见 §3.3 的修订说明。
- **agent 一次都没调 `write_todos`**。§2.2 把它标为「开」且 [§5.2 已定义 `todo.updated` 事件](./01architecture.md)，但线性任务下框架不会触发它。该事件的 payload 仍无实测样本，前端渲染分支暂时无从对照。
- **prompt cache 命中率高达 62%**，直接影响 §6.4 的配额口径，详见主文档。

> **第三次观测最值得记的一条（2026-08-03，P0 步骤四验收）**：**同一份数据、同一个问题，
> 三次跑出的行业年化波动率相差一个量级**（第二次 9.63% / 19.41% / 33.54%，第三次
> 114.2% / 294.3% / 399.9%）。成因查明：第三次 agent 写了
> `group.sort_values('date')`，而测试数据的日期标签是循环的（`2026-01-01` ~ `01-28`
> 反复出现），按它排序把时间序列打乱，收益率变成跳变，标准差因此暴涨。
> 更讽刺的是它自己在上一行注释里写了「日期标签循环使用，但数据本身按时间顺序排列，
> 故直接按行序计算」，下一行就把这个判断推翻了。
>
> **这一条不是平台缺陷，日期循环是测试数据的特性，真实持仓数据不会这样。** 但它给出的
> 结论仍然成立且重要：**agent 在同一输入上的分析结果不稳定，而教师无从判断哪次是对的。**
> 这正是 §7.1「本期不建评测体系」那个 TODO 的第一份实证 —— 评测要验的不只是「跑没跑通」，
> 还得是「同一问题的答案是否可复现」。三次样本，不足以定结论，继续积累。

> **TODO** ｜ 待回答：评测方案。需要一组金标准用例（输入数据 + 期望结论）与打分方式。下期做，阻塞于提示词定型。

---

## 附录：与主文档的对应

| 本文章节 | 主文档 |
|---|---|
| §3 工具集契约 | §5.6 Agent 侧的工具接口（本文为准，主文档已同步） |
| §4 文件系统语义 | §5.5 沙箱生命周期、[ADR-0016](./adr/0016-sandbox-filesystem-backend.md) |
| §4.3 产物判定 | §5.1 时序图的 `artifacts[]`、§6.2 `artifacts` 表 |
| §2.2 HITL 开关 | §5.3 中断恢复 |
| §2.3 模型 | [ADR-0009](./adr/0009-default-model-selection.md) |
| §7.3 观察项 | §11 P0 探针 |
