"""隔离必须做在数据访问层，而「做在数据访问层」这件事本身要有一条测试盯着。

架构原话是**「不要指望每个接口都记得加 where 条件」**。这个文件就是那句话的可执行版本：
只要仓储层不提供「不带 user 也能查」的入口，端点里那种遗漏就写不出来。

**没有这条测试，半年后新加的一个查询方法就会绕过隔离** —— 而绕过去了不报错，
只是别人的数据开始出现在响应里。
"""

import inspect

from run.repository import RunRepository
from thread.repository import ThreadRepository

# 归当前用户所有的那几张表的仓储。**新加一个要往这里补一行** ——
# 漏了它，这条测试就管不到那一层
OWNED_REPOSITORY = (RunRepository, ThreadRepository)

USER_CONTEXT = "user_id"

# 不服务任何用户请求、因此确实不需要 user 上下文的方法。
# **每加一个都要在这里写清理由**：这份清单就是「隔离在数据层」这条规矩的例外总账，
# 空着最好，长了就该警觉
SYSTEM_METHOD = {
    # 崩溃恢复扫的是「此刻还没跑完的 run」，与谁提交的无关。调用方是 worker 的启动
    # 路径，那里根本没有登录用户
    (RunRepository, "unfinished"),
    # 状态流转，由 worker 在已经领到任务之后调用 —— 授权发生在提交那一刻，
    # 而 run 是按 id 精确定位的，不存在「扫出别人的行」这回事
    (RunRepository, "start"),
    (RunRepository, "succeed"),
    (RunRepository, "fail"),
    # 同上，取消也是一次按 id 精确定位的状态流转。它有两个调用方：worker 在 step
    # 边界上发现标志时，以及取消端点 —— 而那个端点在调它之前已经用带 user 的查询
    # 确认过归属，查不到就是 404，走不到这一步
    (RunRepository, "cancel"),
    # 同上，两者都是按 id 精确定位的状态流转：`wait_approval` 由 worker 在发现中断时调，
    # `resume` 由审批端点调 —— 而那个端点在此之前已经用带 user 的查询确认过归属
    (RunRepository, "wait_approval"),
    (RunRepository, "resume"),
}


def _public_method(repository: type) -> list[tuple[str, inspect.Signature]]:
    return [
        (name, inspect.signature(member))
        for name, member in inspect.getmembers(repository, inspect.isfunction)
        if not name.startswith("_")
    ]


def test_every_public_repository_method_takes_a_user_context() -> None:
    missing = [
        f"{repository.__name__}.{name}"
        for repository in OWNED_REPOSITORY
        for name, signature in _public_method(repository)
        if (repository, name) not in SYSTEM_METHOD and USER_CONTEXT not in signature.parameters
    ]

    assert missing == [], f"这些方法不带 user 上下文就能调，隔离在它们身上是漏的：{missing}"


def test_the_user_context_cannot_be_left_out_by_accident() -> None:
    """`user_id` 必须是**必填的关键字参数**。

    给个默认值等于「忘了传就查全库」，而位置参数迟早会与别的 id 传反 ——
    两种写法都能编译、能跑、不报错。
    """
    sloppy = [
        f"{repository.__name__}.{name}"
        for repository in OWNED_REPOSITORY
        for name, signature in _public_method(repository)
        if USER_CONTEXT in signature.parameters
        and (
            signature.parameters[USER_CONTEXT].kind is not inspect.Parameter.KEYWORD_ONLY
            or signature.parameters[USER_CONTEXT].default is not inspect.Parameter.empty
        )
    ]

    assert sloppy == [], f"这些方法的 user 上下文可以被漏掉或传反：{sloppy}"


def test_the_exception_list_only_names_methods_that_exist() -> None:
    """例外清单会随着方法改名而失效，而失效的方式是静默的 —— 那一层又变回没人管。"""
    for repository, name in SYSTEM_METHOD:
        assert hasattr(repository, name), f"{repository.__name__}.{name} 已经不存在了，例外清单该更新"
