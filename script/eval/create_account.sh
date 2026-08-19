#!/usr/bin/env bash
# 建一个专用的评估账号。
#
# **平台没有公开的注册端点**（建号是管理员的事），所以与 verify.sh 同一套做法：
# 进 api 容器算口令哈希（与登录校验用的是同一套参数，在外面另算一份等于把参数抄第二遍）、
# 进 postgres 插行，插完回读一次 —— 撞名时 ON CONFLICT 什么都不做而 psql 照样退 0，
# 失败要等到登录那一步才现形，那时报出来的是「登不进去」，不指向造号。
#
# **为什么要专用号**：评估一轮 30 次分析，混进教师自己的会话列表既碍事，也会吃掉他的日配额。
#
# 用法：bash script/eval/create_account.sh [用户名] [口令]
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/compose.yml"
NAME="${1:-zuel-eval}"
PASSWORD="${2:-}"

if [[ -z $PASSWORD ]]; then
    echo "用法：bash script/eval/create_account.sh [用户名] <口令>" >&2
    echo "口令不给默认值 —— 一个所有机器上都一样的评估账号口令迟早会被当成正式账号用" >&2
    exit 2
fi

set -a
# shellcheck disable=SC1091
. "$REPO_ROOT/docker/.env"
set +a

compose() { docker compose -f "$COMPOSE_FILE" -p zuel-platform "$@"; }

HASHED="$(compose exec -T api python -c "
from app.auth.password import PasswordHasher
print(PasswordHasher().hash('$PASSWORD'))" | tr -d '\r')"
[[ -n $HASHED ]] || { echo "算不出口令哈希，api 容器有问题" >&2; exit 1; }

compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "INSERT INTO users (id, name, email, password_hash, role, is_active, created_at)
     VALUES (gen_random_uuid(), '$NAME', '$NAME@eval.zuel.edu.cn', '$HASHED', 'teacher', true, now())
     ON CONFLICT (name) DO NOTHING;" >/dev/null

EXIST="$(compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT count(*) FROM users WHERE name = '$NAME';" | tr -d '[:space:]')"
[[ $EXIST == 1 ]] || { echo "账号 $NAME 没建出来（库里有 ${EXIST:-?} 行）" >&2; exit 1; }

echo "评估账号就绪：$NAME"
echo "跑评估前 export 这两个变量："
echo "  export EVAL_USERNAME=$NAME"
echo "  export EVAL_PASSWORD=<刚才那个口令>"
