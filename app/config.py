"""平台配置的唯一入口。

外部配置一律从这里读，业务代码不直接调 `os.getenv`。
"""

import shlex
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from sandbox.container import (
    DEFAULT_CPUS,
    DEFAULT_IMAGE,
    DEFAULT_MEMORY,
    DEFAULT_NETWORK,
    DEFAULT_PIDS_LIMIT,
    DEFAULT_RUNTIME,
    DEFAULT_TMP_SIZE,
    Hardening,
)
from sandbox.pool import (
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_LEASE_TIMEOUT,
    DEFAULT_MAX_CONTAINER,
    DEFAULT_QUEUE_TIMEOUT,
)
from sandbox.quota import DEFAULT_DISK_QUOTA, DEFAULT_QUOTA_COMMAND
from sandbox.remote import DEFAULT_BROKER_URL
from store.postgres import (
    DEFAULT_DATABASE,
    DEFAULT_HOST,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USER,
    DRIVER,
    NATIVE_DRIVER,
    build_dsn,
)
from store.redis import DEFAULT_URL
from task.queue import DEFAULT_CLAIM_IDLE_MILLISECOND
from worker.loop import DEFAULT_CONCURRENCY, DEFAULT_HEARTBEAT_SECOND

# .env 在仓库根而不在 app/，且门禁（cwd=app/）与 uvicorn（cwd 不定）的工作目录并不一致，
# 因此按本文件位置解析成绝对路径 —— 相对路径或向上搜索都会在某种场景下静默读到别的文件。
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


SETTINGS_CONFIG = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    # .env 里可能有部署脚本用的其他变量，多出来的键不该让平台起不来
    extra="ignore",
    # get_settings() 让全进程共用一个实例，冻结它才不构成可变全局状态
    frozen=True,
)


class StoreSettings(BaseSettings):
    """连两个外部存储需要的那几项。

    **单独分一层是为了 Alembic 与测试**：迁移只需要连得上库，不该因为缺
    `DEEPSEEK_API_KEY` 而跑不起来。配置项本身仍只在这里定义一次，`Settings` 继承它。
    """

    model_config = SETTINGS_CONFIG

    # 拆成五项而不是一整条 DSN，是为了让 compose 只覆盖主机名，
    # 密码不必经过 compose 的变量插值，理由见 store/postgres.py 的 build_dsn
    postgres_host: str = Field(
        default=DEFAULT_HOST,
        description="Postgres 主机。compose 部署时是服务名 postgres",
    )
    postgres_port: int = Field(default=DEFAULT_PORT, gt=0, description="Postgres 端口")
    postgres_user: str = Field(default=DEFAULT_USER, min_length=1, description="Postgres 用户名")
    postgres_password: SecretStr = Field(
        default=SecretStr(DEFAULT_PASSWORD),
        description="Postgres 口令。默认值只够开发机用，上线前必须改",
    )
    postgres_db: str = Field(default=DEFAULT_DATABASE, min_length=1, description="Postgres 库名")

    redis_url: str = Field(
        default=DEFAULT_URL,
        description="Redis 连接串。事件通道与任务队列都落在这里。无口令，因此不必拆开",
    )

    def postgres_dsn(self) -> str:
        """拼出 SQLAlchemy 用的 Postgres 连接串。

        Returns:
            带 `+psycopg` 驱动后缀的 DSN。
        """
        return self._postgres_dsn(DRIVER)

    def postgres_conninfo(self) -> str:
        """拼出原生 psycopg 用的 Postgres 连接串。

        LangGraph 的 checkpointer 直接用 psycopg，它不认 SQLAlchemy 的驱动后缀。

        Returns:
            不带驱动后缀的 DSN。
        """
        return self._postgres_dsn(NATIVE_DRIVER)

    def _postgres_dsn(self, driver: str) -> str:
        return build_dsn(
            host=self.postgres_host,
            port=self.postgres_port,
            user=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            database=self.postgres_db,
            driver=driver,
        )


