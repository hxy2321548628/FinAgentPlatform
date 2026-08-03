"""产物下载。

**本期直接回字节**，不做 302 跳预签名 URL —— 没有对象存储可跳。产物大到会占住
网关 worker 时这条要改回架构定的跳转，那要等 MinIO 落地。

产物标识的形状是 `{thread_id}/{outputs 下的相对路径}`：本期没有 artifacts 表，
产物的唯一身份就是「哪个会话的哪个文件」。等表建起来，这里换成表主键，端点形状不变。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.error import not_found
from api.platform import Platform, get_platform
from sandbox.path import PathEscapeError

router = APIRouter(prefix="/artifacts", tags=["artifact"])


@router.get("/{artifact_id:path}")
async def download_artifact(
    artifact_id: str,
    platform: Annotated[Platform, Depends(get_platform)],
) -> FileResponse:
    """取回一个产物。"""
    thread_id, _, relative_path = artifact_id.partition("/")
    if not thread_id or not relative_path or not platform.workspace.exists(thread_id):
        raise _missing(artifact_id)

    try:
        path = platform.workspace.artifact(thread_id, relative_path)
    except PathEscapeError as exc:
        # 越界与不存在对外是同一个回答，否则这个端点就成了探测宿主机文件的工具
        raise _missing(artifact_id) from exc

    if not path.is_file():
        raise _missing(artifact_id)
    return FileResponse(path)


def _missing(artifact_id: str) -> Exception:
    return not_found(f"产物不存在：{artifact_id}")
