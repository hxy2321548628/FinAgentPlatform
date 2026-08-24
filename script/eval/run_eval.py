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
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from client import POLL_INTERVAL_SECOND, PlatformClient, PlatformError
from langfuse import Evaluation, Langfuse
from langfuse.api.core.api_error import ApiError
from metric import (
    USAGE_COMPONENTS,
    RunFacts,
    aggregate_usage,
    cost_of,
    evaluate,
    extract,
    total_cost_of_usage,
)

DATA_DIR = Path(__file__).parent / "data"
RESULT_DIR = Path(__file__).parent / "result"
DATASET_NAME = "zuel-finance-eval-v1"
DEFAULT_BASE_URL = "http://127.0.0.1"

# **probe 分两类**：链路触发型能判「这题有没有真的走到要测的路上」，
# 数据特征型（缺失值、异常值、中文、不存在的字段）不存在触发一说，记不适用
TRIGGER_PROBE = ("approval", "pip_install", "compaction", "multi_turn")

MEMORY_PROBE_COUNT_FIELDS = {
    "memory_probe_hit_count": "hit_count",
    "memory_recall_correct_count": "recall_correct_count",
    "memory_recall_expected_count": "recall_expected_count",
    "memory_selected_count": "selected_count",
    "memory_contamination_count": "contamination_count",
    "memory_body_truncated_count": "body_truncated_count",
    "memory_extractor_hit_count": "extractor_hit_count",
    "memory_consolidator_hit_count": "consolidator_hit_count",
}


def make_task(client: PlatformClient, record: list[dict[str, Any]]) -> Any:  # noqa: ANN401 - 交给 SDK 的回调
    """造一个跑单题的 task，顺带把过程记进 record。"""

    def task(*, item: Any, **_: Any) -> dict[str, Any]:  # noqa: ANN401 - SDK 按关键字传 DatasetItem
        source = dict(item.input or {})
        expected = dict(item.expected_output or {})
        meta = dict(item.metadata or {})

        thread_id = client.create_thread()
        for name in source.get("files", []):
            client.upload(thread_id, DATA_DIR / str(name))

        turns = [
            str(source["question"]),
            *[str(one) for one in source.get("turns", [])],
        ]
        memory_keywords = _memory_keywords(meta)
        rounds: list[dict[str, Any]] = []
        for position, question in enumerate(turns):
            expected_memory_slugs = None
            if memory_keywords:
                expected_memory_slugs = (
                    set()
                    if position == 0
                    else _expected_memory_slugs(client, thread_id, memory_keywords)
                )
            rounds.append(
                _one_turn(
                    client,
                    thread_id,
                    question,
                    expected_memory_slugs=expected_memory_slugs,
                )
            )
        last = rounds[-1]
        files = client.files(thread_id)
        if expected.get("artifact_glob_scope") == "last_turn":
            # 多轮题问的是「第二轮之后的产物守不守约定」，把第一轮的产物算进来就白判了
            files = [one for one in files if one["path"] not in last["files_before"]]

        verdict = evaluate(
            expected, answer=last["facts"].answer, files=files, status=last["status"]
        )
        output = _summarise(item, meta, rounds, verdict, files)
        record.append(output | {"answer": last["facts"].answer, "turns": turns})
        print(
            f"  {item.id}: {'过' if verdict.ok else '未过'} {verdict.detail}",
            flush=True,
        )
        return output

    return task


def _one_turn(
    client: PlatformClient,
    thread_id: str,
    question: str,
    *,
    expected_memory_slugs: set[str] | None = None,
) -> dict[str, Any]:
    """跑一轮问答，返回这一轮的事实。中途停在审批上由客户端自动批准。"""
    before = {one["path"] for one in client.files(thread_id)}
    run_id = client.submit(thread_id, question)
    status, approvals = client.wait(run_id)
    facts = _with_terminal_tokens(extract(client.replay(run_id)), client.run(run_id))
    ledger = (
        client.wait_memory_usage(run_id)
        if status == "succeeded"
        else client.memory_usage(run_id)
    )
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "status": status,
        "approvals": approvals,
        "facts": facts,
        "files_before": before,
        "memory_job_status": ledger.get("job_status"),
        "usage_selector": _usage_entry(ledger.get("selector")),
        "usage_extractor": _usage_entry(ledger.get("extractor")),
        "usage_consolidator": _usage_entry(ledger.get("consolidator")),
        "memory_probe": _memory_probe(
            ledger,
            expected_memory_slugs=expected_memory_slugs,
        ),
    }


