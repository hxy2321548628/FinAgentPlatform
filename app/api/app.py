"""FastAPI 应用的组装。

**本期只做架构定的六个端点**，认证、管理、取消、审批都不在这里 —— 那几项各有各的
前置条件（用户体系、HITL），本期一个都不满足。

字段级的请求/响应文档以 `/docs` 的 OpenAPI 为准，不在这里手写第二份。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.error import install_handler
from api.platform import Platform, build_platform
from api.route import artifact, run, thread
from config import get_settings

API_PREFIX = "/api"


def create_app(platform: Platform | None = None) -> FastAPI:
    """组装应用。

    Args:
        platform: 运行时。不传则按配置自建，并由应用负责关闭；
            传了则由调用方负责其生命周期 —— 测试据此塞进假的沙箱池与假的智能体。

    Returns:
        可交给 uvicorn 的应用。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = platform is None
        current = platform if platform is not None else build_platform(get_settings())
        if owned:
            # 不起它的话，容器只在有新申请时才回收 —— 而 idle 回收要防的恰恰是
            # 「没人再来申请，容器却一直占着内存」
            current.pool.start_sweeper()
        app.state.platform = current
        try:
            yield
        finally:
            if owned:
                await current.executor.aclose()
                await current.pool.aclose()

    app = FastAPI(
        title="金融学院智能体平台",
        description="教师用自然语言提问，智能体写 Python 在隔离沙箱中执行，返回结果与图表。",
        lifespan=lifespan,
    )
    install_handler(app)
    for router in (thread.router, run.router, artifact.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
