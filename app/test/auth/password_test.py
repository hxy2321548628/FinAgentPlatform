"""口令哈希的测试。

**参数用最低档**：默认档一次 64 MiB、几十毫秒，而这里要算十几次。
档位本身另有一条用例盯着，不靠这些用例保证。
"""

import pytest

from auth.password import MEMORY_COST, PARALLELISM, TIME_COST, PasswordHasher

PASSWORD = "口令-correct"


@pytest.fixture
def hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def test_the_right_password_verifies(hasher: PasswordHasher) -> None:
    assert hasher.verify(hasher.hash(PASSWORD), PASSWORD) is True


def test_a_wrong_password_is_refused_without_raising(hasher: PasswordHasher) -> None:
    """登录端点里「口令错」是正常分支，不该靠捕获异常来表达。"""
    assert hasher.verify(hasher.hash(PASSWORD), "别的口令") is False


def test_the_same_password_hashes_differently_every_time(hasher: PasswordHasher) -> None:
    """每次的盐不同 —— 否则同一个口令在库里长一个样，一眼看得出谁和谁用的是同一个。"""
    assert hasher.hash(PASSWORD) != hasher.hash(PASSWORD)


def test_a_long_password_is_not_silently_truncated(hasher: PasswordHasher) -> None:
    """在 72 字节处静默截断是 bcrypt 的坑，选 argon2id 的理由之一就是躲开它。"""
    long = "长" * 100
    assert hasher.verify(hasher.hash(long + "尾巴"), long + "别的") is False


def test_a_corrupted_hash_fails_instead_of_raising(hasher: PasswordHasher) -> None:
    """库里那串被手工改过、或来自另一套算法时，要让登录失败而不是让端点 500。"""
    assert hasher.verify("这不是一个哈希", PASSWORD) is False


def test_the_hash_declares_the_parameters_it_used() -> None:
    """参数写死在模块顶而不是跟着库的默认档走 —— 库改默认值不该静默改变已部署系统的强度。"""
    encoded = PasswordHasher().hash(PASSWORD)

    assert encoded.startswith("$argon2id$")
    assert f"m={MEMORY_COST},t={TIME_COST},p={PARALLELISM}" in encoded
