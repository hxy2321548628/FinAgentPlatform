"""把运行快照里的 MCP 引用装成外部工具。

**这是本期唯一一处「平台的可用性挂在一台校外机器上」的代码**，形状因此与别的装配层
不同 —— 每一条都是从实测来的，不是从文档来的：

- **逐个 server 各要各的。** `MultiServerMCPClient.get_tools()` 内部是 `gather`，
  一个连不上就整批抛 —— 照官方示例写（一个 client 装所有 server）的后果是校外任意
  一台机器下线，所有挂了 MCP 的分析全都拿不到工具。
- **超时由平台自己 `asyncio.timeout` 压住。** connection 的 `timeout` 管不到 SSE 的
  读等待，真正的上限是 `sse_read_timeout`（默认 300 秒）—— 实测一台「接受连接但不
  回应」的服务要等 **300.05 秒**才抛出来，而教师看到的是「点了提问，什么都没发生」。
  connection 上那两个字段也一并设成平台的值，但**判据盯的是外层这一道**。
- **单次调用超时不抛，返回一条 `ToolMessage(status="error")`。** 实测直接抛
  `TimeoutError` 会掀掉整次分析 —— 而那次分析可能已经跑了二十分钟。
- **与内置工具撞名的外部工具一律剔除。** 实测不是「两个同名工具选一个」，而是外部
  工具**静默顶掉**内置那个，内置的从工具列表里消失。于是一个上架时人畜无害的服务，
  只要事后加一个叫 `read_file` 的工具，就能接管平台的文件读取 —— agent 以为在读
  沙箱，实际把路径与后续内容发去了校外。**防线因此在装配层，不只在上架审核上**：
  上架时那份清单会过期，装配时的剔除不会。

**不挂 MCP 时这个模块一个动作都不做**，与 skill 数为 0 时一次 broker 都不打同形 ——
绝大多数分析走的是那条路，而「平台好像变慢了」不会有任何日志指向这里。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from langchain_mcp_adapters.sessions import Connection, SSEConnection, StreamableHttpConnection

from app.agent.config import McpReference

logger = logging.getLogger(__name__)

# 装配时拉一次工具清单的上限。**这道防线不是框架给的，是平台自己包上去的** ——
# 取 30 是接入规范给外部服务的承诺值，与单次调用同一个数
MCP_CONNECT_TIMEOUT = 30.0

# 单次工具调用的上限。超时返回错误结果而不是抛异常
MCP_CALL_TIMEOUT = 30.0

# 一次 run 最多挂几个服务。实测一个服务平均带 3～4 个工具，3 个服务约 12 个外部工具，
# 加上内置 8 个已经 20 个，再多模型选不准。**这个数是猜的，列为观察项**
MAX_MCP_SERVER = 3

# 外部工具不许占用的名字：DeepAgents 的八个内置文件工具，加上派子智能体的 `task`。
# **硬编码是有意的** —— 装配层要在拿到工具的那一刻就判断，而这时 agent 还没建起来。
# `agent/test` 里有一条用例拿真实的 FilesystemMiddleware 对着它核，上游加了第九个
# 内置工具时那条会红
RESERVED_TOOL_NAME = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute", "task"}
)

CALL_TIMEOUT_MESSAGE = f"调用超时（{MCP_CALL_TIMEOUT:.0f} 秒），这个外部服务这次没有响应。"


@dataclass(frozen=True)
class McpTarget:
    """装配一个 server 需要的全部信息。

    **凭据在这里已经是取出来的值，不是键名。** 库里只存键名，值在 `.env` 里 ——
    这一步的翻译由调用方（worker 侧的仓储）完成，装配层不认识 Settings。
    """

    server_id: str
    name: str
    url: str
    transport: str
    credential: str | None
    declared_tool_name: list[str]
    enabled: bool
    disabled_reason: str | None


class McpTargetLoaderProtocol(Protocol):
    """装配层对目录层的全部要求。"""

    async def load_mcp_target(self, server_id: str) -> McpTarget | None:
        """按快照里的稳定标识读一条目录记录，连同它此刻的状态。"""
        ...


class McpFailureRecorderProtocol(Protocol):
    """装配层对熔断计数器的全部要求。"""

    async def record_failure(self, server_id: str, *, reason: str) -> None:
        """记一次传输层失败；到阈值时由实现方停用这个服务。"""
        ...

    async def record_success(self, server_id: str) -> None:
        """成功一次即清零。"""
        ...


async def load_mcp_tools(
    references: Sequence[McpReference],
    *,
    loader: McpTargetLoaderProtocol,
    recorder: McpFailureRecorderProtocol | None = None,
) -> list[BaseTool]:
    """按快照顺序逐个 server 取工具，一个坏的不影响别的。

    Args:
        references: 运行快照里冻结的 MCP 引用。
        loader: 目录层。
        recorder: 熔断计数器；不传则只降级不计数。

    Returns:
        可直接交给 `create_deep_agent(tools=...)` 的外部工具，已剔除撞名的那些。
        没有引用时是空列表，且**一次目录查询都不发生**。
    """
    if not references:
        return []

    collected: list[BaseTool] = []
    taken: set[str] = set()
    for reference in references:
        target = await loader.load_mcp_target(reference.server_id)
        if target is None:
            logger.warning("MCP 快照指向的目录记录已不存在：server_id=%s", reference.server_id)
            continue
        if not target.enabled:
            # C4：已停用的**一次都不连**。连一次就等于把停用变成了「每次多等 30 秒」
            logger.warning(
                "MCP 已停用，跳过且不发起连接：server_id=%s name=%s reason=%s",
                target.server_id,
                target.name,
                target.disabled_reason,
            )
            continue
        tools = await _load_one(target, recorder=recorder)
        if tools is None:
            continue
        _warn_on_drift(target, [one.name for one in tools])
        collected.extend(_usable(target, tools, taken))
    return collected


async def probe_mcp_server(
    target: McpTarget, *, recorder: McpFailureRecorderProtocol | None = None
) -> list[str] | None:
    """管理员的「测试连接」：连一次，拿到工具名就算通。

    **走的是装配同一条路、同一个计数器。** 另写一份的话，验收判据（它走的正是这条）
    验的就是一条没人走的路 —— 而它照样绿。

    Args:
        target: 目录记录，**这里不看 `enabled`** —— 探活正是管理员判断「它回来没有」
            的手段，对一个已停用的服务尤其要能连。
        recorder: 熔断计数器。

    Returns:
        实际拿到的工具名；连不上则 None。
    """
    tools = await _load_one(target, recorder=recorder)
    return None if tools is None else [one.name for one in tools]


async def _load_one(target: McpTarget, *, recorder: McpFailureRecorderProtocol | None) -> list[BaseTool] | None:
    """要一个 server 的工具清单；连不上返回 None 而不是抛。"""
    client = MultiServerMCPClient(
        {target.name: _connection(target)},
        tool_interceptors=[_CallGuard(server_id=target.server_id, recorder=recorder)],
    )
    try:
        async with asyncio.timeout(MCP_CONNECT_TIMEOUT):
            tools = await client.get_tools(server_name=target.name)
    except TimeoutError:
        await _record_failure(recorder, target, reason=f"装配超时（{MCP_CONNECT_TIMEOUT:.0f} 秒）")
        return None
    # **这里抓的是宽类型，理由要写明**：适配器把底层异常（`httpx.ConnectError` 等）
    # 包进 TaskGroup 的 `ExceptionGroup` 里，抓具体类型抓不到。放过去的话，一台校外
    # 机器下线就会掀掉一次已经跑了二十分钟的分析
    except Exception as error:
        await _record_failure(recorder, target, reason=f"连接失败：{type(error).__name__}")
        return None
    if recorder is not None:
        await recorder.record_success(target.server_id)
    return tools


async def _record_failure(recorder: McpFailureRecorderProtocol | None, target: McpTarget, *, reason: str) -> None:
    logger.warning("MCP 装配失败，跳过这一个：server_id=%s name=%s %s", target.server_id, target.name, reason)
    if recorder is not None:
        await recorder.record_failure(target.server_id, reason=reason)


def _connection(target: McpTarget) -> Connection:
    """按目录记录拼一条连接配置。

    connection 上的两个超时字段也设成平台的值 —— 双保险。**但它们管不住一个 hang 住
    的服务**，真正掐断的是外层的 `asyncio.timeout`。
    """
    headers = None if target.credential is None else {"Authorization": target.credential}
    if target.transport == "sse":
        return SSEConnection(
            url=target.url,
            transport="sse",
            headers=headers,
            timeout=MCP_CONNECT_TIMEOUT,
            sse_read_timeout=MCP_CONNECT_TIMEOUT,
        )
    return StreamableHttpConnection(
        url=target.url,
        transport="streamable_http",
        headers=headers,
        timeout=MCP_CONNECT_TIMEOUT,
        sse_read_timeout=MCP_CONNECT_TIMEOUT,
    )


@dataclass(frozen=True)
class _CallGuard:
    """给单次工具调用压一道超时，并把结果记进同一个熔断计数器。

    **超时返回错误结果而不是抛异常**：抛出去的话，一次慢调用会掀掉整次分析（实测），
    而那次分析可能已经跑了二十分钟。返回一条人话，模型看到它会自己决定换个方法或者
    如实告诉教师 —— 与子智能体失败只返回错误文本是同一条规矩。

    **工具自己报错不算失败。** 那条路走的是正常返回（服务答话了），只有超时才计数。
    """

    server_id: str
    recorder: McpFailureRecorderProtocol | None

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
    ) -> MCPToolCallResult:
        """拦一次工具调用。"""
        try:
            async with asyncio.timeout(MCP_CALL_TIMEOUT):
                result = await handler(request)
        except TimeoutError:
            logger.warning("MCP 工具调用超时：server=%s tool=%s", request.server_name, request.name)
            if self.recorder is not None:
                await self.recorder.record_failure(
                    self.server_id, reason=f"工具调用超时（{MCP_CALL_TIMEOUT:.0f} 秒）：{request.name}"
                )
            return ToolMessage(content=CALL_TIMEOUT_MESSAGE, tool_call_id="", status="error")
        if self.recorder is not None:
            await self.recorder.record_success(self.server_id)
        return result


def _warn_on_drift(target: McpTarget, actual: list[str]) -> None:
    """实际拿到的工具名与上架时那份清单比对。

    **不一致不拦，只记。** 清单过期是静默的 —— 不比对就永远发现不了，而拦下来会让
    一次正常的上游升级把所有人的分析打断。
    """
    declared = set(target.declared_tool_name)
    found = set(actual)
    if declared == found:
        return
    logger.warning(
        "MCP 工具清单与上架时不一致：server_id=%s name=%s 少了=%s 多了=%s",
        target.server_id,
        target.name,
        sorted(declared - found),
        sorted(found - declared),
    )


def _usable(target: McpTarget, tools: list[BaseTool], taken: set[str]) -> list[BaseTool]:
    """剔除撞名的外部工具。

    两种撞名都剔：与平台内置的（会把内置那个静默顶掉，是安全问题），以及与前一个
    server 已经给出的同名工具（后一个会把前一个顶掉，症状同样是「调了但结果不对」）。
    """
    kept: list[BaseTool] = []
    for tool in tools:
        if tool.name in RESERVED_TOOL_NAME:
            logger.warning(
                "外部工具与平台内置工具撞名，已剔除：server_id=%s name=%s tool=%s",
                target.server_id,
                target.name,
                tool.name,
            )
            continue
        if tool.name in taken:
            logger.warning(
                "两个外部服务提供了同名工具，保留先装上的那个：server_id=%s name=%s tool=%s",
                target.server_id,
                target.name,
                tool.name,
            )
            continue
        taken.add(tool.name)
        kept.append(tool)
    return kept