class Settings(StoreSettings):
    """平台运行所需的外部配置。

    缺必填项时构造即抛 `ValidationError`，让进程在启动时失败，
    而不是等到第一次调模型才炸。
    """

    model_config = SETTINGS_CONFIG

    deepseek_api_key: SecretStr = Field(description="DeepSeek API 凭据。无默认值，缺失即启动失败")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        description="DeepSeek API 地址",
    )
    model_main: str = Field(
        default="deepseek-v4-pro",
        description="主模型，承担多步推理与代码生成",
    )
    model_aux: str = Field(
        default="deepseek-v4-flash",
        description="辅助模型，承担意图分类等轻量调用",
    )

    broker_url: str = Field(
        default=DEFAULT_BROKER_URL,
        description="sandbox-broker 的地址。它是唯一持有 docker.sock 的进程，只在内网监听",
    )

    worker_concurrency: int = Field(
        default=DEFAULT_CONCURRENCY,
        gt=0,
        description="一个 worker 同时驱动几个 run。副本数解决的是可用性，这一项才是吞吐",
    )
    worker_heartbeat_second: float = Field(
        default=DEFAULT_HEARTBEAT_SECOND,
        gt=0,
        description="worker 多久给自己持有的任务消息续一次命。要明显小于认领阈值",
    )
    worker_claim_idle_millisecond: int = Field(
        default=DEFAULT_CLAIM_IDLE_MILLISECOND,
        gt=0,
        description="任务消息闲置多久后允许别的 worker 认领，毫秒。崩溃恢复的延迟上限就是它",
    )

    sandbox_image: str = Field(
        default=DEFAULT_IMAGE,
        description="沙箱镜像，须预先在本机构建或导入",
    )
    sandbox_workspace_root: Path = Field(
        # 生产挂在 /data/sandbox 下，但开发机上没有那个目录，默认值放仓库内才能开箱即跑
        default=REPO_ROOT / "data" / "sandbox",
        description="各会话 workspace 的宿主机根目录",
    )
    sandbox_max_container: int = Field(
        default=DEFAULT_MAX_CONTAINER,
        gt=0,
        description="同时存活的沙箱容器数上限，容量瓶颈是宿主机内存",
    )
    sandbox_idle_timeout: float = Field(
        default=DEFAULT_IDLE_TIMEOUT,
        gt=0,
        description="沙箱无人使用多久后回收，秒",
    )
    sandbox_queue_timeout: float = Field(
        default=DEFAULT_QUEUE_TIMEOUT,
        gt=0,
        description="沙箱排队等待的上限，秒。超时的 run 转失败且标记可重试",
    )
    sandbox_lease_timeout: float = Field(
        default=DEFAULT_LEASE_TIMEOUT,
        gt=0,
        description="租约多久没人碰就强制归还，秒。api 崩在 acquire 与 release 之间时的兜底",
    )

    # 加固清单里有中间档的几项。只读 rootfs、cap-drop、no-new-privileges 不在此列 ——
    # 它们只有开和关，做成配置就是给静默失守留入口，见 sandbox/container.py。
    sandbox_runtime: str = Field(
        default=DEFAULT_RUNTIME,
        description="容器运行时。runsc 即 gVisor，换成 runc 等于把隔离退回一层容器边界",
    )
    sandbox_network: str = Field(
        default=DEFAULT_NETWORK,
        description="沙箱网络。P1 定案为 none，agent 因此装不了任何包",
    )
    sandbox_memory: str = Field(
        default=DEFAULT_MEMORY,
        description="单沙箱内存上限，含 /tmp 的 tmpfs 占用",
    )
    sandbox_cpus: str = Field(
        default=DEFAULT_CPUS,
        description="单沙箱 CPU 核数上限。死循环被限在这个数以内",
    )
    sandbox_pids_limit: int = Field(
        default=DEFAULT_PIDS_LIMIT,
        gt=0,
        description="单沙箱进程数上限，挡 fork 炸弹",
    )
    sandbox_tmp_size: str = Field(
        default=DEFAULT_TMP_SIZE,
        description="/tmp 的 tmpfs 限容。吃的是宿主机内存，不限容一句 dd 就能撑爆",
    )

    sandbox_user: str = Field(
        default="",
        description="沙箱以谁的身份跑，形如 1000:1000。留空即当前进程的 uid:gid；broker 进容器后须显式给宿主用户",
    )

    sandbox_disk_quota: str = Field(
        default=DEFAULT_DISK_QUOTA,
        description="每个会话 workspace 的硬上限（XFS bhard）。留空则不设配额，仅限没有 XFS 的环境",
    )
    sandbox_quota_command: str = Field(
        default=shlex.join(DEFAULT_QUOTA_COMMAND),
        description="xfs_quota 的调用方式。它要 CAP_SYS_ADMIN，非 root 跑平台时前面要加 sudo",
    )

    def quota_command(self) -> tuple[str, ...]:
        """把配置里的命令串拆成 argv。

        Returns:
            调用 xfs_quota 的命令与前缀。
        """
        return tuple(shlex.split(self.sandbox_quota_command))

    def sandbox_owner(self) -> tuple[int, int] | None:
        """把 `sandbox_user` 解析成 workspace 目录该有的属主。

        Returns:
            `(uid, gid)`；未配置则 None，表示跟着当前进程走。

        Raises:
            ValueError: 配置的格式不是 `uid:gid`。
        """
        if not self.sandbox_user:
            return None
        uid, _, gid = self.sandbox_user.partition(":")
        if not uid.isdigit() or not gid.isdigit():
            message = f"SANDBOX_USER 须形如 1000:1000：{self.sandbox_user!r}"
            raise ValueError(message)
        return int(uid), int(gid)

    def hardening(self) -> Hardening:
        """把加固相关的配置项收成一组，交给容器。

        Returns:
            容器创建时用的资源限额与隔离档位。
        """
        return Hardening(
            runtime=self.sandbox_runtime,
            network=self.sandbox_network,
            memory=self.sandbox_memory,
            cpus=self.sandbox_cpus,
            pids_limit=self.sandbox_pids_limit,
            tmp_size=self.sandbox_tmp_size,
            user=self.sandbox_user or None,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全进程共享的配置实例。

    缓存的作用不只是省一次文件读取：配置在首次调用时校验一次，
    校验失败就是启动失败，不会出现「一半请求成功一半炸」的中间状态。
    """
    return Settings()
