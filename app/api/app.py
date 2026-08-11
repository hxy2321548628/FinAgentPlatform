"""FastAPI 应用的组装。

字段级的请求/响应文档以 `/docs` 的 OpenAPI 为准，不在这里手写第二份。

**登录挂在路由器上，不逐个端点挂**：漏挂一个就是一个不需要登录的入口，
而这种缺口不报错。`/auth` 是唯一不挂的那个 —— 还没登录的人正是要走它。
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from api.error import install_handler
from api.platform import Platform, build_platform
from api.route import admin, artifact, auth, file, group, metric, run, thread
from api.security import limit_by_user, require_user
from auth.bootstrap import ensure_first_admin
from config import get_settings
from log import configure
from telemetry.setup import API_SERVICE, instrument
from telemetry.setup import configure as configure_trace

logger = logging.getLogger(__name__)

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
        if owned:
            settings = get_settings()
            # 探针在 create_app 里就挂上了，这里才接后端 —— 读配置只能在这时候，
            # 而中间件必须在应用开始服务之前加
            configure_trace(service_name=API_SERVICE, endpoint=settings.otel_endpoint)
            await ensure_first_admin(
                repository=current.user,
                hasher=current.password,
                name=settings.admin_name,
                password=settings.admin_password.get_secret_value(),
            )
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
    # **必须在应用开始服务之前**：Starlette 的中间件栈一旦建起来就加不进新的中间件。
    # 没配后端时它只是把 span 落到空实现上，几乎不要钱
    instrument(app)
    app.include_router(auth.router, prefix=API_PREFIX)
    # 抓取端点不挂登录，也不带 /api 前缀 —— 挡它的是 nginx，理由写在 route/metric.py
    app.include_router(metric.router)
    for router in (thread.router, file.router, run.router, artifact.router, group.router, admin.router):
        app.include_router(
            router,
            prefix=API_PREFIX,
            dependencies=[Depends(require_user), Depends(limit_by_user)],
        )
    return app


# 必须在导入时就装配，不能推迟到 lifespan：uvicorn 在跑 lifespan 之前就会打出
# 「Started server process」这两行，装晚了它们就是夹在 JSON 中间的纯文本，
# 整份日志没法再逐行解析。这里不读 Settings —— CI 没有 .env，导入即失败。
configure()

app = create_app()
