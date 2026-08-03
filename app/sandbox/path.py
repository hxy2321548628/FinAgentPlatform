"""沙箱路径的翻译。

agent 看到的是容器内的 `/workspace/...`，而驱动七个文件工具的 `FilesystemBackend`
以 thread 的 workspace 目录为虚拟根，认的是 `/...`。两个视角之间的翻译只在这里发生。

**越界防护不在本模块**：`..` 与指向外部的符号链接由 `FilesystemBackend` 的
`virtual_mode` 规范化后拦下（实测符号链接也挡得住），本模块只负责剥掉 `/workspace`
前缀、并挡住压根不在该前缀下的路径。分两层是因为符号链接必须在真实文件系统上
解析才能判定，纯字符串处理做不到。
"""

from pathlib import Path

# agent 视角的 workspace 挂载点，与容器内的 bind-mount 目标一致
SANDBOX_ROOT = "/workspace"

VIRTUAL_ROOT = "/"


class PathEscapeError(ValueError):
    """路径不在 `/workspace` 下。

    由调用方在边界处捕获并转成工具的 `error` 字段 —— 抛到 LangGraph 会让整个 run 失败，
    而返回错误能让 LLM 自己改路径重试。
    """


def to_virtual_path(sandbox_path: str) -> str:
    """把 agent 视角的路径翻译成 `FilesystemBackend` 的虚拟路径。

    Args:
        sandbox_path: 容器内的绝对路径，形如 `/workspace/data.csv`。

    Returns:
        以 workspace 为根的虚拟路径，形如 `/data.csv`。

    Raises:
        PathEscapeError: 路径不在 `/workspace` 下。
    """
    if sandbox_path != SANDBOX_ROOT and not sandbox_path.startswith(f"{SANDBOX_ROOT}/"):
        message = f"路径必须在 {SANDBOX_ROOT} 下：{sandbox_path!r}"
        raise PathEscapeError(message)

    return VIRTUAL_ROOT + sandbox_path.removeprefix(SANDBOX_ROOT).lstrip("/")


def thread_workspace(root: Path, thread_id: str) -> Path:
    """给出某个 thread 在宿主机上的 workspace 目录。

    Args:
        root: 所有 thread 的 workspace 根目录。
        thread_id: 会话标识。

    Returns:
        该 thread 的 workspace 目录，不保证已存在。

    Raises:
        PathEscapeError: thread_id 会让目录落到根目录之外。
    """
    if not thread_id:
        message = "thread_id 不能为空"
        raise PathEscapeError(message)

    base = root.resolve()
    resolved = (base / thread_id).resolve()
    if resolved.parent != base:
        message = f"thread_id 越出了 workspace 根目录：{thread_id!r}"
        raise PathEscapeError(message)
    return resolved
