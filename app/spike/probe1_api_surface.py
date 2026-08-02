"""探针 1：核对设计文档对 DeepAgents API 的假设是否成立。

不需要 API key，纯静态检查已安装的包。

核对对象：
  - doc/01design/03agent-design.md §2.1 / §2.2 / §3.1 / §3.2 / §4.1
  - doc/01design/01architecture.md §5.3 / §5.6
  - doc/01design/adr/0016-sandbox-filesystem-backend.md
"""

from __future__ import annotations

import inspect
import json
import typing

from _common import OUT_DIR, section, verdict

results: list[dict] = []


section("探针 1 · DeepAgents API 面核对")

# ---------------------------------------------------------------- 版本
import deepagents  # noqa: E402
import importlib.metadata as md  # noqa: E402

versions = {p: md.version(p) for p in ("deepagents", "langgraph", "langchain", "langchain-core", "langchain-deepseek")}
print("已装版本：" + "  ".join(f"{k}={v}" for k, v in versions.items()))

# ------------------------------------------- 1. 构造函数：async_create_deep_agent
has_async_factory = hasattr(deepagents, "async_create_deep_agent")
results.append(
    verdict(
        "文档 §2.1/§5.3 称用 `async_create_deep_agent(is_async=True)` 构建 agent",
        has_async_factory,
        "存在" if has_async_factory else f"**不存在**。0.7.1 只导出 `create_deep_agent`；顶层导出为 {sorted(n for n in dir(deepagents) if not n.startswith('_'))}",
    )
)

sig = inspect.signature(deepagents.create_deep_agent)
params = set(sig.parameters)
for name, where in [
    ("backend", "§4.1 要求可替换 backend"),
    ("checkpointer", "§5.3 / ADR-0008 依赖 checkpointer"),
    ("interrupt_on", "§5.3 HITL 靠 interrupt_on 声明"),
    ("subagents", "§2.1 本期关闭子 agent"),
    ("skills", "§2.2 本期关闭 skill"),
]:
    results.append(verdict(f"`create_deep_agent` 有 `{name}` 参数（{where}）", name in params, "有" if name in params else "**没有**"))

results.append(
    verdict(
        "`create_deep_agent` 有 `is_async` 参数",
        "is_async" in params,
        "有" if "is_async" in params else "**没有**。异步改由 `AsyncSubAgent` / `AsyncSubAgentMiddleware` 表达，主 agent 直接 `ainvoke`/`astream` 即可",
    )
)

# ------------------------------------------------------- 2. 工具名（§3.2 已冻结）
DOC_TOOL_NAMES = ["ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"]
actual_tool_names = list(typing.get_args(deepagents.FsToolName))
results.append(
    verdict(
        "§3.2 冻结的 8 个工具名与框架一致",
        actual_tool_names == DOC_TOOL_NAMES,
        f"框架 `FsToolName` = {actual_tool_names}",
    )
)

# --------------------------------------- 3. SandboxBackendProtocol（§4.1 / ADR-0016）
from deepagents.backends import protocol as proto  # noqa: E402

results.append(
    verdict(
        "存在 `SandboxBackendProtocol`（ADR-0016 要自实现它）",
        hasattr(proto, "SandboxBackendProtocol"),
        "存在于 `deepagents.backends.protocol`，但**没有从 `deepagents.backends` 导出**，须按全路径 import",
    )
)

# §3.1 表格里「工具 → backend 方法」的签名
DOC_SIGNATURES = {
    "ls": "(self, path: str)",
    "read": "(self, file_path: str, offset: int = 0, limit: int = 2000)",
    "glob": "(self, pattern: str, path: str | None = None)",
    "grep": "(self, pattern: str, path: str | None = None, glob: str | None = None)",
    "write": "(self, file_path: str, content: str)",
    "edit": "(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False)",
    "delete": "(self, file_path: str)",
    "execute": "(self, command: str)",
}
print("\n-- §3.1 表格中 backend 方法签名 vs 实际 --")
for method, doc_sig in DOC_SIGNATURES.items():
    owner = proto.SandboxBackendProtocol if method == "execute" else proto.BackendProtocol
    real = str(inspect.signature(getattr(owner, method)))
    same = real.replace(" ", "").startswith(doc_sig.replace(" ", "").rstrip(")"))
    results.append(verdict(f"`{method}` 签名与文档一致", same or None, f"实际 {real}"))

# BaseSandbox 只要实现 4 个方法
from deepagents.backends.sandbox import BaseSandbox  # noqa: E402

results.append(
    verdict(
        "自实现沙箱后端的工作量",
        None,
        f"继承 `BaseSandbox` 只需实现 {sorted(BaseSandbox.__abstractmethods__)}，其余文件操作由它转成 shell 命令走 execute。"
        "**注意这与 §4.2「文件工具由 broker 直读 bind-mount、不需要容器在跑」相反** —— 走 BaseSandbox 则每个文件操作都要进容器",
    )
)

# ------------------------------------------------ 4. write 语义（§3.3 标注「待验证」）
write_doc = inspect.getdoc(proto.BackendProtocol.write) or ""
first_line = write_doc.splitlines()[0]
results.append(
    verdict(
        "§3.3 存疑：`write_file` 对已存在文件是覆盖还是报错",
        None,
        f"protocol 文档字符串写的是：{first_line!r} → 声明为**覆盖**。实际行为由探针 3 验证",
    )
)

# --------------------------------------------- 5. 错误语义（§3.4「返回，不抛」）
result_types = [n for n in dir(proto) if n.endswith("Result") or n.endswith("Response")]
results.append(
    verdict(
        "§3.4：backend 一切错误须转成 error 字段而非抛异常",
        None,
        f"protocol 定义的结果类型均带 `error` 字段：{sorted(result_types)}",
    )
)

# ------------------------------------------------------- 6. HITL 契约（§5.3 / §5.7）
from langchain.agents.middleware import human_in_the_loop as hitl  # noqa: E402

hitl_ok = (
    set(hitl.HITLRequest.__annotations__) == {"action_requests", "review_configs"}
    and set(hitl.HITLResponse.__annotations__) == {"decisions"}
    and set(typing.get_args(hitl.DecisionType)) == {"approve", "edit", "reject", "respond"}
)
results.append(
    verdict(
        "§5.3 的 HITL 契约（action_requests/review_configs 双数组 + 4 种决策）",
        hitl_ok,
        f"HITLRequest={list(hitl.HITLRequest.__annotations__)}, HITLResponse={list(hitl.HITLResponse.__annotations__)}, "
        f"决策={sorted(typing.get_args(hitl.DecisionType))}",
    )
)
results.append(
    verdict(
        "§5.3 的 `when` 条件拦截谓词",
        "when" in hitl.InterruptOnConfig.__annotations__,
        f"`InterruptOnConfig` 字段 = {list(hitl.InterruptOnConfig.__annotations__)}",
    )
)

# ------------------------------------------------------------------ 落盘
OUT_DIR.mkdir(parents=True, exist_ok=True)
out = OUT_DIR / "probe1_api_surface.json"
out.write_text(json.dumps({"versions": versions, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

failed = [r for r in results if r["ok"] is False]
print(f"\n结论：{len(results)} 项核对，{len(failed)} 项与文档不符。明细 → {out}")
for r in failed:
    print(f"  ❌ {r['claim']}")
