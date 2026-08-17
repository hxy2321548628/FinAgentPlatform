"""任务队列的测试，连真 Redis。

ADR-0005 把 consumer group 的这几行点名为「自写的、要自己保证正确性」的部分，
因此这里验的都是**分发语义**：不重复、不丢、崩了能被别人接走。
用假 Redis 验不了这些 —— 要验的正是 Redis 那几条命令组合起来是什么行为。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.agent.config import AgentConfig
from app.task.queue import RunTask, TaskQueue

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
    task = a_task("算个波动率").model_copy(update={"agent_config": AgentConfig(system_prompt="每句以喵开头")})
    await queue.publish(task)

    delivery = await queue.reserve()

    assert delivery is not None
    assert delivery.task == task


def test_an_old_task_without_agent_config_uses_platform_defaults() -> None:
    old_payload = RunTask(run_id=uuid4().hex, thread_id=uuid4().hex).model_dump(exclude={"agent_config"})

    restored = RunTask.model_validate(old_payload)

    assert restored.agent_config == AgentConfig()


def test_the_task_snapshot_omits_default_none_values() -> None:
    task = a_task().model_copy(update={"agent_config": AgentConfig()})

    payload = task.model_dump(exclude_none=True)

    assert payload["agent_config"] == {}


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


async def test_a_queue_that_never_started_reports_no_backlog(live_cache: Redis) -> None:
    """Consumer group 还没建出来时答 0，而不是抛。

    全新部署到第一条任务投进来之间就是这个状态，而这个数要喂给抓取端点 ——
    让它 500 的话，监控恰好在最该看它的那一段（刚部署完）是瞎的。
    """
    assert await make_queue(live_cache, "worker-never-started").pending_count() == 0


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


# ------------------------------------------------------------------ 队列里还有谁
# 收割孤儿 run 的唯一判据。**误判的代价是不对称的**：漏掉一个孤儿只是它多躺一会儿，
# 而错杀一个正在跑的 run 会把教师烧了几十万 token 的分析判成失败。
# 因此这一组的重点全在「什么不该被算成孤儿」
async def test_a_task_a_worker_is_holding_counts_as_in_flight(queue: TaskQueue) -> None:
    """领了还没 ack 的，正被某个 worker 跑着。"""
    task = a_task()
    await queue.publish(task)
    await queue.reserve()

    assert await queue.in_flight() == {task.run_id}


async def test_a_task_nobody_has_picked_up_yet_counts_as_in_flight(queue: TaskQueue) -> None:
    """**这一条是本组的重点。**

    worker 并发满了的时候，`queued` 的 run 会合法地在流里等很久 —— 它既不在 pending
    列表里（还没人领），也不该被当成孤儿。只看 pending 的话，一次积压就会把
    整批还没轮到的 run 判成失败。
    """
    task = a_task()
    await queue.publish(task)

    assert await queue.in_flight() == {task.run_id}


async def test_an_acked_task_is_no_longer_in_flight(queue: TaskQueue) -> None:
    """跑完 ack 掉的不在队列里了 —— 库里若还是 queued/running，那就是个孤儿。"""
    task = a_task()
    await queue.publish(task)
    delivery = await queue.reserve()
    assert delivery is not None

    await queue.ack(delivery.id)

    assert await queue.in_flight() == set()


async def test_both_the_held_and_the_waiting_are_reported_together(queue: TaskQueue) -> None:
    """两个来源要合起来答，少哪一半都会错杀一批。"""
    held = a_task("有人拿着")
    waiting = a_task("还没轮到")
    await queue.publish(held)
    await queue.reserve()
    await queue.publish(waiting)

    assert await queue.in_flight() == {held.run_id, waiting.run_id}


async def test_a_queue_that_never_started_reports_nothing_in_flight(live_cache: Redis) -> None:
    """Group 还没建出来时答空集，而不是抛。

    **答空集是安全的**：那时库里也不可能有 queued/running 的 run。
    抛的话收割器会崩在启动那一刻，而它是个 cron —— 没人会看见。
    """
    assert await make_queue(live_cache, "worker-never-started").in_flight() == set()
