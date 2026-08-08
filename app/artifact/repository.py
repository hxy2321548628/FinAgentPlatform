"""`artifacts` 表的读写。

**写在 worker 那一侧。** 字节由 broker 传进对象存储（只有它碰得到 workspace），
但落表要连 Postgres，而 broker 至今一行 SQL 都不发 —— 给它开一条库连接，只为写一张
它自己不查的表，不划算。broker 传完把元数据交回来，worker 顺手落表。

表结构由 Alembic 管（`migration/`），不在这里 `create_all`。
"""

import logging
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from artifact.model import Artifact, ArtifactRecord, CollectedArtifact

logger = logging.getLogger(__name__)


class ArtifactRepository:
    """`artifacts` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def add(self, run_id: str, collected: list[CollectedArtifact]) -> list[Artifact]:
        """记下一次 run 的产物。

        **没传进对象存储的那些不落表**：表里的每一行都必须指向一个真的对象，
        否则查出来的 `s3_key` 下载不了，而那种 404 不指向原因。它们仍能按旧形状下载 ——
        字节还在 workspace 里。

        Args:
            run_id: 产出它们的 run。
            collected: 本次认领到的产物。

        Returns:
            落表之后的记录，带上主键。没有可落表的则为空列表。

        Raises:
            IntegrityError: `run_id` 没有对应的 run 行。
        """
        record = [
            ArtifactRecord(id=uuid4(), run_id=UUID(run_id), s3_key=one.s3_key, mime=one.mime, size=one.size)
            for one in collected
            if one.s3_key is not None
        ]
        if not record:
            return []
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add_all(record)
            await session.commit()
        logger.info("产物已落表：%d 个", len(record))
        return [one.to_artifact() for one in record]

    async def list(self, run_id: str) -> list[Artifact]:
        """列出一次 run 的全部产物。

        Args:
            run_id: 要查的 run。

        Returns:
            该 run 的产物，没有则空列表。
        """
        statement = select(ArtifactRecord).where(ArtifactRecord.run_id == UUID(run_id))
        async with AsyncSession(self._engine) as session:
            found = (await session.exec(statement)).all()
        return [one.to_artifact() for one in found]
