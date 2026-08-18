import asyncio

from app.worker.watchdog import Watchdog

# 盖时间戳的间隔与判死的阈值。取得很小是为了让用例几百毫秒就跑完，
# 两者的比值与生产里一致（阈值远大于间隔）
BEAT = 0.01
STALE = 0.15


async def test_a_wedged_event_loop_gets_the_process_halted() -> None:
    """看门狗跑在线程里，因此事件循环停转时它照样动得了手。

    没有人盖时间戳，等同于事件循环从一开始就卡住。
    """
    halted: list[int] = []
    dog = Watchdog(beat_second=BEAT, stale_second=STALE, halt=lambda: halted.append(1))

    dog.watch()
    await asyncio.sleep(STALE * 3)
    dog.stop()

    assert halted


async def test_a_long_await_is_not_mistaken_for_a_wedged_loop() -> None:
    """一次分析要跑几十分钟，主循环长时间停在 await 上是常态，不是卡死。

    判据必须是「事件循环还调度得动」，不是「有没有在干活」——
    后者会把每一次正常的长分析都判成死。
    """
    halted: list[int] = []
    dog = Watchdog(beat_second=BEAT, stale_second=STALE, halt=lambda: halted.append(1))
    beat = asyncio.create_task(dog.beat())

    dog.watch()
    await asyncio.sleep(STALE * 3)
    dog.stop()
    beat.cancel()

    assert not halted


async def test_stopping_the_watchdog_ends_the_thread() -> None:
    """优雅停机时看门狗要先撤，否则收尾那几步会被它当成卡死。"""
    dog = Watchdog(beat_second=BEAT, stale_second=STALE, halt=lambda: None)

    thread = dog.watch()
    dog.stop()
    thread.join(timeout=1)

    assert not thread.is_alive()