def _with_terminal_tokens(facts: RunFacts, run: dict[str, Any]) -> RunFacts:
    """用数据库累计账替换 replay 中只覆盖最后一段的 token。"""
    tokens = run.get("tokens")
    if not isinstance(tokens, dict):
        raise PlatformError("run 响应缺少 tokens 累计账")
    names = ("input_cache_read", "input_uncached", "output")
    values = tuple(tokens.get(name) for name in names)
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in values
    ):
        raise PlatformError("run 响应的 tokens 累计账非法")
    cached, uncached, output = values
    total_input = cached + uncached
    return replace(
        facts,
        tokens_cache_read=cached,
        tokens_uncached=uncached,
        tokens_output=output,
        cache_hit_rate=cached / total_input if total_input else 0.0,
        cost_yuan=cost_of(cached=cached, uncached=uncached, output=output),
    )


def _usage_entry(value: object) -> dict[str, Any] | None:
    """账本分项只接受 JSON 对象；缺项保持未验，不伪造零。"""
    return dict(value) if isinstance(value, dict) else None


def _memory_probe(
    ledger: dict[str, Any],
    *,
    expected_memory_slugs: set[str] | None = None,
) -> dict[str, int | None]:
    """从平台审计账构造能直接量出的记忆原始计数。"""
    selector = _usage_entry(ledger.get("selector"))
    extractor = _usage_entry(ledger.get("extractor"))
    consolidator = _usage_entry(ledger.get("consolidator"))

    def count(component: dict[str, Any] | None, field: str) -> int | None:
        if component is None:
            return None
        value = component.get(field)
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else None
        )

    selected_slugs = None if selector is None else selector.get("selected_slugs")
    selected_count = (
        len(selected_slugs)
        if isinstance(selected_slugs, list)
        and all(isinstance(slug, str) for slug in selected_slugs)
        else None
    )
    comparable_slugs = (
        set(selected_slugs)
        if selected_count is not None and isinstance(selected_slugs, list)
        else None
    )
    correct_count = (
        None
        if expected_memory_slugs is None or comparable_slugs is None
        else len(comparable_slugs & expected_memory_slugs)
    )
    expected_count = (
        None if expected_memory_slugs is None else len(expected_memory_slugs)
    )
    contamination_count = (
        None
        if expected_memory_slugs is None or comparable_slugs is None
        else len(comparable_slugs - expected_memory_slugs)
    )
    return {
        "hit_count": count(selector, "hit_count"),
        "recall_correct_count": correct_count,
        "recall_expected_count": expected_count,
        "selected_count": selected_count,
        "contamination_count": contamination_count,
        "body_truncated_count": count(selector, "rejected_count"),
        "extractor_hit_count": count(extractor, "hit_count"),
        "consolidator_hit_count": count(consolidator, "hit_count"),
    }


def _memory_keywords(meta: dict[str, Any]) -> tuple[str, ...]:
    """取评估题显式给定的记忆标签词；未给时不猜 ground truth。"""
    value = meta.get("memory_expected_keywords")
    if not isinstance(value, list):
        return ()
    return tuple(
        keyword.strip().casefold()
        for keyword in value
        if isinstance(keyword, str) and keyword.strip()
    )


