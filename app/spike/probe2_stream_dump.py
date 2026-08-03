"""探针 2：跑一次真实分析，落盘 DeepAgents 实际吐出的流式结构。

对应架构文档 §11 的 P0 探针①②与 03agent-design §7.2/§7.3：
  - dump `astream(stream_mode=[...], subgraphs=True)` 的每一个 chunk，
    供回填 §5.2「Agent 层事件 payload 待定」的那张表
  - 记录轮次、token 消耗、调用了哪些工具、产物是否落在 outputs/、是否触发 pip install

验收 case 与 03agent-design §7.2 一致：给一份持仓 CSV，按行业分组算年化波动率并画图。
代码在 Docker 容器里执行（docker_sandbox.py），不落宿主机。

需要 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

import asyncio
import collections
import json
import sys
import random
from pathlib import Path
from typing import Any

from _common import OUT_DIR, dump_jsonl, fresh_workspace, load_env, require, section, verdict, write_out
from deepagents import create_deep_agent
from docker_sandbox import DockerSandbox, build_image, image_exists
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver

load_env()

# 03agent-design §6 的提示词骨架，一字未改
SYSTEM_PROMPT = """你是金融学院的数据分析助手，帮助教师完成金融数据分析任务。

工作方式：
- 工作目录是 /workspace，你的文件工具和代码执行都在这里
- 写代码时，先用 write_file 存成 .py 文件，再用 execute 运行它
- 图表、报表等需要交付给用户的产物，一律存到 /workspace/outputs/
- 环境不能访问公网。装包用 pip（已配置内网镜像），不要从网上下载数据

