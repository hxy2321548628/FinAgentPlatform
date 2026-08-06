"""会话在宿主机上的文件空间。

**本期没有 threads 表，一个会话在服务端的全部实体就是这里的一个目录** ——
「会话存不存在」问的就是「目录在不在」。容器可以随时销毁重建，这个目录不会跟着没。

上传的文件名与产物路径都来自 HTTP 请求，属于不可信输入，越界防护在本模块。
"""

from pathlib import Path
from uuid import uuid4

from sandbox.path import OUTPUT_DIR, PathEscapeError, thread_workspace
from sandbox.quota import NoQuota, QuotaProtocol


class Workspace:
    """所有会话的文件空间。

    **是会话目录的唯一创建者**：沙箱池与容器都经这里拿目录，磁盘配额才有一个
    单一的落点 —— 分散创建的话，总有一条路径会绕过配额，而绕过去了没有任何症状。

    Args:
        root: 各会话目录所在的宿主机根目录。
        quota: 目录配额，不传则不设 —— 只有 CI 与没挂 XFS 的开发机该用这个默认值。
    """

    def __init__(self, root: Path, quota: QuotaProtocol | None = None) -> None:
        self._root = root
        self._quota = quota or NoQuota()

    def create(self) -> str:
        """开一个新会话。

        Returns:
            新会话的标识。

        Raises:
            QuotaError: 目录建出来了但配额没设上。
        """
        thread_id = uuid4().hex
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
        """返回会话目录，不存在则创建，并确保配额已设上。

        每次都设一遍而不只在新建时设：配额跟着目录而不跟着容器，容器销毁重建、
        甚至平台重启之后，这是让配额回到位的唯一时机（本期没有任何持久化状态）。
        两条子命令都是幂等赋值，重复设不会出错。

        Args:
            thread_id: 会话标识。

        Returns:
            宿主机上的目录。

        Raises:
            PathEscapeError: 标识会让目录落到根目录之外。
            QuotaError: 配额没能设上。
        """
        workspace = thread_workspace(self._root, thread_id)
        workspace.mkdir(parents=True, exist_ok=True)
        self._quota.assign(thread_id, workspace)
        return workspace

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
