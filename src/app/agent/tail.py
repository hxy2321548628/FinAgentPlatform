"""在上下文末尾注入一块动态元信息。

**为什么在末尾而不是系统提示词里**：前缀里放每轮都变的内容，等于每轮打掉整段
prompt cache —— 按平台的价签，input 命中与不命中差 30 倍。代价是模型对它的注意力
弱于系统提示词，因此措辞要更硬。

**为什么是一个块而不是三个中间件**：用户信息、system-reminder、状态栏是同一个机制的
三类内容 —— 都落在末尾、都每轮变、都抢同一份注意力预算。分成三个的话，位置与预算要各处理
三遍，且先后顺序由注册顺序隐式决定，改一处会静默挪动另外两处。

**块要写回 state（2026-08-19 改，此前是反的）**。放在末尾**并不足以**保住缓存 ——
块若只作用于当次调用、不写回 state，下一轮那一格就换成了真实历史：服务端缓存里是块、
请求里是回复，**从这里分叉，其后全部重算**。首轮实测每轮多付 200–320 个未命中 token。

因此改为只追加、不修改：块进 state，下一轮的请求是这一轮的严格扩展。代价是陈旧状态
会累积，缓解办法是**内容没变就不再追加**（见 `_last_block`）—— 这既省 token，
也少给模型几条自相矛盾的旧读数。
"""

import logging
import re
from collections.abc import Sequence
from typing import Protocol

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

logger = logging.getLogger(__name__)

# 整块的字符预算。**宁可截断也不挤掉对话** —— 尾部块是辅助信息，
# 而被它挤出去的是教师真正问的东西。上限的由来见 P13 计划 §7 第 1 条
TAIL_BUDGET_CHAR = 1200
SECTION_SEPARATOR = "\n"
BLOCK_HEADER = "<system-reminder>"
BLOCK_FOOTER = "</system-reminder>"

# 装包的痕迹。与评估侧 metric.py 用的是同一组标记，改一处要想着另一处
INSTALL_MARKER = ("pip install", "pip3 install", "uv pip install")
# `pip install -q pandas scipy==1.11` 里要的是 pandas 与 scipy：跳过选项，留包名
INSTALL_ARGUMENT_PATTERN = re.compile(r"install\s+((?:(?!-)[\w\-\[\]=<>.!]+\s*)+)")


class TailSection(Protocol):
    """尾部块里的一节。返回空串表示这一轮没什么可说的。"""

    @property
    def title(self) -> str:
        """这一节的标题，出现在块里。"""

    @property
    def policy(self) -> str:
        """拿这个读数该怎么办。空串表示这一节的规则显而易见，不必多说。

        **光给读数不够**：书里在六个模型上量过，只给原始读数与什么都不给相差
        不过两三个百分点，补上一句「该怎么用」才把通过率拉高十几到四十几个点。
        计数器那类「到顶了就停」的规则模型自己推得出来，而「力气该花多少」推不出来。
        """

    def render(self, request: ModelRequest) -> str:
        """按当前这次模型调用渲染本节内容。"""


class TailContextMiddleware(AgentMiddleware):
    """把若干节动态信息拼成一块，附在最后一条消息之后。

    Args:
        sections: 要注入的各节，按给定顺序排列。
        budget_char: 整块的字符上限，超出即从后往前丢节。
    """

    def __init__(self, *, sections: Sequence[TailSection], budget_char: int = TAIL_BUDGET_CHAR) -> None:
        super().__init__()
        self._sections = tuple(sections)
        self._budget = budget_char

    @property
    def name(self) -> str:
        """独立的名字：它不替换任何核心中间件，只是多出来的一个。"""
        return "TailContext"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: object,
    ) -> ModelResponse:
        """在这一次调用的消息末尾追加状态块，并把它留在轨迹里。"""
        block = self.render_block(request)
        if not block or block == self._last_block(request):
            return handler(request)  # type: ignore[operator, no-any-return]
        response: ModelResponse = handler(request.override(messages=self._appended(request, block)))  # type: ignore[operator]
        return self._persisted(response, block)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: object,
    ) -> ModelResponse:
        """异步路径，与同步那支做同一件事。

        **两支都要有**：平台一路走 `astream`，只实现同步那支的话单测全绿、
        真图一跑就抛 NotImplementedError。
        """
        block = self.render_block(request)
        if not block or block == self._last_block(request):
            return await handler(request)  # type: ignore[operator, no-any-return]
        response: ModelResponse = await handler(  # type: ignore[operator]
            request.override(messages=self._appended(request, block))
        )
        return self._persisted(response, block)

    def _appended(self, request: ModelRequest, block: str) -> list[AnyMessage]:
        """把块接在最后一条消息之后，作为这一次调用的输入。"""
        return [*request.messages, HumanMessage(content=block)]

    def _persisted(self, response: ModelResponse, block: str) -> ModelResponse:
        """把块写进 state，排在模型这一轮的回复之前。

        **顺序不能反**：块是模型看到的输入，回复是它的输出，写反了下一轮读起来
        就成了「先答后问」。写回去之后，下一轮的请求才是这一轮的严格扩展。
        """
        response.result = [HumanMessage(content=block), *response.result]
        return response

    def _last_block(self, request: ModelRequest) -> str | None:
        """轨迹里最后一个状态块的原文，没有则 None。

        用途是判重：状态没变就不必再说一遍。持久追加的代价就是陈旧状态累积，
        少追加一条是一条。
        """
        for message in reversed(list(request.messages)):
            if isinstance(message, HumanMessage) and str(message.content).startswith(BLOCK_HEADER):
                return str(message.content)
        return None

    def render_block(self, request: ModelRequest) -> str:
        """拼出这一轮的块；没有任何一节有内容时返回空串。

        **超预算时从后往前丢整节，不切半句** —— 半截的状态信息比没有更糟，
        模型会把截断处当成事实。
        """
        history = "".join(
            str(one.content)
            for one in request.messages
            if isinstance(one, HumanMessage) and str(one.content).startswith(BLOCK_HEADER)
        )
        rendered: list[str] = []
        for section in self._sections:
            try:
                body = section.render(request).strip()
                policy = section.policy.strip()
            except Exception:
                # 一节坏掉不该让整次分析失败：状态信息是辅助的，对话本身不是
                logger.warning("尾部块的某一节渲染失败，已跳过：%s", section.title, exc_info=True)
                continue
            if not body:
                continue
            # **策略只说一次**：它是不变的那一半，而读数每轮都变。说过的那条块还留在
            # 轨迹里（持久追加），模型仍看得到 —— 每轮重复一遍纯属白付 token
            if policy and policy not in history:
                body = f"{body}。{policy}"
            rendered.append(f"{section.title}：{body}")

        while rendered and len(SECTION_SEPARATOR.join(rendered)) > self._budget:
            dropped = rendered.pop()
            logger.info("尾部块超出 %d 字符预算，丢掉一节：%s", self._budget, dropped[:20])
        if not rendered:
            return ""
        return SECTION_SEPARATOR.join((BLOCK_HEADER, *rendered, BLOCK_FOOTER))


