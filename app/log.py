"""结构化日志：进程日志输出成 JSON 行，并自动带上当前 run 的身份。

与 `run/log.py` 是两件事：那里存的是推给教师看的业务事件，这里是给运维排障看的进程日志。
名字相近，职责不重叠。

`run_id` / `thread_id` 走 `contextvars` 而不是逐个函数加参数 —— 日志点散在执行器、
沙箱池、backend、路由各处，加参数会让一串与日志无关的签名都沾上它。
"""

import json
import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

DEFAULT_LEVEL = "INFO"

# uvicorn 自带 handler 输出人类可读的文本行。不摘掉的话，这几行会夹在 JSON 行中间，
# 让整份日志无法被 jq 逐行解析。
UVICORN_LOGGER = ("uvicorn", "uvicorn.error", "uvicorn.access")

# 模块级 ContextVar 不构成可变全局状态：每个任务持有自己的一份，
# `asyncio.create_task` 启动时复制当前 context，因此两个 run 之间不会串。
_RUN_ID: ContextVar[str | None] = ContextVar("run_id", default=None)
_THREAD_ID: ContextVar[str | None] = ContextVar("thread_id", default=None)


class JsonFormatter(logging.Formatter):
    """把一条日志渲染成一行 JSON。

    异常一并塞进同一行的 `exception` 字段：traceback 直接换行输出会把一条日志拆成
    十几行，逐行解析的工具在这里全部失败。
    """

    def format(self, record: logging.LogRecord) -> str:
        """渲染一条日志记录。"""
        line: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        run_id, thread_id = _RUN_ID.get(), _THREAD_ID.get()
        # 启动、路由这些日志本就不属于任何 run，硬塞一个空值只会污染过滤条件
        if run_id is not None:
            line["run_id"] = run_id
        if thread_id is not None:
            line["thread_id"] = thread_id

        if record.exc_info is not None:
            line["exception"] = self.formatException(record.exc_info)

        # 中文转成 \uXXXX 之后连 grep 都用不了，而日志首先是给人看的
        return json.dumps(line, ensure_ascii=False, default=str)


@contextmanager
def run_context(*, run_id: str, thread_id: str) -> Generator[None]:
    """在上下文内把 run 的身份带进每一行日志，退出时恢复原值。

    Args:
        run_id: 当前 run。
        thread_id: run 所属的会话。

    Yields:
        无。上下文内产生的日志都会带上这两个 id。
    """
    run_token = _RUN_ID.set(run_id)
    thread_token = _THREAD_ID.set(thread_id)
    try:
        yield
    finally:
        _RUN_ID.reset(run_token)
        _THREAD_ID.reset(thread_token)


def configure(*, level: str = DEFAULT_LEVEL) -> None:
    """把全进程的日志切成 JSON 行，输出到 stdout。

    Args:
        level: 根 logger 的级别。
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in UVICORN_LOGGER:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
