"""Langfuse 接入：配没配全、身份对不对得上。

**这两件事失效时都不会报错**：没配全却以为在记，或者记了但每条 trace 都没有主人 ——
前者要等到打开 Langfuse 发现空的才发现，后者要等到有人问「这个月谁花得最多」才发现。
"""

from contextlib import nullcontext

import pytest
from pydantic import SecretStr

from app.agent.trace import SESSION_KEY, USER_KEY, attribution, create_callback, propagation
from config import Settings

BASE_URL = "http://127.0.0.1:3000"

PUBLIC_KEY = "pk-lf-test"

SECRET_KEY = "sk-lf-test"


def a_settings(**override: object) -> Settings:
    """一份配置。

    **三项 Langfuse 显式置空，不走默认值** —— `Settings` 会读仓库根的 `.env`，
    而开发机上那份多半是配好的。不写死的话「没配」这条用例在配了 Langfuse 的机器上
    直接红，且红得像是代码坏了。
    """
    field: dict[str, object] = {
        "deepseek_api_key": SecretStr("sk-test"),
        "langfuse_base_url": "",
        "langfuse_public_key": "",
        "langfuse_secret_key": SecretStr(""),
    }
    field.update(override)
    return Settings(**field)  # type: ignore[arg-type]


def test_nothing_configured_means_no_callback() -> None:
    assert create_callback(a_settings()) is None


@pytest.mark.parametrize(
    ("missing", "left"),
    [
        ("langfuse_base_url", "缺地址"),
        ("langfuse_public_key", "缺 public key"),
        ("langfuse_secret_key", "缺 secret key"),
    ],
)
def test_a_half_configured_langfuse_is_switched_off_entirely(missing: str, left: str) -> None:
    """**「配了一半」必须与「没配」同样处理。**

    留一半的话客户端会构造成功而上报一直失败，症状是 Langfuse 上空空如也 ——
    而那时人们会去查网络、查密钥，不会想到是这里少了一项。
    """
    field: dict[str, object] = {
        "langfuse_base_url": BASE_URL,
        "langfuse_public_key": PUBLIC_KEY,
        "langfuse_secret_key": SecretStr(SECRET_KEY),
    }
    field[missing] = SecretStr("") if missing == "langfuse_secret_key" else ""

    assert create_callback(a_settings(**field)) is None


def test_a_run_is_attributed_to_its_session_and_submitter() -> None:
    """两个键都要在：少了 session 就串不成一次会话，少了 user 就答不出「谁花了多少」。"""
    metadata = attribution(thread_id="thread-1", user_id="teacher-1")

    assert metadata == {SESSION_KEY: "thread-1", USER_KEY: "teacher-1"}


def test_an_anonymous_run_carries_no_user_key_at_all() -> None:
    """**不写空串**：那会在 Langfuse 那边多出一个名字为空的「用户」，把账搅浑。"""
    metadata = attribution(thread_id="thread-1", user_id=None)

    assert metadata == {SESSION_KEY: "thread-1"}


def test_an_anonymous_run_propagates_nothing() -> None:
    """没有提交人就没什么可传播的，交出一个不做事的上下文。"""
    with propagation(thread_id="thread-1", user_id=None) as entered:
        assert entered is None


def test_a_named_run_propagates_a_real_context() -> None:
    """**这一条挡的是本期最贵的那个 bug。**

    `metadata` 里的两个键只让**根** span 带上身份 —— 回调在 `on_chain_start` 里
    进的那个上下文，传不到 LangGraph 后续开出的 async 任务里。而 token 全记在
    那些任务产生的 GENERATION 上，于是「谁花了多少」按用户切出来每人都是 0，
    接口却一路返回 200。实测：裸模型调用的 GENERATION 带得上 user_id，走图的带不上。

    因此有提交人时必须交出一个**真的**上下文管理器，不能是空壳。
    """
    context = propagation(thread_id="thread-1", user_id="teacher-1")

    assert not isinstance(context, nullcontext)
