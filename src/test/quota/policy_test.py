"""档位的测试：按角色分级，允许逐个用户覆盖。"""

from src.app.quota.policy import (
    DEFAULT_CONCURRENT_RUN,
    DEFAULT_RATE_LIMIT,
    DEFAULT_TOKEN_DAILY,
    QuotaPolicy,
)
from src.app.user.model import UserRole


def test_a_user_without_an_override_follows_the_role() -> None:
    allowance = QuotaPolicy().allow(role=UserRole.STUDENT, token_daily=None, concurrent_run=None)

    assert allowance.token_daily == DEFAULT_TOKEN_DAILY[UserRole.STUDENT]
    assert allowance.concurrent_run == DEFAULT_CONCURRENT_RUN[UserRole.STUDENT]


def test_an_override_wins_over_the_role() -> None:
    """管理员将来要能单独调某个人的配额，那条路必须现在就是通的。"""
    allowance = QuotaPolicy().allow(role=UserRole.STUDENT, token_daily=42, concurrent_run=7)

    assert allowance.token_daily == 42
    assert allowance.concurrent_run == 7


def test_zero_is_an_override_not_an_absence() -> None:
    """把某个人的配额调成 0 是「禁用」，不能被当成「没设过，跟角色走」。"""
    allowance = QuotaPolicy().allow(role=UserRole.TEACHER, token_daily=0, concurrent_run=0)

    assert allowance.token_daily == 0
    assert allowance.concurrent_run == 0


def test_students_get_less_than_teachers() -> None:
    """学生的档位必须低于教师。

    两个角色权限完全相同，**配额是它们唯一的实质差别** —— 学生人数远多于教师，
    档位若相同，成本结构就由学生侧主导。这条不验具体数值，只验分级还在。
    """
    policy = QuotaPolicy()

    student = policy.allow(role=UserRole.STUDENT, token_daily=None, concurrent_run=None)
    teacher = policy.allow(role=UserRole.TEACHER, token_daily=None, concurrent_run=None)

    assert student.token_daily is not None
    assert teacher.token_daily is not None
    assert student.token_daily < teacher.token_daily
    assert student.concurrent_run <= teacher.concurrent_run


def test_every_role_has_a_tier() -> None:
    """漏一个角色的话，那个角色的人一提交就 KeyError —— 500 而不是 429。

    **`None` 是查得到的答案（不限），不是查不到。** 这条要能把两者分开，
    否则「漏了一个角色」会伪装成「那个角色不限」，而那是 fail-open。
    """
    policy = QuotaPolicy()

    for role in UserRole:
        allowance = policy.allow(role=role, token_daily=None, concurrent_run=None)
        assert allowance.token_daily is None or allowance.token_daily > 0
        assert allowance.concurrent_run > 0


def test_only_the_admin_tier_is_unlimited() -> None:
    """**成本闸门只剩教师与学生两档，别的角色不许悄悄跟着松掉。**

    `reviewer` 特别容易被顺手划到 admin 那一边 —— 它多的只是审平台目录的能力，
    跑分析时就是个普通老师。
    """
    policy = QuotaPolicy()

    unlimited = {
        role for role in UserRole if policy.allow(role=role, token_daily=None, concurrent_run=None).token_daily is None
    }

    assert unlimited == {UserRole.ADMIN}


def test_an_override_can_only_tighten_an_unlimited_tier() -> None:
    """管理员要把某个人（包括另一个管理员）按住时，那条路必须是通的。"""
    allowance = QuotaPolicy().allow(role=UserRole.ADMIN, token_daily=1000, concurrent_run=None)

    assert allowance.token_daily == 1000


def test_the_concurrency_tier_stays_below_the_sandbox_pool() -> None:
    """这道闸拦的就是「单个用户占满整个沙箱池」，它必须明显小于池容量（架构 §8.1 建议 20）。"""
    from src.app.sandbox.pool import DEFAULT_MAX_CONTAINER

    for limit in DEFAULT_CONCURRENT_RUN.values():
        assert limit < DEFAULT_MAX_CONTAINER


def test_the_rate_limit_is_far_above_human_speed() -> None:
    """这道闸误伤的是正常用户，因此宁松勿紧 —— 每秒至少放行一次。"""
    assert DEFAULT_RATE_LIMIT >= 60
