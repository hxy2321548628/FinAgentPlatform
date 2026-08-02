"""探针 3：写操作重复执行的实际行为。

回答 03agent-design §3.3 的三条断言：
  - `write_file` 对已存在文件是覆盖还是报错（文档标「⚠️ 待验证」）
  - `edit_file` 重放时 old_string 已不存在 → 报错（文档标「❌ 不幂等」）
  - `delete` 重放时文件已不存在 → 报错（文档标「❌ 不幂等」）

`write_file` 工具是 backend.write 的薄封装（middleware/filesystem.py 只加了路径校验与
权限判断，没有 exists 守卫），所以在 backend 层测即为工具层结论。

不需要 API key。两个 backend 都测：FilesystemBackend（宿主）与 DockerSandbox（容器）。
"""

from __future__ import annotations

import json
from pathlib import Path

from _common import OUT_DIR, fresh_workspace, section, verdict
from docker_sandbox import DockerSandbox, build_image, image_exists

results: list[dict] = []


def exercise(label: str, backend, root: str) -> dict:
    """对一个 backend 跑完整的「首次 → 重放」序列，返回观测结果。"""
    obs: dict[str, object] = {"backend": label}
    path = f"{root}/probe3.txt"

    first = backend.write(path, "第一次内容\n")
    second = backend.write(path, "第二次内容\n")
    after = backend.read(path)
    content = (after.file_data or {}).get("content") if after.file_data else None
    obs["write_first"] = {"error": first.error, "path": first.path}
    obs["write_second"] = {"error": second.error, "path": second.path}
    obs["content_after_second_write"] = content
    obs["write_is_overwrite"] = second.error is None and content is not None and "第二次" in content

    edit1 = backend.edit(path, "第二次内容", "第三次内容")
    edit2 = backend.edit(path, "第二次内容", "第三次内容")
    obs["edit_first"] = {"error": edit1.error, "occurrences": edit1.occurrences}
    obs["edit_replay"] = {"error": edit2.error, "occurrences": edit2.occurrences}
    obs["edit_replay_differs"] = (edit1.error, edit1.occurrences) != (edit2.error, edit2.occurrences)

    del1 = backend.delete(path)
    del2 = backend.delete(path)
    obs["delete_first"] = {"error": del1.error, "path": del1.path}
    obs["delete_replay"] = {"error": del2.error, "path": del2.path}
    obs["delete_replay_differs"] = (del1.error is None) != (del2.error is None)
    return obs


section("探针 3 · 写操作重放行为")

observations: list[dict] = []

# ---------------------------------------------------- FilesystemBackend（宿主）
from deepagents.backends import FilesystemBackend  # noqa: E402

# virtual_mode=True：agent 看到的 '/xxx' 映射到 root_dir 下，而不是宿主机真实根目录
fs_root = fresh_workspace("probe3_fs")
observations.append(exercise("FilesystemBackend", FilesystemBackend(root_dir=str(fs_root), virtual_mode=True), ""))

# --------------------------------------------------------- DockerSandbox（容器）
if not image_exists("zuel-spike-sandbox:latest"):
    build_image()
with DockerSandbox(fresh_workspace("probe3_docker")) as sandbox:
    observations.append(exercise("DockerSandbox", sandbox, "/workspace"))

# ------------------------------------------------------------------ 判定
for obs in observations:
    print(f"\n-- {obs['backend']} --")
    results.append(
        verdict(
            f"[{obs['backend']}] §3.3 存疑项：`write_file` 对已存在文件是**覆盖**",
            bool(obs["write_is_overwrite"]),
            f"第二次 write 的 error={obs['write_second']['error']!r}，读回内容={obs['content_after_second_write']!r}",
        )
    )
    results.append(
        verdict(
            f"[{obs['backend']}] §3.3 断言：`edit_file` 重放结果与首次**不同**",
            bool(obs["edit_replay_differs"]),
            f"首次 {obs['edit_first']} → 重放 {obs['edit_replay']}",
        )
    )
    results.append(
        verdict(
            f"[{obs['backend']}] §3.3 断言：`delete` 重放结果与首次**不同**",
            bool(obs["delete_replay_differs"]),
            f"首次 {obs['delete_first']} → 重放 {obs['delete_replay']}",
        )
    )

out = OUT_DIR / "probe3_write_idempotency.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"observations": observations, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n明细 → {out}")
