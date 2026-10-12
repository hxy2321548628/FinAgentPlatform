"""验证 Git 归档发布始终取指定提交，并排除凭据和部署缓存。"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "package.py"
SPEC = importlib.util.spec_from_file_location("release_package", SCRIPT)
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class PackageTest(unittest.TestCase):
    def test_sensitive_files_and_nested_cache_are_excluded(self) -> None:
        for name in (
            ".env",
            "src/.env.local",
            "web/node_modules/a.js",
            "data/postgres/file",
            "src/.venv/bin/python",
            "deployment-workflow/dist/package.tar.gz",
        ):
            self.assertFalse(PACKAGE.include(Path(name)), name)
        self.assertTrue(PACKAGE.include(Path(".env.example")))
        self.assertTrue(PACKAGE.include(Path("src/app/api/app.py")))

    def test_ref_archive_ignores_dirty_checkout_and_records_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()
            tools = root / "tools"
            (tools / "linux").mkdir(parents=True)
            (tools / "linux/install.sh").write_text("#!/bin/bash\necho ok\n")
            for name, value in {
                "docker/compose.yml": "services: {}",
                "src/pyproject.toml": "[project]",
                "web/package.json": "{}",
                ".env": "SECRET=hidden",
                ".env.example": "SECRET=placeholder",
                "main.txt": "committed main",
                "deployment-workflow/dist/cache.txt": "excluded",
            }.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)

            def git(*args: str) -> str:
                return subprocess.check_output(
                    ["git", "-C", str(repo), *args], text=True
                ).strip()

            git("init", "-q")
            git("config", "user.name", "测试")
            git("config", "user.email", "test@example.invalid")
            git("add", ".")
            git("commit", "-qm", "main snapshot")
            commit = git("rev-parse", "HEAD")
            (repo / "main.txt").write_text("uncommitted change")
            result_file = root / "result.json"
            with (
                patch.object(PACKAGE, "ROOT", tools),
                patch.object(PACKAGE, "SOURCE", repo),
                patch.object(
                    sys,
                    "argv",
                    ["package.py", "--ref", commit, "--result-file", str(result_file)],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                PACKAGE.main()
            result = json.loads(result_file.read_text())
            self.assertEqual(result["source_commit"], commit)
            with tarfile.open(result["archive"]) as archive:
                prefix = result["version"]
                self.assertEqual(
                    archive.extractfile(prefix + "/app/main.txt").read(),
                    b"committed main",
                )
                names = archive.getnames()
                self.assertNotIn(prefix + "/app/.env", names)
                self.assertNotIn(
                    prefix + "/app/deployment-workflow/dist/cache.txt", names
                )
                metadata = json.load(archive.extractfile(prefix + "/release.json"))
                self.assertEqual(metadata["source_commit"], commit)
                self.assertEqual(metadata["quality_gate"], "not_run")
                services = json.load(
                    archive.extractfile(prefix + "/app/docker/release.yml")
                )["services"]
                self.assertEqual(
                    services["broker"]["environment"]["SANDBOX_IMAGE"],
                    metadata["sandbox_image"],
                )


if __name__ == "__main__":
    unittest.main()
