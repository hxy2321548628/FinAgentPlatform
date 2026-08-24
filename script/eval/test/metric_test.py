"""判据评估器与指标提取的测试。

**正反两向都要有**：一个只会判「过」的评估器，与没有评估器是同一件事。

跑法（不进两端门禁，评估工具不属于平台运行时）：
    PYTHONPATH=script/eval src/.venv/bin/python -m pytest script/eval
"""

import pytest
from metric import aggregate_usage, cost_of, evaluate, extract, total_cost_of_usage


def event(kind: str, **data: object) -> dict[str, object]:
    return {"type": kind, "ts": 0, "run_id": "r1", "path": [], "data": data}


def test_numbers_match_in_percent_or_decimal_form() -> None:
    """31.98% 与 0.3198 是同一个数。答复用哪种写法是它的自由，判据不该挑食。"""
    expected = {
        "answer_numbers": [{"label": "占比", "value": 0.319844, "rel_tol": 0.02}]
    }

    assert evaluate(expected, answer="食品饮料占比 31.98%", files=[]).ok
    assert evaluate(expected, answer="食品饮料占比为 0.3198", files=[]).ok


def test_a_number_outside_the_tolerance_fails() -> None:
    """容差外必须判失败 —— 这条不成立的话上面那条也就没有意义。"""
    expected = {
        "answer_numbers": [{"label": "占比", "value": 0.319844, "rel_tol": 0.02}]
    }

    verdict = evaluate(expected, answer="食品饮料占比 45.00%", files=[])

    assert not verdict.ok
    assert "占比" in verdict.detail


def test_a_number_range_accepts_either_way_of_handling_missing_values() -> None:
    """五粮液删除法 0.2432、前值填充 0.2182，两种都算对 —— 判据不绑定解法。"""
    expected = {"answer_number_range": [{"label": "五粮液", "min": 0.21, "max": 0.25}]}

    assert evaluate(expected, answer="五粮液年化波动率 0.2432", files=[]).ok
    assert evaluate(expected, answer="五粮液年化波动率 0.2182", files=[]).ok
    assert not evaluate(expected, answer="五粮液年化波动率 0.31", files=[]).ok


def test_artifact_glob_looks_at_the_workspace_tree() -> None:
    expected = {"artifact_glob": "outputs/*.png"}
    produced = [{"path": "outputs/行业占比.png", "is_dir": False, "size": 40000}]

    assert evaluate(expected, answer="见图", files=produced).ok
    assert not evaluate(
        expected,
        answer="见图",
        files=[{"path": "outputs/note.txt", "is_dir": False, "size": 10}],
    ).ok


def test_an_empty_file_is_not_an_artifact() -> None:
    """零字节的图打不开。**产物存在**与**产物可用**不是一回事。"""
    expected = {"artifact_glob": "outputs/*.png"}

    assert not evaluate(
        expected,
        answer="见图",
        files=[{"path": "outputs/x.png", "is_dir": False, "size": 0}],
    ).ok


def test_workspace_absent_catches_a_leftover_temp_file() -> None:
    expected = {"workspace_absent": ["tmp_returns.csv"]}

    assert evaluate(expected, answer="删好了", files=[]).ok
    assert not evaluate(
        expected,
        answer="删好了",
        files=[{"path": "tmp_returns.csv", "is_dir": False, "size": 12}],
    ).ok


def test_keyword_requirements_are_checked_both_ways() -> None:
    all_of = {"answer_must_include_all": ["2025-03-03", "贵州茅台"]}
    any_of = {"answer_must_include_any": ["缺失", "空值"]}

    assert evaluate(all_of, answer="2025-03-03 的贵州茅台价格明显异常", files=[]).ok
    assert not evaluate(all_of, answer="贵州茅台价格异常", files=[]).ok
    assert evaluate(any_of, answer="缺失值按前值填充", files=[]).ok
    assert not evaluate(any_of, answer="数据很完整", files=[]).ok


