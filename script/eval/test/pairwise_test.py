"""Pairwise 判分器的测试。"""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from create_pairwise_prompt import RUBRIC
from pairwise import (
    PairwiseJudge,
    PairwiseResult,
    default_output_path,
    evaluate_payloads,
    file_sha256,
    pair_rows,
    parse_direction,
    summarize,
)

P14_SHA256 = "a5b78a53ffe28bfc8a2e15982afac1b70b0afb891fbd3020d8338df45fb301fd"


class FakePrompt:
    """提供可观察答案顺序的假 rubric。"""

    prompt = "题目：{{question}}\nA（{{label_a}}）：{{answer_a}}\nB（{{label_b}}）：{{answer_b}}"
    version = 7


class FakeLangfuse:
    """只实现 PairwiseJudge 需要的 prompt 查询。"""

    def get_prompt(self, name: str, label: str = "") -> FakePrompt:
        assert name == "pairwise-rubric"
        assert label == "production"
        return FakePrompt()


def a_judge(outputs: list[str]) -> tuple[PairwiseJudge, list[dict[str, object]]]:
    """造一个依次返回指定内容的判分器。"""
    pending: Iterator[str] = iter(outputs)
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": next(pending)}}]}
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://model"
    )
    return PairwiseJudge(langfuse=FakeLangfuse(), client=client), requests


def test_bidirectional_agreement_keeps_the_winner_and_swaps_positions() -> None:
    """A/B 与 B/A 都选 candidate 时才记 candidate 胜。"""
    judge, requests = a_judge(
        [
            "candidate",
            "  candidate\n",
        ]
    )

    result = judge.compare(question="问", baseline="基线", candidate="候选")

    assert result.winner == "candidate"
    assert result.position_flip is False
    assert result.rubric_version == 7
    prompts = [str(one["messages"]) for one in requests]
    assert "A（baseline）：基线" in prompts[0]
    assert "B（candidate）：候选" in prompts[0]
    assert "A（candidate）：候选" in prompts[1]
    assert "B（baseline）：基线" in prompts[1]


def test_opposite_bidirectional_verdicts_become_a_tie() -> None:
    """两个方向结论相反说明尺子有位置偏差，不得强行选一边。"""
    judge, _ = a_judge(
        [
            "candidate",
            "baseline",
        ]
    )

    result = judge.compare(question="问", baseline="基线", candidate="候选")

    assert result.winner == "tie"
    assert result.position_flip is True


def test_an_invalid_direction_becomes_a_tie_instead_of_using_the_other_one() -> None:
    """任一方向解析不了都记 tie，否则只跑成了单向判分。"""
    judge, _ = a_judge(
        [
            "candidate",
            "candidate 更好",
        ]
    )

    result = judge.compare(question="问", baseline="基线", candidate="候选")

    assert result.winner == "tie"
    assert result.invalid_count == 1


def test_parser_only_accepts_the_three_frozen_labels() -> None:
    """只容许精确标签及首尾空白；JSON、解释、大小写和位置字母都无效。"""
    for label in ("baseline", "candidate", "tie"):
        assert parse_direction(f" \n{label}\t").winner == label
    for raw in (
        '{"winner": "tie"}',
        "```candidate```",
        "candidate 更好",
        "candidate\n证据更完整",
        "Candidate",
        "A",
        "",
    ):
        assert parse_direction(raw).winner is None


def test_rubric_matches_the_strict_label_only_parser() -> None:
    assert "只能输出一个标签" in RUBRIC
    assert '{"winner"' not in RUBRIC


def test_summary_reports_win_flip_tie_and_invalid_rates() -> None:
    """最终结果要同时量候选胜率与尺子自身噪声。"""
    rows = [
        PairwiseResult.agreed("candidate", rubric_version=3),
        PairwiseResult.agreed("baseline", rubric_version=3),
        PairwiseResult.disagreed("candidate", "baseline", rubric_version=3),
        PairwiseResult.invalid("candidate", rubric_version=3),
    ]

    result = summarize(rows)

    assert result == {
        "total": 4,
        "baseline_wins": 1,
        "candidate_wins": 1,
        "ties": 2,
        "position_flips": 1,
        "invalid_pairs": 1,
        "invalid_directions": 1,
        "baseline_win_rate": 0.25,
        "candidate_win_rate": 0.25,
        "position_flip_rate": 0.25,
        "invalid_rate": 0.25,
        "tie_rate": 0.5,
    }


def row(
    item_id: str,
    *,
    answer: str,
    thread_id: str,
    replica: int | None = None,
    turns: list[str] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "item_id": item_id,
        "thread_id": thread_id,
        "run_ids": [f"run-{thread_id}"],
        "turns": turns or ["第一问", "第二问"],
        "answer": answer,
    }
    if replica is not None:
        result["replica"] = replica
    return result


