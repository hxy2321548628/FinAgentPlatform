"""探针 5：崩溃重放时，worker 侧自构造幂等键的各字段是否稳定。

ADR-0014 的落地方案 B 打算用 (thread_id, checkpoint_ns, 操作, 路径, 内容 hash)
拼去重键 —— 因为探针 4 发现 backend 拿不到 tool_call_id。本探针验证这个支点。

模拟的是真实场景：**崩溃发生在工具执行途中**（探针 4 已证明 HITL 审批恢复
不会重跑工具，所以那条路径不需要验）。做法是让 backend 在第一次 write 时抛异常，
再用同一个 thread 恢复，比对两次调用看到的上下文是否一致。

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

load_env()

CALL_LOG: list[dict[str, Any]] = []

# 拼幂等键的候选字段。thread_id 与 checkpoint_ns 是方案 B 明确要用的，
# 另外两个顺带观测 —— 若它们更稳定，方案 B 可以改用。
KEY_FIELDS = ("thread_id", "checkpoint_ns", "checkpoint_id", "__pregel_task_id")


class CrashOnceBackend(FilesystemBackend):
    """第一次 write 时抛异常模拟崩溃，同时记录当次能看到的上下文。"""

    def __init__(self, root_dir: str) -> None:
        super().__init__(root_dir=root_dir, virtual_mode=True)
        self._crashed = False

    def write(self, file_path: str, content: str):  # noqa: ANN201
        from langgraph.config import get_config

        configurable = dict(get_config().get("configurable", {}))
        CALL_LOG.append(
            {
                "attempt": len(CALL_LOG) + 1,
                "file_path": file_path,
                "content_sha": hash(content),
                **{f: str(configurable.get(f)) for f in KEY_FIELDS},
            }
        )
        if not self._crashed:
            self._crashed = True
            # 模拟进程在工具执行途中挂掉。真实 backend 一律返回 error 不抛异常
            # （智能体设计 §3.4），这里是刻意为之。
            raise RuntimeError("模拟崩溃：工具执行途中进程挂掉")
        return super().write(file_path, content)


class RecordingBackend(FilesystemBackend):
    """只记录每次 write 看到的上下文，不制造崩溃。用于并行调用场景。"""

    def __init__(self, root_dir: str) -> None:
        super().__init__(root_dir=root_dir, virtual_mode=True)

    def write(self, file_path: str, content: str):  # noqa: ANN201
        from langgraph.config import get_config

        configurable = dict(get_config().get("configurable", {}))
        CALL_LOG.append({"file_path": file_path, **{f: str(configurable.get(f)) for f in KEY_FIELDS}})
        return super().write(file_path, content)


def tool_call_ids(state) -> list[str]:  # noqa: ANN001
    return [c["id"] for m in state.values.get("messages", []) for c in (getattr(m, "tool_calls", None) or [])]


async def main() -> None:
    section("探针 5 · 崩溃重放时幂等键各字段的稳定性")
    require("DEEPSEEK_API_KEY")
    results: list[dict] = []

    workspace = fresh_workspace("probe5")
    agent = create_deep_agent(
        model=ChatDeepSeek(model=require("MODEL_MAIN"), temperature=0),
        backend=CrashOnceBackend(str(workspace)),
        system_prompt="你是数据分析助手，工作目录是 /workspace。直接完成用户要求，不要多问。",
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "probe5-thread"}}
    prompt = "把一行文本 hello 写进 /workspace/note.txt，只做这一件事。"

    # ------------------------------------------------------ 第一次：撞崩溃
    try:
        await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]}, config)
    except Exception as exc:  # noqa: BLE001 - 就是要接住模拟的崩溃
        print(f"第一次执行如期崩溃：{type(exc).__name__}")

    state_mid = await agent.aget_state(config)
    ids_before = tool_call_ids(state_mid)

    # -------------------------------------------- 第二次：同 thread 恢复重跑
    await agent.ainvoke(None, config)
    state_after = await agent.aget_state(config)
    ids_after = tool_call_ids(state_after)

    results.append(
        verdict(
            "崩溃后节点确实重跑了（否则本探针无意义）",
            len(CALL_LOG) >= 2,
            f"backend.write 共被调用 {len(CALL_LOG)} 次",
        )
    )
    if len(CALL_LOG) < 2:
        raise SystemExit("节点没有重跑，无法比对")

    first, second = CALL_LOG[0], CALL_LOG[1]
    print(f"\n第一次：{json.dumps(first, ensure_ascii=False)}")
    print(f"重放后：{json.dumps(second, ensure_ascii=False)}")

    for field in KEY_FIELDS:
        results.append(
            verdict(
                f"`{field}` 在重放前后一致",
                first[field] == second[field],
                f"{first[field]!r} → {second[field]!r}",
            )
        )

    results.append(
        verdict(
            "工具入参（路径 + 内容）在重放前后一致",
            (first["file_path"], first["content_sha"]) == (second["file_path"], second["content_sha"]),
            f"{first['file_path']!r} → {second['file_path']!r}",
        )
    )
    results.append(
        verdict(
            "顺带复核：`tool_call_id` 在崩溃重放前后也一致",
            bool(ids_before) and ids_before == ids_after,
            f"{ids_before} → {ids_after}",
        )
    )

    stable = [f for f in KEY_FIELDS if first[f] == second[f]]
    results.append(
        verdict(
            "**ADR-0014 方案 B 是否成立**",
            "thread_id" in stable and "checkpoint_ns" in stable,
            f"重放中保持稳定的字段：{stable}；发生变化的：{[f for f in KEY_FIELDS if f not in stable]}",
        )
    )

    # ------------------------------------- 场景二：同一轮里的多个工具调用会撞键吗
    #
    # checkpoint_ns 内嵌的 UUID 就是 __pregel_task_id，即它是**按节点任务**生成的，
    # 不是按工具调用。若同一个 AIMessage 带多个 tool_calls，它们在同一个 tools 节点
    # 里执行 —— 那 checkpoint_ns 就区分不开这几次调用，方案 B 的键必须靠
    # (操作, 路径, 内容 hash) 才能拆开。这里实测确认。
    parallel_log: list[dict[str, Any]] = []
    CALL_LOG.clear()
    workspace2 = fresh_workspace("probe5_parallel")
    agent2 = create_deep_agent(
        model=ChatDeepSeek(model=require("MODEL_MAIN"), temperature=0),
        backend=RecordingBackend(str(workspace2)),
        system_prompt="你是数据分析助手，工作目录是 /workspace。直接完成用户要求，不要多问。",
        checkpointer=InMemorySaver(),
    )
    config2 = {"configurable": {"thread_id": "probe5-parallel"}}
    async for chunk in agent2.astream(
        {"messages": [{"role": "user", "content": "创建两个文件 /workspace/a.txt 和 /workspace/b.txt，内容分别是 A 和 B。"}]},
        config2,
        stream_mode="updates",
    ):
        for node, payload in (chunk or {}).items():
            if node != "model" or not payload:
                continue
            for msg in payload.get("messages", []):
                calls = getattr(msg, "tool_calls", None) or []
                if len(calls) > 1:
                    parallel_log.append({"count": len(calls), "names": [c["name"] for c in calls]})

    results.append(
        verdict(
            "观测到同一个 AIMessage 带多个 tool_calls",
            None,
            f"{parallel_log or '本次未出现并行调用，模型逐个串行调用'}",
        )
    )

    ns_per_call = {c["file_path"]: c["checkpoint_ns"] for c in CALL_LOG}
    distinct_ns = set(ns_per_call.values())
    print(f"\n并行 write 各自看到的 checkpoint_ns：{json.dumps(ns_per_call, ensure_ascii=False, indent=2)}")
    results.append(
        verdict(
            "并行工具调用各自拿到**不同**的 checkpoint_ns",
            len(CALL_LOG) > 1 and len(distinct_ns) == len(CALL_LOG),
            f"{len(CALL_LOG)} 次 write，{len(distinct_ns)} 个不同的 checkpoint_ns"
            + ("→ LangGraph 把每个工具调用拆成独立 task，键不会撞" if len(distinct_ns) == len(CALL_LOG) else "→ **会撞键**，方案 B 的键必须再含 (操作, 路径, 内容 hash)"),
        )
    )

    out = OUT_DIR / "probe5_replay_key_stability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"crash_replay": [first, second], "parallel": parallel_log, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n明细 → {out}")


if __name__ == "__main__":
    asyncio.run(main())
