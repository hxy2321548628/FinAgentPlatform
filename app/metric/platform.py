"""平台状态的指标：run 各态计数、任务队列积压、当日 token。

**这三样都是「现查」的**，进程里不留任何计数器。理由不是省事：api 有一个进程、worker
有两个副本，任何攒在进程里的数都要在 PromQL 那一侧 `sum()` 才对得上，而漏了 `sum()`
不会报错，只会给出一个偏小的数。库里查出来的则是全平台唯一的一份。

**per-user token 的窗口与配额同一条时间线**（今天零点起），否则看板上的数与教师看到的
配额提示永远差一截，而两边各自都「没错」。
"""

from datetime import datetime
from typing import Protocol

from prometheus_client import CollectorRegistry, Gauge

from event.model import RunStatus
from metric.exposition import NAMESPACE, create_registry
from quota.usage import day_start
from report.usage import UserUsage
from run.repository import LIVE_STATUS

# token 三元组在指标里的标签值。与 `run.finished` 事件的字段名一致，
# 不另起一套 —— 两套名字对照着看是排障时最没必要的负担
CACHE_READ_KIND = "cache_read"
UNCACHED_KIND = "uncached"
OUTPUT_KIND = "output"


class RunCounterProtocol(Protocol):
    """按状态数 run 的能力。"""

    async def live_count(self) -> dict[RunStatus, int]:
        """给出还没走到终态的各状态各有多少个。"""
        ...


class QueueDepthProtocol(Protocol):
    """看任务队列积压的能力。"""

    async def pending_count(self) -> int:
        """给出领了但还没 ack 的任务条数。"""
        ...


class TokenReportProtocol(Protocol):
    """按用户聚合 token 的能力。"""

    async def by_user(self, *, since: datetime, until: datetime) -> list[UserUsage]:
        """给出窗口内每个用户的用量。"""
        ...


async def collect_platform(
    *,
    runs: RunCounterProtocol,
    queue: QueueDepthProtocol,
    report: TokenReportProtocol,
    now: datetime,
) -> CollectorRegistry:
    """现查一遍平台状态，装进一个新注册表。

    Args:
        runs: run 的计数来源。
        queue: 任务队列。
        report: 用量报表。
        now: 当前时刻，决定「今天」从哪儿算起。

    Returns:
        填好的注册表，可直接渲染。
    """
    registry = create_registry()
    await _fill_run(registry, runs)
    await _fill_queue(registry, queue)
    await _fill_token(registry, report, now)
    return registry


async def _fill_run(registry: CollectorRegistry, runs: RunCounterProtocol) -> None:
    """各状态的 run 计数。

    **没有的那一态也要写 0** —— 缺一条序列与「值是 0」在 PromQL 里是两回事，
    前者会让告警规则整条不成立，而不是不触发。
    """
    gauge = Gauge(
        "run",
        "还没走到终态的 run 数，按状态分",
        labelnames=("status",),
        namespace=NAMESPACE,
        registry=registry,
    )
    counted = await runs.live_count()
    for status in LIVE_STATUS:
        gauge.labels(status=status.value).set(counted.get(status, 0))


async def _fill_queue(registry: CollectorRegistry, queue: QueueDepthProtocol) -> None:
    """队列积压。

    **它与 `zuel_run{status="queued"}` 不是同一个数**：这里是 Redis Stream 的 pending
    列表，装的是「领走了但还没 ack」的任务；那边是库里还没开跑的 run。两者一起看才
    分得清「没人领」和「领了跑不完」—— 只看一个的话，两种故障长得一模一样。
    """
    gauge = Gauge(
        "task_pending",
        "任务队列里领了但还没 ack 的条数",
        namespace=NAMESPACE,
        registry=registry,
    )
    gauge.set(await queue.pending_count())


async def _fill_token(registry: CollectorRegistry, report: TokenReportProtocol, now: datetime) -> None:
    """今天各用户烧掉的 token。

    标签用用户名而不是 id：报警发到飞书上时，一串 uuid 需要再查一次库才知道是谁。
    基数是教师人数量级，Prometheus 扛得住。
    """
    gauge = Gauge(
        "token_today",
        "今天各用户的 token 用量，按 cache 命中与否分",
        labelnames=("user", "kind"),
        namespace=NAMESPACE,
        registry=registry,
    )
    for one in await report.by_user(since=day_start(now), until=now):
        gauge.labels(user=one.name, kind=CACHE_READ_KIND).set(one.cache_read)
        gauge.labels(user=one.name, kind=UNCACHED_KIND).set(one.uncached)
        gauge.labels(user=one.name, kind=OUTPUT_KIND).set(one.output)
