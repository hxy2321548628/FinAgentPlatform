"""前缀稳定性：A2 那条规则本身。

**DeepSeek 的 prompt cache 是服务端按前缀自动命中的**，平台这边能做的只有一件事 ——
让前缀别变。命中与不命中的单价差 30 倍，而前缀被打掉这件事不报错，只是变贵。

deepagents 自带的 `append_prompt_caching_middleware` 只装 Anthropic / Bedrock /
Fireworks 三家，**DeepSeek 一个都不沾**，所以没有中间件替我们守这条规则 —— 只有这份测试。
"""

from typing import Any, ClassVar

import pytest
from deepagents.backends.state import StateBackend
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.factory import Agent
from app.agent.tail import BLOCK_HEADER


class RecordingModel(GenericFakeChatModel):
    """记录每次调用收到了什么的假模型。"""

    seen: ClassVar[list[list[Any]]] = []

    def bind_tools(self, tools: Any, **keyword: Any) -> "RecordingModel":  # noqa: ANN401
        return self

    def _generate(self, messages: list[Any], *argument: Any, **keyword: Any) -> Any:  # noqa: ANN401
        RecordingModel.seen.append(list(messages))
        return super()._generate(messages, *argument, **keyword)


async def drain(stream: Any) -> None:  # noqa: ANN401
    async for _ in stream:
        pass


@pytest.fixture(autouse=True)
def _clear() -> None:
    RecordingModel.seen = []


async def test_the_prefix_stays_byte_identical_across_turns() -> None:
    """两轮之间系统提示词必须逐字节相同 —— 变一个字就是整段缓存作废。"""
    model = RecordingModel(messages=iter([AIMessage(content="好的") for _ in range(20)]))
    runner = Agent(model=model, checkpointer=InMemorySaver())
    backend = StateBackend()

    await drain(runner.stream(backend, "prefix-thread", "第一问：算一下波动率"))
    await drain(runner.stream(backend, "prefix-thread", "第二问：再画张图"))

    prompts = {
        str(message.content) for call in RecordingModel.seen for message in call if isinstance(message, SystemMessage)
    }
    assert len(RecordingModel.seen) >= 2
    assert len(prompts) == 1, "系统提示词在两轮之间变了，前缀缓存会每轮作废"


async def test_the_dynamic_block_rides_at_the_tail_not_in_the_prefix() -> None:
    """动态信息该出现在最后一条消息里，而不是系统提示词里。

    **标记文本跟着常量走**，不写死 —— 2026-08-19 把它从「平台状态」改成
    `<system-reminder>` 时，两条写死的断言一起红了，而红的地方与改动无关。
    """
    model = RecordingModel(messages=iter([AIMessage(content="好的") for _ in range(40)]))
    runner = Agent(model=model, checkpointer=InMemorySaver())
    backend = StateBackend()

    for turn in range(3):
        await drain(runner.stream(backend, "tail-thread", f"第 {turn} 问"))

    last_call = RecordingModel.seen[-1]
    system = next(one for one in last_call if isinstance(one, SystemMessage))
    assert BLOCK_HEADER not in str(system.content)
    assert BLOCK_HEADER in str(last_call[-1].content)


async def test_each_turn_extends_the_previous_call_verbatim() -> None:
    """每一次调用的消息序列必须是上一次的**严格扩展**。

    这条就是「缓存前缀不断」的定义，也是本期最贵的一条判据：块只作用于当次调用、
    不写回 state 的话，下一次调用在块的位置换成了真实历史 —— 服务端缓存里那一格是块、
    请求里那一格是回复，**从这里分叉**，其后全部重算。
    """
    model = RecordingModel(messages=iter([AIMessage(content="好的") for _ in range(40)]))
    runner = Agent(model=model, checkpointer=InMemorySaver())
    backend = StateBackend()

    for turn in range(4):
        await drain(runner.stream(backend, "grow-thread", f"第 {turn} 问"))

    for index, (earlier, later) in enumerate(zip(RecordingModel.seen, RecordingModel.seen[1:], strict=False)):
        head = [str(one.content) for one in later[: len(earlier)]]
        assert head == [str(one.content) for one in earlier], f"第 {index + 1} 次调用没有沿用上一次的前缀"


async def test_an_unchanged_block_is_not_appended_twice() -> None:
    """状态没变就不必再说一遍 —— 持久追加的代价是陈旧状态累积，能省一条是一条。"""
    model = RecordingModel(messages=iter([AIMessage(content="好的") for _ in range(40)]))
    runner = Agent(model=model, checkpointer=InMemorySaver())
    backend = StateBackend()

    for turn in range(5):
        await drain(runner.stream(backend, "dup-thread", f"第 {turn} 问"))

    last_call = RecordingModel.seen[-1]
    blocks = [str(one.content) for one in last_call if str(one.content).startswith(BLOCK_HEADER)]
    assert len(blocks) == len(set(blocks)), f"历史里有内容完全相同的重复状态块：{blocks}"
