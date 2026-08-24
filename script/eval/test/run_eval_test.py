"""结果聚合的测试。

跑法（不进两端门禁，评估工具不属于平台运行时）：
    PYTHONPATH=script/eval src/.venv/bin/python -m pytest script/eval
"""

from types import SimpleNamespace

import pytest
from langfuse.api.core.api_error import ApiError
from metric import RunFacts, Verdict, cost_of
from run_eval import (
    _cost_spread,
    _expected_memory_slugs,
    _memory_batch_metrics,
    _memory_probe_summary,
    _one_turn,
    _summarise,
    main,
    run_evaluators,
)


def row(item_id: str, cost: float) -> dict[str, object]:
    return {"item_id": item_id, "cost_yuan": cost}


def test_the_spread_is_relative_not_absolute() -> None:
    """必须取相对值，否则最贵那道题一个人就把噪声带定死了。

    首轮实测各题绝对成本差二十倍（0.06 元到 1.30 元）：便宜那题翻一倍才 0.06 元的极差，
    而贵那题波动百分之几就有 0.05 元 —— 按绝对值排，便宜题的剧烈波动永远排不上号。
    """
    rows = [
        row("cheap", 0.01),
        row("cheap", 0.02),
        row("pricey", 1.00),
        row("pricey", 1.05),
    ]

    # cheap 翻了一倍（1.0），pricey 只动了百分之五
    assert _cost_spread(rows) == 1.0


def test_a_single_replicate_yields_no_spread() -> None:
    """一个点算不出极差 —— 报 0 等于宣称这批毫无波动，那是假红的来源。"""
    assert _cost_spread([row("only", 0.5)]) is None


def test_a_zero_cost_row_is_skipped_instead_of_dividing_by_zero() -> None:
    """成本为零的那组不参与，而不是让整批算崩。

    零成本意味着这次 run 根本没跑起来（token 全零），它的「相对波动」没有意义。
    """
    rows = [row("dead", 0.0), row("dead", 0.0), row("live", 0.10), row("live", 0.12)]

    assert _cost_spread(rows) == pytest.approx(0.2)


def test_concurrency_defaults_to_one_so_old_rounds_stay_reproducible() -> None:
    """默认串行。

    **前几轮基线都是串行跑的**，并发会引入资源争抢这一个新的波动源，
    `latency_second` 首先就不可比了 —— 而 P13⑥ 量的正是同题副本之间的波动。
    想快要显式要，不能靠默认值悄悄改掉执行方式。
    """
    from run_eval import build_parser

    assert build_parser().parse_args([]).concurrency == 1


def test_concurrency_is_a_dial_not_a_switch() -> None:
    """给几就是几 —— 平台侧的每用户并发闸另有配额覆盖，不在这里兜底。

    在这里悄悄夹到 3 的话，跑批会「看着按 10 跑」而实际是 3，**而这不会报错**。
    """
    from run_eval import build_parser

    assert build_parser().parse_args(["--concurrency", "10"]).concurrency == 10


def test_langfuse_dataset_failure_is_reported_without_an_sdk_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """dry-run 也要先取数据集；上游 502 应该成为可读的自检失败。"""

    class BrokenLangfuse:
        def __init__(self, **_: object) -> None:
            pass

        def get_dataset(self, _: str) -> object:
            raise ApiError(status_code=502, body="", headers={})

    monkeypatch.setattr("run_eval.Langfuse", BrokenLangfuse)
    monkeypatch.setattr("sys.argv", ["run_eval.py", "--dry-run"])
    monkeypatch.setenv("EVAL_USERNAME", "probe")
    monkeypatch.setenv("EVAL_PASSWORD", "probe")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "probe")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "probe")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://langfuse")

    assert main() == 2
    captured = capsys.readouterr()
    assert "Langfuse 数据集读取失败" in captured.err
    assert "502" in captured.err


def facts(*, cost: float = 1.0) -> RunFacts:
    return RunFacts(
        answer="完成",
        status="succeeded",
        error_code=None,
        tokens_cache_read=10,
        tokens_uncached=20,
        tokens_output=5,
        cache_hit_rate=1 / 3,
        compaction_count=0,
        offload_count=0,
        interrupt_count=0,
        question_count=0,
        todo_update_count=0,
        tool_calls=1,
        tool_errors=0,
        tool_error_rate=0.0,
        llm_rounds=2,
        installed_package=False,
        cost_yuan=cost,
        latency_second=1.0,
        queue_second=0.1,
    )


def turn(*, cost: float = 1.0, **extra: object) -> dict[str, object]:
    return {
        "run_id": "r1",
        "thread_id": "t1",
        "status": "succeeded",
        "facts": facts(cost=cost),
        **extra,
    }


def summarise(rounds: list[dict[str, object]]) -> dict[str, object]:
    return _summarise(
        SimpleNamespace(id="E01"),
        {"probe": "none"},
        rounds,
        Verdict(ok=True, detail=""),
        [],
    )


