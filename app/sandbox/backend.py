"""沙箱后端：把一个 thread 的 workspace 与沙箱容器包成 DeepAgents 的 backend。

七个文件工具直接读写宿主机上的 bind-mount 目录，**只有 `execute` 进容器** ——
沙箱被回收之后翻看历史文件不必冷启动一个容器。

磁盘操作委托给框架的 `FilesystemBackend`（虚拟根设成该 thread 的 workspace），
本模块负责它不做的三件事：

1. 把 agent 视角的 `/workspace` 前缀翻译掉；
2. 把它遇到越界路径时抛出的异常转成 `error` 字段 —— 抛异常会让整个 run 失败，
   而返回错误能让 LLM 自己改路径重试；
3. `execute` 与产物判定。
"""

import os
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)

from sandbox.container import ContainerError, ContainerProtocol
from sandbox.path import OUTPUT_DIR, to_sandbox_path, to_virtual_path

DEFAULT_EXECUTE_TIMEOUT = 120

# 容器层面就没跑起来时的退出码。命令自身的退出码一律以容器返回的为准
EXECUTION_FAILED_EXIT_CODE = 1

# FilesystemBackend 越界时抛 ValueError，磁盘故障抛 OSError。
# PathEscapeError 是 ValueError 的子类，一并被兜住。
FILE_ERROR = (ValueError, OSError)


