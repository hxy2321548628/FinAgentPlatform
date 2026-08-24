"""Pairwise 评估：对同题基线与候选答复做双向判定。"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx
from langfuse import Langfuse

PROMPT_NAME = "pairwise-rubric"
DEFAULT_MODEL = "deepseek-v4-flash"
RESULT_DIR = Path(__file__).parent / "result"
TEMPERATURE = 0.0

Winner = Literal["baseline", "candidate", "tie"]
VALID_WINNERS = frozenset[Winner]({"baseline", "candidate", "tie"})


class PromptLike(Protocol):
    """Langfuse 文本 prompt 在本模块需要的最小形状。"""

    prompt: str
    version: int


class PromptRepository(Protocol):
    """只暴露读取已锁版 rubric 的能力。"""

    def get_prompt(self, name: str, label: str = "") -> PromptLike:
        """读取指定标签的文本 prompt。"""


@dataclass(frozen=True)
class DirectionResult:
    """一个展示顺序的判定结果。"""

    winner: Winner | None
    reason: str
    raw: str


@dataclass(frozen=True)
class PairwiseResult:
    """A/B 与 B/A 双向判定合并后的结果。"""

    winner: Winner
    forward: DirectionResult
    reverse: DirectionResult
    rubric_version: int

    @property
    def position_flip(self) -> bool:
        """两个有效方向是否给出相反的非 tie 结论。"""
        first, second = self.forward.winner, self.reverse.winner
        return (
            first in {"baseline", "candidate"}
            and second in {"baseline", "candidate"}
            and first != second
        )

    @property
    def invalid_count(self) -> int:
        """两个方向中无法解析的数量。"""
        return int(self.forward.winner is None) + int(self.reverse.winner is None)

    @classmethod
    def agreed(cls, winner: Winner, *, rubric_version: int) -> "PairwiseResult":
        """为汇总测试构造双向一致的结果。"""
        direction = DirectionResult(winner=winner, reason="", raw="")
        return cls(
            winner=winner,
            forward=direction,
            reverse=direction,
            rubric_version=rubric_version,
        )

    @classmethod
    def disagreed(
        cls,
        forward: Literal["baseline", "candidate"],
        reverse: Literal["baseline", "candidate"],
        *,
        rubric_version: int,
    ) -> "PairwiseResult":
        """为汇总测试构造位置翻转结果。"""
        return cls(
            winner="tie",
            forward=DirectionResult(winner=forward, reason="", raw=""),
            reverse=DirectionResult(winner=reverse, reason="", raw=""),
            rubric_version=rubric_version,
        )

    @classmethod
    def invalid(cls, valid: Winner, *, rubric_version: int) -> "PairwiseResult":
        """为汇总测试构造单向无效结果。"""
        return cls(
            winner="tie",
            forward=DirectionResult(winner=valid, reason="", raw=""),
            reverse=DirectionResult(winner=None, reason="解析失败", raw=""),
            rubric_version=rubric_version,
        )


class PairwiseJudge:
    """用同一 rubric 按两种展示顺序比较答复。"""

    def __init__(
        self,
        *,
        langfuse: PromptRepository,
        client: httpx.Client,
        model: str = DEFAULT_MODEL,
    ) -> None:
        prompt = langfuse.get_prompt(PROMPT_NAME, label="production")
        self._template = str(prompt.prompt)
        self._version = int(prompt.version)
        self._client = client
        self._model = model

    @property
    def rubric_version(self) -> int:
        """返回当前锁定的 rubric 版本。"""
        return self._version

    def compare(
        self, *, question: str, baseline: str, candidate: str
    ) -> PairwiseResult:
        """做 A/B 与 B/A 双向判定，不一致或任一无效都记 tie。"""
        forward = self._score(
            question=question,
            label_a="baseline",
            answer_a=baseline,
            label_b="candidate",
            answer_b=candidate,
        )
        reverse = self._score(
            question=question,
            label_a="candidate",
            answer_a=candidate,
            label_b="baseline",
            answer_b=baseline,
        )
        winner: Winner = (
            forward.winner
            if forward.winner is not None and forward.winner == reverse.winner
            else "tie"
        )
        return PairwiseResult(
            winner=winner,
            forward=forward,
            reverse=reverse,
            rubric_version=self._version,
        )

    def _score(
        self,
        *,
        question: str,
        label_a: Literal["baseline", "candidate"],
        answer_a: str,
        label_b: Literal["baseline", "candidate"],
        answer_b: str,
    ) -> DirectionResult:
        """按一个展示顺序请求模型并严格解析。"""
        filled = (
            self._template.replace("{{question}}", question)
            .replace("{{label_a}}", label_a)
            .replace("{{answer_a}}", answer_a)
            .replace("{{label_b}}", label_b)
            .replace("{{answer_b}}", answer_b)
        )
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": filled}],
                    "temperature": TEMPERATURE,
                },
            )
            response.raise_for_status()
            raw = str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError) as error:
            return DirectionResult(
                winner=None, reason=f"判分请求失败：{type(error).__name__}", raw=""
            )
        return parse_direction(raw)


def parse_direction(raw: str) -> DirectionResult:
    """只接受三个精确标签；首尾空白之外的任何内容都算无效。"""
    winner = raw.strip()
    if winner not in VALID_WINNERS:
        return DirectionResult(
            winner=None, reason=f"判分输出解析不了：{raw[:80]}", raw=raw
        )
    return DirectionResult(winner=winner, reason="", raw=raw)


def summarize(rows: list[PairwiseResult]) -> dict[str, int | float]:
    """统计候选胜率、tie 率与尺子自身的位置/解析噪声。"""
    total = len(rows)
    baseline_wins = sum(one.winner == "baseline" for one in rows)
    candidate_wins = sum(one.winner == "candidate" for one in rows)
    ties = sum(one.winner == "tie" for one in rows)
    flips = sum(one.position_flip for one in rows)
    invalid_pairs = sum(one.invalid_count > 0 for one in rows)
    invalid_directions = sum(one.invalid_count for one in rows)
    denominator = total or 1
    return {
        "total": total,
        "baseline_wins": baseline_wins,
        "candidate_wins": candidate_wins,
        "ties": ties,
        "position_flips": flips,
        "invalid_pairs": invalid_pairs,
        "invalid_directions": invalid_directions,
        "baseline_win_rate": baseline_wins / denominator,
        "candidate_win_rate": candidate_wins / denominator,
        "position_flip_rate": flips / denominator,
        "invalid_rate": invalid_pairs / denominator,
        "tie_rate": ties / denominator,
    }


def _group_rows(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """按 item_id 保留副本顺序分组。"""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    items = payload.get("items")
    if not isinstance(items, list):
        raise TypeError("评估结果缺 items 数组")
    for row in items:
        if not isinstance(row, dict) or not isinstance(row.get("item_id"), str):
            raise TypeError("评估记录缺 item_id")
        grouped[row["item_id"]].append(row)
    return dict(grouped)


def pair_rows(
    baseline: dict[str, object], candidate: dict[str, object]
) -> list[tuple[str, int, dict[str, object], dict[str, object]]]:
    """按题目与副本序号稳定配对，绝不依赖 JSON 文件里的出现顺序。"""
    baseline_rows = _group_rows(baseline)
    candidate_rows = _group_rows(candidate)
    if baseline_rows.keys() != candidate_rows.keys():
        raise ValueError("基线与候选的题目集不一致")
    paired: list[tuple[str, int, dict[str, object], dict[str, object]]] = []
    for item_id in sorted(baseline_rows):
        before, before_explicit = _replicas(
            item_id, baseline_rows[item_id], batch="基线"
        )
        after, after_explicit = _replicas(
            item_id, candidate_rows[item_id], batch="候选"
        )
        if before_explicit != after_explicit:
            raise ValueError(f"{item_id} 的 replica 标识方式不一致")
        if before.keys() != after.keys():
            raise ValueError(
                f"{item_id} 的 replica 集不一致：{sorted(before)} != {sorted(after)}"
            )
        paired.extend(
            (item_id, replica, before[replica], after[replica])
            for replica in sorted(before)
        )
    return paired


def _replicas(
    item_id: str, rows: list[dict[str, object]], *, batch: str
) -> tuple[dict[int, dict[str, object]], bool]:
    """读取显式 replica；P14 老结果没有该字段时按唯一 run/thread 标识稳定编号。"""
    explicit = ["replica" in row for row in rows]
    if any(explicit) and not all(explicit):
        raise ValueError(f"{batch} {item_id} 只有部分记录带 replica")
    if all(explicit):
        found: dict[int, dict[str, object]] = {}
        for row in rows:
            replica = row.get("replica")
            if (
                not isinstance(replica, int)
                or isinstance(replica, bool)
                or replica <= 0
            ):
                raise ValueError(f"{batch} {item_id} 的 replica 必须是正整数")
            if replica in found:
                raise ValueError(f"{batch} {item_id} 的 replica={replica} 重复")
            found[replica] = row
        return found, True

    keyed = [(_stable_row_key(item_id, row, batch=batch), row) for row in rows]
    keys = [key for key, _ in keyed]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{batch} {item_id} 缺 replica，且稳定记录标识重复")
    return {
        index: row
        for index, (_, row) in enumerate(sorted(keyed, key=lambda one: one[0]), start=1)
    }, False


def _stable_row_key(
    item_id: str, row: dict[str, object], *, batch: str
) -> tuple[str, ...]:
    thread_id = row.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        return ("thread", thread_id)
    run_ids = row.get("run_ids")
    if (
        isinstance(run_ids, list)
        and run_ids
        and all(isinstance(one, str) and one for one in run_ids)
    ):
        return ("runs", *(str(one) for one in run_ids))
    raise ValueError(f"{batch} {item_id} 缺 replica，也没有唯一 thread_id/run_ids")


def evaluate_payloads(
    *,
    baseline: dict[str, object],
    candidate: dict[str, object],
    judge: PairwiseJudge,
    baseline_sha256: str,
) -> dict[str, object]:
    """对两批本地结果逐副本判定，返回可落盘的完整载荷。"""
    details: list[dict[str, object]] = []
    results: list[PairwiseResult] = []
    for item_id, replica, before, after in pair_rows(baseline, candidate):
        before_turns = before.get("turns")
        after_turns = after.get("turns")
        if not isinstance(before_turns, list) or not before_turns:
            raise ValueError(f"{item_id} 的基线记录缺 turns")
        if before_turns != after_turns:
            raise ValueError(f"{item_id} 第 {replica} 副本的题面不一致")
        result = judge.compare(
            question=_question_sequence(before_turns),
            baseline=str(before.get("answer", "")),
            candidate=str(after.get("answer", "")),
        )
        results.append(result)
        details.append(
            {
                "item_id": item_id,
                "replica": replica,
                "baseline_thread_id": before.get("thread_id"),
                "candidate_thread_id": after.get("thread_id"),
                "winner": result.winner,
                "position_flip": result.position_flip,
                "invalid_count": result.invalid_count,
                "forward": asdict(result.forward),
                "reverse": asdict(result.reverse),
            }
        )
        print(f"  {item_id} #{replica}: {result.winner}", flush=True)
    return {
        "baseline_run": baseline.get("run_name"),
        "candidate_run": candidate.get("run_name"),
        "baseline_sha256": baseline_sha256,
        "rubric_version": judge.rubric_version,
        "summary": summarize(results),
        "items": details,
    }


def _question_sequence(turns: list[object]) -> str:
    """保留多轮题的完整用户问题序列，避免把末轮答复配给孤立的一句话。"""
    if len(turns) == 1:
        return str(turns[0])
    return "\n\n".join(
        f"第 {index} 轮用户问题：{turn}" for index, turn in enumerate(turns, start=1)
    )


def file_sha256(path: Path) -> str:
    """按文件原始字节计算 SHA256，确保冻结的是那一份基线而非重排后的 JSON。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_output_path(
    baseline: Path, candidate: Path, *, result_dir: Path = RESULT_DIR
) -> Path:
    """选择未占用的独立结果路径，不覆盖输入文件或上一轮判分。"""
    stem = f"pairwise-{baseline.stem}-vs-{candidate.stem}"
    index = 1
    while True:
        suffix = "" if index == 1 else f"-{index}"
        target = result_dir / f"{stem}{suffix}.json"
        if not target.exists() and not any(
            _same_path(target, source) for source in (baseline, candidate)
        ):
            return target
        index += 1