class StepBudgetSection:
    """已用步数 / 上限。

    **平台有三道静默的闸**，agent 撞上去之前拿不到任何信号，这是其中一道：
    撞上 `recursion_limit` 就直接断，而它事先完全不知道自己走到哪儿了。

    Args:
        limit: 平台配的图上步数上限。
    """

    def __init__(self, *, limit: int) -> None:
        self._limit = limit

    @property
    def title(self) -> str:
        """本节标题。"""
        return "步数"

    @property
    def policy(self) -> str:
        """读数配套的操作策略。

        **「快到上限了」推不出「该做什么」** —— 这正是书里说规则不显然的那一类，
        所以要把动作写明白：先落盘再继续，到尾声直接交付而不是停在半路。
        """
        return (
            "过半之后不要再起新的探索分支，先把已有结果写进 outputs/；剩三轮以内直接给结论，宁可少一张图也不要停在半路"
        )

    def render(self, request: ModelRequest) -> str:
        """报出已用轮数与上限。

        **每一轮都报（2026-08-19 改回来）**：此前设过「走过半程才开口」的闸门，
        依据是「块每轮都变会打掉缓存」—— 那个依据成立，但处置错了，真正的解法是
        把块写回轨迹（见模块 docstring），不是闭嘴。闸门还有个副作用：它按上限的
        一半算，60 步要跑到 15 轮才开口，而多数分析总共才 6–11 轮，等于从不开口。

        **步数是估算**：图上的一步不等于一轮模型调用（工具节点也算步），
        实测一次分析约 17 轮模型调用对应 34 步左右。
        """
        used = sum(1 for message in request.messages if isinstance(message, AIMessage))
        budget_turn = max(self._limit // 2, 1)
        return f"已用约 {used} 轮模型调用，上限 {self._limit} 步（约合 {budget_turn} 轮）"


class InstalledPackageSection:
    """本会话已经装过哪些包。

    P12 之后「装完当前会话一直在」，但 agent 记不住 —— 没有这一节它会把同一个包
    重复装一遍，每次都是几十秒和一次白烧的工具调用。
    """

    @property
    def title(self) -> str:
        """本节标题。"""
        return "已装的包"

    @property
    def policy(self) -> str:
        """规则本身够显然（「装过就别再装」），但代价不显然，所以点一句。"""
        return "这些直接 import，不要重装 —— 重装一次要几十秒且没有任何效果"

    def render(self, request: ModelRequest) -> str:
        """从历史的工具调用里扫出装过的包名。"""
        found: list[str] = []
        for message in request.messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                found.extend(_installed_from(str(call.get("args", ""))))
        unique = list(dict.fromkeys(found))
        return "、".join(unique) if unique else ""


def _installed_from(command: str) -> list[str]:
    """从一条命令里取出被安装的包名，取不到就返回空。"""
    if not any(marker in command for marker in INSTALL_MARKER):
        return []
    return [_bare_name(one) for one in INSTALL_ARGUMENT_PATTERN.findall(command)]


def _bare_name(argument: str) -> str:
    """去掉版本约束与 extras，只留包名。"""
    return re.split(r"[=<>!\[]", argument, maxsplit=1)[0].strip()