class SandboxBackend(SandboxBackendProtocol):
    """一个 thread 的文件空间与执行环境。

    Args:
        workspace: 该 thread 在宿主机上的 workspace 目录，需已存在。
        container: 承载 `execute` 的容器。
    """

    def __init__(self, workspace: Path, container: ContainerProtocol) -> None:
        self._workspace = workspace.resolve()
        self._disk = FilesystemBackend(root_dir=self._workspace, virtual_mode=True)
        self._container = container

    @property
    def id(self) -> str:
        """沙箱标识，取容器的。"""
        return self._container.id

    def ls(self, path: str) -> LsResult:
        """列出目录内容。"""
        try:
            result = self._disk.ls(to_virtual_path(path))
        except FILE_ERROR as exc:
            return LsResult(error=str(exc))
        return LsResult(error=result.error, entries=_relocate_file(result.entries))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """读取文件的一段。"""
        try:
            return self._disk.read(to_virtual_path(file_path), offset, limit)
        except FILE_ERROR as exc:
            return ReadResult(error=str(exc))

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入文件，已存在则覆盖。"""
        try:
            return self._disk.write(to_virtual_path(file_path), content)
        except FILE_ERROR as exc:
            return WriteResult(error=str(exc))

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        """替换文件里的字符串。"""
        try:
            return self._disk.edit(to_virtual_path(file_path), old_string, new_string, replace_all)
        except FILE_ERROR as exc:
            return EditResult(error=str(exc))

    def delete(self, file_path: str) -> DeleteResult:
        """删除文件。"""
        try:
            return self._disk.delete(to_virtual_path(file_path))
        except FILE_ERROR as exc:
            return DeleteResult(error=str(exc))

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        """按通配符找文件。"""
        try:
            result = self._disk.glob(pattern, _optional_virtual_path(path))
        except FILE_ERROR as exc:
            return GlobResult(error=str(exc))
        return GlobResult(
            error=result.error,
            matches=_relocate_file(result.matches),
            truncated=result.truncated,
        )

    def grep(
        self, pattern: str, path: str | None = None, glob: str | None = None, *, max_count: int | None = None
    ) -> GrepResult:
        """在文件内容里找字面串。"""
        try:
            result = self._disk.grep(pattern, _optional_virtual_path(path), glob, max_count=max_count)
        except FILE_ERROR as exc:
            return GrepResult(error=str(exc))
        return GrepResult(
            error=result.error,
            matches=None if result.matches is None else [_relocate_match(one) for one in result.matches],
            truncated=result.truncated,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """把字节写进 workspace。批量操作允许部分成功。"""
        return [self._upload_one(path, content) for path, content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """从 workspace 取出字节。批量操作允许部分成功。"""
        return [self._download_one(path) for path in paths]

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """在沙箱容器里执行 shell 命令。

        容器不可达、超时、docker 调用失败都转成带错误文本的返回值，
        让 LLM 看到失败并自己决定下一步。
        """
        try:
            result = self._container.exec(command, timeout=timeout or DEFAULT_EXECUTE_TIMEOUT)
        except ContainerError as exc:
            return ExecuteResponse(output=f"沙箱执行失败：{exc}", exit_code=EXECUTION_FAILED_EXIT_CODE)
        return ExecuteResponse(output=result.output, exit_code=result.exit_code)

    def artifact_mark(self) -> int:
        """取一个产物判定的基准时刻，**用文件系统自己的时钟**。

        不能用 `time.time_ns()`：那读的是细粒度的 CLOCK_REALTIME，而内核给 inode 打
        时间戳用的是**粗粒度时钟**（每个 tick 更新一次，NOHZ 下进程一空闲就停在那儿）。
        两者最多差一个 tick，实测约 0.4 毫秒 —— 基准取墙钟的话，紧接着写下的产物
        mtime 反而更早，于是被判成「运行之前就有的」而**静默漏掉，没有任何报错**。

        把会话目录 touch 一下再读它的 mtime，基准与判据就出自同一个时钟 ——
        产物在它的子目录里，同一个文件系统同一份时钟。

        **取的是会话目录而不是 `outputs/`，因为这里不能建目录。** 第一版在这里
        `mkdir` 出 `outputs/`，而这个方法跑在 broker 进程里、那个进程是 root，
        于是目录属主成了 root，**以宿主用户跑的沙箱一个字节都写不进去**。
        症状完全不指向权限：`execute` 全部成功，agent 只是「选择」把图存到
        `outputs_final/` 之类的地方，最后产物一个都没有。`outputs/` 该由沙箱自己建。

        Returns:
            Unix 时间戳，纳秒。交给 `artifact_since` 用。
        """
        os.utime(self._workspace, None)
        return self._workspace.stat().st_mtime_ns

    def artifact_since(self, since_ns: int) -> list[Path]:
        """列出 `outputs/` 下在给定时刻之后写入的文件。

        **判据用整数纳秒，不用 `st_mtime`。** 后者是 float，在当前 epoch 只有
        238 纳秒的分辨率，舍入能把刚写下的产物压到 `since_ns` 之下 —— 产物被静默漏掉，
        而且没有任何报错指向原因。

        Args:
            since_ns: Unix 时间戳，纳秒。通常取自这次 run 开始前。

        Returns:
            宿主机上的产物路径，按路径排序。目录不存在时为空。
        """
        output_dir = self._workspace / OUTPUT_DIR
        if not output_dir.is_dir():
            return []
        return sorted(
            path
            for path in output_dir.rglob("*")
            # 产物会被下载给教师，跟随符号链接等于把任意宿主文件当成产物送出去
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime_ns >= since_ns
        )

    def _upload_one(self, path: str, content: bytes) -> FileUploadResponse:
        try:
            response = self._disk.upload_files([(to_virtual_path(path), content)])[0]
        except FILE_ERROR as exc:
            return FileUploadResponse(path=path, error=str(exc))
        # 结果里回填 agent 视角的路径，调用方不该看到虚拟路径
        return FileUploadResponse(path=path, error=response.error)

    def _download_one(self, path: str) -> FileDownloadResponse:
        try:
            response = self._disk.download_files([to_virtual_path(path)])[0]
        except FILE_ERROR as exc:
            return FileDownloadResponse(path=path, error=str(exc))
        return FileDownloadResponse(path=path, content=response.content, error=response.error)


def _optional_virtual_path(path: str | None) -> str | None:
    """翻译 glob 与 grep 的可选 path，不传就是整个 workspace。"""
    return None if path is None else to_virtual_path(path)


def _relocate_file(entry: list[FileInfo] | None) -> list[FileInfo] | None:
    """把结果里的虚拟路径换成 agent 视角的路径。"""
    if entry is None:
        return None
    return [{**one, "path": to_sandbox_path(one["path"])} for one in entry]


def _relocate_match(match: GrepMatch) -> GrepMatch:
    return {**match, "path": to_sandbox_path(match["path"])}
