"""FastAPI 应用的组装。

**本期只做架构定的六个端点**，认证、管理、取消、审批都不在这里 —— 那几项各有各的
前置条件（用户体系、HITL），本期一个都不满足。

字段级的请求/响应文档以 `/docs` 的 OpenAPI 为准，不在这里手写第二份。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.error import install_handler
from api.platform import Platform, build_platform
from api.route import artifact, run, thread
from config import get_settings
from log import configure

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
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        owned = platform is None
        current = platform if platform is not None else await build_platform(get_settings())
        app.state.platform = current
        try:
            yield
        finally:
            if owned:
                # 沙箱的起停与 idle 回收都在 broker 那边，这里只有一条到它的连接。
                # 在跑的 run 也不必等 —— 它们在 worker 进程里，api 重启不影响
                current.backend_factory.close()
                await current.connection.aclose()
                await current.engine.dispose()
                await current.cache.aclose()

    app = FastAPI(
        title="金融学院智能体平台",
        description="教师用自然语言提问，智能体写 Python 在隔离沙箱中执行，返回结果与图表。",
        lifespan=lifespan,
    )
    install_handler(app)
    for router in (thread.router, run.router, artifact.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


# 必须在导入时就装配，不能推迟到 lifespan：uvicorn 在跑 lifespan 之前就会打出
# 「Started server process」这两行，装晚了它们就是夹在 JSON 中间的纯文本，
# 整份日志没法再逐行解析。这里不读 Settings —— CI 没有 .env，导入即失败。
configure()

app = create_app()
