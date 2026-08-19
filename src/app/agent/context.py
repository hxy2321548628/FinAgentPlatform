"""上下文预算：什么时候把历史折成摘要、什么时候把大工具结果挪出去。

**为什么要有这个模块**：deepagents 的默认阈值是从模型 profile 推出来的 ——
`max_input_tokens=1000000` × `('fraction', 0.85)`，即 85 万 token 才压。
2026-08-19 实测：模型确实吃得下百万上下文（第一发就过），**profile 没骗人**；
但一次真实分析的消息历史峰值只有两万左右（首轮 10 题实测，最贵的一道 21k），
那条线因此永远够不着 —— **压缩机制装着，却从未生效过一次**。

**阈值改由平台显式定**，理由与[技术宪法](../../../.claude/python-constitution.md)第二条一致：
关键参数不能是从第三方 profile 里静默推出来的，一个从上游数据推出的阈值改变时不会有
任何提示，症状只是「今天怎么这么贵」。
"""

from typing import Any

from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel

# 消息历史达到这个规模就折成摘要。
#
# **取 4 万的依据**（2026-08-19 首轮评估实测）：十道题里九道的单轮历史在 2k–7k，
# 最贵的一道（把整段数据序列打印出来分析）到 21k。取实测峰值的约两倍 ——
# 长分析与多轮追问碰得到，寻常题碰不到。
#
# **它是个观察项**：跑几轮之后回看有多少题真的触发了。一次都不触发说明定高了，
# 每题都触发说明定低了（压缩本身要花一次摘要调用，还会丢细节）
CONTEXT_TRIGGER_TOKEN = 40_000

# 压的时候保留最近多少原文，按 trigger 的比例算。
#
# **两个坑都栽过（2026-08-19 实测）**：
#
# 1. **不显式给 keep 就等于不压**。`SummarizationMiddleware` 的类默认是
#    `("messages", 20)` —— 保留最近二十条消息，而一次分析的历史通常就十几条，
#    于是「没有任何东西可以折叠」，token 再多也不触发。deepagents 自己那个构造器用的
#    `("fraction", 0.10)` 是按模型上下文的一成算，一百万的一成同样够不着。
# 2. **keep 写成独立常量，验收时会自相矛盾**。把 trigger 调到 2000 去验「压缩真的触发得了」，
#    而 keep 还钉在 8000 —— 保留的比触发线还多，逻辑上永远不可能压。
#    按比例联动之后，调一个另一个跟着走
CONTEXT_KEEP_RATIO = 0.2
# 保留的下限。太小的话每压一次都几乎清空历史，agent 会反复丢失刚说过的话
CONTEXT_KEEP_FLOOR_TOKEN = 500


def create_squeezer(
    model: BaseChatModel,
    backend: BackendProtocol,
    *,
    trigger_token: int = CONTEXT_TRIGGER_TOKEN,
) -> AgentMiddleware:
    """造一份平台自己的压缩中间件。

    **名字与基础栈里那份一致是有意的**：deepagents 按 `.name` 合并自定义中间件，
    重名即原地替换。叫别的名字就成了叠加两套压缩 —— 两套都改写历史，谁先触发不确定，
    而且都会打掉前缀缓存。

    Args:
        model: 摘要用的模型，与主模型同一个。
        backend: 折起来的历史转存到哪里。
        trigger_token: 历史达到多少 token 就压。默认是平台常量，验收时会调到极小值；
            保留量按它的比例算，因此调小它不会造出「保留的比触发线还多」这种不可能的配置。

    Returns:
        可直接传进 `create_deep_agent(middleware=...)` 的中间件。
    """
    keep_token = max(int(trigger_token * CONTEXT_KEEP_RATIO), CONTEXT_KEEP_FLOOR_TOKEN)
    return SummarizationMiddleware(
        model,
        backend=backend,
        trigger=("tokens", trigger_token),
        keep=("tokens", keep_token),
        # **显式跟着 trigger 走**：不给的话这一项会落到类默认的 `None`（等于关掉），
        # 而 deepagents 那个构造器给的是按模型上下文比例算的值 —— 两者行为不同，
        # 而差异不报错，只是某些轮次的消息内容悄悄变了
        truncate_args_settings={"trigger": ("tokens", trigger_token), "keep": ("tokens", keep_token)},
    )


# 单次工具结果超过这个规模就挪到磁盘，模型只看到一句「存在哪儿了」。
#
# **取 4000 的依据**（2026-08-19 首轮评估实测，按未命中 token ÷ 工具调用次数粗估）：
# 十道题里九道每次工具输出在 312–701 token，最贵的一道（把 265 条异常记录逐行打印）
# 每次约 13856。**框架默认的 20000 正好卡在这两类中间** —— 两边都够不着，
# 于是那一万四每一轮都重新计费一遍，单题烧掉 12.5 万未命中 token、1.30 元，
# 是其余各题的 10–20 倍。取正常值上限的约六倍：拦得住异常，碰不着寻常题
TOOL_RESULT_EVICT_TOKEN = 4_000


def create_offloader(
    backend: BackendProtocol,
    *,
    evict_token: int = TOOL_RESULT_EVICT_TOKEN,
) -> AgentMiddleware[Any, Any, Any]:
    """造一份平台自己的文件系统中间件，只为把卸载阈值调下来。

    **名字与基础栈里那份一致是有意的**：deepagents 按 `.name` 合并自定义中间件，
    重名即原地替换。叫别的名字就成了装两套文件工具，同名工具会互相覆盖。

    **替换会丢掉基础栈传的两个参数，这里逐一确认过可以不传**：
    `custom_tool_descriptions` 取自模型 profile，而本平台用的 DeepSeek profile
    是空的（`tool_description_overrides == {}`）；`_permissions` 平台从不传，
    删文件的确认走的是 `interrupt_on`。**换模型或改用 permissions 时这两条要重看。**

    Args:
        backend: 文件工具落在哪个后端上。
        evict_token: 单次工具结果超过多少 token 就挪到磁盘。

    Returns:
        可直接传进 `create_deep_agent(middleware=...)` 的中间件。
    """
    return FilesystemMiddleware(backend=backend, tool_token_limit_before_evict=evict_token)
