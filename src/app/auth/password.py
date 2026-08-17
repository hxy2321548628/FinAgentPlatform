"""口令哈希：argon2id。

**不自己实现哈希，也不用库的默认档。** 参数写成模块顶常量有两个理由：将来调高时
有据可查；而库改自己的默认值时，已部署系统的强度不会被静默改掉。

选 argon2id 而不是 bcrypt：内存硬度更好，且 bcrypt 有 72 字节静默截断这个坑 ——
超长口令的后半截根本不参与计算，而这件事一声不响。
"""

from argon2 import PasswordHasher as Argon2Hasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError

# RFC 9106 的第二组推荐参数：64 MiB 内存、3 轮、4 路并行。
# 内存是这里的成本大头 —— 一次校验占 64 MiB，登录并发很低，够用
TIME_COST = 3
MEMORY_COST = 65536
PARALLELISM = 4
HASH_LENGTH = 32
SALT_LENGTH = 16


class PasswordHasher:
    """算哈希与验哈希。

    Args:
        time_cost: 迭代轮数。
        memory_cost: 内存占用，KiB。
        parallelism: 并行度。
    """

    def __init__(
        self,
        *,
        time_cost: int = TIME_COST,
        memory_cost: int = MEMORY_COST,
        parallelism: int = PARALLELISM,
    ) -> None:
        self._hasher = Argon2Hasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=HASH_LENGTH,
            salt_len=SALT_LENGTH,
            type=Type.ID,
        )

    def hash(self, password: str) -> str:
        """算出可直接落库的哈希串，其中已经含盐与参数。

        Args:
            password: 明文口令。

        Returns:
            形如 `$argon2id$v=19$m=65536,t=3,p=4$...` 的编码串。
        """
        return self._hasher.hash(password)

    def verify(self, hashed: str, password: str) -> bool:
        """校验口令。

        **对不上不抛异常，返回 False**：调用方是登录端点，那里「口令错」是正常分支
        而不是故障。库里那条哈希串本身坏掉（被手工改过、或来自另一套算法）时同样
        返回 False —— 让登录失败，而不是让整个端点 500。

        Args:
            hashed: 库里存的哈希串。
            password: 待校验的明文口令。

        Returns:
            对得上则 True。
        """
        try:
            return self._hasher.verify(hashed, password)
        # UnicodeEncodeError 也在列：库把哈希串按 ASCII 编码（真哈希本来就是 ASCII），
        # 因此库里那一列若被手工写成中文，它会在解析之前就抛 —— 而那仍然只是「口令对不上」
        except (VerificationError, InvalidHashError, UnicodeEncodeError):
            return False
