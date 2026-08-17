"""会话标题：首次提问之后的一次轻量模型调用。

**不让教师先给会话起名。** 那是一道横在「我想问个问题」前面的门槛，而多数人会跳过它 ——
于是侧边栏变成一排「未命名」，等于没有列表。

**这一次调用不能挡住提交。** 提交那条路要在几十毫秒内返回 202，模型往返却要一两秒；
因此它挂在响应之后跑，起不出来就留空，绝不影响任何一次分析。也正因为如此，
这里的每一条失败路径都只记日志 —— 抛出去只会让一个后台任务无声无息地死掉。

**走辅助模型而不是主模型**：概括一句话不需要多步推理能力，而主模型贵一个数量级。
这一次的 token 不计入教师的配额，也不进成本看板 —— 它不属于任何一个 run，
而输入几十、输出十几个 token，相对一次分析的几万是千分之几。
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.app.thread.repository import ThreadRepository

logger = logging.getLogger(__name__)

# 标题最长几个字。侧边栏一行放得下才有意义，超出的部分只会被省略号吃掉。
# 模型不一定听话，因此这个数既写进提示词也当作硬截断
MAX_TITLE_LENGTH = 20

# 一次调用最多等多久，秒。**这是唯一的止损手段** —— 见 `_ask` 里为什么不设 token 上限。
#
# **给得宽是有理由的。** 起标题挂在响应之后，教师一秒都不会等它；掐紧了反而更贵：
# 15 秒实测会在真实长度的提问上把第一次调用掐掉，客户端接着重试一次，
# 于是总耗时 18 秒还白花一份 token。推理模型的耗时随提问长度走，一分钟是留够的余量
TIMEOUT_SECOND = 60.0

PROMPT = (
    f"你是一个会话标题生成器。用不超过 {MAX_TITLE_LENGTH} 个汉字概括用户这次数据分析请求的主题，"
    "作为会话列表里的标题。只输出标题本身：不要引号、不要句号、不要任何解释。"
)

# 模型爱给标题套引号，各种都见过
STRIPPED = "\"'“”‘’《》「」 \t\n"

# 收拾不出标题时往日志里带多少原始回答。够看出「模型到底说了什么」，又不至于刷屏
RAW_ANSWER_LOG_LENGTH = 200


class TitleWriter:
    """给会话起标题。

    Args:
        model: 辅助模型。
        repository: 会话仓储，标题写回它。
        max_length: 标题的硬截断长度。
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        repository: ThreadRepository,
        max_length: int = MAX_TITLE_LENGTH,
    ) -> None:
        self._model = model
        self._repository = repository
        self._max_length = max_length

    async def compose(self, thread_id: str, *, user_id: str, content: str) -> None:
        """按教师的问题给会话起个标题并写回去。

        **写之前再查一次标题还空不空。** 调用方在提交那一刻查过一次（那是为了不白花
        这次调用），但模型往返的这一两秒里教师可能已经自己改了名 —— 拿生成的结果盖掉
        人手填的标题，是那种「我明明改过」的故障。

        起不出来就什么都不做：会话留着空标题，前端回落到时间显示。

        Args:
            thread_id: 会话标识。
            user_id: 会话的主人。查不到（或不是他的）就什么都不做。
            content: 教师的问题。
        """
        thread = await self._repository.get(thread_id, user_id=user_id)
        if thread is None or thread.title:
            return

        title = await self._ask(content)
        if not title:
            return
        await self._repository.update(thread_id, user_id=user_id, title=title)
        logger.info("会话标题已生成：thread_id=%s title=%r", thread_id, title)

    async def _ask(self, content: str) -> str:
        """问一次模型，拿到收拾干净的标题；出岔子就是空串。

        **不给 `max_tokens`。** 辅助模型是个推理模型，而那个参数掐的是「推理 + 输出」
        的总和 —— 推理不会因为预算见底就收尾，于是掐出来的结果是它把额度全花在推理上、
        `content` 一个字都不剩。实测 48 / 256 / 512 / 1024 全部如此，而**每一次都是
        HTTP 200**：调用成功、日志全绿、标题恒为空。止损因此交给 `TIMEOUT_SECOND`
        与 `_tidy` 的硬截断，它们管的是「等多久」与「留多长」，不掺进模型的推理预算。
        """
        try:
            answer = await self._model.ainvoke(
                [SystemMessage(content=PROMPT), HumanMessage(content=content)],
                timeout=TIMEOUT_SECOND,
            )
        # 模型那一侧什么都可能出事：断连、超时、限流、凭据过期。宽捕获是刻意的 ——
        # 一个起不出来的标题不该让任何东西失败，而让异常逃出后台任务只会让它静默死掉
        except Exception:
            logger.warning("会话标题没生成出来，留空", exc_info=True)
            return ""

        title = _tidy(answer.text, self._max_length)
        if not title:
            # **这一条不能省。** 「调用成功但收拾出来是空的」是上面那个 max_tokens 坑的
            # 全部症状 —— 没有它，故障现场就只剩一个空标题和一条 200 的访问日志
            logger.warning("模型答了但收拾不出标题，留空：原始回答=%r", answer.text[:RAW_ANSWER_LOG_LENGTH])
        return title


def _tidy(raw: str, max_length: int) -> str:
    """把模型的回答收拾成一个标题。

    Args:
        raw: 模型原样的输出。
        max_length: 硬截断长度。

    Returns:
        单行、去掉包裹符号、不超长的标题；没内容则空串。
    """
    # 多行时只取第一行：模型偶尔会先给标题再补一句解释，而那一句会挤满整个侧边栏
    first = raw.strip().splitlines()[0] if raw.strip() else ""
    return first.strip(STRIPPED)[:max_length]
