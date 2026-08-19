"""上下文预算的测试。

**这里验的是「阈值是平台自己定的」**，以及**「产物落点过得了平台的路径闸」**——
后者不成立时前者毫无意义：写盘被驳回是静默的，阈值调到多低都不会有任何区别。

「压缩在多少 token 时真的发生」不在这里验，那要真跑一次图，是验收判据 P13② 的活。
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.state import StateBackend
from deepagents.middleware.filesystem import TOO_LARGE_TOOL_MSG
from langchain.tools import ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.agent.context import (
    CONTEXT_KEEP_RATIO,
    CONTEXT_TRIGGER_TOKEN,
    HISTORY_DIR,
    TOOL_RESULT_DIR,
    create_offloader,
    create_squeezer,
    pin_artifact_path,
)
from app.sandbox.backend import SandboxBackend
from app.sandbox.container import CommandResult
from app.sandbox.path import to_virtual_path

# 卸载后的替换文案由框架给，取它的固定前缀当标记 ——
# 自己抄一份的话，上游改词时这条判据会静默变成「永远匹配不上」
OFFLOAD_MARKER = TOO_LARGE_TOOL_MSG.split("{")[0]


class StoppedContainer:
    """不会被调用的容器：卸载只写文件，一条命令都不执行。"""

    @property
    def id(self) -> str:
        return "fake-container-id"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        raise AssertionError(f"卸载路径不该执行命令：{command!r}（timeout={timeout}）")


def a_backend(workspace: Path) -> SandboxBackend:
    """真的 backend，不是替身 —— 要验的正是它那道路径闸。"""
    return SandboxBackend(workspace=workspace, container=StoppedContainer())


def a_request() -> ToolCallRequest:
    """一次 execute 的工具调用请求，中间件只读它的名字与 id。"""
    return ToolCallRequest(
        tool_call={"name": "execute", "args": {}, "id": "call_abc", "type": "tool_call"},
        tool=None,
        state={},
        runtime=ToolRuntime(
            state={},
            context=None,
            config={},
            stream_writer=lambda _: None,
            tool_call_id="call_abc",
            store=None,
        ),
    )


def a_handler(content: str) -> Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]]:
    """交出一条指定大小的工具结果，替中间件下游的那一段。"""

    async def handle(request: ToolCallRequest) -> ToolMessage | Command[object]:
        return ToolMessage(content=content, tool_call_id=str(request.tool_call["id"]), name="execute", status="success")

    return handle


def a_squeezer() -> object:
    return create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend())


def test_the_trigger_is_a_platform_constant_not_a_profile_guess() -> None:
    """阈值必须来自平台，不能是从模型 profile 推出来的那个。

    默认是 85% × 100 万。实测模型确实吃得下百万上下文，但一次分析的历史峰值只有两万 ——
    那条线因此永远够不着，压缩等于从未生效过。
    """
    # 私有属性：上游改名这条就会失灵，所以另有一条真跑的判据（P13②）兜底
    assert a_squeezer()._lc_helper.trigger == ("tokens", CONTEXT_TRIGGER_TOKEN)  # type: ignore[attr-defined]


def test_the_platform_copy_replaces_the_default_one() -> None:
    """名字必须与基础栈里那份一致，否则不是替换而是叠加。

    两套压缩都改写历史，谁先触发不确定，且都会打掉前缀缓存。
    """
    assert a_squeezer().name == "SummarizationMiddleware"  # type: ignore[attr-defined]


def test_the_threshold_is_far_below_the_model_ceiling() -> None:
    """实测上限一百万。阈值贴着上限定就等于不压；离得太近也一样。"""
    assert CONTEXT_TRIGGER_TOKEN < 200_000


def test_the_trigger_can_be_dialled_down_for_verification() -> None:
    """压缩到底触没触发，只有把阈值调到极小值跑一道普通题才验得出来（P13②）。"""
    squeezer = create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend(), trigger_token=2_000)

    assert squeezer._lc_helper.trigger == ("tokens", 2_000)  # type: ignore[attr-defined]


def test_keeping_by_token_not_by_message_count() -> None:
    """按条数保留等于不压。

    类默认是保留最近二十条消息，而一次分析的历史通常就十几条 —— 没有任何东西可以折叠，
    token 再多也不触发。2026-08-19 真机上栽出来的。
    """
    keep = a_squeezer()._lc_helper.keep  # type: ignore[attr-defined]

    assert keep == ("tokens", int(CONTEXT_TRIGGER_TOKEN * CONTEXT_KEEP_RATIO))


def test_a_dialled_down_trigger_still_leaves_room_to_compact() -> None:
    """验收时把 trigger 调到极小，保留量要跟着走。

    keep 写死的话会出现「保留的比触发线还多」—— 逻辑上永远不可能压，
    而那个「没触发」看着就像功能坏了。
    """
    squeezer = create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend(), trigger_token=2_000)

    kind, keep_token = squeezer._lc_helper.keep  # type: ignore[attr-defined]

    assert kind == "tokens"
    assert keep_token < 2_000


# ---------------------------------------------------------------- 产物落点
async def test_a_large_tool_result_really_lands_on_disk(tmp_path: Path) -> None:
    """端到端：超限的工具结果必须真的被换成一句路径，文件真的躺在盘上。

    **这是本模块最贵的一条判据**。此前只验「阈值等于常量」，而阈值从来不是变量 ——
    框架把落点算成 `/large_tool_results`（它只在 `CompositeBackend` 上取 artifacts_root，
    其余一律按 `/` 算），平台的路径闸要求一切在 `/workspace` 下，写盘因此被驳回；
    驳回后 `_aprocess_large_message` 原样返回消息，不抛异常也不记日志。
    于是阈值从两万调到一百毫无区别，卸载一次都没成功过。
    """
    backend = a_backend(tmp_path)
    offloader = create_offloader(backend, evict_token=10)

    result = await offloader.awrap_tool_call(a_request(), a_handler("x" * 5000))

    assert isinstance(result, ToolMessage)
    assert str(result.content).startswith(OFFLOAD_MARKER)
    assert (tmp_path / ".large_tool_results").is_dir()
    assert [one.read_text() for one in (tmp_path / ".large_tool_results").iterdir()] == ["x" * 5000]


async def test_a_small_tool_result_passes_through_untouched(tmp_path: Path) -> None:
    """够不着阈值的照原样走 —— 上面那条不成立时，这条能证明它不是「什么都卸载」。"""
    offloader = create_offloader(a_backend(tmp_path), evict_token=10_000)

    result = await offloader.awrap_tool_call(a_request(), a_handler("短输出"))

    assert isinstance(result, ToolMessage)
    assert result.content == "短输出"
    assert not (tmp_path / ".large_tool_results").exists()


def test_the_offload_path_clears_the_platform_path_gate() -> None:
    """落点必须过得了 `to_virtual_path` —— 过不了就是那次静默驳回。"""
    offloader = create_offloader(StateBackend())

    assert to_virtual_path(TOOL_RESULT_DIR) == "/.large_tool_results"
    assert offloader._large_tool_results_prefix == TOOL_RESULT_DIR  # type: ignore[attr-defined]


def test_the_history_archive_path_clears_the_platform_path_gate() -> None:
    """压缩的归档落点同样要过闸。

    **它坏掉的样子是「压了但没留底」**：摘要照常替换历史，归档写盘失败后
    `file_path` 变成 None，那句「完整历史已存到 …」根本不会拼进摘要 ——
    折掉的原文再也找不回来。2026-08-19 库里 26 次压缩，26 次 file_path 为空。
    """
    squeezer = create_squeezer(GenericFakeChatModel(messages=iter([])), StateBackend())

    assert to_virtual_path(HISTORY_DIR) == "/.conversation_history"
    assert squeezer._history_path_prefix == HISTORY_DIR  # type: ignore[attr-defined]
    assert squeezer._media_prefix == f"{HISTORY_DIR}/media"  # type: ignore[attr-defined]


def test_pinning_a_path_the_framework_no_longer_has_fails_loudly() -> None:
    """上游改了属性名就要当场炸，不能悄悄多挂一个没人读的属性。

    `setattr` 到一个不存在的名字不会报错，框架的默认落点原封不动继续用 ——
    症状与修复前一模一样，而且这次连线索都没有。
    """
    with pytest.raises(AttributeError, match="改名"):
        pin_artifact_path(SimpleNamespace(), _nonexistent_prefix="/workspace/x")
