"""sandbox-broker 服务的组装。

**这个进程是唯一持有 `docker.sock` 的地方。** 它不认识模型、不认识事件、不认识 run ——
只认「哪个会话、要对它的文件或容器做什么」。api 进程被 agent 生成的内容影响之后，
能做的最多是发几个 HTTP 请求过来。

不对外暴露：Compose 里只在内部网络上开端口，不经 Nginx。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from broker.route import router
from broker.runtime import Broker, build_broker
from config import get_settings
from log import configure


def create_app(broker: Broker | None = None) -> FastAPI:
    """组装 broker 服务。

    Args:
        broker: 运行时。不传则按配置自建，并由应用负责关闭；
            传了则由调用方负责其生命周期 —— 测试据此塞进假的沙箱池。

    Returns:
        可交给 uvicorn 的应用。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        owned = broker is None
        current = broker if broker is not None else build_broker(get_settings())
        if owned:
            await current.pool.reclaim()
            current.pool.start_sweeper()
        app.state.broker = current
        try:
            yield
        finally:
            if owned:
                await current.pool.aclose()

    app = FastAPI(
        title="sandbox-broker",
        description="沙箱容器与会话目录的唯一入口。仅供 api 进程内部调用，不对外暴露。",
        lifespan=lifespan,
    )
    app.include_router(router)
    if broker is not None:
        # 注入进来的运行时立刻就位，不等 lifespan：httpx 的 ASGI 传输（测试走这条）
        # 压根不跑 lifespan，只在这里挂的话每个请求都会拿不到运行时
        app.state.broker = broker
    return app


configure()

app = create_app()
