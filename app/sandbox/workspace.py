"""会话在宿主机上的文件空间。

**目录不是会话的身份，`threads` 表才是。** 这里只管「那个会话的文件放在哪」——
标识由建表那一侧发过来，本模块不发号。容器可以随时销毁重建，这个目录不会跟着没。

broker 自己的 `exists` 仍然保留，但它答的是「目录在不在」这个 broker 视角的问题；
api 侧判断会话存不存在一律查表，不再调它。

上传的文件名与产物路径都来自 HTTP 请求，属于不可信输入，越界防护在本模块。
"""

import logging
import os
from pathlib import Path

from sandbox.path import OUTPUT_DIR, PathEscapeError, thread_workspace
from sandbox.quota import NoQuota, QuotaProtocol

logger = logging.getLogger(__name__)


class Workspace:
    """所有会话的文件空间。

    **是会话目录的唯一创建者**：沙箱池与容器都经这里拿目录，磁盘配额才有一个
    单一的落点 —— 分散创建的话，总有一条路径会绕过配额，而绕过去了没有任何症状。

    Args:
        root: 各会话目录所在的宿主机根目录。
        quota: 目录配额，不传则不设 —— 只有 CI 与没挂 XFS 的开发机该用这个默认值。
        owner: 新建目录要交给谁，形如 `(1000, 1000)`。不传则跟着当前进程走。
    """

    def __init__(
        self,
        root: Path,
        quota: QuotaProtocol | None = None,
        owner: tuple[int, int] | None = None,
    ) -> None:
        self._root = root
        self._quota = quota or NoQuota()
        self._owner = owner

    def create(self, thread_id: str) -> str:
        """给一个已经存在的会话开出它的目录。

        **标识由调用方给，不在这里发。** 会话的身份长在 `threads` 表上，目录是它的
        副产品 —— 这里自己发号的话，「会话存不存在」就有两个真相源，而它们会分叉。

        Args:
            thread_id: 会话标识。

        Returns:
            同一个标识，方便调用方直接接着用。

        Raises:
            PathEscapeError: 标识会让目录落到根目录之外。
            QuotaError: 目录建出来了但配额没设上。
        """
        self.path(thread_id)
        return thread_id

    def exists(self, thread_id: str) -> bool:
        """会话是否存在。

        非法的标识一律当作不存在 —— 对外的表现就该是 404，
        分成「不存在」与「格式不对」两种回答等于告诉调用方哪些 id 是真的。
        """
        try:
            return thread_workspace(self._root, thread_id).is_dir()
        except PathEscapeError:
            return False

    def path(self, thread_id: str) -> Path:
        """返回会话目录，不存在则创建并设上配额。

        **配额只在新建时设一次**：XFS project quota 是落在盘上的（目录的 projid 是
        inode 属性，限额在文件系统的 quota 记录里），容器销毁重建、平台重启、
        甚至重新挂载之后它都还在。每次都重设一遍不会更安全，只会给每一次
        `read_file` 都搭上两个 `xfs_quota` 子进程。

        Args:
            thread_id: 会话标识。

        Returns:
            宿主机上的目录。

        Raises:
            PathEscapeError: 标识会让目录落到根目录之外。
            QuotaError: 配额没能设上。
        """
        workspace = thread_workspace(self._root, thread_id)
        if workspace.is_dir():
            return workspace

        workspace.mkdir(parents=True, exist_ok=True)
        self._hand_over(workspace)
        self._quota.assign(thread_id, workspace)
        return workspace

    def _hand_over(self, workspace: Path) -> None:
        """把新建的目录交给沙箱要用的那个用户。

        **broker 进容器之后是 root，建出来的目录就是 root 属主**，而沙箱以宿主用户跑，
        于是一个字节都写不进去。症状极具迷惑性：`execute` 照常成功（脚本在 /tmp 里跑），
        agent 只是「选择」把图存到别处，最后产物一个都没有 —— 全程没有一条报错指向权限。
        """
        if self._owner is None:
            return
        uid, gid = self._owner
        try:
            os.chown(workspace, uid, gid)
        except OSError:
            logger.warning("workspace 属主没能改成 %d:%d，沙箱可能写不进去：%s", uid, gid, workspace, exc_info=True)

    def save(self, thread_id: str, filename: str, content: bytes) -> Path:
        """把上传的文件落进会话目录。

        Args:
            thread_id: 会话标识。
            filename: 上传时带的文件名，不可信。
            content: 文件内容。

        Returns:
            落盘后的路径。

        Raises:
            PathEscapeError: 文件名不能作为会话目录下的一个文件。
        """
        # 只取末段：`../../etc/passwd` 与 `/etc/passwd` 都会被收成 `passwd`
        name = Path(filename).name
        if not name or name in {".", ".."}:
            message = f"文件名不可用：{filename!r}"
            raise PathEscapeError(message)

        target = self.path(thread_id) / name
        target.write_bytes(content)
        return target

    def artifact(self, thread_id: str, relative_path: str) -> Path:
        """定位会话产出的一个产物。

        Args:
            thread_id: 会话标识。
            relative_path: 相对 `outputs/` 的路径。

        Returns:
            宿主机上的文件路径，可能不存在。

        Raises:
            PathEscapeError: 路径指向 `outputs/` 之外。
        """
        output_dir = (self.path(thread_id) / OUTPUT_DIR).resolve()
        target = (output_dir / relative_path).resolve()
        # 跟随符号链接就等于把任意宿主文件当成产物送出去，resolve 之后再比前缀才挡得住
        if target != output_dir and output_dir not in target.parents:
            message = f"产物路径越出了 {OUTPUT_DIR}/：{relative_path!r}"
            raise PathEscapeError(message)
        return target