def _same_path(left: Path, right: Path) -> bool:
    return left.expanduser().resolve() == right.expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    parser = argparse.ArgumentParser(description="对两批评估结果做双向 pairwise 判定")
    parser.add_argument("baseline", type=Path, help="基线 JSON 文件")
    parser.add_argument("candidate", type=Path, help="候选 JSON 文件")
    parser.add_argument(
        "--output", type=Path, help="输出 JSON，默认写入 script/eval/result"
    )
    return parser


def main() -> int:
    """运行双向 pairwise 判定并将结果落盘。"""
    argument = build_parser().parse_args()
    if _same_path(argument.baseline, argument.candidate):
        print("基线与候选不能是同一个文件", file=sys.stderr)
        return 2
    target = argument.output or default_output_path(
        argument.baseline, argument.candidate
    )
    if any(
        _same_path(target, source) for source in (argument.baseline, argument.candidate)
    ):
        print("输出路径不能覆盖基线或候选文件", file=sys.stderr)
        return 2
    if target.exists():
        print(f"输出文件已存在，拒绝覆盖：{target}", file=sys.stderr)
        return 2
    try:
        baseline = json.loads(argument.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(argument.candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"评估结果读取失败：{error}", file=sys.stderr)
        return 2
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        print("基线与候选都必须是 JSON 对象", file=sys.stderr)
        return 2
    baseline_sha256 = file_sha256(argument.baseline)
    required = (
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "DEEPSEEK_API_KEY",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"缺环境变量：{' / '.join(missing)}", file=sys.stderr)
        return 2
    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_BASE_URL"],
    )
    headers = {"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as client:
        judge = PairwiseJudge(
            langfuse=langfuse,
            client=client,
            model=os.environ.get("MODEL_AUX", DEFAULT_MODEL),
        )
        payload = evaluate_payloads(
            baseline=baseline,
            candidate=candidate,
            judge=judge,
            baseline_sha256=baseline_sha256,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError:
        print(f"输出文件已存在，拒绝覆盖：{target}", file=sys.stderr)
        return 2
    print(f"本地结果：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
