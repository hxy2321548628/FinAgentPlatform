"""从一次 run 的事件流里提取事实，并按题目自带的判据判成败。

**判据一律来自题面，不来自系统提示词。** P15 要改的就是提示词，照着提示词措辞写的
判据等于同时改考卷和答案 —— 那样分数涨了也说明不了任何事。

**指标全部取自平台已有的数据**，不为评估另造采集通路。这是把评估集走真实链路换来的。
"""

import fnmatch
import os
import re
from dataclasses import dataclass
from typing import Any

# 答复里的数字：带 % 的按百分数解释，不带的两种解释都试一次 ——
# 教师问的是占比，agent 写 31.98%、0.3198、31.98 都算答对了
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
PERCENT_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
# 装包的痕迹：P12 之后 agent 缺库自己装，这是 pip_install 那道题的 probe 判据
INSTALL_MARKER = ("pip install", "pip3 install", "uv pip install")

# 大工具结果被挪到磁盘时，替代文本的开头。**由 deepagents 写死**
# （`middleware/_message_eviction.py` 的 TOO_LARGE_TOOL_MSG），升级依赖时要对一眼
OFFLOAD_MARKER = "Tool result too large"

# 提问工具的名字。**与后端 `app/agent/question.py` 各写一处** ——
# 它改名的话这里会静默数成 0，而 0 与「一次都没问」长得一模一样
QUESTION_TOOL = "ask_user_question"

# 模型单价，每百万 token 人民币。**默认值与 `docker/.env` 的三项同源** ——
# 那里改了这里也要改，否则算出来的钱和账单对不上。
# 命中与不命中差 30 倍，这个倍数就是「成本作主判据」的全部意义：
# 命中率是个比值，分子分母同向变化时它不敏感，而钱不会
PRICE_UNCACHED = float(os.environ.get("MODEL_MAIN_PRICE_INPUT", "9"))
PRICE_CACHED = float(os.environ.get("MODEL_MAIN_PRICE_CACHED", "0.30"))
PRICE_OUTPUT = float(os.environ.get("MODEL_MAIN_PRICE_OUTPUT", "27"))
PRICE_UNIT = 1_000_000
# 空文件不算产物：零字节的图打不开，「存在」与「可用」不是一回事
MIN_ARTIFACT_BYTE = 1


@dataclass(frozen=True)
class RunFacts:
    """一次 run 的全部可量事实。"""

    answer: str
    status: str
    error_code: str | None
    tokens_cache_read: int
    tokens_uncached: int
    tokens_output: int
    cache_hit_rate: float
    compaction_count: int
    # 大工具结果被挪到磁盘的次数。**一次都没有也是有意义的读数**：
    # 说明阈值仍然够不着，而不是「没数据」
    offload_count: int
    interrupt_count: int
    # agent 主动提问了几次。**它是 interrupt_count 的一个子集** —— 那个数里
    # 还混着删文件的审批，两者混在一起就答不出「提问会不会滥用」这个问题
    question_count: int
    # 清单被改写了几次。**一次都没有也是有意义的读数**：说明这道题模型不认为
    # 值得列清单，而不是「没数据」
    todo_update_count: int
    tool_calls: int
    tool_errors: int
    tool_error_rate: float
    llm_rounds: int
    installed_package: bool
    # 这次分析花了多少钱，元。**本期的主判据**
    cost_yuan: float
    latency_second: float
    queue_second: float


def cost_of(*, cached: int, uncached: int, output: int) -> float:
    """按平台单价算一次分析的钱，元。

    Args:
        cached: 命中缓存的输入 token 数。
        uncached: 未命中的输入 token 数。
        output: 输出 token 数。

    Returns:
        人民币金额。
    """
    return (cached * PRICE_CACHED + uncached * PRICE_UNCACHED + output * PRICE_OUTPUT) / PRICE_UNIT


@dataclass(frozen=True)
class Verdict:
    """一道题判下来的结果。`detail` 要说清是哪一条不满足。"""

    ok: bool
    detail: str


