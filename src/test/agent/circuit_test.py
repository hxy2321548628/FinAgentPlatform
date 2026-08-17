"""MCP 熔断的测试，连真 Redis。"""

import pytest
from redis.asyncio import Redis

from app.agent.circuit import MCP_FAILURE_THRESHOLD, McpCircuit


class Disabler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.disabled: set[str] = set()

    async def disable_for_failure(self, server_id: str, *, reason: str) -> bool:
        self.calls.append((server_id, reason))
        # 库里那条更新只对还在 enabled 的行生效，这里照着同一条语义
        if server_id in self.disabled:
            return False
        self.disabled.add(server_id)
        return True


@pytest.fixture
def disabler() -> Disabler:
    return Disabler()


@pytest.fixture
def circuit(live_cache: Redis, disabler: Disabler) -> McpCircuit:
    return McpCircuit(live_cache, disabler)


async def test_failures_short_of_the_threshold_do_not_disable_anything(circuit: McpCircuit, disabler: Disabler) -> None:
    for _ in range(MCP_FAILURE_THRESHOLD - 1):
        await circuit.record_failure("srv-1", reason="连接失败")

    assert disabler.calls == []
    assert await circuit.failure_count("srv-1") == MCP_FAILURE_THRESHOLD - 1


async def test_five_in_a_row_disables_and_writes_the_reason(circuit: McpCircuit, disabler: Disabler) -> None:
    for _ in range(MCP_FAILURE_THRESHOLD):
        await circuit.record_failure("srv-2", reason="连接失败：ExceptionGroup")

    assert [server_id for server_id, _ in disabler.calls] == ["srv-2"]
    reason = disabler.calls[0][1]
    assert f"连续失败 {MCP_FAILURE_THRESHOLD} 次" in reason
    assert "ExceptionGroup" in reason


async def test_one_success_in_the_middle_clears_the_count(circuit: McpCircuit, disabler: Disabler) -> None:
    """判据是「中间没有成功过」，不是「一段时间内失败了几次」。"""
    for _ in range(MCP_FAILURE_THRESHOLD - 1):
        await circuit.record_failure("srv-3", reason="连接失败")
    await circuit.record_success("srv-3")
    for _ in range(MCP_FAILURE_THRESHOLD - 1):
        await circuit.record_failure("srv-3", reason="连接失败")

    assert disabler.calls == []


async def test_the_database_is_written_once_even_if_failures_keep_coming(
    circuit: McpCircuit, disabler: Disabler
) -> None:
    """停用之后还在失败的那些不该反复写库，也不该反复刷 WARNING。"""
    for _ in range(MCP_FAILURE_THRESHOLD + 3):
        await circuit.record_failure("srv-4", reason="连接失败")

    assert list(disabler.disabled) == ["srv-4"]


async def test_a_manual_recovery_clears_the_counter(circuit: McpCircuit) -> None:
    """不清零的话，恢复之后再失败一次就立刻又被停用。"""
    for _ in range(MCP_FAILURE_THRESHOLD):
        await circuit.record_failure("srv-5", reason="连接失败")

    await circuit.reset("srv-5")

    assert await circuit.failure_count("srv-5") == 0


async def test_two_servers_are_counted_apart(circuit: McpCircuit, disabler: Disabler) -> None:
    for _ in range(MCP_FAILURE_THRESHOLD - 1):
        await circuit.record_failure("srv-6", reason="连接失败")
        await circuit.record_failure("srv-7", reason="连接失败")

    assert disabler.calls == []
    assert await circuit.failure_count("srv-6") == MCP_FAILURE_THRESHOLD - 1
