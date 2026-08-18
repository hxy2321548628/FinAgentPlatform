"""Worker 进程的入口。

    cd src && uv run python -m app.worker.main

**它不是一个 HTTP 服务**，因此没有 uvicorn，也不对外开端口 —— 它只跟 Redis、
Postgres 和 broker 说话。要看它在干什么，看日志。

`SIGTERM` 走优雅停机：不再领新任务，等在跑的 run 结束。`docker compose up -d`
的滚动重启发的就是它，而一次分析要跑几十分钟，掐掉等于把已经花掉的 token 扔了。

**看门狗与它正好相反**：事件循环卡死时 `SIGTERM` 那条路根本走不通（处理器自己
也要事件循环去调度），只能由看门狗从线程里把进程结束掉，靠 Docker 重启拉回来。
"""

import asyncio
import contextlib
import logging
import signal

from app.worker.runtime import build_worker
from app.worker.watchdog import Watchdog
from config import get_settings
from log import configure

logger = logging.getLogger(__name__)


async def serve() -> None:
    """起 worker，接住停机信号，收尾。"""
    settings = get_settings()
    runtime = await build_worker(settings)
    watchdog = Watchdog()
    beat = asyncio.create_task(watchdog.beat())
    watchdog.watch()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, lambda: asyncio.create_task(runtime.worker.stop()))
    try:
        await runtime.worker.run()
    finally:
        # 先撤看门狗再收尾：归还连接与等 run 结束的这段没人盖时间戳
        watchdog.stop()
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        logger.info("worker 停机")
        await runtime.aclose()


def main() -> None:
    """进程入口。"""
    configure()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
