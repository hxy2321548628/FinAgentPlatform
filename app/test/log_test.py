"""结构化日志的测试：验的是「一行能不能被 jq 解析」与「run 身份有没有带上」。"""

import asyncio
import json
import logging
from collections.abc import Iterator
from io import StringIO

import pytest

from log import JsonFormatter, configure, run_context

LOGGER_NAME = "test.structured"


@pytest.fixture
def sink() -> Iterator[StringIO]:
    """一个只挂了 JSON formatter 的日志出口，测完摘干净。"""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


def lines(sink: StringIO) -> list[dict[str, object]]:
    """把出口里的每一行当 JSON 解析 —— 解析不了就是 jq 也解析不了。"""
    return [json.loads(one) for one in sink.getvalue().splitlines()]


# ------------------------------------------------------------------ 行的形状
def test_a_log_line_is_a_single_json_object(sink: StringIO) -> None:
    logging.getLogger(LOGGER_NAME).info("沙箱已就绪")

    assert lines(sink) == [
        {
            "ts": lines(sink)[0]["ts"],
            "level": "INFO",
            "logger": LOGGER_NAME,
            "message": "沙箱已就绪",
        }
    ]


def test_percent_style_arguments_are_rendered_into_the_message(sink: StringIO) -> None:
    """现有日志点全是 `logger.info("x=%s", v)` 的写法，不渲染就只剩模板。"""
    logging.getLogger(LOGGER_NAME).warning("沙箱 idle 超时，回收容器：thread_id=%s", "8f3a")

    assert lines(sink)[0]["message"] == "沙箱 idle 超时，回收容器：thread_id=8f3a"


def test_chinese_stays_readable_instead_of_escaped(sink: StringIO) -> None:
    """日志首先是给人看的，转义成 unicode 码点之后连 grep 都用不了。"""
    logging.getLogger(LOGGER_NAME).info("容器启动失败")

    assert "容器启动失败" in sink.getvalue()


def test_the_timestamp_is_iso8601_with_a_timezone(sink: StringIO) -> None:
    logging.getLogger(LOGGER_NAME).info("一")

    assert str(lines(sink)[0]["ts"]).endswith("+00:00")


def test_an_exception_is_rendered_into_the_same_line(sink: StringIO) -> None:
    """Traceback 换行输出会把一条日志拆成十几行，jq 逐行解析全部失败。"""
    try:
        message = "docker 调用失败"
        raise RuntimeError(message)
    except RuntimeError:
        logging.getLogger(LOGGER_NAME).warning("容器启动失败", exc_info=True)

    line = lines(sink)[0]
    assert "RuntimeError: docker 调用失败" in str(line["exception"])
    assert len(sink.getvalue().splitlines()) == 1


# ------------------------------------------------------------------ run 上下文
def test_a_line_inside_a_run_carries_both_ids(sink: StringIO) -> None:
    with run_context(run_id="run-1", thread_id="thread-1"):
        logging.getLogger(LOGGER_NAME).info("开始执行")

    line = lines(sink)[0]
    assert line["run_id"] == "run-1"
    assert line["thread_id"] == "thread-1"


def test_a_line_outside_a_run_omits_the_ids(sink: StringIO) -> None:
    """启动、路由这些日志本就不属于任何 run，硬塞一个空值只会污染 jq 的过滤。"""
    logging.getLogger(LOGGER_NAME).info("应用已启动")

    assert "run_id" not in lines(sink)[0]
    assert "thread_id" not in lines(sink)[0]


def test_the_ids_are_restored_after_leaving_the_context(sink: StringIO) -> None:
    with run_context(run_id="run-1", thread_id="thread-1"):
        pass
    logging.getLogger(LOGGER_NAME).info("收尾")

    assert "run_id" not in lines(sink)[0]


async def test_two_concurrent_runs_do_not_see_each_others_ids(sink: StringIO) -> None:
    """两个 run 同时在跑是常态，串号会让排障时的日志过滤直接失效。"""

    async def one(run_id: str) -> None:
        with run_context(run_id=run_id, thread_id=f"thread-{run_id}"):
            await asyncio.sleep(0)
            logging.getLogger(LOGGER_NAME).info("干活")

    await asyncio.gather(one("run-1"), one("run-2"))

    assert {str(line["run_id"]) for line in lines(sink)} == {"run-1", "run-2"}


async def test_all_lines_of_one_run_can_be_filtered_by_run_id(sink: StringIO) -> None:
    """验收标准①：一次 run 的全部日志能按 run_id 过滤出来。"""
    with run_context(run_id="run-1", thread_id="thread-1"):
        logging.getLogger(LOGGER_NAME).info("申请沙箱")
        logging.getLogger(LOGGER_NAME).info("沙箱就绪")
    logging.getLogger(LOGGER_NAME).info("与本 run 无关")

    assert len([line for line in lines(sink) if line.get("run_id") == "run-1"]) == 2


# ------------------------------------------------------------------ 安装
def test_configure_routes_uvicorn_logs_through_the_json_formatter() -> None:
    """Uvicorn 自带的文本行会夹在 JSON 行中间，让整份日志无法被 jq 逐行解析。"""
    root_handler = logging.getLogger().handlers[:]
    uvicorn = logging.getLogger("uvicorn.access")
    uvicorn_handler, propagate = uvicorn.handlers[:], uvicorn.propagate
    uvicorn.addHandler(logging.StreamHandler())

    try:
        configure(level="INFO")

        assert uvicorn.handlers == []
        assert uvicorn.propagate is True
        assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)
    finally:
        logging.getLogger().handlers = root_handler
        uvicorn.handlers, uvicorn.propagate = uvicorn_handler, propagate
