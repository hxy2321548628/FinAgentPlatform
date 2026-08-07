"""档位的测试：按角色分级，允许逐个用户覆盖。"""

from quota.policy import (
    DEFAULT_CONCURRENT_RUN,
    DEFAULT_RATE_LIMIT,
    DEFAULT_TOKEN_DAILY,
    QuotaPolicy,
)
from user.model import UserRole


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

    assert student.token_daily < teacher.token_daily
    assert student.concurrent_run <= teacher.concurrent_run


def test_every_role_has_a_tier() -> None:
    """漏一个角色的话，那个角色的人一提交就 KeyError —— 500 而不是 429。"""
    policy = QuotaPolicy()

    for role in UserRole:
        assert policy.allow(role=role, token_daily=None, concurrent_run=None).token_daily > 0


def test_the_concurrency_tier_stays_below_the_sandbox_pool() -> None:
    """这道闸拦的就是「单个用户占满整个沙箱池」，它必须明显小于池容量（架构 §8.1 建议 20）。"""
    from sandbox.pool import DEFAULT_MAX_CONTAINER

    for limit in DEFAULT_CONCURRENT_RUN.values():
        assert limit < DEFAULT_MAX_CONTAINER


def test_the_rate_limit_is_far_above_human_speed() -> None:
    """这道闸误伤的是正常用户，因此宁松勿紧 —— 每秒至少放行一次。"""
    assert DEFAULT_RATE_LIMIT >= 60
