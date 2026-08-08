"""产物的数据形状：`artifacts` 表的一行，以及刚传上去、还没落表的那份元数据。

**产物的身份从此长在这张表上**，不再是「哪个会话的哪个文件」。旧形状仍然认得，
那是兼容期的事，见 api 侧的产物端点。
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import BigInteger, Column, Index
from sqlmodel import Field, SQLModel

TABLE_NAME = "artifacts"


@dataclass(frozen=True)
class CollectedArtifact:
    """一次 run 认领到的一个产物，还没落表。

    **`s3_key` 可以为空**：对象存储传不上去时，这次分析本身是跑完了的，字节也还躺在
    workspace 里 —— 为了一次存储抖动把几十分钟的分析判成失败不划算。空的那些不落表，
    表里的每一行都必须指向一个真的对象，否则查出来的键下载不了。

    **`path` 留着不是冗余**：它是旧形状的标识，兼容期内的历史事件按它取产物，
    也是 `s3_key` 为空时唯一还能下载的途径。
    """

    path: str
    mime: str
    size: int
    s3_key: str | None = None


@dataclass(frozen=True)
class Artifact:
    """一个已经落表的产物。"""

    id: str
    run_id: str
    s3_key: str
    mime: str
    size: int


class ArtifactRecord(SQLModel, table=True):
    """`artifacts` 表的一行。"""

    __tablename__ = TABLE_NAME
    # 唯一的查询模式是「列出一次执行的产物」
    __table_args__ = (Index("ix_artifacts_run", "run_id"),)

    id: UUID = Field(primary_key=True)
    run_id: UUID = Field(index=False, foreign_key="runs.id")
    s3_key: str
    mime: str
    # bigint 而不是 int：int 列封顶 2GB，而超限是在 run 跑完之后才炸，
    # 那时分析的钱已经花掉了
    size: int = Field(sa_column=Column(BigInteger, nullable=False))

    def to_artifact(self) -> Artifact:
        """转成调用方认的那个形状。"""
        return Artifact(
            id=self.id.hex,
            run_id=self.run_id.hex,
            s3_key=self.s3_key,
            mime=self.mime,
            size=self.size,
        )
