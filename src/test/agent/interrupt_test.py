"""哪些工具调用要停下来等教师确认。

**这一组测试钉的是一条安全语义，不是实现细节**：平台对教师的承诺是「删文件要你点头」，
而 2026-08-18 的验收照出这条承诺有一条绕行路 —— agent 不调 `delete`，改用
`execute` 跑 `rm`，闸门一次都没响（P3①、P9⑤ 五条断言全红）。
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from deepagents.backends import FilesystemBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolRuntime

from app.agent.factory import Agent
from app.agent.interrupt import (
    ALLOWED_DECISION,
    DELETE_TOOL,
    EXECUTE_TOOL,
    INTERRUPT_ON,
    removes_files,
)
from app.agent.question import QUESTION_ALLOWED_DECISION, QUESTION_TOOL


class ToolCallingModel(BaseChatModel):
    """第一轮发一次 `execute`，之后收工。真图要一个确定的模型才验得了闸门。"""

    command: str = ""
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "tool-calling"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # noqa: ANN401 - 必须匹配 LangChain 抽象签名
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(self, *argument: Any, **keyword: Any) -> ChatResult:  # noqa: ANN401 - 基类参数繁杂
        self.calls += 1
        if self.calls > 1:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="做完了"))])
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": EXECUTE_TOOL,
                    "args": {"command": self.command},
                    "id": "call-execute",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def request(command: str) -> ToolCallRequest:
    """造一个只有 args 有意义的 `execute` 调用请求。

    谓词只读 `tool_call`，其余三个字段框架在 batch 模式下也给不全（`tool=None`）。
    """
    return ToolCallRequest(
        tool_call=ToolCall(name=EXECUTE_TOOL, args={"command": command}, id="call-1"),
        tool=None,
        state={},
        runtime=cast(ToolRuntime[None, dict[str, object]], None),
    )


def when() -> object:
    return INTERRUPT_ON[EXECUTE_TOOL]["when"]


# ------------------------------------------------------------ 命令串的识别
def test_a_plain_command_is_not_intercepted() -> None:
    """绝大多数 execute 是跑分析脚本。拦错了，一次分析要教师点十几次确认。"""
    assert removes_files("python /workspace/analyze.py") is False


def test_removing_a_file_is_intercepted() -> None:
    assert removes_files("rm /workspace/README.md") is True


def test_removal_behind_a_separator_is_intercepted() -> None:
    """实测到的真实绕行写法：`rm` 藏在第二段里，只看整串第一个词是看不见的。"""
    assert removes_files('cd /workspace && rm -f README.md && echo "已删除"') is True


def test_removal_by_absolute_path_is_intercepted() -> None:
    assert removes_files("/bin/rm -rf /workspace/outputs") is True


def test_an_env_assignment_prefix_does_not_hide_the_removal() -> None:
    """`FOO=1 rm x` 的第一个词是赋值不是命令名，跳过它才看得见 `rm`。"""
    assert removes_files("PYTHONPATH=/workspace rm /workspace/a.csv") is True


def test_the_word_rm_inside_an_argument_is_not_intercepted() -> None:
    """`rm` 出现在参数位置上不是删除动作。拦它就是纯误伤。"""
    assert removes_files('echo "rm 只是个词"') is False
    assert removes_files("pip install rm-tool") is False


def test_a_file_named_like_the_command_is_not_intercepted() -> None:
    assert removes_files("python rm.py") is False


def test_the_other_removal_commands_are_intercepted() -> None:
    for command in ("rmdir /workspace/tmp", "unlink /workspace/a.csv", "shred /workspace/a.csv"):
        assert removes_files(command) is True, command


# ------------------------------------------------------------ 装配出来的配置
def test_the_predicate_reads_the_command_argument() -> None:
    predicate = when()
    assert callable(predicate)
    assert predicate(request("rm /workspace/a.csv")) is True
    assert predicate(request("python /workspace/analyze.py")) is False


def test_a_call_without_a_command_is_not_intercepted() -> None:
    """参数缺失或不是字符串时不拦：读不懂的调用交给框架自己去报错。"""
    predicate = when()
    broken = ToolCallRequest(
        tool_call=ToolCall(name=EXECUTE_TOOL, args={}, id="call-1"),
        tool=None,
        state={},
        runtime=cast(ToolRuntime[None, dict[str, object]], None),
    )
    assert callable(predicate)
    assert predicate(broken) is False


def test_delete_is_still_intercepted_without_a_predicate() -> None:
    """`delete` 低频高危，全量拦。写谓词只会给它多一条会错位的路。"""
    assert INTERRUPT_ON[DELETE_TOOL]["allowed_decisions"] == list(ALLOWED_DECISION)
    assert "when" not in INTERRUPT_ON[DELETE_TOOL]


def test_both_tools_offer_the_same_four_decisions() -> None:
    """四种决策是四条不同的恢复路径，少给一种前端就少一个按钮。"""
    for name in (DELETE_TOOL, EXECUTE_TOOL):
        assert INTERRUPT_ON[name]["allowed_decisions"] == list(ALLOWED_DECISION)


def test_nothing_else_is_intercepted() -> None:
    assert set(INTERRUPT_ON) == {DELETE_TOOL, EXECUTE_TOOL, QUESTION_TOOL}


def test_a_question_only_offers_a_reply() -> None:
    """**提问型中断与审批型不是一回事。**

    审批停下来是「这件事做不做」，提问停下来是「这句话你怎么说」。批准一个不执行的
    调用没有意义，改参数改的也只是「问什么」—— 因此只剩 `respond` 一条路。
    """
    assert INTERRUPT_ON[QUESTION_TOOL]["allowed_decisions"] == list(QUESTION_ALLOWED_DECISION)
    assert INTERRUPT_ON[QUESTION_TOOL]["allowed_decisions"] == ["respond"]
    assert "when" not in INTERRUPT_ON[QUESTION_TOOL]


# ---------------------------------------------- 真图：闸门到底响不响
async def test_a_real_graph_stops_on_an_execute_that_removes_files(tmp_path: Path) -> None:
    """**这条走的是真图，不是配置断言。**

    「配置里写着拦」与「跑起来真的停」是两件事：2026-08-18 那次红就红在后者 ——
    配置一个字没错，闸门却一次没响，因为模型根本没走被拦的那个工具。这里让模型
    确定地发一次 `execute` + `rm`，验中断真的落到了 checkpoint 上。
    """
    agent = Agent(model=ToolCallingModel(command="rm /workspace/probe.txt"), checkpointer=InMemorySaver())
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    async for _ in agent.stream(backend, "thread-execute", "删掉它"):
        pass
    actions = await agent.pending(backend, "thread-execute")

    assert [one.tool_name for one in actions] == [EXECUTE_TOOL]
    assert actions[0].args["command"] == "rm /workspace/probe.txt"
    assert actions[0].allowed_decisions == list(ALLOWED_DECISION)


async def test_a_real_graph_runs_a_harmless_execute_without_stopping(tmp_path: Path) -> None:
    """对照组。少了它，「一律拦 execute」也能让上面那条过 —— 而那样平台没法用。"""
    agent = Agent(model=ToolCallingModel(command="echo 你好"), checkpointer=InMemorySaver())
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    async for _ in agent.stream(backend, "thread-harmless", "跑一下"):
        pass

    assert await agent.pending(backend, "thread-harmless") == []


class QuestioningModel(BaseChatModel):
    """第一轮问教师一句，第二轮把收到的回答复述出来。

    第二轮的复述是这条用例的要害：它证明**教师那句话真的进了模型的上下文**，
    而不只是「没报错」。
    """

    question: str = "收益率按日频还是月频？"
    calls: int = 0
    heard: str = ""

    @property
    def _llm_type(self) -> str:
        return "questioning"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # noqa: ANN401 - 必须匹配 LangChain 抽象签名
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(self, *argument: Any, **keyword: Any) -> ChatResult:  # noqa: ANN401 - 基类参数繁杂
        self.calls += 1
        if self.calls > 1:
            messages = argument[0] if argument else keyword["messages"]
            answers = [one for one in messages if isinstance(one, ToolMessage) and one.name == QUESTION_TOOL]
            self.heard = str(answers[-1].content) if answers else ""
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=f"按{self.heard}算完了"))])
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": QUESTION_TOOL,
                    "args": {"question": self.question},
                    "id": "call-question",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


async def test_a_real_graph_stops_on_a_question(tmp_path: Path) -> None:
    """**这条走的是真图。** 「配置里写着拦」与「跑起来真的停」是两件事。"""
    agent = Agent(model=QuestioningModel(), checkpointer=InMemorySaver())
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    async for _ in agent.stream(backend, "thread-question", "算一下波动率"):
        pass
    actions = await agent.pending(backend, "thread-question")

    assert [one.tool_name for one in actions] == [QUESTION_TOOL]
    assert actions[0].args["question"] == "收益率按日频还是月频？"
    assert actions[0].allowed_decisions == ["respond"]


async def test_the_teachers_answer_reaches_the_model(tmp_path: Path) -> None:
    """P14① 的离线一半：教师的话作为工具结果回到上下文，run 从 checkpoint 接着跑。

    **验的是「口径带上了」而不是「没报错」** —— 后者在教师那句话被丢掉时同样会绿。
    """
    model = QuestioningModel()
    agent = Agent(model=model, checkpointer=InMemorySaver())
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    async for _ in agent.stream(backend, "thread-answer", "算一下波动率"):
        pass
    async for _ in agent.resume(backend, "thread-answer", [{"type": "respond", "message": "用月频"}]):
        pass

    assert model.heard == "用月频"
    assert await agent.pending(backend, "thread-answer") == []


async def test_a_reply_without_a_message_is_what_the_platform_must_never_forward(tmp_path: Path) -> None:
    """**这一条钉的是平台那道校验为什么必须存在。**

    库里 `_process_decision` 对 `respond` 直接取 `decision["message"]`。平台放行的话
    就炸在这里 —— 而这时决策早已 202、run 已经重投，教师看到的是一次 `INTERNAL`，
    错误信息一个字都不指向「少了一句话」。
    """
    agent = Agent(model=QuestioningModel(), checkpointer=InMemorySaver())
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    async for _ in agent.stream(backend, "thread-bare", "算一下波动率"):
        pass

    with pytest.raises(KeyError):
        async for _ in agent.resume(backend, "thread-bare", [{"type": "respond"}]):
            pass