def extract(events: list[dict[str, Any]]) -> RunFacts:
    """把事件流折成一组事实。"""
    answer: list[str] = []
    tokens = {"input_cache_read": 0, "input_uncached": 0, "output": 0}
    counter = {"compaction": 0, "interrupt": 0, "call": 0, "error": 0, "offload": 0, "question": 0, "todo": 0}
    status, code, installed = "unknown", None, False
    stamp: dict[str, int] = {}

    for one in events:
        kind = str(one.get("type", ""))
        data = one.get("data") or {}
        stamp.setdefault(kind, int(one.get("ts", 0)))
        stamp[f"last.{kind}"] = int(one.get("ts", 0))
        match kind:
            case "token":
                answer.append(str(data.get("text", "")))
            case "compaction":
                counter[kind] += 1
            case "interrupt":
                counter[kind] += 1
                counter["question"] += sum(
                    1 for action in data.get("actions") or [] if action.get("tool_name") == QUESTION_TOOL
                )
            case "todo.updated":
                counter["todo"] += 1
            case "tool_call":
                counter["call"] += 1
                installed = installed or _is_install(data)
            case "tool_result":
                counter["error"] += int(data.get("status") == "error")
                counter["offload"] += int(OFFLOAD_MARKER in str(data.get("content", "")))
            case "run.finished" | "run.cancelled":
                tokens.update({k: int(v) for k, v in (data.get("tokens") or {}).items()})
                status = "succeeded" if kind == "run.finished" else "cancelled"
            case "run.failed":
                status, code = "failed", str(data.get("code", "")) or None

    cached, uncached = tokens["input_cache_read"], tokens["input_uncached"]
    total_input = cached + uncached
    return RunFacts(
        answer="".join(answer),
        status=status,
        error_code=code,
        tokens_cache_read=cached,
        tokens_uncached=uncached,
        tokens_output=tokens["output"],
        cache_hit_rate=cached / total_input if total_input else 0.0,
        compaction_count=counter["compaction"],
        offload_count=counter["offload"],
        interrupt_count=counter["interrupt"],
        question_count=counter["question"],
        todo_update_count=counter["todo"],
        tool_calls=counter["call"],
        tool_errors=counter["error"],
        tool_error_rate=counter["error"] / counter["call"] if counter["call"] else 0.0,
        # **近似值，只作诊断不作判据**：事件流里没有「模型调用」这种事件，
        # 用工具轮数 + 收尾那一轮来估
        llm_rounds=counter["call"] + 1,
        installed_package=installed,
        cost_yuan=cost_of(cached=cached, uncached=uncached, output=tokens["output"]),
        latency_second=_span(stamp, "run.started", "last.run.finished"),
        queue_second=_span(stamp, "sandbox.queued", "sandbox.ready"),
    )


def evaluate(
    expected: dict[str, Any], *, answer: str, files: list[dict[str, Any]], status: str = "succeeded"
) -> Verdict:
    """按题目自带的判据判一道题，失败时说清卡在哪一条。"""
    missing = [
        detail
        for detail in (
            _check_artifact(expected.get("artifact_glob"), files),
            _check_absent(expected.get("workspace_absent"), files),
            _check_numbers(expected.get("answer_numbers"), answer),
            _check_ranges(expected.get("answer_number_range"), answer),
            _check_keywords(expected.get("answer_must_include_all"), answer, every=True),
            _check_keywords(expected.get("answer_must_include_any"), answer, every=False),
            _check_pattern(expected.get("answer_must_match"), answer),
            _check_status(expected.get("run_status"), status),
        )
        if detail
    ]
    return Verdict(ok=not missing, detail="；".join(missing))


def _is_install(data: dict[str, Any]) -> bool:
    text = str(data.get("args", ""))
    return any(marker in text for marker in INSTALL_MARKER)


def _span(stamp: dict[str, int], start: str, end: str) -> float:
    if start not in stamp or end not in stamp:
        return 0.0
    return max(stamp[end] - stamp[start], 0) / 1000


def _candidates(answer: str) -> list[float]:
    """答复里出现过的数，按两种写法各解释一次。"""
    found = [float(one) / 100 for one in PERCENT_PATTERN.findall(answer)]
    for one in NUMBER_PATTERN.findall(answer):
        value = float(one)
        found.extend((value, value / 100))
    return found


def _check_artifact(pattern: str | None, files: list[dict[str, Any]]) -> str:
    if not pattern:
        return ""
    hit = [
        one
        for one in files
        if not one.get("is_dir")
        and fnmatch.fnmatch(str(one.get("path", "")), pattern)
        and int(one.get("size") or 0) >= MIN_ARTIFACT_BYTE
    ]
    return "" if hit else f"没有产出匹配 {pattern} 的非空文件"


def _check_absent(names: list[str] | None, files: list[dict[str, Any]]) -> str:
    if not names:
        return ""
    paths = {str(one.get("path", "")) for one in files}
    left = [name for name in names if name in paths]
    return f"该删掉的文件还在：{'、'.join(left)}" if left else ""


def _check_numbers(wanted: list[dict[str, Any]] | None, answer: str) -> str:
    if not wanted:
        return ""
    found = _candidates(answer)
    missing = [
        str(one.get("label", one.get("value")))
        for one in wanted
        if not any(
            abs(value - float(one["value"])) <= abs(float(one["value"])) * float(one["rel_tol"]) for value in found
        )
    ]
    return f"答复里没有这些数：{'、'.join(missing)}" if missing else ""


def _check_ranges(wanted: list[dict[str, Any]] | None, answer: str) -> str:
    if not wanted:
        return ""
    found = _candidates(answer)
    missing = [
        str(one.get("label", ""))
        for one in wanted
        if not any(float(one["min"]) <= value <= float(one["max"]) for value in found)
    ]
    return f"这些数不在允许区间内：{'、'.join(missing)}" if missing else ""


def _check_keywords(wanted: list[str] | None, answer: str, *, every: bool) -> str:
    if not wanted:
        return ""
    hit = [one for one in wanted if one in answer]
    if every and len(hit) != len(wanted):
        return f"答复里缺这些说法：{'、'.join(one for one in wanted if one not in answer)}"
    if not every and not hit:
        return f"答复里一个都没提到：{'、'.join(wanted)}"
    return ""


def _check_pattern(pattern: str | None, answer: str) -> str:
    if not pattern:
        return ""
    return "" if re.search(pattern, answer) else f"答复不匹配 {pattern}"


def _check_status(wanted: str | None, status: str) -> str:
    if not wanted:
        return ""
    return "" if status == wanted else f"run 的终态是 {status}，判据要的是 {wanted}"
