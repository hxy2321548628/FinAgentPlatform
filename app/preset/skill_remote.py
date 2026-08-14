"""API/Worker 到 Broker 的 Skill 存储与对齐客户端。"""

import base64
from collections.abc import Sequence

from agent.config import SkillReference
from preset.skill_package import SkillFile
from sandbox.remote import BrokerConnection


class RemoteSkillStore:
    """只封装 Broker Skill 端点的 HTTP 细节。"""

    def __init__(self, connection: BrokerConnection) -> None:
        self._connection = connection

    async def save_version(self, skill_id: str, version: int, files: Sequence[SkillFile]) -> None:
        """持久化一版已经校验的文件。"""
        await self._connection.call(
            "POST",
            f"/skill/{skill_id}/versions/{version}",
            json={
                "files": [{"path": one.path, "content": base64.b64encode(one.content).decode("ascii")} for one in files]
            },
        )

    async def align(self, thread_id: str, references: Sequence[SkillReference]) -> None:
        """按完整清单对齐一个会话的 Skill。"""
        await self._connection.call(
            "POST",
            f"/threads/{thread_id}/skill/align",
            json={
                "skills": [{"skill_id": one.skill_id, "version": one.version, "name": one.name} for one in references]
            },
        )
