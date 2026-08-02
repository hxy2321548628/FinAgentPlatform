"""探针 4：HITL 中断恢复前后 `tool_call_id` 是否稳定。

这是 ADR-0014「工具幂等键用 tool_call_id，broker 侧去重」整个方案的支点，
架构文档 §5.6 与 §10.2 都把它标为「待验证」。

顺带回答两个连带问题：
  a. 中断恢复后，工具究竟被 backend 执行了几次（§5.3「整个节点从头重跑」的实际影响）
  b. backend 方法内部能不能拿到 tool_call_id —— 若拿不到，ADR-0014 的机制没有落点

需要 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from _common import OUT_DIR, fresh_workspace, load_env, require, section, verdict
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

load_env()

CALL_LOG: list[dict[str, Any]] = []


class InstrumentedBackend(FilesystemBackend):
    """记录每一次 write 调用，并探查此刻能从 langgraph 上下文里看到什么。"""

    def write(self, file_path: str, content: str):  # noqa: ANN201
        entry: dict[str, Any] = {"file_path": file_path, "content_head": content[:40]}
        try:
            from langgraph.config import get_config

            cfg = get_config()
            configurable = dict(cfg.get("configurable", {}))
            entry["config_keys"] = sorted(configurable)
            # ADR-0014 需要的键：backend 能否自己拿到 tool_call_id
            entry["tool_call_id_visible"] = any("tool_call_id" in k for k in configurable)
        except Exception as exc:  # noqa: BLE001
            entry["config_error"] = f"{type(exc).__name__}: {exc}"
            entry["tool_call_id_visible"] = False
        CALL_LOG.append(entry)
        return super().write(file_path, content)


def tool_call_ids(state) -> list[dict[str, str]]:  # noqa: ANN001
    """把 state 里所有 AIMessage 的 tool_calls 和 ToolMessage 的 tool_call_id 摘出来。"""
    found = []
    for msg in state.values.get("messages", []):
        for call in getattr(msg, "tool_calls", None) or []:
            found.append({"kind": "AIMessage.tool_calls", "name": call.get("name"), "id": call.get("id")})
        if getattr(msg, "tool_call_id", None):
            found.append({"kind": "ToolMessage", "name": getattr(msg, "name", None), "id": msg.tool_call_id})
    return found


async def main() -> None:
    section("探针 4 · interrupt 恢复前后 tool_call_id 稳定性")
    results: list[dict] = []
    require("DEEPSEEK_API_KEY")

    workspace = fresh_workspace("probe4")
    agent = create_deep_agent(
        model=ChatDeepSeek(model=require("MODEL_MAIN"), temperature=0),
        backend=InstrumentedBackend(root_dir=str(workspace), virtual_mode=True),
        system_prompt="你是数据分析助手，工作目录是 /workspace。直接完成用户要求，不要多问。",
        checkpointer=InMemorySaver(),
        interrupt_on={"write_file": {"allowed_decisions": ["approve", "reject", "edit"]}},
    )
    config = {"configurable": {"thread_id": "probe4-thread"}}
    prompt = "把一行文本 hello 写进 /workspace/note.txt，只做这一件事。"

    # ---------------------------------------------------------- 跑到中断
    await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]}, config)
    state_before = await agent.aget_state(config)

    interrupts = [i for task in state_before.tasks for i in task.interrupts]
    results.append(
        verdict(
            "§5.3：中断在工具调用边界之前发生，可用 aget_state() 检出",
            bool(interrupts),
            f"检出 {len(interrupts)} 个 pending interrupt；state.next={state_before.next}",
        )
    )
    if not interrupts:
        raise SystemExit("没有触发中断，探针无法继续 —— 检查模型是否真的调了 write_file")

    payload = interrupts[0].value
    payload_shape = (
        {k: type(v).__name__ for k, v in payload.items()} if isinstance(payload, dict) else type(payload).__name__
    )
    results.append(
        verdict(
            "§5.3：interrupt payload 是 action_requests + review_configs 双数组",
            isinstance(payload, dict) and {"action_requests", "review_configs"} <= set(payload),
            f"实际结构 {payload_shape}",
        )
    )

    ids_before = tool_call_ids(state_before)
    writes_before = [e for e in ids_before if e["name"] == "write_file"]
    print(f"\n中断前的 tool_call_id：{json.dumps(ids_before, ensure_ascii=False)}")
    calls_before_resume = len(CALL_LOG)

    # ------------------------------------------------------------ 批准恢复
    await agent.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
    state_after = await agent.aget_state(config)
    ids_after = tool_call_ids(state_after)
    print(f"恢复后的 tool_call_id：{json.dumps(ids_after, ensure_ascii=False)}")

    ai_ids_before = {e["id"] for e in writes_before}
    ai_ids_after = {e["id"] for e in ids_after if e["kind"] == "AIMessage.tool_calls" and e["name"] == "write_file"}
    tool_ids_after = {e["id"] for e in ids_after if e["kind"] == "ToolMessage" and e["name"] == "write_file"}

    results.append(
        verdict(
            "**ADR-0014 的支点**：write_file 的 tool_call_id 在恢复前后一致",
            bool(ai_ids_before) and ai_ids_before == ai_ids_after,
            f"中断前 {sorted(ai_ids_before)} → 恢复后 {sorted(ai_ids_after)}",
        )
    )
    results.append(
        verdict(
            "工具结果（ToolMessage）回填的 tool_call_id 与中断前的调用 id 一致",
            bool(tool_ids_after) and tool_ids_after <= ai_ids_before,
            f"ToolMessage.tool_call_id = {sorted(tool_ids_after)}",
        )
    )

    # -------------------------------------------- 连带问题 a：backend 被调了几次
    results.append(
        verdict(
            "§5.3「恢复时整个节点从头重跑」对 write 的实际影响",
            None,
            f"backend.write 全程被调用 {len(CALL_LOG)} 次（中断前 {calls_before_resume} 次，恢复后 {len(CALL_LOG) - calls_before_resume} 次）。"
            f"调用明细：{json.dumps(CALL_LOG, ensure_ascii=False)}",
        )
    )

    # ---------------------------------- 连带问题 b：backend 内部能否看到 tool_call_id
    visible = any(e.get("tool_call_id_visible") for e in CALL_LOG)
    seen_keys = sorted({k for e in CALL_LOG for k in e.get("config_keys", [])})
    results.append(
        verdict(
            "ADR-0014 落点：backend 方法内部能直接拿到 tool_call_id",
            visible,
            f"`get_config()['configurable']` 里可见的键：{seen_keys}。"
            + ("" if visible else " → **拿不到**。`BackendProtocol.write(file_path, content)` 也不带该参数，去重键需要另找传递路径（见 FINDINGS）"),
        )
    )

    out = OUT_DIR / "probe4_interrupt_toolcallid.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "interrupt_payload": payload if isinstance(payload, dict) else str(payload),
                "ids_before": ids_before,
                "ids_after": ids_after,
                "backend_calls": CALL_LOG,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\n明细 → {out}")


if __name__ == "__main__":
    asyncio.run(main())
