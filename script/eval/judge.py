"""辅助模型判分：只判「分析思路是否站得住」这一个维度。

**为什么不用主模型**：给自己的输出打分有偏，且贵一个数量级。

**为什么只判一个维度**：判分模型自己有方差，能写成客观判据的一律不交给它。
这一项是唯一写不成客观判据的 —— 「思路站不站得住」没法用正则判。

**rubric 从 Langfuse 取并锁 production 标签**，版本号跟着结果一起落盘：
不记版本号的话，半年后不知道这批分是哪一版打的，跨轮对比就没有意义。
"""

import json
import os
import re
from dataclasses import dataclass

import httpx
from langfuse import Langfuse

PROMPT_NAME = "judge-rubric"
DEFAULT_MODEL = "deepseek-v4-flash"
TIMEOUT_SECOND = 120.0
# 判分要的是稳定而不是创意。**不设 max_tokens** —— 推理型模型会把预算全花在推理上，
# 结果 content 恒为空，而每次都是 HTTP 200
TEMPERATURE = 0.0
SCORE_PATTERN = re.compile(r'"score"\s*:\s*([1-5])')


@dataclass(frozen=True)
class Judgement:
    """一次判分的结果。"""

    score: int | None
    reason: str
    rubric_version: int


class Judge:
    """按 Langfuse 上托管的 rubric 判分。

    Args:
        langfuse: 已建好的客户端，用来取 rubric。
        client: 已建好的 HTTP 客户端，指向模型网关。
        model: 判分用的模型，默认辅助模型。
    """

    def __init__(self, *, langfuse: Langfuse, client: httpx.Client, model: str = DEFAULT_MODEL) -> None:
        prompt = langfuse.get_prompt(PROMPT_NAME, label="production")
        self._template = str(prompt.prompt)
        self._version = int(prompt.version)
        self._client = client
        self._model = model

    @property
    def rubric_version(self) -> int:
        """这一批分是哪一版 rubric 打的。"""
        return self._version

    def score(self, *, question: str, answer: str) -> Judgement:
        """判一条答复。

        **判不出来时返回 None 而不是 0** —— 0 是「很差」，None 是「没判成」，
        混在一起会让一次网络故障看着像质量暴跌。
        """
        if not answer.strip():
            return Judgement(score=None, reason="答复是空的，没有可判的内容", rubric_version=self._version)
        filled = self._template.replace("{{question}}", question).replace("{{answer}}", answer)
        response = self._client.post(
            "/chat/completions",
            json={"model": self._model, "messages": [{"role": "user", "content": filled}], "temperature": TEMPERATURE},
        )
        if response.is_error:
            return Judgement(score=None, reason=f"判分请求失败：{response.status_code}", rubric_version=self._version)
        content = str(response.json()["choices"][0]["message"]["content"])
        return self._parse(content)

    def _parse(self, content: str) -> Judgement:
        """从模型输出里取分数。它常常会多写几个字，正则比 json.loads 稳。"""
        try:
            parsed = json.loads(content.strip().strip("`"))
            return Judgement(
                score=int(parsed["score"]),
                reason=str(parsed.get("reason", "")),
                rubric_version=self._version,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            found = SCORE_PATTERN.search(content)
            if not found:
                return Judgement(score=None, reason=f"判分输出解析不了：{content[:80]}", rubric_version=self._version)
            return Judgement(score=int(found.group(1)), reason=content[:120], rubric_version=self._version)


def create_judge(*, langfuse: Langfuse, client: httpx.Client) -> Judge:
    """按环境里的模型配置造一个判分器。"""
    return Judge(langfuse=langfuse, client=client, model=os.environ.get("MODEL_AUX", DEFAULT_MODEL))
