"""事件循环的看门狗：卡死时把进程结束掉，交给 Docker 重启。

**单副本部署下没有第二个进程能接管**，而 Docker 的 `restart` 只认进程退出 ——
健康检查判出 unhealthy 并不会让它重启容器（那是 Swarm 才有的行为）。因此
「进程还活着但事件循环不转了」必须由进程自己变成「进程退出」，否则没有任何东西
会发现它：任务照样被领走，然后永远不动，直到认领阈值到了被自己重启后的下一条命捡回来。

**判据是「事件循环还调度得动」，不是「有没有在干活」。** 一次分析要跑几十分钟，
主循环长时间停在 `await` 上是常态；按「有没有进展」判死会把每一次正常的长分析都误杀。
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 多久盖一次时间戳
DEFAULT_BEAT_SECOND = 10.0

# 多久没盖上就判定卡死。要远大于盖章间隔 —— 一次 GC 停顿或一段密集的
# 事件翻译都可能让盖章晚上几秒，那不是卡死
DEFAULT_STALE_SECOND = 60.0

# 退出码。挑一个不与正常失败重合的值，好在日志里一眼认出是被看门狗结束的
HALT_EXIT_CODE = 70


def _halt() -> None:
    """立刻结束进程。

    **不能走 `SIGTERM` 那条优雅停机的路** —— 那个处理器本身要事件循环去调度，
    而这时它已经不转了。日志先冲干净，否则最关键的那一行会跟着进程一起没。
    """
    logging.shutdown()
    os._exit(HALT_EXIT_CODE)


class Watchdog:
    """盯着事件循环还转不转，不转就结束进程。

    Args:
        beat_second: 事件循环多久盖一次时间戳。
        stale_second: 时间戳多久没更新就判定卡死。
        halt: 判定卡死后做什么，默认是结束进程。
        now: 取当前时刻，用单调钟 —— 系统时间回拨不该被当成卡死。
    """

    def __init__(
        self,
        *,
        beat_second: float = DEFAULT_BEAT_SECOND,
        stale_second: float = DEFAULT_STALE_SECOND,
        halt: Callable[[], None] = _halt,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._beat_second = beat_second
        self._stale_second = stale_second
        self._halt = halt
        self._now = now
        self._stamped = now()
        self._stopping = threading.Event()

    async def beat(self) -> None:
        """在事件循环里跑：定期盖时间戳。被取消即结束。"""
        while True:
            self._stamped = self._now()
            await asyncio.sleep(self._beat_second)

    def watch(self) -> threading.Thread:
        """起一个守护线程盯着时间戳。

        **必须是线程而不是任务**：事件循环卡住的时候，任何跑在它上面的东西
        一起卡住，包括本该来救场的那个。

        Returns:
            已经跑起来的守护线程。
        """
        thread = threading.Thread(target=self._watch, name="worker-watchdog", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """撤掉看门狗。

        **优雅停机时要先撤**：收尾那几步会归还连接、等在跑的 run 结束，
        期间没人盖时间戳，留着它只会在正常停机的路上开一枪。
        """
        self._stopping.set()

    def _watch(self) -> None:
        while not self._stopping.wait(self._beat_second):
            idle = self._now() - self._stamped
            if idle < self._stale_second:
                continue
            logger.critical("事件循环已经 %.0f 秒没有响应，结束进程等待重启", idle)
            self._halt()
            return