def test_pairing_uses_explicit_item_and_replica_instead_of_file_order() -> None:
    baseline = {
        "items": [
            row("E02", replica=1, answer="b-e02", thread_id="b3"),
            row("E01", replica=2, answer="b-e01-r2", thread_id="b2"),
            row("E01", replica=1, answer="b-e01-r1", thread_id="b1"),
        ]
    }
    candidate = {
        "items": [
            row("E01", replica=1, answer="c-e01-r1", thread_id="c1"),
            row("E02", replica=1, answer="c-e02", thread_id="c3"),
            row("E01", replica=2, answer="c-e01-r2", thread_id="c2"),
        ]
    }

    paired = pair_rows(baseline, candidate)

    assert [
        (item, replica, before["answer"], after["answer"])
        for item, replica, before, after in paired
    ] == [
        ("E01", 1, "b-e01-r1", "c-e01-r1"),
        ("E01", 2, "b-e01-r2", "c-e01-r2"),
        ("E02", 1, "b-e02", "c-e02"),
    ]


def test_multi_turn_judging_keeps_the_whole_question_sequence() -> None:
    """多轮题不能只拿最后一句去判；前文正是最后答复所依赖的分析上下文。"""
    baseline = {
        "run_name": "baseline",
        "items": [
            row(
                "E08",
                replica=1,
                answer="基线答复",
                thread_id="baseline-thread",
                turns=["先记住项目口径", "现在按该口径继续分析"],
            )
        ],
    }
    candidate = {
        "run_name": "candidate",
        "items": [
            row(
                "E08",
                replica=1,
                answer="候选答复",
                thread_id="candidate-thread",
                turns=["先记住项目口径", "现在按该口径继续分析"],
            )
        ],
    }
    judge, requests = a_judge(["tie", "tie"])

    evaluate_payloads(
        baseline=baseline,
        candidate=candidate,
        judge=judge,
        baseline_sha256="frozen",
    )

    prompt = str(requests[0]["messages"])
    assert "第 1 轮用户问题：先记住项目口径" in prompt
    assert "第 2 轮用户问题：现在按该口径继续分析" in prompt


def test_legacy_rows_get_a_stable_replica_order_independent_of_file_order() -> None:
    before = [
        row("E01", answer="baseline-b", thread_id="b"),
        row("E01", answer="baseline-a", thread_id="a"),
    ]
    after = [
        row("E01", answer="candidate-d", thread_id="d"),
        row("E01", answer="candidate-c", thread_id="c"),
    ]

    first = pair_rows({"items": before}, {"items": after})
    shuffled = pair_rows({"items": before[::-1]}, {"items": after[::-1]})

    assert first == shuffled
    assert [
        (replica, left["thread_id"], right["thread_id"])
        for _, replica, left, right in first
    ] == [
        (1, "a", "c"),
        (2, "b", "d"),
    ]


def test_duplicate_or_mismatched_replica_sets_fail_closed() -> None:
    duplicate = {
        "items": [
            row("E01", replica=1, answer="a", thread_id="a"),
            row("E01", replica=1, answer="b", thread_id="b"),
        ]
    }
    candidate = {
        "items": [
            row("E01", replica=1, answer="c", thread_id="c"),
            row("E01", replica=2, answer="d", thread_id="d"),
        ]
    }

    with pytest.raises(ValueError, match="replica"):
        pair_rows(duplicate, candidate)
    with pytest.raises(ValueError, match="replica"):
        pair_rows(
            {"items": [row("E01", replica=1, answer="a", thread_id="a")]}, candidate
        )


def test_payload_keeps_rubric_hash_bidirectional_evidence_and_all_turns() -> None:
    judge, requests = a_judge(["candidate", "candidate"])
    baseline = {
        "run_name": "p14-baseline",
        "items": [row("E08", replica=1, answer="旧答复", thread_id="before")],
    }
    candidate = {
        "run_name": "p15-candidate",
        "items": [row("E08", replica=1, answer="新答复", thread_id="after")],
    }

    payload = evaluate_payloads(
        baseline=baseline,
        candidate=candidate,
        judge=judge,
        baseline_sha256=P14_SHA256,
    )

    assert payload["rubric_version"] == 7
    assert payload["baseline_sha256"] == P14_SHA256
    assert payload["summary"] == {
        "total": 1,
        "baseline_wins": 0,
        "candidate_wins": 1,
        "ties": 0,
        "position_flips": 0,
        "invalid_pairs": 0,
        "invalid_directions": 0,
        "baseline_win_rate": 0.0,
        "candidate_win_rate": 1.0,
        "position_flip_rate": 0.0,
        "invalid_rate": 0.0,
        "tie_rate": 0.0,
    }
    assert payload["items"][0]["forward"]["raw"] == "candidate"  # type: ignore[index]
    assert "第 1 轮用户问题：第一问" in str(requests[0]["messages"])
    assert "第 2 轮用户问题：第二问" in str(requests[0]["messages"])


def test_p14_baseline_file_has_the_frozen_sha256() -> None:
    baseline = Path(__file__).parents[1] / "result" / "p14-baseline.json"

    assert file_sha256(baseline) == P14_SHA256


def test_default_output_is_separate_and_never_overwrites_an_existing_result(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "p14-baseline.json"
    candidate = tmp_path / "p15-candidate.json"
    baseline.write_text("baseline", encoding="utf-8")
    candidate.write_text("candidate", encoding="utf-8")

    first = default_output_path(baseline, candidate, result_dir=tmp_path)
    first.write_text("old result", encoding="utf-8")
    second = default_output_path(baseline, candidate, result_dir=tmp_path)

    assert first not in {baseline, candidate}
    assert second not in {baseline, candidate, first}
    assert baseline.read_text(encoding="utf-8") == "baseline"
