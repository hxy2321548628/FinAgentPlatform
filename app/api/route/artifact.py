"""产物下载。

**字节不经这个进程。** 鉴权与标识解析在这里做完，然后用 `X-Accel-Redirect` 把「取字节」
交给 nginx —— 它 `proxy_pass` 到 MinIO，产物流直接从 nginx 发给浏览器。

架构原本定的是 302 跳预签名 URL，理由是别让网关代理二进制流。理由成立，但预签名 URL 的
host 得是浏览器够得着的地址，而内网无域名、MinIO 不对外暴露端口。改由 nginx 直发之后
原意仍然达成 —— 要保护的是 FastAPI 的 worker（数量少、还要扛所有 SSE 长连接），
而代理大文件正是 nginx 的本职；签名只在 nginx 与 MinIO 之间走一趟，浏览器看不到。

产物标识有两种形状，兼容期内都认：

- **不含 `/`** 的是 `artifacts` 表的主键，P4 之后的事件用它；
- **含 `/`** 的是旧形状 `{thread_id}/{outputs 下的相对路径}`，180 天保留期内的历史事件
  还指着它。

**不迁移历史事件**：`run_events` 是不可变的日志，回写它就等于让「当时发生了什么」
不再可信。兼容期跟着保留期走，届时删掉旧形状那条分支。
"""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.error import not_found
from api.platform import Platform, get_platform
from api.security import CurrentUser
from artifact.model import Artifact
from artifact.store import artifact_key, guess_mime
from sandbox.remote import BrokerError

router = APIRouter(prefix="/artifacts", tags=["artifact"])

# nginx 认这个头，把响应体换成它自己从上游取来的字节。**只在 nginx 后面有效** ——
# 直接跑 uvicorn 时浏览器只会收到一个空响应，因此那条路由配置关掉（见 Settings）
ACCEL_REDIRECT_HEADER = "X-Accel-Redirect"


@router.get("/{artifact_id:path}")
async def download_artifact(
    artifact_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> Response:
    """取回一个产物。

    两种标识形状都认，见模块 docstring。
    """
    if "/" in artifact_id:
        return await _by_path(artifact_id, current.user_id, platform)
    return await _by_id(artifact_id, current.user_id, platform)


async def _by_id(artifact_id: str, user_id: str, platform: Platform) -> Response:
    """按表主键取。归属经 `runs.user_id` 判定，查不到与不是你的给同一个回答。"""
    found = await platform.artifacts.get(artifact_id, user_id=user_id)
    if found is None:
        raise _missing(artifact_id)
    return _send(found, platform)


async def _by_path(artifact_id: str, user_id: str, platform: Platform) -> Response:
    """按旧形状取：先查表换成对象键，查不到再回落到 workspace。

    **越权检查落在会话上**：旧形状的身份就是「哪个会话的哪个文件」，因此
    「这个产物是不是你的」等价于「这个会话是不是你的」。

    回落这条分支是给 P4 之前的产物留的 —— 它们从没进过对象存储，字节只在 workspace 里。
    """
    thread_id, _, relative_path = artifact_id.partition("/")
    if not thread_id or not relative_path:
        raise _missing(artifact_id)
    if await platform.thread.get(thread_id, user_id=user_id) is None:
        raise _missing(artifact_id)

    # 键是精确匹配，而表里只可能有平台自己生成的键 —— 带 `..` 的路径拼出来的键
    # 一个都对不上，于是落到下面的回落分支，由 broker 那一侧挡掉越界
    found = await platform.artifacts.by_key(
        artifact_key(user_id=user_id, thread_id=thread_id, relative_path=relative_path)
    )
    if found is not None:
        return _send(found, platform)

    try:
        content = await platform.workspace.artifact(artifact_id)
    except BrokerError as exc:
        # 越界与不存在对外是同一个回答，否则这个端点就成了探测宿主机文件的工具
        raise _missing(artifact_id) from exc
    return Response(content=content, media_type=guess_mime(relative_path))


def _send(found: Artifact, platform: Platform) -> Response:
    """把一个已经在对象存储里的产物发出去。

    Raises:
        HTTPException: 表里有行却没配对象存储 —— 那是配置错了，字节取不回来。
    """
    if platform.artifact is None:
        raise _missing(found.id)
    if platform.artifact_direct_send:
        target = _accel_target(platform.artifact.presign(found.s3_key))
        return Response(headers={ACCEL_REDIRECT_HEADER: target}, media_type=found.mime)
    # 没有 nginx 的那条路（开发机直接跑 uvicorn）：只好自己取回来再转发
    return Response(content=platform.artifact.get(found.s3_key), media_type=found.mime)


def _accel_target(presigned: str) -> str:
    """把预签名 URL 削成只剩路径与查询串。

    `X-Accel-Redirect` 只认本 server 上的 URI，带 host 的整条 URL 它不跳。
    削掉之后剩下的正是 `/{桶名}/{键}?{签名}` —— nginx 那条 `internal` location
    就按桶名匹配，原样转给 MinIO，路径一个字符都不用改写。
    """
    parsed = urlsplit(presigned)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def _missing(artifact_id: str) -> Exception:
    return not_found(f"产物不存在：{artifact_id}")
