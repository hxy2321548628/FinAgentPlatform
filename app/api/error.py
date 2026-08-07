"""对外的统一错误结构。

`code` 是稳定的机器可读枚举，前端据此决定行为；`message` 是中文，前端可直接展示。
**两者的职责不能混** —— 改 `message` 的措辞不应该导致前端逻辑失效。
"""

from enum import StrEnum

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    """错误码的完整清单。

    枚举列的是整套契约，但本期只会产生其中三个 —— 认证、配额、限流都还没做，
    列全是为了让前端有一份完整的分支表。
    """

    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    INTERNAL = "INTERNAL"


class ErrorDetail(BaseModel):
    """错误的正文。"""

    code: ErrorCode = Field(description="稳定的机器可读枚举")
    message: str = Field(min_length=1, description="中文说明，前端可直接展示")


class ErrorResponse(BaseModel):
    """所有非 2xx 响应的统一形状。"""

    error: ErrorDetail


class ApiError(HTTPException):
    """带平台错误码的 HTTP 异常。

    Args:
        status_code: HTTP 状态码。
        code: 平台错误码。
        message: 中文说明。
    """

    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message


def not_found(message: str) -> ApiError:
    """资源不存在。

    越权访问他人资源时也返回这个而不是 403 —— 403 等于确认了资源存在，
    可以被用来探测别人有哪些会话。
    """
    return ApiError(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, message)


def invalid(message: str) -> ApiError:
    """参数校验失败。"""
    return ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.VALIDATION_ERROR, message)


def unauthenticated(message: str) -> ApiError:
    """未登录、session 过期，或用户名口令对不上。

    **口令错与用户不存在返回同一句话**：分开说等于告诉试探的人「这个用户名是存在的」。
    """
    return ApiError(status.HTTP_401_UNAUTHORIZED, ErrorCode.UNAUTHENTICATED, message)


def install_handler(app: FastAPI) -> None:
    """把框架抛出的异常统一收敛成上面的结构。

    不装的话 FastAPI 会返回 `{"detail": ...}`，前端就得同时认两种错误形状。
    """

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _respond(exc.status_code, exc.code, exc.message)

    # 挂在 Starlette 的基类上而不是 FastAPI 的子类上：路由不匹配时抛出的是前者，
    # 只挂子类的话「访问了一个不存在的路径」会漏回框架默认的 {"detail": ...}
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == status.HTTP_404_NOT_FOUND else ErrorCode.INTERNAL
        return _respond(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _respond(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.VALIDATION_ERROR,
            "; ".join(f"{'.'.join(str(part) for part in one['loc'])}: {one['msg']}" for one in exc.errors()),
        )


def _respond(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message or code.value))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