def usage(cost: float) -> dict[str, object]:
    return {
        "tokens_cache_read": 0,
        "tokens_uncached": 10,
        "tokens_output": 1,
        "cost_yuan": cost,
        "latency_second": 0.1,
        "model": "aux",
        "hit_count": 0,
        "rejected_count": 0,
    }


def test_new_result_reserves_auxiliary_usage_without_faking_a_total() -> None:
    """API 账本尚未接入时三个分项是 None，因此总成本也只能是未验。"""
    output = summarise([turn(cost=1.0)])

    assert output["usage_main"]["cost_yuan"] == 1.0  # type: ignore[index]
    assert output["usage_selector"] is None
    assert output["usage_extractor"] is None
    assert output["usage_consolidator"] is None
    assert output["cost_yuan_main"] == 1.0
    assert output["cost_yuan_total"] is None
    assert output["cost_usage_complete"] is False


def test_complete_component_ledgers_are_summed_exactly_once() -> None:
    output = summarise(
        [
            turn(
                cost=1.0,
                usage_main=usage(1.0),
                usage_selector=usage(0.2),
                usage_extractor=usage(0.3),
                usage_consolidator=usage(0.4),
            )
        ]
    )

    assert output["cost_yuan_main"] == 1.0
    assert output["cost_yuan_selector"] == 0.2
    assert output["cost_yuan_extractor"] == 0.3
    assert output["cost_yuan_consolidator"] == 0.4
    assert output["cost_yuan_total"] == pytest.approx(1.9)
    assert output["cost_usage_complete"] is True


def test_auxiliary_ledgers_require_an_explicitly_separated_main_ledger() -> None:
    """终态 token 将来会含 selector；没有独立 main 账时不能再加 selector 造成双计。"""
    output = summarise(
        [
            turn(
                cost=1.2,
                usage_selector=usage(0.2),
                usage_extractor=usage(0.3),
                usage_consolidator=usage(0.4),
            )
        ]
    )

    assert output["cost_yuan"] == 1.2
    assert output["usage_main"] is None
    assert output["cost_yuan_total"] is None
    assert output["cost_usage_complete"] is False


def test_selector_included_in_run_is_subtracted_before_totaling() -> None:
    """selector 的 token 已合入终态 usage，但它的实际成本来自辅助模型账本。"""
    selector = usage(0.2) | {
        "tokens_cache_read": 0,
        "tokens_uncached": 10,
        "tokens_output": 1,
        "included_in_run": True,
    }
    output = summarise(
        [
            turn(
                cost=99.0,
                usage_selector=selector,
                usage_extractor=usage(0.3) | {"included_in_run": False},
                usage_consolidator=usage(0.4) | {"included_in_run": False},
            )
        ]
    )

    expected_main = cost_of(cached=10, uncached=10, output=4)
    assert output["cost_yuan_main"] == expected_main
    assert output["cost_yuan_total"] == pytest.approx(expected_main + 0.2 + 0.3 + 0.4)


def test_an_incomplete_p15_total_has_no_cost_spread() -> None:
    rows = [
        {"item_id": "E01", "cost_yuan": 0.1, "cost_yuan_total": None},
        {"item_id": "E01", "cost_yuan": 0.2, "cost_yuan_total": None},
    ]

    assert _cost_spread(rows) is None


def test_an_incomplete_main_ledger_does_not_publish_a_fake_zero_mean() -> None:
    item = SimpleNamespace(
        output={
            "item_id": "E01",
            "success": True,
            "cost_yuan": 1.2,
            "cost_yuan_main": None,
            "cost_yuan_total": None,
            "probe_hit": None,
            "question_count": 0,
            "todo_update_count": 0,
        }
    )

    names = {score.name for score in run_evaluators(item_results=[item])}

    assert "pass_rate" in names
    assert "mean_cost_yuan_main" not in names
    assert "mean_cost_yuan" not in names
    assert "mean_cost_yuan_total" not in names


def test_missing_memory_probe_data_stays_unverified() -> None:
    summary = _memory_probe_summary([turn()])

    assert summary["memory_probe_hit_count"] is None
    assert summary["memory_probe_hit"] is None
    assert summary["memory_recall_accuracy"] is None
    assert summary["memory_pollution_rate"] is None
    assert summary["memory_body_truncation_rate"] is None


def test_zero_memory_probe_hits_are_unverified_not_failed() -> None:
    summary = _memory_probe_summary(
        [
            turn(
                memory_probe={
                    "hit_count": 0,
                    "recall_correct_count": 0,
                    "recall_expected_count": 2,
                    "selected_count": 0,
                    "contamination_count": 0,
                    "body_truncated_count": 0,
                    "extractor_hit_count": 0,
                    "consolidator_hit_count": 0,
                }
            )
        ]
    )

    assert summary["memory_probe_hit_count"] == 0
    assert summary["memory_probe_hit"] is None
    assert summary["memory_recall_accuracy"] is None
    assert summary["memory_pollution_rate"] is None


