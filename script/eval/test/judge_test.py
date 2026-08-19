"""判分器的测试。**不调真实模型** —— 验的是解析与降级，不是模型答得准不准。"""

import httpx
from judge import Judge


class FakePrompt:
    prompt = "题目：{{question}}\n答复：{{answer}}"
    version = 3


class FakeLangfuse:
    def get_prompt(self, name: str, label: str = "") -> FakePrompt:
        return FakePrompt()


def a_judge(content: str, *, status: int = 200) -> Judge:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://model")
    return Judge(langfuse=FakeLangfuse(), client=client)  # type: ignore[arg-type]


def test_a_clean_json_answer_is_parsed() -> None:
    verdict = a_judge('{"score": 4, "reason": "口径交代清楚"}').score(question="问", answer="答")

    assert verdict.score == 4
    assert verdict.reason == "口径交代清楚"
    assert verdict.rubric_version == 3


def test_a_chatty_answer_still_yields_a_score() -> None:
    """模型常常会在 JSON 前后多写几个字，正则比 json.loads 稳。"""
    verdict = a_judge('好的，我的判断是：\n```json\n{"score": 2, "reason": "没有支撑"}\n```').score(
        question="问", answer="答"
    )

    assert verdict.score == 2


def test_an_unparseable_answer_scores_none_not_zero() -> None:
    """判不出来是 None，不是 0 —— 0 是「很差」，混在一起会让一次故障看着像质量暴跌。"""
    verdict = a_judge("我觉得还行吧").score(question="问", answer="答")

    assert verdict.score is None


def test_a_failed_request_scores_none() -> None:
    verdict = a_judge("", status=500).score(question="问", answer="答")

    assert verdict.score is None
    assert "500" in verdict.reason


def test_an_empty_answer_is_not_sent_to_the_model() -> None:
    """空答复没有可判的内容，送过去只是白花一次调用。"""
    verdict = a_judge('{"score": 5}').score(question="问", answer="   ")

    assert verdict.score is None
