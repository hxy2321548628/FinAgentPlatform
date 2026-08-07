"""会话状态的落库：把 LangGraph 的 checkpointer 接到 Postgres 上。

**表结构由框架自己建、自己迁移**（`setup()`），本项目一个字都不改 —— 它随 LangGraph
版本走，手工动过就等着下次升级时冲突。因此 checkpoint 那几张表不进 Alembic。

连接池是独立的一条，不与 run 元数据那条 SQLAlchemy 池子共用：checkpointer 吃的是
原生 psycopg 连接，且要求 autocommit。
"""

import logging
from dataclasses import dataclass
from typing import cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# checkpointer 要求连接按字典取行。行工厂是通过 kwargs 传进去的，类型系统看不见，
# 因此建池那里要 cast 一次
type CheckpointPool = AsyncConnectionPool[AsyncConnection[DictRow]]

# 一次 run 期间 checkpoint 的读写相当密集（每个节点一次），但都是短事务。
# 与 SANDBOX_MAX_CONTAINER 同数量级即够
DEFAULT_MAX_SIZE = 10

# checkpointer 的 setup() 与写入都要求 autocommit —— 它自己不开事务。
# dict_row 是它读结果时的假设，换成默认的 tuple 行会在第一次查询就报 KeyError
CONNECTION_KWARGS = {"autocommit": True, "row_factory": dict_row}


@dataclass(frozen=True)
class Checkpoint:
    """checkpointer 与它独占的连接池。

    两样绑在一起，是因为池子的生命周期必须比 saver 长 —— 分开持有就会出现
    「池子关了，saver 还在被图调用」。
    """

    saver: AsyncPostgresSaver
    pool: CheckpointPool

    async def aclose(self) -> None:
        """关掉连接池。"""
        await self.pool.close()


async def open_checkpoint(dsn: str, *, max_size: int = DEFAULT_MAX_SIZE) -> Checkpoint:
    """开一条到 Postgres 的池子，建好 checkpoint 的表，返回可直接交给图的 saver。

    `setup()` 是幂等的：已经建过就只补版本差，因此每次进程启动都跑一次是安全的。

    Args:
        dsn: psycopg 形式的 DSN，即不带 `+psycopg` 后缀的那种。
        max_size: 池子上限。

    Returns:
        可交给 `create_runner` 的 checkpointer，以及要在关闭时归还的池子。
    """
    pool = cast(
        CheckpointPool,
        AsyncConnectionPool(
            conninfo=dsn,
            max_size=max_size,
            kwargs=CONNECTION_KWARGS,
            # 构造时开池会在没有事件循环的场景下报警告，且开池失败要能当场抛出来
            open=False,
        ),
    )
    await pool.open(wait=True)
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return Checkpoint(saver=saver, pool=pool)