def test_triggered_memory_probe_can_report_a_real_zero_pollution_rate() -> None:
    summary = _memory_probe_summary(
        [
            turn(
                memory_probe={
                    "hit_count": 2,
                    "recall_correct_count": 3,
                    "recall_expected_count": 4,
                    "selected_count": 3,
                    "contamination_count": 0,
                    "body_truncated_count": 1,
                    "extractor_hit_count": 1,
                    "consolidator_hit_count": 1,
                }
            )
        ]
    )

    assert summary["memory_probe_hit"] is True
    assert summary["memory_recall_accuracy"] == 0.75
    assert summary["memory_pollution_rate"] == 0.0
    assert summary["memory_body_truncation_rate"] == 0.5


def test_batch_memory_rates_ignore_rows_without_ground_truth() -> None:
    """只有 E08 带召回真值；其余九题的 None 不能把这一个有效 probe 整批抹掉。"""
    rows = [
        {
            "memory_probe_hit_count": 2,
            "memory_recall_correct_count": 1,
            "memory_recall_expected_count": 2,
            "memory_selected_count": 2,
            "memory_contamination_count": 1,
            "memory_body_truncated_count": 0,
        },
        {
            "memory_probe_hit_count": 0,
            "memory_recall_correct_count": None,
            "memory_recall_expected_count": None,
            "memory_selected_count": 0,
            "memory_contamination_count": None,
            "memory_body_truncated_count": 0,
        },
    ]

    metrics = _memory_batch_metrics(rows)

    assert metrics["memory_recall_accuracy"] == 0.5
    assert metrics["memory_pollution_rate"] == 0.5
    assert metrics["memory_body_truncation_rate"] == 0.0


def test_one_turn_waits_for_memory_ledger_and_keeps_raw_selection_evidence() -> None:
    selector = {
        "model": "aux",
        "tokens_cache_read": 1,
        "tokens_uncached": 2,
        "tokens_output": 3,
        "cost_yuan": 0.01,
        "duration_ms": 9,
        "hit_count": 1,
        "rejected_count": 1,
        "fallback_reason": "invalid_output",
        "included_in_run": True,
        "selected_slugs": ["relevant", "dropped-by-budget"],
    }
    extractor = usage(0.02) | {
        "hit_count": 2,
        "included_in_run": False,
        "selected_slugs": [],
    }
    consolidator = usage(0.0) | {
        "hit_count": 0,
        "included_in_run": False,
        "selected_slugs": [],
    }

    class Client:
        def files(self, thread_id: str) -> list[dict[str, object]]:
            return []

        def submit(self, thread_id: str, question: str) -> str:
            return "run-1"

        def wait(self, run_id: str) -> tuple[str, int]:
            return "succeeded", 0

        def replay(self, run_id: str) -> list[dict[str, object]]:
            return []

        def run(self, run_id: str) -> dict[str, object]:
            return {
                "status": "succeeded",
                "tokens": {
                    "input_cache_read": 9,
                    "input_uncached": 14,
                    "output": 18,
                },
            }

        def wait_memory_usage(self, run_id: str) -> dict[str, object]:
            return {
                "job_status": "succeeded",
                "selector": selector,
                "extractor": extractor,
                "consolidator": consolidator,
            }

    result = _one_turn(  # type: ignore[arg-type]
        Client(),
        "thread-1",
        "问题",
        expected_memory_slugs={"relevant"},
    )

    assert result["usage_selector"] == selector
    assert result["facts"].tokens_cache_read == 9
    assert result["facts"].tokens_uncached == 14
    assert result["facts"].tokens_output == 18
    assert result["usage_extractor"] == extractor
    assert result["usage_consolidator"] == consolidator
    assert result["memory_job_status"] == "succeeded"
    assert result["memory_probe"] == {
        "hit_count": 1,
        "recall_correct_count": 1,
        "recall_expected_count": 1,
        "selected_count": 2,
        "contamination_count": 1,
        "body_truncated_count": 1,
        "extractor_hit_count": 2,
        "consolidator_hit_count": 0,
    }
    output = summarise([result])
    assert output["memory_selection_evidence"] == [
        {
            "run_id": "run-1",
            "selected_slugs": ["relevant", "dropped-by-budget"],
            "fallback_reason": "invalid_output",
        }
    ]
    assert output["memory_job_statuses"] == ["succeeded"]


def test_expected_memory_slugs_are_grounded_in_teacher_visible_content() -> None:
    class Client:
        def memories(self, thread_id: str) -> list[dict[str, object]]:
            assert thread_id == "thread-1"
            return [{"slug": "naming"}, {"slug": "unrelated"}]

        def memory(self, thread_id: str, slug: str) -> dict[str, object]:
            assert thread_id == "thread-1"
            return {
                "slug": slug,
                "name": "图片命名约定" if slug == "naming" else "数据摘要",
                "description": "持久约定",
                "content": "文件名以 ZUEL- 开头" if slug == "naming" else "持仓市值",
            }

    assert _expected_memory_slugs(  # type: ignore[arg-type]
        Client(),
        "thread-1",
        ("zuel-",),
    ) == {"naming"}