def test_extract_counts_what_the_indicators_need() -> None:
    """指标全部来自事件流。少数一次压缩，A1 的主指标就偏一次。"""
    events = [
        event("run.started", thread_id="t1", resumed=False),
        event("sandbox.queued", position=2),
        event("sandbox.ready"),
        event(
            "tool_call", id="c1", name="execute", args={"command": "pip install scipy"}
        ),
        event(
            "tool_result",
            tool_call_id="c1",
            name="execute",
            content="ok",
            status="success",
        ),
        event("tool_call", id="c2", name="execute", args={"command": "python x.py"}),
        event(
            "tool_result",
            tool_call_id="c2",
            name="execute",
            content="boom",
            status="error",
        ),
        event("compaction", cutoff_index=12, file_path="/workspace/h.md"),
        event(
            "interrupt",
            actions=[
                {
                    "index": 0,
                    "tool_name": "delete",
                    "args": {},
                    "allowed_decisions": ["approve"],
                }
            ],
        ),
        event("token", text="结论是"),
        event("token", text="占比 31.98%"),
        event(
            "run.finished",
            status="succeeded",
            tokens={"input_cache_read": 30, "input_uncached": 70, "output": 10},
        ),
    ]

    seen = extract(events)

    assert seen.answer == "结论是占比 31.98%"
    assert seen.tokens_cache_read == 30
    assert seen.tokens_uncached == 70
    assert seen.cache_hit_rate == 0.3
    assert seen.compaction_count == 1
    assert seen.interrupt_count == 1
    assert seen.tool_calls == 2
    assert seen.tool_error_rate == 0.5
    assert seen.installed_package is True
    assert seen.error_code is None


def test_extract_reports_the_failure_code() -> None:
    events = [
        event("run.started", thread_id="t1", resumed=False),
        event(
            "run.failed", code="RECURSION_LIMIT", message="步数超了", retryable=False
        ),
    ]

    seen = extract(events)

    assert seen.error_code == "RECURSION_LIMIT"
    assert seen.compaction_count == 0


def result(**output: object) -> object:
    """伪造一条 experiment 的 item 结果，只需要 .output。

    `cost_yuan` 给个默认值：它是主判据，每条记录都有，而这几条用例验的是别的东西。
    """
    return type("Item", (), {"output": {"cost_yuan": 0.1, **output}})()


def test_probe_coverage_is_absent_when_nothing_is_probeable() -> None:
    """没有可判的 probe 时不能报 0 —— 0 会被读成「一题都没触发」，那是假红。

    尺子自身的校验先坏在这里的话，后面每一批的「未验」都会当成「没触发」。
    """
    from run_eval import run_evaluators

    rows = [
        result(
            item_id="E10",
            success=True,
            cache_hit_rate=0.9,
            probe_hit=None,
            probe="none",
        )
    ]

    names = {one.name for one in run_evaluators(item_results=rows)}

    assert "probe_coverage" not in names
    assert "pass_rate" in names


def test_spread_is_absent_without_a_second_copy() -> None:
    """一个副本算不出极差。报 0 等于说「这批一点波动都没有」。"""
    from run_eval import run_evaluators

    rows = [
        result(
            item_id="E10",
            success=True,
            cache_hit_rate=0.9,
            probe_hit=None,
            probe="none",
        )
    ]

    assert "cost_spread" not in {one.name for one in run_evaluators(item_results=rows)}


def test_probe_coverage_counts_only_the_probeable_ones() -> None:
    from run_eval import run_evaluators

    rows = [
        result(
            item_id="E05",
            success=True,
            cache_hit_rate=0.5,
            probe_hit=True,
            probe="approval",
        ),
        result(
            item_id="E07",
            success=True,
            cache_hit_rate=0.5,
            probe_hit=False,
            probe="compaction",
        ),
        result(
            item_id="E10",
            success=True,
            cache_hit_rate=0.5,
            probe_hit=None,
            probe="none",
        ),
    ]

    coverage = next(
        one for one in run_evaluators(item_results=rows) if one.name == "probe_coverage"
    )

    assert coverage.value == 0.5


def test_offloaded_tool_results_are_counted() -> None:
    """卸载到底触发了几次要数得出来。

    **不数就没法验**：A9 把阈值从 20000 降到 4000，而「降了阈值」与「真的拦住了」
    是两件事 —— 首轮那道最贵的题正是因为够不着默认阈值，一次都没触发过。
    """
    events = [
        event(
            "tool_result",
            status="success",
            content="Tool result too large, the result of this tool call abc was saved in the filesystem at this path: /tmp/x",
        ),
        event("tool_result", status="success", content="正常的输出"),
        event(
            "tool_result",
            status="success",
            content="Tool result too large, ... at this path: /tmp/y",
        ),
    ]

    assert extract(events).offload_count == 2


def test_a_run_without_offloading_reports_zero_not_none() -> None:
    """一次都没触发是个有意义的读数（说明阈值仍然够不着），不是缺数据。"""
    assert (
        extract(
            [event("tool_result", status="success", content="正常的输出")]
        ).offload_count
        == 0
    )


