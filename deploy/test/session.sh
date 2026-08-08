#!/usr/bin/env bash
#
# 验收脚本共用的「先有个号」。**只被 source，不单独执行。**
#
#   source "$(dirname "${BASH_SOURCE[0]}")/session.sh"
#   JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
#   USER_ID="$(zuel_open_session "$JAR")"
#   curl -fsS -b "$JAR" "$BASE_URL/api/threads" ...
#
# P3 之后 `/api/*` 一律要会话 cookie，四个验收脚本都得先登录。抄四份的话，
# 登录方式一改就是改一处漏三处 —— 这个文件就是那「一处」。
#
# **要 docker**：平台没有公开的注册端点（建号是管理员的事），所以造号得进 api 容器
# 算口令哈希、进 postgres 插行。调用方给的 BASE_URL 必须指向同一套 compose 栈。
#
# **每次调用造一个新号**，不复用上一轮的：配额是按用户按天算的，复用会让
# 「今日已用 token」跨轮次串味，而串味的表现是莫名其妙的 429。

ZUEL_COMPOSE_PROJECT="${ZUEL_COMPOSE_PROJECT:-zuel-platform}"

# **按标签找容器，不走 `docker compose`**：compose 一读配置就要求 SANDBOX_USER 等插值
# 变量已经 export，而这个文件可能在调用方补齐那些变量之前就被 source。
# 直接 `docker exec` 没有这层依赖 —— 容器已经跑起来了，配置早就用过了
zuel_container() {
    docker ps -q --filter "label=com.docker.compose.project=$ZUEL_COMPOSE_PROJECT" \
        --filter "label=com.docker.compose.service=$1" | head -1
}

# 建号。口令哈希由 api 容器里的 PasswordHasher 算，与登录校验用的是同一套参数 ——
# 在外面另算一份就等于把参数抄了第二遍
zuel_make_user() {
    local name="$1" password="$2" role="${3:-teacher}" api postgres hashed
    api="$(zuel_container api)"
    postgres="$(zuel_container postgres)"
    [[ -n $api && -n $postgres ]] || return 1
    hashed="$(docker exec -i "$api" python -c "
from auth.password import PasswordHasher
print(PasswordHasher().hash('$password'))" | tr -d '\r')"
    [[ -n $hashed ]] || return 1
    docker exec -i "$postgres" psql -U "${POSTGRES_USER:-zuel}" -d "${POSTGRES_DB:-zuel}" -tAc \
        "INSERT INTO users (id, name, password_hash, role, is_active, created_at)
         VALUES (gen_random_uuid(), '$name', '$hashed', '$role', true, now())
         ON CONFLICT (name) DO NOTHING;" >/dev/null
}

zuel_login() {
    local name="$1" password="$2" jar="$3"
    curl -fsS -c "$jar" -o /dev/null -X POST "$BASE_URL/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$name" --arg p "$password" '{name:$n,password:$p}')"
}

# 造号 + 登录，cookie 落进 $1，标准输出是这个号的 user_id。
#
# 失败时返回非零且不输出 —— 调用方据此提前退出，而不是拿着空 id 一路验到底：
# 没有号的话后面每一条都会红成 401，红的原因看不出是「登录没成」还是「功能坏了」。
zuel_open_session() {
    local jar="$1" role="${2:-teacher}"
    local name="zuel-${role}-$$-$(date +%s%N | tail -c 7)"
    local password="zuel-secret-$$"
    local user_id
    zuel_make_user "$name" "$password" "$role" || return 1
    zuel_login "$name" "$password" "$jar" || return 1
    # 管道的退出码是 jq 的：curl 挂了 jq 照样以 0 收场，只是吐出空串。
    # 不显式查一下的话，调用方会拿着空 id 一路走到某个不相干的地方才报错
    user_id="$(curl -fsS -b "$jar" "$BASE_URL/api/auth/me" | jq -r '.id // empty')"
    [[ -n $user_id ]] || return 1
    printf '%s\n' "$user_id"
}
