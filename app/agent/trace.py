"""把一次分析送进 Langfuse。

**Langfuse 是外部服务，不由本项目编排**（2026-08-13 定案）。因此这里只做两件事：
按配置造一个回调处理器，以及把「这一次是谁在跑」翻译成它认的那几个 metadata 键。

**回调挂在图上而不是挂在模型上。** 挂模型只能看到「调了几次 LLM」；挂图能看到节点、
工具调用与中断，而 agent 出问题的地方绝大多数在工具那一段，不在模型那一段。

**没配就返回 None，不是返回一个空实现。** 空实现会让「配错了」与「故意没配」长得一样，
而这两件事的处置完全相反。调用方据此决定挂不挂，日志里说得出是哪一种。

> **这条路上会送出会话全文。** 教师的提问、上传数据的内容、模型的答复都在 trace 里 ——
> 这是 2026-08-13 主动接受的一次边界变更（原 §6.3 是「管理员看得到用量、看不到会话内容」）。
> 谁能打开 Langfuse，谁就看得见全部会话内容。
"""

import logging

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from config import Settings

logger = logging.getLogger(__name__)

# Langfuse 认的 metadata 键。**名字由它的 langchain 集成写死**，不是我们能取的
USER_KEY = "langfuse_user_id"
SESSION_KEY = "langfuse_session_id"


def create_callback(settings: Settings) -> BaseCallbackHandler | None:
    """按配置造一个 Langfuse 回调，没配全就返回 None。

    Args:
        settings: 平台配置。

    Returns:
        可挂到图上的处理器；地址、public key、secret key 任缺其一则 None。
    """
    secret = settings.langfuse_secret_key.get_secret_value()
    if not (settings.langfuse_host and settings.langfuse_public_key and secret):
        logger.info("Langfuse 未配置齐全，本进程不上报追踪")
        return None
    # **构造客户端这一步不能省**：回调自己不持有配置，它按 public key 去取全局客户端。
    # 少了这一步，回调会去读进程环境变量 —— 那正是本项目禁止的读配置方式
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=secret,
        host=settings.langfuse_host,
    )
    logger.info("Langfuse 追踪已开启：host=%s", settings.langfuse_host)
    return CallbackHandler()


def attribution(*, thread_id: str, user_id: str | None) -> dict[str, str]:
    """把身份翻译成 Langfuse 认的 metadata。

    **会话对它是 session，用户对它是 user** —— 对上这两个键，它那边才答得出
    「谁花了多少」与「这一个会话里发生了什么」；对不上就只剩一堆孤立的 trace。

    Args:
        thread_id: 会话标识。
        user_id: 提交的人。**匿名时不写这个键**，写空串会在它那边多出一个叫「」的用户。

    Returns:
        可直接并进 LangGraph config 的 metadata。
    """
    metadata = {SESSION_KEY: thread_id}
    if user_id:
        metadata[USER_KEY] = user_id
    return metadata
