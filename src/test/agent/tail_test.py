"""尾部注入块的测试。

**这里验的是位置与预算，不是内容** —— 内容（用户信息、reminder 说什么）归 P15。
位置错一格就是每轮打掉整段 prompt cache，而那件事不报错，只是变贵。
"""

from typing import Any

from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.tail import InstalledPackageSection, StepBudgetSection, TailContextMiddleware


class FixedSection:
    """固定内容的一节，用来验预算与拼接。"""

    def __init__(self, title: str, body: str, policy: str = "") -> None:
        self._title = title
        self._body = body
        self._policy = policy

    @property
    def title(self) -> str:
        return self._title

    @property
    def policy(self) -> str:
        return self._policy

    def render(self, request: ModelRequest) -> str:
        return self._body


class ExplodingSection:
    """渲染时抛异常的一节。"""

    @property
    def title(self) -> str:
        return "会炸的一节"

    @property
    def policy(self) -> str:
        return ""

    def render(self, request: ModelRequest) -> str:
        raise RuntimeError("这一节坏了")


class FakeResponse:
    """带 result 的响应替身 —— 块要写进这里才进得了 state。"""

    def __init__(self) -> None:
        self.result: list[Any] = [AIMessage(content="好的")]


def a_request(*message: Any) -> Any:  # noqa: ANN401 - 测试替身
    """造一个只带消息的最小请求替身。"""

    class Request:
        def __init__(self, messages: list[Any] | None = None) -> None:
            self.messages = list(message) if messages is None else messages

        def override(self, **change: Any) -> "Request":  # noqa: ANN401
            return Request(change.get("messages", self.messages))

    return Request()


def test_the_block_goes_after_the_last_message() -> None:
    """位置就是这一条的全部意义：落进前缀就是每轮打掉整段缓存。"""
    middleware = TailContextMiddleware(sections=[FixedSection("环境", "沙箱正常")])
    seen: dict[str, Any] = {}

    def handler(request: Any) -> FakeResponse:  # noqa: ANN401
        seen["messages"] = request.messages
        return FakeResponse()

    middleware.wrap_model_call(a_request(HumanMessage(content="算一下波动率")), handler)

    assert len(seen["messages"]) == 2
    assert isinstance(seen["messages"][-1], HumanMessage)
    assert "沙箱正常" in str(seen["messages"][-1].content)
    assert "算一下波动率" in str(seen["messages"][0].content)


def test_nothing_is_appended_when_every_section_is_silent() -> None:
    """没话可说时不该多出一条空消息 —— 那是白烧的 token，还打乱对话结构。"""
    middleware = TailContextMiddleware(sections=[FixedSection("环境", "")])
    seen: dict[str, Any] = {}

    def handler(request: Any) -> FakeResponse:  # noqa: ANN401
        seen["messages"] = request.messages
        return FakeResponse()

    middleware.wrap_model_call(a_request(HumanMessage(content="问题")), handler)

    assert len(seen["messages"]) == 1


def test_the_budget_drops_whole_sections_from_the_end() -> None:
    """超预算丢整节，不切半句 —— 半截的状态信息比没有更糟，模型会把截断处当事实。"""
    middleware = TailContextMiddleware(
        sections=[FixedSection("甲", "一" * 50), FixedSection("乙", "二" * 50)],
        budget_char=80,
    )

    block = middleware.render_block(a_request(HumanMessage(content="问题")))

    assert "甲" in block
    assert "乙" not in block


def test_a_broken_section_does_not_sink_the_run() -> None:
    """状态信息是辅助的，对话本身不是。"""
    middleware = TailContextMiddleware(sections=[ExplodingSection(), FixedSection("环境", "沙箱正常")])

    block = middleware.render_block(a_request(HumanMessage(content="问题")))

    assert "沙箱正常" in block


def test_step_budget_counts_the_model_turns() -> None:
    """撞上限的 run 会直接断，而 agent 事先拿不到任何信号 —— 这一节就是那个信号。

    **过半才开口**，所以这里把上限调小，让两轮就算走过半程。
    """
    section = StepBudgetSection(limit=4)
    request = a_request(
        HumanMessage(content="问题"),
        AIMessage(content="第一轮"),
        AIMessage(content="第二轮"),
    )

    assert "2" in section.render(request)
    assert "4" in section.render(request)


def test_installed_packages_are_read_off_the_history() -> None:
    """P12 之后装完当前会话一直在。没有这一节，agent 会把同一个包重复装一遍。"""
    section = InstalledPackageSection()
    request = a_request(
        AIMessage(
            content="装个包",
            tool_calls=[{"id": "c1", "name": "execute", "args": {"command": "pip install statsmodels"}}],
        ),
        AIMessage(
            content="再装一个",
            tool_calls=[{"id": "c2", "name": "execute", "args": {"command": "pip install scipy==1.11"}}],
        ),
    )

    body = section.render(request)

    assert "statsmodels" in body
    assert "scipy" in body


def test_no_package_section_when_nothing_was_installed() -> None:
    section = InstalledPackageSection()

    assert section.render(a_request(HumanMessage(content="问题"))) == ""


def test_the_block_never_touches_the_system_message() -> None:
    """块只能落在消息末尾，不许碰系统提示词。

    碰了就是每轮打掉整段 prompt cache —— 平台的价签是命中与不命中差 30 倍，
    而这件事不报错，只是变贵。
    """
    middleware = TailContextMiddleware(sections=[FixedSection("环境", "沙箱正常")])
    seen: dict[str, Any] = {}

    def handler(request: Any) -> FakeResponse:  # noqa: ANN401
        seen["changed"] = getattr(request, "system_message", "没动过")
        return FakeResponse()

    middleware.wrap_model_call(a_request(HumanMessage(content="问题")), handler)

    assert seen["changed"] == "没动过"


def test_a_policy_is_spoken_once_not_every_turn() -> None:
    """策略是不变的那一半，说过就留在轨迹里了 —— 每轮重复一遍纯属白付 token。"""
    middleware = TailContextMiddleware(sections=[FixedSection("沙箱", "正常", policy="别慌")])

    first = middleware.render_block(a_request(HumanMessage(content="问题")))
    assert "别慌" in first

    # 轨迹里已经有那条块了（持久追加），这一轮就不该再说一遍策略
    again = middleware.render_block(a_request(HumanMessage(content="问题"), HumanMessage(content=first)))
    assert "正常" in again
    assert "别慌" not in again


def test_the_step_section_reports_on_every_turn() -> None:
    """每一轮都报读数。

    此前设过「走过半程才开口」的闸门 —— 依据（块每轮变会打掉缓存）成立，但处置错了：
    真正的解法是把块写回轨迹，不是闭嘴。何况 60 步的一半是 15 轮，而多数分析总共 6–11 轮。
    """
    section = StepBudgetSection(limit=60)

    early = section.render(a_request(HumanMessage(content="问题"), AIMessage(content="一轮")))
    assert "1" in early
