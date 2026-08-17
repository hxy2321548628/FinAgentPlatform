"""会话标题生成的测试。

不打真模型 —— CI 里没有凭据，也不该花钱。假模型给什么，就验收拾成了什么。
"""

import logging
from typing import ClassVar

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.thread.repository import ThreadRepository
from app.thread.title import MAX_TITLE_LENGTH, TitleWriter
from app.user.repository import User


class RecordingModel(FakeListChatModel):
    """记下调用时收到了哪些参数的假模型。"""

    received: ClassVar[dict[str, object]] = {}

    def _call(self, *args: object, **kwargs: object) -> str:
        # 类属性而不是实例属性：`FakeListChatModel` 是 pydantic 模型，
        # 实例上塞不进未声明的字段
        RecordingModel.received = dict(kwargs)
        return "波动率分析"


class ExplodingModel(FakeListChatModel):
    """一调就炸的模型。断连、限流、凭据过期在这里是同一件事。

    炸在 `_call` 而不是 `ainvoke`：那是框架真正落到实现的那一层，
    盖掉 `ainvoke` 等于连框架自己的调用路径一起绕过去了。
    """

    def _call(self, *args: object, **kwargs: object) -> str:
        message = "模型断连"
        raise RuntimeError(message)


@pytest.fixture
def threads(live_engine: AsyncEngine) -> ThreadRepository:
    return ThreadRepository(live_engine)


def _writer(model: BaseChatModel, threads: ThreadRepository) -> TitleWriter:
    return TitleWriter(model=model, repository=threads)


async def test_the_title_comes_from_the_question(threads: ThreadRepository, owner: User) -> None:
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["行业波动率分析"]), threads)

    await writer.compose(created.id, user_id=owner.id, content="按行业分组算年化波动率")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == "行业波动率分析"


async def test_quotes_around_the_title_are_stripped(threads: ThreadRepository, owner: User) -> None:
    """模型爱给标题套引号，带着引号进侧边栏很难看。"""
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["“行业波动率分析”"]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == "行业波动率分析"


async def test_an_over_long_title_is_cut(threads: ThreadRepository, owner: User) -> None:
    """提示词里写了字数上限，但模型不一定听 —— 硬截断是那道兜底。"""
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["标题" * 50]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert len(found.title) == MAX_TITLE_LENGTH


async def test_only_the_first_line_becomes_the_title(threads: ThreadRepository, owner: User) -> None:
    """模型偶尔会先给标题再补一句解释，那一句会挤满整个侧边栏。"""
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["波动率分析\n这个标题概括了用户的请求。"]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == "波动率分析"


async def test_a_model_failure_leaves_the_title_empty(threads: ThreadRepository, owner: User) -> None:
    """起不出来就留空。抛出去只会让后台任务无声无息地死掉，而分析本身跟标题无关。"""
    created = await threads.create(user_id=owner.id)
    writer = _writer(ExplodingModel(responses=[""]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == ""


async def test_an_empty_answer_leaves_the_title_empty(threads: ThreadRepository, owner: User) -> None:
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["   "]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == ""


async def test_an_answer_that_tidies_to_nothing_is_logged(
    threads: ThreadRepository, owner: User, caplog: pytest.LogCaptureFixture
) -> None:
    """**「调用成功但收拾出来是空的」必须在日志里留痕。**

    这是真实踩过的坑：辅助模型是推理模型，给它设 `max_tokens` 掐的是「推理 + 输出」
    的总和，于是它把额度全花在推理上、`content` 一个字不剩 —— 而每一次都是 HTTP 200。
    没有这条日志，现场就只剩一个空标题和一条 200 的访问日志，什么都不指向真因。
    """
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=[""]), threads)

    with caplog.at_level(logging.WARNING, logger="app.thread.title"):
        await writer.compose(created.id, user_id=owner.id, content="一")

    assert any("收拾不出标题" in one.getMessage() for one in caplog.records)


async def test_the_model_is_not_given_a_token_budget(threads: ThreadRepository, owner: User) -> None:
    """掐 token 预算对推理模型等于让标题恒为空，而它不报错 —— 止损交给超时与硬截断。"""
    model = RecordingModel(responses=["波动率分析"])
    writer = _writer(model, threads)
    created = await threads.create(user_id=owner.id)

    await writer.compose(created.id, user_id=owner.id, content="一")

    assert "max_tokens" not in model.received


async def test_a_title_the_teacher_typed_is_not_overwritten(threads: ThreadRepository, owner: User) -> None:
    """模型往返的一两秒里教师可能已经自己改了名。盖掉它是「我明明改过」那种故障。"""
    created = await threads.create(user_id=owner.id)
    await threads.update(created.id, user_id=owner.id, title="我自己起的名")
    writer = _writer(FakeListChatModel(responses=["模型起的名"]), threads)

    await writer.compose(created.id, user_id=owner.id, content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == "我自己起的名"


async def test_someone_elses_thread_is_left_alone(threads: ThreadRepository, owner: User) -> None:
    """会话标识来自请求，越权在这一层也拦得住 —— 仓储的每个查询都带 user 过滤。"""
    created = await threads.create(user_id=owner.id)
    writer = _writer(FakeListChatModel(responses=["改成我的"]), threads)

    await writer.compose(created.id, user_id="00000000000000000000000000000000", content="一")

    found = await threads.get(created.id, user_id=owner.id)
    assert found is not None
    assert found.title == ""