def _expected_memory_slugs(
    client: PlatformClient,
    thread_id: str,
    keywords: tuple[str, ...],
) -> set[str]:
    """用题面标签词在第一轮实际抽取结果中确定后续召回的 ground truth。"""
    expected: set[str] = set()
    for summary in client.memories(thread_id):
        slug = summary.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        detail = client.memory(thread_id, slug)
        searchable = "\n".join(
            str(detail.get(field, "")) for field in ("name", "description", "content")
        ).casefold()
        if any(keyword in searchable for keyword in keywords):
            expected.add(slug)
    return expected


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
    questions = sum(one["facts"].question_count for one in rounds)
    todo_updates = sum(one["facts"].todo_update_count for one in rounds)
    installed = any(one["facts"].installed_package for one in rounds)
    total_input = total_cached + total_uncached
    usage = _usage_summary(rounds)
    memory_probe = _memory_probe_summary(rounds)
    output = {
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
        # P13/P14 的字段保留为主 run 成本，旧结果和旧看板继续能读。
        "cost_yuan": sum(one["facts"].cost_yuan for one in rounds),
        "usage_main": usage["main"],
        "usage_selector": usage["selector"],
        "usage_extractor": usage["extractor"],
        "usage_consolidator": usage["consolidator"],
        "memory_job_statuses": [one.get("memory_job_status") for one in rounds],
        "memory_selection_evidence": [_selection_evidence(one) for one in rounds],
        "cost_yuan_main": _usage_cost(usage["main"]),
        "cost_yuan_selector": _usage_cost(usage["selector"]),
        "cost_yuan_extractor": _usage_cost(usage["extractor"]),
        "cost_yuan_consolidator": _usage_cost(usage["consolidator"]),
        "cost_yuan_total": total_cost_of_usage(
            [usage[one] for one in USAGE_COMPONENTS]
        ),
        "interrupt_count": interrupts,
        "question_count": questions,
        "todo_update_count": todo_updates,
        "installed_package": installed,
        "tool_calls": sum(one["facts"].tool_calls for one in rounds),
        "tool_error_rate": facts.tool_error_rate,
        "llm_rounds": sum(one["facts"].llm_rounds for one in rounds),
        "latency_second": sum(one["facts"].latency_second for one in rounds),
        "artifacts": [
            one["path"] for one in files if one["path"].startswith("outputs/")
        ],
        "probe_hit": _probe_hit(
            str(meta.get("probe", "none")),
            compaction,
            interrupts,
            installed,
            len(rounds),
        ),
    }
    output["cost_usage_complete"] = output["cost_yuan_total"] is not None
    return output | memory_probe


def _selection_evidence(round_: dict[str, Any]) -> dict[str, Any]:
    """保留每个 run 的选中 slug 与降级原因，供离线核对。"""
    selector = _usage_entry(round_.get("usage_selector"))
    return {
        "run_id": round_.get("run_id"),
        "selected_slugs": None if selector is None else selector.get("selected_slugs"),
        "fallback_reason": None
        if selector is None
        else selector.get("fallback_reason"),
    }


