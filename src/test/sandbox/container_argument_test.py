from pathlib import Path

import pytest

from app.sandbox.container import ContainerError, DockerContainer
from app.sandbox.path import MEMORY_DIR, SANDBOX_ROOT


def test_docker_masks_real_memory_with_an_empty_read_only_tmpfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argument: list[str] = []

    def fake_run_docker(command: list[str], *, timeout: int) -> str:
        del timeout
        argument.extend(command)
        return "container-id\n"

    monkeypatch.setattr("app.sandbox.container._run_docker", fake_run_docker)
    DockerContainer("thread-1", tmp_path).start()

    masks = [argument[index + 1] for index, value in enumerate(argument) if value == "--tmpfs"]
    memory_mount = next(value for value in masks if value.startswith(f"{SANDBOX_ROOT}/{MEMORY_DIR}:"))
    assert "ro" in memory_mount.split(":", 1)[1].split(",")
    assert "mode=0555" in memory_mount
    assert argument.index(memory_mount) > argument.index(f"{tmp_path.resolve()}:{SANDBOX_ROOT}")


def test_docker_does_not_recreate_a_missing_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    absent = tmp_path / "deleted-thread"
    called = False

    def fake_run_docker(command: list[str], *, timeout: int) -> str:
        del command, timeout
        nonlocal called
        called = True
        return "container-id"

    monkeypatch.setattr("app.sandbox.container._run_docker", fake_run_docker)

    with pytest.raises(ContainerError, match="workspace 目录不存在"):
        DockerContainer("thread-1", absent).start()

    assert not called
    assert not absent.exists()
