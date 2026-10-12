"""为堡垒机传包生成独立发布包，不包含本地凭据或运行数据。"""

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (
    ROOT.parent
    if (ROOT.parent / "src/pyproject.toml").exists()
    else ROOT.parent / "FinAgentPlatform-main"
)
EXCLUDED = {
    ".git",
    ".venv",
    "deployment-workflow",
    "node_modules",
    "data",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "coverage",
    "test-results",
    "playwright-report",
}


def digest_file(path: Path) -> str:
    """以流式读取校验文件并及时关闭句柄。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def include(path: Path) -> bool:
    """过滤凭据、开发缓存和运行数据。"""
    return not (
        set(path.parts) & EXCLUDED
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.suffix in {".pyc", ".pyo"}
        or path.name == ".coverage"
    )


def copy_source(destination: Path) -> None:
    for path in SOURCE.rglob("*"):
        relative = path.relative_to(SOURCE)
        if path.is_file() and not path.is_symlink() and include(relative):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def copy_ref(destination: Path, ref: str) -> str:
    """从指定 Git 提交提取已跟踪源码，忽略工作目录改动和部署目录。"""
    commit = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "--verify", ref + "^{commit}"],
        text=True,
    ).strip()
    payload = subprocess.check_output(
        ["git", "-C", str(SOURCE), "archive", "--format=tar", commit]
    )
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive.getmembers():
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Git 归档包含非法路径")
            if member.isfile() and include(relative):
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    target.write_bytes(stream.read())
    return commit


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref", help="业务源码 Git 引用，例如 origin/main；不会切换当前分支"
    )
    parser.add_argument(
        "--run-checks", action="store_true", help="在实际打包源码上运行统一 make 门禁"
    )
    parser.add_argument(
        "--result-file", type=Path, help="写入本次产物路径，供直接部署脚本使用"
    )
    parser.add_argument(
        "--with-images", action="store_true", help="需要 Docker Linux 容器引擎"
    )
    args = parser.parse_args()
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="finagent-release-") as temp:
        release = Path(temp) / version
        app = release / "app"
        commit = copy_ref(app, args.ref) if args.ref else None
        if not args.ref:
            copy_source(app)
        if args.run_checks:
            subprocess.run(["make", "sync-locked"], cwd=app, check=True)
            subprocess.run(["make", "all"], cwd=app, check=True)
        shutil.copytree(ROOT / "linux", release / "linux")
        tags = {
            name: f"finagent/{name}:{version}" for name in ("backend", "web", "sandbox")
        }
        services = {
            service: {
                "restart": "on-failure",
                "image": tags["web" if service == "nginx" else "backend"],
            }
            for service in ("api", "worker", "broker", "nginx")
        }
        for service in ("api", "worker", "broker"):
            services[service]["environment"] = {"SANDBOX_IMAGE": tags["sandbox"]}
        services.update(
            {service: {"restart": "on-failure"} for service in ("postgres", "redis")}
        )
        (app / "docker/release.yml").write_text(
            json.dumps({"services": services}, indent=2), encoding="utf-8"
        )
        (release / "release.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "mode": "images" if args.with_images else "source",
                    "sandbox_image": tags["sandbox"],
                    "source_ref": args.ref,
                    "source_commit": commit,
                    "quality_gate": "passed" if args.run_checks else "not_run",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if args.with_images:
            for name, context, dockerfile in (
                ("backend", "src", "src/Dockerfile"),
                ("web", "web", "web/Dockerfile"),
                ("sandbox", ".", "docker/sandbox.Dockerfile"),
            ):
                run(
                    "docker",
                    "build",
                    "--platform",
                    "linux/amd64",
                    "-t",
                    tags[name],
                    "-f",
                    str(app / dockerfile),
                    str(app / context),
                )
            for image in ("postgres:16-alpine", "redis:7-alpine"):
                run("docker", "pull", "--platform", "linux/amd64", image)
            run(
                "docker",
                "save",
                "-o",
                str(release / "images.tar"),
                *tags.values(),
                "postgres:16-alpine",
                "redis:7-alpine",
            )
        # Windows checkout 的 shell 文件统一转换为 LF；由 bash 调用，无需依赖可执行位。
        for path in release.rglob("*"):
            if path.is_file() and path.suffix in {".sh", ".service"}:
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        manifest = {
            str(p.relative_to(release)).replace("\\", "/"): digest_file(p)
            for p in release.rglob("*")
            if p.is_file()
        }
        (release / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        archive = output / f"FinAgentPlatform-{version}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(release, arcname=version)
        digest = digest_file(archive)
        archive.with_suffix(archive.suffix + ".sha256").write_text(
            f"{digest}  {archive.name}\n", encoding="ascii"
        )
        if args.result_file:
            args.result_file.write_text(
                json.dumps(
                    {
                        "archive": str(archive.resolve()),
                        "version": version,
                        "source_commit": commit,
                    }
                ),
                encoding="utf-8",
            )
        print(
            f"发布包：{archive}\nSHA256：{digest}\n模式：{args.with_images and '镜像包' or '源码包（服务器联网构建）'}"
        )


if __name__ == "__main__":
    main()
