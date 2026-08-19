r"""给已经跑完的评估批次补判分，并算出判分噪声带。

**为什么是事后补而不是跑的时候判**：首轮基线定案不接 judge —— rubric 还没稳定，
拿一把没校准的尺子量等于白量。等两批输出都在手上，用同一版 rubric 一起判，
两批的分才可比。

**判分噪声带（P13⑧）**：同题三副本的分数极差。这个数决定 P15 的验收标准长什么样 ——
压不住就说明绝对打分靠不住，主观项要改走 pairwise。

用法：
    set -a && . docker/.env && set +a
    LANGFUSE_BASE_URL=http://localhost:3000 \\
    src/.venv/bin/python script/eval/judge_results.py after-round-1 probe-round-1
"""

import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

import httpx
from judge import create_judge
from langfuse import Langfuse

RESULT_DIR = Path(__file__).parent / "result"


def main() -> int:
    """给命令行点名的批次补判分。"""
    names = sys.argv[1:]
    if not names:
        print("用法：judge_results.py <批次名> [批次名...]", file=sys.stderr)
        return 2

    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_BASE_URL"],
    )
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    headers = {"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}

    with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as http:
        judge = create_judge(langfuse=langfuse, client=http)
        print(f"rubric v{judge.rubric_version}")
        for name in names:
            _judge_one_batch(name, judge=judge, langfuse=langfuse)
    langfuse.flush()
    return 0


def _judge_one_batch(name: str, *, judge: Any, langfuse: Langfuse) -> None:  # noqa: ANN401
    """判一个批次，写回本地并上报。"""
    target = RESULT_DIR / f"{name}.json"
    if not target.exists():
        print(f"  {name}: 没有这个批次的结果文件", file=sys.stderr)
        return
    payload = json.loads(target.read_text(encoding="utf-8"))
    for row in payload["items"]:
        # **多轮题要拿最后一轮的提问**：答复是最后一轮的，配第一轮的问题就成了「答非所问」。
        # E08 第一轮问行业占比、第二轮问收盘价走势，配错之后 judge 给了 1 分（其余题 4–5 分），
        # 而它的客观判据是过的 —— 尺子自己错了，看着却像被测对象错了
        verdict = judge.score(question=row["turns"][-1], answer=row["answer"])
        row["plan_quality"] = verdict.score
        row["plan_quality_reason"] = verdict.reason
        row["rubric_version"] = verdict.rubric_version
        if verdict.score is not None:
            langfuse.create_score(
                name="plan_quality",
                value=float(verdict.score),
                data_type="NUMERIC",
                session_id=row["thread_id"],
                comment=verdict.reason,
                metadata={"rubric_version": verdict.rubric_version, "batch": name},
            )
        print(f"  {row['item_id'][13:]:<26} {verdict.score if verdict.score is not None else '判不出'}")
    payload["judge_noise"] = _noise(payload["items"])
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(name, payload)


def _noise(rows: list[dict[str, Any]]) -> dict[str, float] | None:
    """同题多副本的判分极差。只有一个副本时返回 None，报 0 等于宣称毫无波动。"""
    grouped: dict[str, list[int]] = {}
    for row in rows:
        if row.get("plan_quality") is not None:
            grouped.setdefault(str(row["item_id"]), []).append(int(row["plan_quality"]))
    spreads = [max(values) - min(values) for values in grouped.values() if len(values) > 1]
    if not spreads:
        return None
    return {"max": float(max(spreads)), "mean": float(statistics.mean(spreads))}


def _report(name: str, payload: dict[str, Any]) -> None:
    scored = [one["plan_quality"] for one in payload["items"] if one.get("plan_quality") is not None]
    noise = payload.get("judge_noise")
    print(
        f"  —— {name}：判出 {len(scored)}/{len(payload['items'])} 条，均分 {statistics.mean(scored):.2f}"
        if scored
        else f"  —— {name}：一条都没判出来"
    )
    if noise:
        print(f"     判分噪声带：同题极差最大 {noise['max']:.0f} 分，平均 {noise['mean']:.2f} 分")
    else:
        print("     判分噪声带：算不出来（这一批每题只有一个副本）")


if __name__ == "__main__":
    sys.exit(main())
