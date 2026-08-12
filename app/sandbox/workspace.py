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
from shutil import rmtree

from sandbox.path import PathEscapeError, thread_workspace
from sandbox.quota import NoQuota, QuotaProtocol

logger = logging.getLogger(__name__)


def _within(base: Path, relative_path: str, *, scope: str) -> Path:
    """把一个相对路径解析成 `base` 下的路径，越界即抛。

    **跟随符号链接就等于把任意宿主文件送出去**，纯字符串校验拦不住这一条 ——
    resolve 之后再比前缀才挡得住。

    Args:
        base: 允许的根，须已 resolve。
        relative_path: 相对它的路径，不可信。
        scope: 出错时说给调用方听的范围名。

    Returns:
        宿主机上的路径，可能不存在。

    Raises:
        PathEscapeError: 解析结果落在 `base` 之外。
    """
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        message = f"路径越出了{scope}：{relative_path!r}"
        raise PathEscapeError(message)
    return target


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

    def save(self, thread_id: str, filename: str, content: bytes, directory: str = "") -> Path:
        """把上传的文件落进会话目录。

        **目标目录必须已经存在。** 它来自侧边栏上的一次点击，点得到就说明它在；
        顺手建出来则会踩一个没有症状的坑 —— broker 在容器里是 root，它建的目录
        沙箱（以宿主用户跑）一个字节都写不进去，而 `execute` 照常成功。

        Args:
            thread_id: 会话标识。
            filename: 上传时带的文件名，不可信。
            content: 文件内容。
            directory: 落到会话目录下的哪个子目录，相对会话根。留空即根下。

        Returns:
            落盘后的路径。

        Raises:
            PathEscapeError: 文件名不能作为一个文件，或目标目录越界、不存在。
        """
        # 只取末段：`../../etc/passwd` 与 `/etc/passwd` 都会被收成 `passwd`
        name = Path(filename).name
        if not name or name in {".", ".."}:
            message = f"文件名不可用：{filename!r}"
            raise PathEscapeError(message)

        parent = self.resolve(thread_id, directory) if directory else self.path(thread_id)
        if not parent.is_dir():
            message = f"目标目录不存在：{directory!r}"
            raise PathEscapeError(message)

        target = parent / name
        target.write_bytes(content)
        return target

    def remove(self, thread_id: str, relative_path: str) -> None:
        """删掉会话目录下的一个文件。

        **只删文件，不删目录**：删目录会连着里面的东西一起没，而侧边栏上那一下点击
        看不出这个后果。

        **不看这个会话有没有 run 在跑。** 加一道「跑着就不许删」的闸要么挡住正常操作
        （几十分钟的分析期间什么都动不了），要么挡不严（判断与删除之间总有空隙）；
        会话是单人使用的，教师删掉自己正在分析的输入文件，得到的是 agent 的一条报错。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。

        Raises:
            PathEscapeError: 路径指向会话目录之外。
            FileNotFoundError: 文件不在。
            IsADirectoryError: 指向的是目录。
        """
        target = self.resolve(thread_id, relative_path)
        if target.is_dir():
            message = f"这是一个目录，不能删：{relative_path!r}"
            raise IsADirectoryError(message)
        target.unlink()

    def destroy(self, thread_id: str) -> None:
        """删掉一个会话的整个目录。

        **这是唯一递归删除的操作**，与 `remove` 的「只删文件」是两回事：那一个来自
        侧边栏上的一次点击，看不出「会连着子项一起没」这个后果；这一个来自「删除会话」，
        教师已经知道整个会话都要没了。

        **调用方必须先销毁容器。** 容器把这个目录 bind mount 了进去，反过来的话，
        删目录的那一刻里面还有一个正在写它的进程。

        目录不在就什么都不做 —— 删一个已经删过的会话不是错误。

        Args:
            thread_id: 会话标识。

        Raises:
            PathEscapeError: 标识会让目录落到根目录之外。
        """
        # 走 thread_workspace 而不是 self.path：后者不存在时会把目录建出来，
        # 而这里正要删掉它
        target = thread_workspace(self._root, thread_id)
        if not target.is_dir():
            return
        # XFS 的 project 配额记录留着不清：projid 由 thread_id 确定性派生，
        # 而 uuid 不会重来一次，因此那条记录既不会被复用也不会挡住谁。清它要多跑一次
        # xfs_quota，而那条路上的每一次失败都只往 stderr 打一句然后退出 0
        rmtree(target)

    def resolve(self, thread_id: str, relative_path: str) -> Path:
        """定位会话目录下的一个路径。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。

        Returns:
            宿主机上的路径，可能不存在。

        Raises:
            PathEscapeError: 路径指向会话目录之外。
        """
        return _within(self.path(thread_id).resolve(), relative_path, scope="会话目录")
