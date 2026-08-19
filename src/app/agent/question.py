"""agent 向教师提问的工具。

**它不执行任何东西。** 真正的实现是教师那句回答：调用被 `INTERRUPT_ON` 拦下来，
run 转 `waiting_approval`，教师给的话作为 `status="success"` 的工具结果回到模型
上下文里。因此这里只需要一个签名与一份工具描述 —— 函数体永远走不到。

**复用的是一条已经验收过的路**（HITL），不是新造的挂起机制：挂起期间既不占队列
消息也不占沙箱，24 小时不回答由 cron 转 `cancelled`，与审批同一套口径。
代价写在 P14 计划 §7 第 1 条：一个等回答的 run 会占掉教师那 5 个待审批名额，
而被挡下来时的报错只说「待审批太多」，不提其中几个是 agent 在问话。

**工具描述的重点是「什么时候不该问」。** 一次提问就是一次打断，每题都停下来问一句
的 agent 教师用两次就不想再用了 —— 这份描述里的硬话是平台唯一能拦住它的地方。
"""

from langchain.agents.middleware.human_in_the_loop import DecisionType
from langchain_core.tools import BaseTool, tool

QUESTION_TOOL = "ask_user_question"

# 只允许 `respond`：这个工具没有别的执行路径，approve 一个不执行的调用毫无意义，
# 而 edit 改的是「问什么」，改完还是要人回答。**它是平台第一个只允许 respond 的工具**
QUESTION_ALLOWED_DECISION: tuple[DecisionType, ...] = ("respond",)

# 函数体走不到时的返回值。留一句可读的，是为了万一有人把这个工具装到没有 HITL 的图上时
# 模型能看懂发生了什么 —— 那种情况下它至少不会以为自己得到了回答
UNANSWERED = "这个提问没有送到教师那里，没有得到回答。请自己选一个合理的口径继续，并在答复里说明你选了什么。"

QUESTION_TOOL_DESCRIPTION = """向教师提一个问题，然后停下来等他回答。

**每调用一次，教师就被打断一次。** 只在「缺了这个答案就没法往下做，而且你自己定不了」
的时候才问。能从数据里看出来的、有公认默认口径的、试一下就知道的，一律自己决定，
并在最终答复里说明你选了什么。

该问的情况：
- 教师的要求有两种以上互不相容的理解，选错了整个分析都白做（例如「收益率」是日频还是月频、
  「前十大」按市值还是按成交额）
- 要用的数据在工作目录里找不到，也判断不出他指的是哪个文件
- 教师给的口径与数据本身矛盾，按哪一个做结论都不一样

不该问的情况：
- 只是想确认自己的想法对不对 —— 直接做，把口径写进答复
- 参数有公认默认值（无风险利率、年化天数、缺失值怎么处理）—— 用默认值并说明
- 删文件、跑命令这类要教师点头的操作 —— 平台自己会拦下来问，你直接调那个工具就行

问题用中文写，一次只问一个，问得具体到教师一句话能答完，不要贴代码。"""


def create_question_tool() -> BaseTool:
    """造一个提问工具。

    **每次装配现造一个**，不做成模块级单例 —— 工具对象会被绑进图，
    共享一个可变对象是平台明令禁止的那类全局状态。

    Returns:
        可直接放进 `tools` 列表的工具。
    """

    @tool(QUESTION_TOOL, description=QUESTION_TOOL_DESCRIPTION)
    def ask_user_question(question: str) -> str:
        """停下来问教师一个问题。"""
        return UNANSWERED

    return ask_user_question
