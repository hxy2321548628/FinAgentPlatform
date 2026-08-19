"""哪些工具调用要停下来等教师确认。

**主图与子图共用这一份配置。** 两处各写一份的代价 2026-08-18 的验收上见过：
子智能体绕过审批的路子与主图一模一样，漏改一处就漏掉一整条路。

**这道闸管的是「教师知不知情」，不是「删得掉删不掉」。** 沙箱本来就把破坏面圈在
本会话自己的工作目录里，容器一销毁全没了；闸门存在的意义是别让 agent 悄悄删掉
教师上传的原始数据。因此谓词只认最直白的那条路，`python -c "os.remove(...)"`、
`find -delete`、`sh -c "rm x"` 一律绕得过去 —— 那是这道闸的边界，不是缺陷。
"""

import re
from pathlib import PurePosixPath
from types import MappingProxyType

from langchain.agents.middleware.human_in_the_loop import DecisionType, InterruptOnConfig
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.agent.question import QUESTION_ALLOWED_DECISION, QUESTION_TOOL

DELETE_TOOL = "delete"
EXECUTE_TOOL = "execute"

# `execute` 的入参名。改了它谓词会静默失效 —— 读不到命令串就一律不拦
COMMAND_ARG = "command"

ALLOWED_DECISION: tuple[DecisionType, ...] = ("approve", "reject", "edit", "respond")

# 出现在命令名位置上就是在删文件
REMOVAL_COMMAND = frozenset({"rm", "rmdir", "unlink", "shred"})

# shell 里把一条命令接到另一条后面的写法。实测 agent 写的是
# `cd /workspace && rm -f README.md`，只看整串第一个词看不见那个 rm
SEPARATOR = re.compile(r"[;&|\n()`]+")

# `FOO=1 rm x` 里的赋值前缀不是命令名，跳过它才轮得到真正的命令名
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def removes_files(command: str) -> bool:
    """这条 shell 命令里有没有直接的删除动作。

    **只看命令名位置**，不做完整 shell 解析：`echo "rm 只是个词"` 不算，
    `cd /workspace && /bin/rm -f a.csv` 算。

    Args:
        command: 交给沙箱里 sh 的完整命令串。

    Returns:
        命令名位置上出现了删除命令则为真。
    """
    return any(_is_removal(segment) for segment in SEPARATOR.split(command))


def _is_removal(segment: str) -> bool:
    for token in segment.split():
        if ASSIGNMENT.match(token):
            continue
        return PurePosixPath(token.strip("'\"")).name in REMOVAL_COMMAND
    return False


def _when_removing(request: ToolCallRequest) -> bool:
    """`execute` 的条件拦截谓词。

    **必须是这次工具调用的纯函数。** 多个中断靠位置索引匹配 resume 值，掺进外部
    状态或时间的谓词会在重放时错位 —— 而错位是静默的：把 A 的决策套到 B 的调用上。
    这里只读 args 里那一个字符串，重放多少次都是同一个答案。
    """
    command = request.tool_call["args"].get(COMMAND_ARG)
    return isinstance(command, str) and removes_files(command)


# **`delete` 全量拦，`execute` 条件拦。**
#
# `delete` 低频高危：P0 实测一次完整分析 16 次工具调用里它一次都没出现过，全量拦
# 不伤可用性。`execute` 反过来 —— 全量拦要教师一次分析点十几次确认，平台会没法用，
# 因此只在命令名位置出现删除命令时才停。
#
# 条件拦截 2026-08-08 定过一次「推后」，2026-08-18 推翻：那次定案假设不拦 `execute`
# 只是少拦一点，而验收照出的是**闸门整个被绕过** —— 同一句提问，模型换用
# `execute` 跑 `rm` 就一次都不停（P3① 四种决策、P9⑤ 嵌套审批，五条断言全红）。
#
# **`ask_user_question` 与这两个不是一回事。** 那两个停下来是「教师，这件事我做不做」，
# 它停下来是「教师，这句话你怎么说」—— 平台侧走的是同一条挂起路径（不占队列、不占沙箱、
# 24 小时超时），但决策只允许 `respond`：批准一个不执行的调用没有意义。
# **前端按 `tool_name` 分流**，不加 `kind` 字段：工具名就是那个客观事实。
INTERRUPT_ON: MappingProxyType[str, InterruptOnConfig] = MappingProxyType(
    {
        DELETE_TOOL: InterruptOnConfig(allowed_decisions=list(ALLOWED_DECISION)),
        EXECUTE_TOOL: InterruptOnConfig(allowed_decisions=list(ALLOWED_DECISION), when=_when_removing),
        QUESTION_TOOL: InterruptOnConfig(allowed_decisions=list(QUESTION_ALLOWED_DECISION)),
    }
)