def test_cost_weighs_uncached_tokens_thirty_times_heavier() -> None:
    """成本是本期的主判据 —— 命中与不命中差 30 倍，这个倍数就是判据的全部意义。

    首轮正是栽在这里：按命中率判出「尾部注入有害」，按单价复算方向是反的。
    """
    only_cached = cost_of(cached=1_000_000, uncached=0, output=0)
    only_uncached = cost_of(cached=0, uncached=1_000_000, output=0)

    assert only_uncached == 30 * only_cached


def test_cost_is_reported_alongside_the_raw_token_counts() -> None:
    """算好的钱要跟着事实一起出来，不能让每个调用方各算一遍。"""
    facts = extract(
        [
            event(
                "run.finished",
                status="succeeded",
                tokens={
                    "input_cache_read": 1_000_000,
                    "input_uncached": 0,
                    "output": 0,
                },
            )
        ]
    )

    assert facts.cost_yuan == cost_of(cached=1_000_000, uncached=0, output=0)
    assert facts.cost_yuan > 0


def test_a_question_is_counted_apart_from_an_approval() -> None:
    """**两者混在一起就答不出「提问会不会滥用」。**

    `interrupt_count` 里既有删文件的审批也有 agent 的提问，而这两件事对教师
    完全不同：一个是「你批不批」，一个是「你说句话」。
    """
    facts = extract(
        [
            {
                "type": "interrupt",
                "ts": 1,
                "data": {
                    "actions": [
                        {
                            "index": 0,
                            "tool_name": "delete",
                            "allowed_decisions": ["approve"],
                        }
                    ]
                },
            },
            {
                "type": "interrupt",
                "ts": 2,
                "data": {
                    "actions": [
                        {
                            "index": 0,
                            "tool_name": "ask_user_question",
                            "allowed_decisions": ["respond"],
                        }
                    ]
                },
            },
        ]
    )

    assert facts.interrupt_count == 2
    assert facts.question_count == 1


def test_todo_updates_are_counted() -> None:
    facts = extract(
        [
            {
                "type": "todo.updated",
                "ts": 1,
                "data": {"todos": [{"content": "读数据", "status": "in_progress"}]},
            },
            {
                "type": "todo.updated",
                "ts": 2,
                "data": {"todos": [{"content": "读数据", "status": "completed"}]},
            },
        ]
    )

    assert facts.todo_update_count == 2


def test_a_run_that_never_asked_or_planned_reads_zero_not_missing() -> None:
    """**0 是有意义的读数**，正是「这个功能对教师不存在」的那个数。"""
    facts = extract(
        [{"type": "token", "ts": 1, "data": {"text": "年化波动率 = 标准差 × √252"}}]
    )

    assert facts.question_count == 0
    assert facts.todo_update_count == 0


def test_usage_aggregation_keeps_auxiliary_models_separate() -> None:
    """分项账先各自相加，selector 不能既算进 main 又单独再加一次。"""
    usage = aggregate_usage(
        [
            {
                "tokens_cache_read": 10,
                "tokens_uncached": 20,
                "tokens_output": 3,
                "cost_yuan": 0.1,
                "latency_second": 0.4,
                "duration_ms": 400,
                "model": "aux-a",
                "hit_count": 1,
                "rejected_count": 2,
                "included_in_run": True,
            },
            {
                "tokens_cache_read": 4,
                "tokens_uncached": 5,
                "tokens_output": 6,
                "cost_yuan": 0.2,
                "latency_second": 0.6,
                "duration_ms": 600,
                "model": "aux-a",
                "hit_count": 3,
                "rejected_count": 1,
                "included_in_run": True,
            },
        ]
    )

    assert usage == {
        "tokens_cache_read": 14,
        "tokens_uncached": 25,
        "tokens_output": 9,
        "cost_yuan": pytest.approx(0.3),
        "latency_second": 1.0,
        "duration_ms": 1000,
        "models": ["aux-a"],
        "hit_count": 4,
        "rejected_count": 3,
        "included_in_run": True,
    }


def test_missing_usage_is_none_not_a_zero_ledger() -> None:
    """没接上账本与模型确实没调用不是一回事；前者必须保持未验。"""
    assert aggregate_usage([None]) is None
    assert aggregate_usage([]) is None


def test_total_cost_requires_every_component_but_accepts_explicit_zero() -> None:
    """只有四项都有账才有总额；显式 0 表示该组件确实未调用，是有效读数。"""
    main = {"cost_yuan": 1.0}
    selector = {"cost_yuan": 0.2}
    extractor = {"cost_yuan": 0.3}
    skipped = {"cost_yuan": 0.0}

    assert total_cost_of_usage([main, selector, extractor, skipped]) == 1.5
    assert total_cost_of_usage([main, selector, extractor, None]) is None
    assert total_cost_of_usage([main, selector, {"cost_yuan": None}, skipped]) is None