分析要求：
- 说明你的分析思路，不要只给结果
- 对数据中的异常值、缺失值要明确指出如何处理的
"""

TASK = "workspace 里有一份持仓数据 holdings.csv，请按行业分组计算各组的年化波动率，并画一张对比图。"

# 只为抓全 StreamPart 结构、不为跑分析的廉价任务。完整分析一次约 30 万 token，
# 而结构捕获两轮就够 —— 结构结论与任务复杂度无关。
QUICK_TASK = "用 ls 看一下 /workspace 下有哪些文件，然后直接告诉我文件名，不要做别的。"

# 专为生成事件映射器的测试 fixture 设计：几轮之内走遍 read_file / write_file /
# execute 三个工具，并**故意读一个不存在的文件**制造 status="error" 的 tool_result
# —— 那是 tool_result 映射的另一个结构分支，成功样本覆盖不到。
FIXTURE_TASK = (
    "按顺序做三件事，每件只做一次，不要重试也不要做别的："
    "① 读 /workspace/missing.csv（它不存在，你会看到报错，看到就继续下一步）；"
    "② 写一个 /workspace/hello.py，内容是打印 hello；"
    "③ 运行它。"
)

# 探针预置的输入文件，判定「agent 是否把产物存进 outputs/」时要排除
INPUT_FILES = {"holdings.csv"}


def make_holdings_csv(path: Path) -> None:
    """造一份可复现的持仓价格数据：3 个行业 × 2 只票 × 120 个交易日。"""
    random.seed(20260802)
    industries = {"银行": ["600036", "601288"], "白酒": ["600519", "000858"], "半导体": ["688981", "002371"]}
    vol = {"银行": 0.008, "白酒": 0.018, "半导体": 0.030}
    rows = ["date,ticker,industry,close"]
    for industry, tickers in industries.items():
        for ticker in tickers:
            price = 100.0
            for day in range(120):
                price *= 1 + random.gauss(0.0003, vol[industry])
                rows.append(f"2026-01-{day % 28 + 1:02d},{ticker},{industry},{price:.4f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


async def main(mode: str = "full") -> None:
    section("探针 2 · 真实分析 + StreamPart 结构落盘" + {"quick": "（quick：只抓结构）", "fixture": "（fixture：为映射器造测试样本）"}.get(mode, ""))
    require("DEEPSEEK_API_KEY")
    results: list[dict] = []

    name = {"quick": "probe2_quick", "fixture": "probe2_fixture"}.get(mode, "probe2")
    task = {"quick": QUICK_TASK, "fixture": FIXTURE_TASK}.get(mode, TASK)
    quick = mode != "full"
    workspace = fresh_workspace(name)
    make_holdings_csv(workspace / "holdings.csv")

    if not image_exists("zuel-spike-sandbox:latest"):
        build_image()

    chunks: list[dict[str, Any]] = []
    mode_shapes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    namespaces: collections.Counter = collections.Counter()

    with DockerSandbox(workspace) as sandbox:
        agent = create_deep_agent(
            model=ChatDeepSeek(model=require("MODEL_MAIN"), temperature=0),
            backend=sandbox,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=InMemorySaver(),  # 跑完要 aget_state 取最终消息与 token 用量
        )
        config = {"configurable": {"thread_id": f"{name}-thread"}, "recursion_limit": 60}

        print(f"提问：{task}\n（流式输出中，chunk 全量落盘）\n")
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": task}]},
            config,
            stream_mode=["updates", "messages", "custom"],
            subgraphs=True,
        ):
            # subgraphs=True 且 stream_mode 为 list 时，chunk 形如 (namespace, mode, payload)
            if isinstance(chunk, tuple) and len(chunk) == 3:
                namespace, mode, payload = chunk
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                namespace, (mode, payload) = (), chunk
            else:
                namespace, mode, payload = (), "<unknown>", chunk

            namespaces[str(namespace)] += 1
            if mode == "updates" and isinstance(payload, dict):
                for node in payload:
                    mode_shapes["updates"][node] += 1
            elif mode == "messages" and isinstance(payload, tuple) and payload:
                mode_shapes["messages"][type(payload[0]).__name__] += 1
            else:
                mode_shapes[str(mode)][type(payload).__name__] += 1

            chunks.append({"ns": list(namespace), "mode": mode, "payload": payload})

        final_state = await agent.aget_state(config)

    # ------------------------------------------------------------ 落盘
    jsonl = dump_jsonl(name, "stream_chunks.jsonl", chunks)

    # ------------------------------------------------------ 汇总观察项
    messages = final_state.values.get("messages", [])
    ai_messages = [m for m in messages if type(m).__name__ == "AIMessage"]
    tool_messages = [m for m in messages if type(m).__name__ == "ToolMessage"]
    tools_used = collections.Counter(
        call.get("name") for m in ai_messages for call in (getattr(m, "tool_calls", None) or [])
    )

    tokens = {"input": 0, "output": 0, "total": 0}
    for m in ai_messages:
        usage = getattr(m, "usage_metadata", None) or {}
        tokens["input"] += usage.get("input_tokens", 0)
        tokens["output"] += usage.get("output_tokens", 0)
        tokens["total"] += usage.get("total_tokens", 0)

    outputs_dir = workspace / "outputs"
    artifacts = sorted(p.relative_to(workspace).as_posix() for p in outputs_dir.rglob("*") if p.is_file()) if outputs_dir.exists() else []
    stray = sorted(
        p.relative_to(workspace).as_posix()
        for p in workspace.rglob("*")
        if p.is_file() and not p.is_relative_to(outputs_dir) and p.name not in INPUT_FILES and p.suffix in {".png", ".jpg", ".svg", ".pdf", ".xlsx", ".csv"}
    )
    execute_cmds = [
        call.get("args", {}).get("command", "")
        for m in ai_messages
        for call in (getattr(m, "tool_calls", None) or [])
        if call.get("name") == "execute"
    ]
    pip_installs = [c for c in execute_cmds if "pip install" in c or "uv pip" in c]

    if not quick:  # quick 任务本就不产出图表，这两条判定不适用
        results.append(verdict("§7.2 验收 case 跑通：agent 写出 Python、在沙箱执行、产出图表", bool(artifacts), f"outputs/ 下的产物：{artifacts or '（空）'}"))
        results.append(verdict("§4.3 产物判定：agent 是否遵守「产物存 outputs/」", bool(artifacts) and not stray, f"outputs/ 内 {len(artifacts)} 个；outputs/ 外的疑似产物 {stray or '无'}"))
    results.append(verdict("§5.2 的 Agent 层事件有真实结构可回填", bool(chunks), f"共 {len(chunks)} 个 chunk 已落盘 → {jsonl.name}"))
    results.append(verdict("§7.3 观察：是否触发 pip install", None, f"{len(pip_installs)} 次：{pip_installs or '无（镜像已预装 pandas/numpy/matplotlib）'}"))
    results.append(verdict("§5.2 的 N（历史截断轮数）与 §6.4 配额的输入", None, f"AIMessage {len(ai_messages)} 轮，ToolMessage {len(tool_messages)} 条，token {tokens}"))
    results.append(verdict("§5.2 `path` 字段来源：子 agent 命名空间", None, f"观测到的 namespace 分布：{dict(namespaces)}"))

    summary = {
        "task": task,
        "rounds_ai_messages": len(ai_messages),
        "tool_messages": len(tool_messages),
        "tokens": tokens,
        "tools_used": dict(tools_used),
        "execute_commands": execute_cmds,
        "pip_installs": pip_installs,
        "artifacts_in_outputs": artifacts,
        "stray_artifacts": stray,
        "stream_mode_shapes": {k: dict(v) for k, v in mode_shapes.items()},
        "namespaces": dict(namespaces),
        "results": results,
    }
    out = OUT_DIR / f"{name}_stream_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    final_text = ai_messages[-1].content if ai_messages else ""
    write_out(name, "final_answer.md", final_text if isinstance(final_text, str) else json.dumps(final_text, ensure_ascii=False))

    print("\n-- 每个 stream_mode 观察到的形状 --")
    for mode, counter in mode_shapes.items():
        print(f"  {mode}: {dict(counter)}")
    print(f"\n明细 → {out}\n流式 chunk → {jsonl}")


if __name__ == "__main__":
    _mode = "quick" if "--quick" in sys.argv else "fixture" if "--fixture" in sys.argv else "full"
    asyncio.run(main(_mode))
