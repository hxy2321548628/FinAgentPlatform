"""上下文预算的测试。

**这里验的是「阈值是平台自己定的」**，不验「压缩在多少 token 时真的发生」——
后者要真跑一次图，是验收判据 P13② 的活。
"""

from deepagents.backends.state import StateBackend
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from app.agent.context import CONTEXT_KEEP_RATIO, CONTEXT_TRIGGER_TOKEN, create_squeezer


def a_squeezer() -> object:
    return create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend())


def test_the_trigger_is_a_platform_constant_not_a_profile_guess() -> None:
    """阈值必须来自平台，不能是从模型 profile 推出来的那个。

    默认是 85% × 100 万。实测模型确实吃得下百万上下文，但一次分析的历史峰值只有两万 ——
    那条线因此永远够不着，压缩等于从未生效过。
    """
    # 私有属性：上游改名这条就会失灵，所以另有一条真跑的判据（P13②）兜底
    assert a_squeezer()._lc_helper.trigger == ("tokens", CONTEXT_TRIGGER_TOKEN)  # type: ignore[attr-defined]


def test_the_platform_copy_replaces_the_default_one() -> None:
    """名字必须与基础栈里那份一致，否则不是替换而是叠加。

    两套压缩都改写历史，谁先触发不确定，且都会打掉前缀缓存。
    """
    assert a_squeezer().name == "SummarizationMiddleware"  # type: ignore[attr-defined]


def test_the_threshold_is_far_below_the_model_ceiling() -> None:
    """实测上限一百万。阈值贴着上限定就等于不压；离得太近也一样。"""
    assert CONTEXT_TRIGGER_TOKEN < 200_000


def test_the_trigger_can_be_dialled_down_for_verification() -> None:
    """压缩到底触没触发，只有把阈值调到极小值跑一道普通题才验得出来（P13②）。"""
    squeezer = create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend(), trigger_token=2_000)

    assert squeezer._lc_helper.trigger == ("tokens", 2_000)  # type: ignore[attr-defined]


def test_keeping_by_token_not_by_message_count() -> None:
    """按条数保留等于不压。

    类默认是保留最近二十条消息，而一次分析的历史通常就十几条 —— 没有任何东西可以折叠，
    token 再多也不触发。2026-08-19 真机上栽出来的。
    """
    keep = a_squeezer()._lc_helper.keep  # type: ignore[attr-defined]

    assert keep == ("tokens", int(CONTEXT_TRIGGER_TOKEN * CONTEXT_KEEP_RATIO))


def test_a_dialled_down_trigger_still_leaves_room_to_compact() -> None:
    """验收时把 trigger 调到极小，保留量要跟着走。

    keep 写死的话会出现「保留的比触发线还多」—— 逻辑上永远不可能压，
    而那个「没触发」看着就像功能坏了。
    """
    squeezer = create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend(), trigger_token=2_000)

    kind, keep_token = squeezer._lc_helper.keep  # type: ignore[attr-defined]

    assert kind == "tokens"
    assert keep_token < 2_000
