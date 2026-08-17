"""Skill 中间件的运行时重载行为。"""

from typing import cast

from deepagents.backends.protocol import BackendProtocol, FileDownloadResponse, LsResult
from deepagents.middleware.skills import SkillsState
from langgraph.runtime import Runtime

from src.app.agent.skill import ReloadingSkillsMiddleware

SKILL_MD = b"---\nname: fresh-skill\ndescription: \xe6\x96\xb0\xe8\xa7\x84\xe5\x88\x99\n---\n\n# Fresh\n"


class RecordingSkillBackend:
    """只实现官方 Skill 扫描会调用的两个异步接口。"""

    def __init__(self) -> None:
        self.listed: list[str] = []
        self.downloaded: list[list[str]] = []

    async def als(self, path: str) -> LsResult:
        self.listed.append(path)
        return LsResult(entries=[{"path": "/workspace/skill/fresh-skill", "is_dir": True}])

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self.downloaded.append(paths)
        return [FileDownloadResponse(path=paths[0], content=SKILL_MD)]


async def test_existing_checkpoint_metadata_does_not_skip_a_fresh_scan() -> None:
    backend = RecordingSkillBackend()
    middleware = ReloadingSkillsMiddleware(
        backend=cast(BackendProtocol, backend),
        sources=[("/workspace/skill/", "平台")],
    )

    state = cast(
        SkillsState,
        {"messages": [], "skills_metadata": [{"name": "old-skill", "description": "旧规则", "path": "/old"}]},
    )
    update = await middleware.abefore_agent(state, cast(Runtime, None), {})

    assert update is not None
    assert [one["name"] for one in update["skills_metadata"]] == ["fresh-skill"]
    assert backend.listed == ["/workspace/skill/"]
    assert backend.downloaded == [["/workspace/skill/fresh-skill/SKILL.md"]]
