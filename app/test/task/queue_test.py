"""任务队列的测试，连真 Redis。

ADR-0005 把 consumer group 的这几行点名为「自写的、要自己保证正确性」的部分，
因此这里验的都是**分发语义**：不重复、不丢、崩了能被别人接走。
用假 Redis 验不了这些 —— 要验的正是 Redis 那几条命令组合起来是什么行为。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from task.queue import RunTask, TaskQueue

# 认领阈值取 0：pending 里的消息一律可认领。取一个很小的正数会让断言的真假
# 取决于两行代码之间过了几毫秒 —— 那种偶发的红比没有测试更糟
INSTANT_CLAIM_MILLISECOND = 0

# 队列空时不必真等 5 秒
SHORT_BLOCK_MILLISECOND = 50


def a_task(content: str = "一") -> RunTask:
    return RunTask(run_id=uuid4().hex, thread_id=uuid4().hex, content=content)


def make_queue(client: Redis, consumer: str, *, claim_idle_millisecond: int = 60_000) -> TaskQueue:
    return TaskQueue(
        client,
        consumer=consumer,
        block_millisecond=SHORT_BLOCK_MILLISECOND,
        claim_idle_millisecond=claim_idle_millisecond,
    )


@pytest.fixture
async def queue(live_cache: Redis) -> TaskQueue:
    created = make_queue(live_cache, "worker-a")
    await created.ensure_group()
    return created


# ------------------------------------------------------------------ 投递与领取
async def test_a_published_task_comes_back_intact(queue: TaskQueue) -> None:
    task = a_task("算个波动率")
    await queue.publish(task)

    delivery = await queue.reserve()

    assert delivery is not None
    assert delivery.task == task


async def test_an_empty_queue_hands_out_nothing(queue: TaskQueue) -> None:
    assert await queue.reserve() is None


async def test_ensure_group_can_be_called_again(live_cache: Redis) -> None:
    """每个 worker 启动时都会调一次，谁先起来谁建 —— 第二个不能因此起不来。"""
    first = make_queue(live_cache, "worker-a")
    await first.ensure_group()

    await make_queue(live_cache, "worker-b").ensure_group()

    await first.publish(a_task())
    assert await first.reserve() is not None


# ------------------------------------------------------------------ 两个副本
async def test_two_workers_never_get_the_same_task(live_cache: Redis) -> None:
    """验收标准③的核心：consumer group 保证一条消息只分给一个消费者。"""
    first, second = make_queue(live_cache, "worker-a"), make_queue(live_cache, "worker-b")
    await first.ensure_group()
    published = [a_task(str(index)) for index in range(6)]
    for task in published:
        await first.publish(task)

    taken: list[str] = []
    for _ in range(len(published)):
        for queue in (first, second):
            delivery = await queue.reserve()
            if delivery is not None:
                taken.append(delivery.task.run_id)

    assert sorted(taken) == sorted(task.run_id for task in published)


async def test_nothing_is_lost_when_both_workers_pull(live_cache: Redis) -> None:
    """不重复之外还要不丢：两条断言少哪一条，另一条都能靠「什么都不发」满足。"""
    first, second = make_queue(live_cache, "worker-a"), make_queue(live_cache, "worker-b")
    await first.ensure_group()
    for index in range(4):
        await first.publish(a_task(str(index)))

    taken = 0
    for _ in range(6):
        for queue in (first, second):
            if await queue.reserve() is not None:
                taken += 1

    assert taken == 4


# ------------------------------------------------------------------ 崩溃与重投
async def test_an_unacked_task_stays_pending(queue: TaskQueue) -> None:
    """领了没 ack 就等于「还没跑完」。worker 被 kill -9 时留下的就是这个状态。"""
    await queue.publish(a_task())
    await queue.reserve()

    assert await queue.pending_count() == 1


async def test_an_acked_task_leaves_the_pending_list(queue: TaskQueue) -> None:
    await queue.publish(a_task())
    delivery = await queue.reserve()
    assert delivery is not None

    await queue.ack(delivery.id)

    assert await queue.pending_count() == 0


async def test_another_worker_claims_what_a_dead_one_left_behind(live_cache: Redis) -> None:
    """验收标准①的前半段：worker 崩了，任务不能就此消失。"""
    dead = make_queue(live_cache, "worker-dead")
    await dead.ensure_group()
    task = a_task()
    await dead.publish(task)
    await dead.reserve()

    alive = make_queue(live_cache, "worker-alive", claim_idle_millisecond=INSTANT_CLAIM_MILLISECOND)
    reclaimed = await alive.reserve()

    assert reclaimed is not None
    assert reclaimed.task.run_id == task.run_id


async def test_a_touched_task_is_not_stolen_from_a_healthy_worker(live_cache: Redis) -> None:
    """跑着的 worker 要能宣告「我还活着」。

    没有这条，认领阈值就必须大于最长的一次 run —— 而那意味着崩溃恢复要等几十分钟。
    """
    busy = make_queue(live_cache, "worker-busy")
    await busy.ensure_group()
    await busy.publish(a_task())
    delivery = await busy.reserve()
    assert delivery is not None

    await busy.touch(delivery.id)
    thief = make_queue(live_cache, "worker-thief", claim_idle_millisecond=60_000)

    assert await thief.reserve() is None


async def test_reclaimed_tasks_are_handed_out_before_new_ones(live_cache: Redis) -> None:
    """崩溃遗留的任务已经烧过一轮 token，排在新任务后面等于把那笔钱再花一次。"""
    dead = make_queue(live_cache, "worker-dead")
    await dead.ensure_group()
    stale = a_task("崩溃前那一条")
    await dead.publish(stale)
    await dead.reserve()
    await dead.publish(a_task("崩溃后新来的"))

    alive = make_queue(live_cache, "worker-alive", claim_idle_millisecond=INSTANT_CLAIM_MILLISECOND)
    first = await alive.reserve()

    assert first is not None
    assert first.task.run_id == stale.run_id
