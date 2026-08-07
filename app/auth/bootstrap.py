"""首个管理员：空库时按配置建一个，否则什么都不做。

空库时一个账号都没有，`/auth/login` 谁也进不去 —— 这是「账号自建」这条路必然要
回答的第一个问题。

**唯一的正确性要求是「只在空库时建」。** 否则运维改过管理员口令之后，一次重启就把它
改回 `.env` 里那个，而这种回退不报错、不留痕，下次有人发现时已经说不清是什么时候变的。

**明确接受的代价**：凭据会出现在进程环境里，能登上服务器的人 `docker inspect` 就看得到。
这在内网单机、运维只有一人的前提下可以接受，与接受 HTTP 明文是同一类判断。
"""

import logging

from sqlalchemy.exc import IntegrityError

from auth.password import PasswordHasher
from user.model import UserRole
from user.repository import UserRepository

logger = logging.getLogger(__name__)


async def ensure_first_admin(
    *,
    repository: UserRepository,
    hasher: PasswordHasher,
    name: str,
    password: str,
) -> bool:
    """库里一个账号都没有时，按配置建出首个管理员。

    Args:
        repository: 用户仓储。
        hasher: 口令哈希器。
        name: 配置里的管理员用户名。
        password: 配置里的管理员口令。

    Returns:
        这一次是否真的建了号。
    """
    if await repository.count() > 0:
        return False

    if not name or not password:
        logger.warning("users 表是空的，却没有配置 ADMIN_NAME / ADMIN_PASSWORD —— 现在没有任何人登得进来")
        return False

    try:
        await repository.create(name=name, password_hash=hasher.hash(password), role=UserRole.ADMIN)
    # 多副本同时启动时两边都会读到 0。撞车的那一方按「已经有人建好了」处理 ——
    # 这正是本函数要保证的结果，不是失败
    except IntegrityError:
        logger.info("首个管理员已由另一个进程建出，本次跳过：name=%s", name)
        return False

    logger.info("空库，已按配置建出首个管理员：name=%s", name)
    return True