def _usage_summary(rounds: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    """聚合主模型与三个辅助环节的本地账本，不主动查询尚未存在的 API。"""
    has_component_ledger = any(
        any(f"usage_{component}" in one for component in USAGE_COMPONENTS)
        for one in rounds
    )
    if has_component_ledger:
        # selector 最终会合入 run 的 TokenUsage。只要开始接分项账，就必须同时给出已经
        # 剥离辅助模型的 main 账；账本明确 included_in_run 时可以从终态 token 重算。
        main = aggregate_usage([one.get("usage_main") for one in rounds])
        if main is None:
            main = aggregate_usage(
                [_main_usage_without_selector(one) for one in rounds]
            )
    else:
        main = aggregate_usage(
            [
                {
                    "tokens_cache_read": one["facts"].tokens_cache_read,
                    "tokens_uncached": one["facts"].tokens_uncached,
                    "tokens_output": one["facts"].tokens_output,
                    "cost_yuan": one["facts"].cost_yuan,
                    "latency_second": one["facts"].latency_second,
                    "model": one.get("model_main"),
                    "hit_count": None,
                    "rejected_count": None,
                }
                for one in rounds
            ]
        )
    return {
        "main": main,
        "selector": aggregate_usage([one.get("usage_selector") for one in rounds]),
        "extractor": aggregate_usage([one.get("usage_extractor") for one in rounds]),
        "consolidator": aggregate_usage(
            [one.get("usage_consolidator") for one in rounds]
        ),
    }


def _main_usage_without_selector(one: dict[str, Any]) -> dict[str, Any] | None:
    """从终态总 token 剥离已合入的 selector，用主模型单价重算 main。"""
    selector = one.get("usage_selector")
    if not isinstance(selector, dict) or not isinstance(
        selector.get("included_in_run"), bool
    ):
        return None
    facts = one["facts"]
    tokens = {
        "tokens_cache_read": facts.tokens_cache_read,
        "tokens_uncached": facts.tokens_uncached,
        "tokens_output": facts.tokens_output,
    }
    if selector["included_in_run"]:
        for field, total in tokens.items():
            selected = selector.get(field)
            if (
                not isinstance(selected, int)
                or isinstance(selected, bool)
                or not 0 <= selected <= total
            ):
                return None
            tokens[field] = total - selected
    return tokens | {
        "cost_yuan": cost_of(
            cached=tokens["tokens_cache_read"],
            uncached=tokens["tokens_uncached"],
            output=tokens["tokens_output"],
        ),
        "latency_second": facts.latency_second,
        "model": one.get("model_main"),
        "hit_count": None,
        "rejected_count": None,
    }


def _usage_cost(usage: dict[str, Any] | None) -> float | None:
    if usage is None:
        return None
    value = usage.get("cost_yuan")
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _memory_probe_summary(
    rounds: list[dict[str, Any]],
) -> dict[str, int | float | bool | None]:
    """汇总确定性的记忆探针；缺账或零命中均不伪装成失败率 0。"""
    counts = {
        output: _sum_memory_count(rounds, source)
        for output, source in MEMORY_PROBE_COUNT_FIELDS.items()
    }
    hit = counts["memory_probe_hit_count"]
    verified = isinstance(hit, int) and hit > 0
    expected = counts["memory_recall_expected_count"]
    selected = counts["memory_selected_count"]
    return counts | {
        # P15 明确规定命中数为 0 记「未验」。因此这里只会是 True 或 None，
        # 不会把未触发写成 False。
        "memory_probe_hit": True if verified else None,
        "memory_recall_accuracy": _verified_rate(
            counts["memory_recall_correct_count"], expected, verified=verified
        ),
        "memory_pollution_rate": _verified_rate(
            counts["memory_contamination_count"], selected, verified=verified
        ),
        "memory_body_truncation_rate": _verified_rate(
            counts["memory_body_truncated_count"], hit, verified=verified
        ),
    }


def _sum_memory_count(rounds: list[dict[str, Any]], field: str) -> int | None:
    values: list[int] = []
    for one in rounds:
        probe = one.get("memory_probe")
        if not isinstance(probe, dict):
            return None
        value = probe.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        values.append(value)
    return sum(values)


def _verified_rate(
    numerator: int | None, denominator: int | None, *, verified: bool
) -> float | None:
    if not verified or numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _probe_hit(
    probe: str, compaction: int, interrupts: int, installed: bool, turns: int
) -> bool | None:
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
        Evaluation(
            name="task_success",
            value=output["success"],
            data_type="BOOLEAN",
            comment=output["detail"],
        ),
        Evaluation(
            name="artifact_produced",
            value=bool(output["artifacts"]),
            data_type="BOOLEAN",
        ),
        # **主判据（v0.5 起）**：命中率是个比值，分子分母同向变化时不敏感 ——
        # 首轮据它判出「尾部注入有害」，按单价复算方向是反的。命中率留着，作归因用
        Evaluation(name="cost_yuan", value=output["cost_yuan"], data_type="NUMERIC"),
        Evaluation(
            name="cache_hit_rate", value=output["cache_hit_rate"], data_type="NUMERIC"
        ),
        Evaluation(
            name="tokens_uncached", value=output["tokens_uncached"], data_type="NUMERIC"
        ),
        Evaluation(
            name="latency_s", value=output["latency_second"], data_type="NUMERIC"
        ),
        Evaluation(
            name="compaction_count",
            value=output["compaction_count"],
            data_type="NUMERIC",
        ),
        Evaluation(
            name="offload_count", value=output["offload_count"], data_type="NUMERIC"
        ),
        Evaluation(
            name="error_code",
            value=output["error_code"] or "none",
            data_type="CATEGORICAL",
        ),
    ]
    total_cost = _record_total_cost(output)
    if total_cost is not None:
        scores.append(
            Evaluation(name="cost_yuan_total", value=total_cost, data_type="NUMERIC")
        )
    for name in (
        "memory_recall_accuracy",
        "memory_pollution_rate",
        "memory_body_truncation_rate",
    ):
        value = output.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool):
            scores.append(
                Evaluation(name=name, value=float(value), data_type="NUMERIC")
            )
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
    main_costs = [_record_main_cost(one) for one in rows]
    scores = [
        Evaluation(
            name="pass_rate",
            value=sum(one["success"] for one in rows) / len(rows),
            data_type="NUMERIC",
        ),
    ]
    if all(one is not None for one in main_costs):
        scores.append(
            Evaluation(
                name="mean_cost_yuan_main",
                value=sum(one for one in main_costs if one is not None)
                / len(main_costs),
                data_type="NUMERIC",
            )
        )
    total_costs = [_record_total_cost(one) for one in rows]
    if all(one is not None for one in total_costs):
        total = sum(one for one in total_costs if one is not None)
        # 原分数名保留，让 P13/P14 的 Langfuse 看板不断线；P15 起它与显式总成本同值。
        scores.extend(
            [
                Evaluation(
                    name="mean_cost_yuan", value=total / len(rows), data_type="NUMERIC"
                ),
                Evaluation(
                    name="mean_cost_yuan_total",
                    value=total / len(rows),
                    data_type="NUMERIC",
                ),
                Evaluation(name="total_cost_yuan", value=total, data_type="NUMERIC"),
            ]
        )

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
    # P14 的两个新读数。**报的是「多少道题用到了」而不是总次数** ——
    # 一道题问了五次和五道题各问一次，对教师是完全不同的两件事。
    # **为 0 时也发**：那正是「这个功能对教师不存在」的读数，与 probe_coverage
    # 那条「算不出就别发」的规矩不冲突 —— 这里 0 是量出来的，不是缺数据
    scores.append(
        Evaluation(
            name="question_rate",
            value=sum(1 for one in rows if one.get("question_count", 0) > 0)
            / len(rows),
            data_type="NUMERIC",
            comment=f"共问了 {sum(one.get('question_count', 0) for one in rows)} 次",
        )
    )
    scores.append(
        Evaluation(
            name="todo_rate",
            value=sum(1 for one in rows if one.get("todo_update_count", 0) > 0)
            / len(rows),
            data_type="NUMERIC",
            comment=f"共刷新清单 {sum(one.get('todo_update_count', 0) for one in rows)} 次",
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
    for name, value in _memory_batch_metrics(rows).items():
        if value is not None:
            scores.append(Evaluation(name=name, value=value, data_type="NUMERIC"))
    return scores


def _record_main_cost(one: dict[str, Any]) -> float | None:
    value = one.get("cost_yuan_main", one.get("cost_yuan"))
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _record_total_cost(one: dict[str, Any]) -> float | None:
    """P15 显式缺总账时返回未验；真正的旧记录才回退主成本。"""
    if "cost_yuan_total" in one:
        value = one.get("cost_yuan_total")
        return (
            float(value)
            if isinstance(value, int | float) and not isinstance(value, bool)
            else None
        )
    return _record_main_cost(one)


def _memory_batch_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """按原始计数聚合记忆指标；没有命中时整项未验。"""

    def rate(numerator: str, denominator: str) -> float | None:
        fields = ("memory_probe_hit_count", numerator, denominator)
        eligible = [
            one
            for one in rows
            if all(
                isinstance(one.get(field), int)
                and not isinstance(one.get(field), bool)
                and int(one[field]) >= 0
                for field in fields
            )
        ]
        hits = sum(int(one["memory_probe_hit_count"]) for one in eligible)
        return _verified_rate(
            sum(int(one[numerator]) for one in eligible),
            sum(int(one[denominator]) for one in eligible),
            verified=bool(eligible) and hits > 0,
        )

    return {
        "memory_recall_accuracy": rate(
            "memory_recall_correct_count", "memory_recall_expected_count"
        ),
        "memory_pollution_rate": rate(
            "memory_contamination_count", "memory_selected_count"
        ),
        "memory_body_truncation_rate": rate(
            "memory_body_truncated_count", "memory_probe_hit_count"
        ),
    }


def _cost_spread(rows: list[dict[str, Any]]) -> float | None:
    """同一道题跑多次的成本**相对**极差，取所有题里最大的那个。

    **必须取相对值**：各题的绝对成本差二十倍（首轮 0.06 元到 1.30 元），
    绝对极差会被最贵那道题一个人定死，别的题波动多大完全看不出来。

    **只有一个副本时返回 None** —— 一个点算不出极差，报 0 等于宣称这批毫无波动。
    """
    grouped: dict[str, list[float]] = {}
    for one in rows:
        cost = _record_total_cost(one)
        if cost is None:
            return None
        grouped.setdefault(str(one["item_id"]), []).append(cost)
    spread = [
        (max(values) - min(values)) / min(values)
        for values in grouped.values()
        if len(values) > 1 and min(values) > 0
    ]
    return max(spread) if spread else None


def _self_check(
    items: list[Any], *, base_url: str, username: str, password: str
) -> int:
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
                problem.append(
                    f"{one.id}: 缺数据文件 {name}（大文件要先跑 make_daily_price.py）"
                )
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
    parser.add_argument(
        "--repeat", type=int, default=1, help="同题跑几个副本，噪声带要 3"
    )
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题，0 表示全跑")
    parser.add_argument(
        "--only", default="", help="只跑 id 里含这些文字的题，逗号分隔，便于挑几道重跑"
    )
    parser.add_argument("--run-name", default="", help="这一批的名字，默认带时间戳")
    parser.add_argument(
        "--base-url", default=os.environ.get("EVAL_BASE_URL", DEFAULT_BASE_URL)
    )
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

    username, password = (
        os.environ.get("EVAL_USERNAME", ""),
        os.environ.get("EVAL_PASSWORD", ""),
    )
    if not (username and password):
        print(
            "缺 EVAL_USERNAME / EVAL_PASSWORD，先跑 script/eval/create_account.sh",
            file=sys.stderr,
        )
        return 2

    try:
        langfuse = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ["LANGFUSE_BASE_URL"],
        )
        dataset = langfuse.get_dataset(DATASET_NAME)
    except ApiError as error:
        print(
            f"Langfuse 数据集读取失败：HTTP {error.status_code}，响应体：{error.body!r}",
            file=sys.stderr,
        )
        return 2
    wanted = [one.strip() for one in argument.only.split(",") if one.strip()]
    items = [
        one
        for one in dataset.items
        if not wanted or any(mark in str(one.id) for mark in wanted)
    ]
    items = items[: argument.limit or None]
    if not items:
        print(f"没有匹配 --only={argument.only!r} 的题", file=sys.stderr)
        return 2
    data = [one for one in items for _ in range(argument.repeat)]
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    run_name = argument.run_name or f"baseline-{stamp}"

    if argument.dry_run:
        return _self_check(
            items, base_url=argument.base_url, username=username, password=password
        )

    record: list[dict[str, Any]] = []
    print(
        f"{run_name}：{len(items)} 题 × {argument.repeat} 副本 = {len(data)} 次真实分析",
        flush=True,
    )
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
        json.dumps(
            {"run_name": run_name, "dataset": DATASET_NAME, "items": record},
            ensure_ascii=False,
            indent=2,
        ),
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
