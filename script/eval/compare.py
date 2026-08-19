"""把几轮评估结果并排比，主判据是每题成本。

**为什么要单独一个脚本**：`run_eval.py` 只管跑与落盘，跨轮对比是另一件事 ——
而这件事有一个坑：**早期几轮的记录里没有 `cost_yuan`**（那个字段是主判据改口之后才加的），
只能拿存下来的三项 token 数复算。复算用的是 `metric.cost_of`，与 runner 同一份单价。

跑法：
    PYTHONPATH=script/eval src/.venv/bin/python script/eval/compare.py 轮次1.json 轮次2.json ...
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from metric import cost_of

# 成本相对极差超过这个数才算「超出噪声带」。
#
# **取 0.326 的依据**：P13⑥ 首轮三副本实测，未命中 token 的相对极差中位数就是 32.6%。
# 比这个小的差异说不清是改进还是抖动
NOISE_BAND = 0.326


def cost_of_record(one: dict[str, object]) -> float:
    """一条记录的成本，老记录没有这个字段就按 token 复算。"""
    if isinstance(one.get("cost_yuan"), int | float):
        return float(one["cost_yuan"])
    return cost_of(
        cached=int(one.get("tokens_cache_read") or 0),
        uncached=int(one.get("tokens_uncached") or 0),
        output=int(one.get("tokens_output") or 0),
    )


def summarize(path: Path) -> tuple[str, dict[str, list[float]], dict[str, list[dict[str, object]]]]:
    """读一轮结果，按题聚成成本列表。"""
    data = json.loads(path.read_text())
    cost: dict[str, list[float]] = defaultdict(list)
    rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for one in data["items"]:
        key = str(one["item_id"]).replace("zuel-eval-v1-", "")
        cost[key].append(cost_of_record(one))
        rows[key].append(one)
    return str(data["run_name"]), dict(cost), dict(rows)


def spread(values: list[float]) -> float | None:
    """相对极差 `(max-min)/min`，一个副本时算不出来就不给数。"""
    if len(values) < 2 or min(values) <= 0:
        return None
    return (max(values) - min(values)) / min(values)


def main(paths: list[Path]) -> int:
    rounds = [summarize(one) for one in paths]
    names = [one[0] for one in rounds]
    questions = sorted({key for _, cost, _ in rounds for key in cost})

    print("每题成本（元，多副本取中位数）\n")
    header = f"{'题':<28}" + "".join(f"{one[:18]:>20}" for one in names) + f"{'末轮 vs 首轮':>16}"
    print(header)
    print("-" * len(header))
    for key in questions:
        cells = []
        for _, cost, _ in rounds:
            values = cost.get(key)
            cells.append(statistics.median(values) if values else None)
        line = f"{key:<28}" + "".join(f"{'—':>20}" if one is None else f"{one:>20.4f}" for one in cells)
        first, last = cells[0], cells[-1]
        change = f"{(last - first) / first:+.0%}" if first and last else "—"
        print(line + f"{change:>16}")

    total = [sum(statistics.median(v) for v in cost.values()) for _, cost, _ in rounds]
    print("-" * len(header))
    print(f"{'合计':<28}" + "".join(f"{one:>20.4f}" for one in total) + f"{(total[-1] - total[0]) / total[0]:+15.0%}")

    print("\n噪声带（同题副本的成本相对极差）\n")
    for name, cost, _ in rounds:
        spreads = [one for one in (spread(v) for v in cost.values()) if one is not None]
        if not spreads:
            print(f"  {name}：单副本，算不出极差")
            continue
        print(f"  {name}：中位数 {statistics.median(spreads):.1%}，最大 {max(spreads):.1%}（{len(spreads)} 题有多副本）")

    print(f"\n超出噪声带（±{NOISE_BAND:.0%}）的题，末轮 vs 首轮\n")
    _, first_cost, _ = rounds[0]
    _, last_cost, _ = rounds[-1]
    moved = False
    for key in questions:
        if key not in first_cost or key not in last_cost:
            continue
        before, after = statistics.median(first_cost[key]), statistics.median(last_cost[key])
        delta = (after - before) / before
        if abs(delta) > NOISE_BAND:
            moved = True
            print(f"  {key:<28}{before:.4f} → {after:.4f}  {delta:+.0%}  {'变好' if delta < 0 else '变差'}")
    if not moved:
        print("  一题都没有 —— 全部落在噪声带里")

    print("\n机制触发次数（末轮）\n")
    _, _, last_rows = rounds[-1]
    for field in ("offload_count", "compaction_count", "interrupt_count"):
        counted = [int(r.get(field) or 0) for rows in last_rows.values() for r in rows]
        hit = sum(1 for one in counted if one > 0)
        print(f"  {field:<20}合计 {sum(counted):>4} 次，{hit}/{len(counted)} 次分析触发过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main([Path(one) for one in sys.argv[1:]]))
