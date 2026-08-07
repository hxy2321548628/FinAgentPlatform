"""Worker 进程的入口。

    cd app && uv run python -m worker.main

**它不是一个 HTTP 服务**，因此没有 uvicorn，也不对外开端口 —— 它只跟 Redis、
Postgres 和 broker 说话。要看它在干什么，看日志。

`SIGTERM` 走优雅停机：不再领新任务，等在跑的 run 结束。`docker compose up -d`
的滚动重启发的就是它，而一次分析要跑几十分钟，掐掉等于把已经花掉的 token 扔了。
"""

import asyncio
import logging
import signal

from config import get_settings
from log import configure
from worker.runtime import build_worker

logger = logging.getLogger(__name__)


async def serve() -> None:
    """起 worker，接住停机信号，收尾。"""
    runtime = await build_worker(get_settings())
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, lambda: asyncio.create_task(runtime.worker.stop()))
    try:
        await runtime.worker.run()
    finally:
        logger.info("worker 停机")
        await runtime.aclose()


def main() -> None:
    """进程入口。"""
    configure()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
