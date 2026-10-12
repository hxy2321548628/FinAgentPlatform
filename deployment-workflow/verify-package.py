"""校验发布包内容、敏感文件过滤和服务镜像配置。"""

import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parent
archive = max((root / "dist").glob("*.tar.gz"))
with tarfile.open(archive) as tar:
    names = tar.getnames()
    prefix = names[0]
    manifest = json.load(tar.extractfile(prefix + "/manifest.json"))
    for name, expected in manifest.items():
        actual = hashlib.sha256(tar.extractfile(prefix + "/" + name).read()).hexdigest()
        assert actual == expected, name
    assert not any("/.env" in n and not n.endswith(".env.example") for n in names)
    assert not any(
        "/node_modules/" in n or "/.venv/" in n or "/data/" in n for n in names
    )
    override = json.load(tar.extractfile(prefix + "/app/docker/release.yml"))
    assert set(override["services"]) == {
        "api",
        "worker",
        "broker",
        "nginx",
        "postgres",
        "redis",
    }
    for service in ("api", "worker", "broker"):
        assert override["services"][service]["environment"]["SANDBOX_IMAGE"].startswith(
            "finagent/sandbox:"
        )
    assert all(s["restart"] == "on-failure" for s in override["services"].values())
    for name in names:
        if name.endswith(".sh"):
            content = tar.extractfile(name).read()
            assert b"\r" not in content and not content.startswith(b"\xef\xbb\xbf")
with archive.open("rb") as stream:
    assert (
        hashlib.file_digest(stream, "sha256").hexdigest()
        == archive.with_suffix(".gz.sha256").read_text().split()[0]
    )
print(
    "PASS: package hashes, excluded secrets/data/cache, six-service override, sandbox version, shell LF/BOM"
)
print(archive.name)
