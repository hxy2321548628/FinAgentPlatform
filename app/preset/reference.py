"""把配置里的 agent 引用解析成一份冻结的快照。

**解析发生在提交那一刻，不在执行那一刻。** 教师提交之后到 worker 领到任务之间可能隔
几分钟，那期间作者随时可能撤回共享或发新版本 —— 在执行侧解析，同一次提交的结果就取决于
worker 什么时候有空。冻结在提交那一刻，历史 run 的快照因此永远读得回它当时用的那份提示词。

**解析不出来一律报错，不静默回退默认提示词。** 静默回退跑得完、不报错，唯一的症状是
回答变了味 —— 那正是这个平台反复警惕的那种失效。代价是教师会撞到一次硬失败，
因此话术必须让他看得懂该做什么。
"""

import logging
from typing import Protocol

from agent.config import AgentConfig, AgentConfigRequest
from preset.repository import ResolvedAgent

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = "这个智能体现在用不了：可能作者已经收回共享或删掉了它。请在配置里重新选一个"


class AgentResolverProtocol(Protocol):
    """引用解析对目录层的全部要求：按提交者身份查一次。"""

    async def resolve(self, agent_id: str, *, user_id: str) -> ResolvedAgent | None:
        """解析一次引用。"""
        ...


class ReferenceUnavailableError(Exception):
    """引用指向的 agent 此刻用不了。

    不存在、已删、没发布过、以及「这个人够不着它」四种情况给同一个回答 ——
    分开说等于告诉试探的人「你猜的这个 id 是存在的」。
    """


async def resolve_reference(
    config: AgentConfigRequest,
    *,
    user_id: str,
    resolver: AgentResolverProtocol,
) -> AgentConfig:
    """把配置里的 agent 引用解析成具体版本与提示词。

    没有引用时原样返回，**一次库都不查** —— 绝大多数提交走的是这条路。

    Args:
        config: 这一轮生效的配置，引用还没解析。
        user_id: 提交的人。**用他的身份去解析** —— 能不能用这个 agent，
            问的是提交的人而不是作者。
        resolver: 目录层。

    Returns:
        解析之后的配置：`agent_id`、`agent_version`、`system_prompt` 三样都在。

    Raises:
        ReferenceUnavailableError: 引用此刻解析不出来。
    """
    if config.agent_id is None:
        return AgentConfig(system_prompt=config.system_prompt)

    resolved = await resolver.resolve(config.agent_id, user_id=user_id)
    if resolved is None:
        logger.info("引用解析失败：agent_id=%s user_id=%s", config.agent_id, user_id)
        raise ReferenceUnavailableError(UNAVAILABLE_MESSAGE)

    logger.info("引用已解析：agent_id=%s version=%s", resolved.agent_id, resolved.version)
    return AgentConfig(
        agent_id=resolved.agent_id,
        agent_version=resolved.version,
        system_prompt=resolved.system_prompt,
    )
