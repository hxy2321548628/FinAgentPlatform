"""跑评估集：把 Langfuse 数据集里的题逐道走一遍真实链路，判成败并上报。

**走 `POST /api/threads/{id}/runs` 而不是直接调装配层**：最贵的那些 bug（沙箱没申请、
broker 少个环境变量、容器里的地址填成 localhost）全都发生在装配层之外，绕过去就照不出来。

**结果两边都留**：Langfuse 承担展示与跨批次对比，本地 JSON 承担离线分析与 pairwise 的基线。

用法：
    export EVAL_USERNAME=zuel-eval EVAL_PASSWORD=...
    export LANGFUSE_BASE_URL=http://localhost:3000    # 容器里那个名字宿主机解析不了
    src/.venv/bin/python script/eval/run_eval.py --repeat 1 --limit 2   # 冒烟
    src/.venv/bin/python script/eval/run_eval.py --repeat 3             # 正式一轮
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from client import POLL_INTERVAL_SECOND, PlatformClient, PlatformError
from langfuse import Evaluation, Langfuse
from metric import evaluate, extract

DATA_DIR = Path(__file__).parent / "data"
RESULT_DIR = Path(__file__).parent / "result"
DATASET_NAME = "zuel-finance-eval-v1"
DEFAULT_BASE_URL = "http://127.0.0.1"

# **probe 分两类**：链路触发型能判「这题有没有真的走到要测的路上」，
# 数据特征型（缺失值、异常值、中文、不存在的字段）不存在触发一说，记不适用
TRIGGER_PROBE = ("approval", "pip_install", "compaction", "multi_turn")


def make_task(client: PlatformClient, record: list[dict[str, Any]]) -> Any:  # noqa: ANN401 - 交给 SDK 的回调
    """造一个跑单题的 task，顺带把过程记进 record。"""

    def task(*, item: Any, **_: Any) -> dict[str, Any]:  # noqa: ANN401 - SDK 按关键字传 DatasetItem
        source = dict(item.input or {})
        expected = dict(item.expected_output or {})
        meta = dict(item.metadata or {})

        thread_id = client.create_thread()
        for name in source.get("files", []):
            client.upload(thread_id, DATA_DIR / str(name))

        turns = [str(source["question"]), *[str(one) for one in source.get("turns", [])]]
        rounds = [_one_turn(client, thread_id, question) for question in turns]
        last = rounds[-1]
        files = client.files(thread_id)
        if expected.get("artifact_glob_scope") == "last_turn":
            # 多轮题问的是「第二轮之后的产物守不守约定」，把第一轮的产物算进来就白判了
            files = [one for one in files if one["path"] not in last["files_before"]]

        verdict = evaluate(expected, answer=last["facts"].answer, files=files, status=last["status"])
        output = _summarise(item, meta, rounds, verdict, files)
        record.append(output | {"answer": last["facts"].answer, "turns": turns})
        print(f"  {item.id}: {'过' if verdict.ok else '未过'} {verdict.detail}", flush=True)
        return output

    return task


def _one_turn(client: PlatformClient, thread_id: str, question: str) -> dict[str, Any]:
    """跑一轮问答，返回这一轮的事实。中途停在审批上由客户端自动批准。"""
    before = {one["path"] for one in client.files(thread_id)}
    run_id = client.submit(thread_id, question)
    status, approvals = client.wait(run_id)
    facts = extract(client.replay(run_id))
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "status": status,
        "approvals": approvals,
        "facts": facts,
        "files_before": before,
    }


def _summarise(
    item: Any,  # noqa: ANN401 - DatasetItem
    meta: dict[str, Any],
    rounds: list[dict[str, Any]],
    verdict: Any,  # noqa: ANN401 - metric.Verdict
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    """把一道题的多轮结果折成一条可上报、可落盘的记录。"""
    last = rounds[-1]
    facts = last["facts"]
    total_uncached = sum(one["facts"].tokens_uncached for one in rounds)
    total_cached = sum(one["facts"].tokens_cache_read for one in rounds)
    compaction = sum(one["facts"].compaction_count for one in rounds)
    offload = sum(one["facts"].offload_count for one in rounds)
    interrupts = sum(one["facts"].interrupt_count for one in rounds)
    installed = any(one["facts"].installed_package for one in rounds)
    total_input = total_cached + total_uncached
    return {
        "item_id": item.id,
        "probe": str(meta.get("probe", "none")),
        "success": verdict.ok,
        "detail": verdict.detail,
        "status": last["status"],
        "error_code": facts.error_code,
        "run_ids": [one["run_id"] for one in rounds],
        "thread_id": last["thread_id"],
        "tokens_uncached": total_uncached,
        "tokens_cache_read": total_cached,
        "tokens_output": sum(one["facts"].tokens_output for one in rounds),
        "cache_hit_rate": total_cached / total_input if total_input else 0.0,
        "compaction_count": compaction,
        "offload_count": offload,
        "cost_yuan": sum(one["facts"].cost_yuan for one in rounds),
        "interrupt_count": interrupts,
        "installed_package": installed,
        "tool_calls": sum(one["facts"].tool_calls for one in rounds),
        "tool_error_rate": facts.tool_error_rate,
        "llm_rounds": sum(one["facts"].llm_rounds for one in rounds),
        "latency_second": sum(one["facts"].latency_second for one in rounds),
        "artifacts": [one["path"] for one in files if one["path"].startswith("outputs/")],
        "probe_hit": _probe_hit(str(meta.get("probe", "none")), compaction, interrupts, installed, len(rounds)),
    }


def _probe_hit(probe: str, compaction: int, interrupts: int, installed: bool, turns: int) -> bool | None:
    """这道题有没有真的走到要测的那条路上。不适用的返回 None，不记「过」。"""
    match probe:
        case "approval":
            return interrupts > 0
        case "pip_install":
            return installed
        case "compaction":
            return compaction > 0
        case "multi_turn":
            return turns > 1
        case _:
            return None


# `**_` 是 SDK 的回调契约：它按关键字传一整组参数，签名少一个就报错
def item_evaluators(*, output: dict[str, Any], **_: Any) -> list[Evaluation]:  # noqa: ANN401
    """把一道题的事实翻译成 Langfuse 的分数。"""
    scores = [
        Evaluation(name="task_success", value=output["success"], data_type="BOOLEAN", comment=output["detail"]),
        Evaluation(name="artifact_produced", value=bool(output["artifacts"]), data_type="BOOLEAN"),
        # **主判据（v0.5 起）**：命中率是个比值，分子分母同向变化时不敏感 ——
        # 首轮据它判出「尾部注入有害」，按单价复算方向是反的。命中率留着，作归因用
        Evaluation(name="cost_yuan", value=output["cost_yuan"], data_type="NUMERIC"),
        Evaluation(name="cache_hit_rate", value=output["cache_hit_rate"], data_type="NUMERIC"),
        Evaluation(name="tokens_uncached", value=output["tokens_uncached"], data_type="NUMERIC"),
        Evaluation(name="latency_s", value=output["latency_second"], data_type="NUMERIC"),
        Evaluation(name="compaction_count", value=output["compaction_count"], data_type="NUMERIC"),
        Evaluation(name="offload_count", value=output["offload_count"], data_type="NUMERIC"),
        Evaluation(name="error_code", value=output["error_code"] or "none", data_type="CATEGORICAL"),
    ]
    if output["probe_hit"] is not None:
        scores.append(
            Evaluation(
                name="probe_hit",
                value=output["probe_hit"],
                data_type="BOOLEAN",
                comment=f"probe={output['probe']}",
            )
        )
    return scores


def run_evaluators(*, item_results: list[Any], **_: Any) -> list[Evaluation]:  # noqa: ANN401
    """整批的分数。**probe_coverage 是尺子自身的校验**，不到 1 说明有题没走到要测的路上。"""
    rows = [one.output for one in item_results if isinstance(one.output, dict)]
    if not rows:
        return []
    scores = [
        Evaluation(name="pass_rate", value=sum(one["success"] for one in rows) / len(rows), data_type="NUMERIC"),
        Evaluation(
            name="mean_cost_yuan",
            value=sum(one["cost_yuan"] for one in rows) / len(rows),
            data_type="NUMERIC",
        ),
    ]

    # **算不出来的时候不发，而不是发一个 0。** 0 会被读成「一题都没触发」「一点波动都没有」，
    # 那正是这份计划反复要挡的那种假红 —— 尺子自己先坏了，后面每一批都跟着错
    probed = [one for one in rows if one["probe_hit"] is not None]
    if probed:
        hit = [one for one in probed if one["probe_hit"]]
        scores.append(
            Evaluation(
                name="probe_coverage",
                value=len(hit) / len(probed),
                data_type="NUMERIC",
                comment=f"{len(hit)}/{len(probed)} 道题真的触发了要测的场景",
            )
        )
    noise = _cost_spread(rows)
    if noise is not None:
        scores.append(
            Evaluation(
                name="cost_spread",
                value=noise,
                data_type="NUMERIC",
                comment="同题多副本的成本相对极差 —— 改进要超过它才算数",
            )
        )
    return scores


def _cost_spread(rows: list[dict[str, Any]]) -> float | None:
    """同一道题跑多次的成本**相对**极差，取所有题里最大的那个。

    **必须取相对值**：各题的绝对成本差二十倍（首轮 0.06 元到 1.30 元），
    绝对极差会被最贵那道题一个人定死，别的题波动多大完全看不出来。

    **只有一个副本时返回 None** —— 一个点算不出极差，报 0 等于宣称这批毫无波动。
    """
    grouped: dict[str, list[float]] = {}
    for one in rows:
        grouped.setdefault(str(one["item_id"]), []).append(float(one["cost_yuan"]))
    spread = [
        (max(values) - min(values)) / min(values) for values in grouped.values() if len(values) > 1 and min(values) > 0
    ]
    return max(spread) if spread else None


def _self_check(items: list[Any], *, base_url: str, username: str, password: str) -> int:
    """不花钱的自检：题目、数据文件、登录、建会话。

    **它挡的是「跑到第 8 题才发现少个数据文件」** —— 那时前面七题的钱已经花掉了。
    """
    problem: list[str] = []
    for one in items:
        source = dict(one.input or {})
        if not str(source.get("question", "")).strip():
            problem.append(f"{one.id}: 没有题面")
        for name in source.get("files", []):
            if not (DATA_DIR / str(name)).exists():
                problem.append(f"{one.id}: 缺数据文件 {name}（大文件要先跑 make_daily_price.py）")
        if not dict(one.expected_output or {}):
            problem.append(f"{one.id}: 没有判据，跑了也判不出成败")

    with httpx.Client(timeout=30.0, follow_redirects=True) as http:
        client = PlatformClient(base_url=base_url, client=http)
        try:
            client.login(name=username, password=password)
            thread_id = client.create_thread()
            client.files(thread_id)
        except PlatformError as error:
            problem.append(f"平台链路不通：{error}")

    for one in problem:
        print(f"  ✗ {one}")
    print(f"自检：{len(items)} 题，{len(problem)} 处问题")
    return 1 if problem else 0


def build_parser() -> argparse.ArgumentParser:
    """命令行参数。**单独成函数是为了能测** —— 默认值本身就是判据。"""
    parser = argparse.ArgumentParser(description="跑金融分析智能体的评估集")
    parser.add_argument("--repeat", type=int, default=1, help="同题跑几个副本，噪声带要 3")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题，0 表示全跑")
    parser.add_argument("--only", default="", help="只跑 id 里含这些文字的题，逗号分隔，便于挑几道重跑")
    parser.add_argument("--run-name", default="", help="这一批的名字，默认带时间戳")
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只自检不跑分析：数据集读得到吗、题目引用的文件都在吗、登录与建会话通吗",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="同时跑几次分析。默认 1（前几轮基线都是串行跑的，并发会让 latency 不可比）；"
        "超过账号的并发 run 上限会被 CONCURRENCY_LIMIT 挡回来，那不是提速是制造失败样本",
    )
    return parser


def main() -> int:
    """跑一轮评估，返回进程退出码。"""
    argument = build_parser().parse_args()

    username, password = os.environ.get("EVAL_USERNAME", ""), os.environ.get("EVAL_PASSWORD", "")
    if not (username and password):
        print("缺 EVAL_USERNAME / EVAL_PASSWORD，先跑 script/eval/create_account.sh", file=sys.stderr)
        return 2

    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_BASE_URL"],
    )
    dataset = langfuse.get_dataset(DATASET_NAME)
    wanted = [one.strip() for one in argument.only.split(",") if one.strip()]
    items = [one for one in dataset.items if not wanted or any(mark in str(one.id) for mark in wanted)]
    items = items[: argument.limit or None]
    if not items:
        print(f"没有匹配 --only={argument.only!r} 的题", file=sys.stderr)
        return 2
    data = [one for one in items for _ in range(argument.repeat)]
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    run_name = argument.run_name or f"baseline-{stamp}"

    if argument.dry_run:
        return _self_check(items, base_url=argument.base_url, username=username, password=password)

    record: list[dict[str, Any]] = []
    print(f"{run_name}：{len(items)} 题 × {argument.repeat} 副本 = {len(data)} 次真实分析", flush=True)
    with httpx.Client(timeout=60.0, follow_redirects=True) as http:
        # **轮询间隔跟着并发走**：限流按用户算 120 次/分钟，间隔不放大的话
        # 并发到 10 光轮询就吃满，然后被自己的账号限流挡下 —— 报的是 RATE_LIMITED，
        # 看着像平台出问题
        client = PlatformClient(
            base_url=argument.base_url,
            client=http,
            poll_second=max(POLL_INTERVAL_SECOND, argument.concurrency * 2),
        )
        client.login(name=username, password=password)
        result = langfuse.run_experiment(
            name="金融分析智能体评估",
            run_name=run_name,
            description="P13 的尺子：judge 不接，全部走 code-based 判据",
            data=data,
            task=make_task(client, record),
            evaluators=[item_evaluators],
            run_evaluators=[run_evaluators],
            # **瓶颈不是沙箱池**（50 个）也不是 worker 并发（20），是**每用户的并发 run 上限**
            # —— 教师档 3，超了直接 CONCURRENCY_LIMIT。要跑更高得先给这个账号配额覆盖
            max_concurrency=argument.concurrency,
        )

    RESULT_DIR.mkdir(exist_ok=True)
    target = RESULT_DIR / f"{run_name}.json"
    target.write_text(
        json.dumps({"run_name": run_name, "dataset": DATASET_NAME, "items": record}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    langfuse.flush()
    print(f"本地结果：{target}")
    print(f"Langfuse：{getattr(result, 'dataset_run_url', '（这一版 SDK 没给链接）')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PlatformError as error:
        print(f"平台接口没按预期响应：{error}", file=sys.stderr)
        sys.exit(1)
