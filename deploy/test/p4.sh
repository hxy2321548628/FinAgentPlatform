#!/usr/bin/env bash
#
# P4 验收三条，一条命令跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/p4.sh
#
# 分工：②⑦ 本脚本自己验（全部免费）；⑧ 委托 p3.sh 做 P3 回归。
# **本脚本自己不再需要 LLM**，`SKIP_LLM` 只是原样转给 p3.sh。
#
# **P4 当初那八条已经撤掉五条**，因为它们验的功能都不在了，留着只会永远红：
#
#   ③④ 产物存储（`0009`，2026-08-12）
#   ①⑥ 完整 trace 与告警（随可观测性，2026-08-13）
#   ⑤  成本看板（账本与 `/api/admin/usage` 撤除，用量改到 Langfuse 上看，同日）
#
# **⑤ 撤掉之后，「谁花了多少」在本仓库内不再有判据。** Langfuse 是外部服务，
# 它有没有收到 trace 不该由本项目的验收脚本来断言 —— 那会让门禁的绿依赖
# 另一个项目起没起。要验就手工打开 Langfuse 看，见运维设计 §8.3。
#
#   SKIP_LLM=1 SKIP_P3=1 bash deploy/test/p4.sh   # 只跑本脚本自己那两条
#
# **跳过的条目在结果表里记「未验」而不是「通过」** —— 静默跳过的门禁等于没有门禁。
#
# **别与别的验收脚本同时跑。** 它们共用同一套 compose 栈，而 p2.sh 会 kill 掉进程、
# p3.sh 会压限流 —— 两边一起跑的结果是双方都红，且红在互不相干的地方。
# 实测踩过一次：p3.sh 正在重启 broker，这边的建会话就成了 500。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"
COMPOSE_PROJECT=zuel-platform

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=$((failed + 1)); }
info() { printf '     %s\n' "$*"; }

failed=0
declare -A VERDICT=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# ------------------------------------------------------------------ 前置检查
log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done
for service in nginx api worker broker postgres redis; do
    docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        --filter "label=com.docker.compose.service=$service" | grep -q . \
        || { echo "$service 没起来，先 docker compose up -d" >&2; exit 1; }
done
pass "六个服务都在跑"

# **compose.yml 里 SANDBOX_USER 是必填插值**，而本脚本靠 `compose exec` 查库、放产物、
# 判 resumed。没设的话每次 exec 都以插值失败告终，而判据只收到一个空输出 —— 症状是
# 「账对不上」，指向成本看板而不是指向这里。实测栽过一次。
# 取的是**正在跑的 broker 那一份**：exec 附着到已有容器，值只需能让插值过去，
# 而与栈实际启动时用的值一致最省事。p1 / p2 / p3 都自己补了这一步，本脚本原来漏了
BROKER_ENV="$(docker inspect "$(docker ps -q \
    --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    --filter label=com.docker.compose.service=broker)" \
    --format '{{range .Config.Env}}{{println .}}{{end}}')"
export SANDBOX_USER="${SANDBOX_USER:-$(grep -m1 '^SANDBOX_USER=' <<<"$BROKER_ENV" | cut -d= -f2-)}"
export SANDBOX_WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$(grep -m1 '^SANDBOX_WORKSPACE_ROOT=' <<<"$BROKER_ENV" | cut -d= -f2-)}"
[[ -n $SANDBOX_USER ]] || { echo "broker 的环境里没有 SANDBOX_USER，栈不是按文档起的" >&2; exit 1; }
compose exec -T postgres true >/dev/null 2>&1 \
    || { echo "compose exec 不通（插值或容器有问题），后面的判据会整片假红" >&2; exit 1; }

source "$REPO_ROOT/deploy/test/session.sh"
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
USER_ID="$(zuel_open_session "$JAR")" || { echo "建号或登录失败" >&2; exit 1; }
pass "会话就绪：user_id=$USER_ID"

# ------------------------------------------------------------------ ② 文件直发
log "② 工作目录里的文件从 nginx 直发，api 进程碰不到字节"
before="$failed"
THREAD="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads" \
    -H 'Content-Type: application/json' -d '{"title":"p4-直发"}' | jq -r .id)"

# 直接往会话工作目录里放一个文件，不必先跑一次真实分析 —— 这一条验的是取回那条路
compose exec -T broker sh -c "
    mkdir -p '${SANDBOX_WORKSPACE_ROOT:-/data/sandbox}/$THREAD/outputs' &&
    echo 'p4-直发-判据' > '${SANDBOX_WORKSPACE_ROOT:-/data/sandbox}/$THREAD/outputs/p4.txt'" >/dev/null 2>&1 \
    && pass "文件已放进会话工作目录" || fail "文件放不进会话工作目录"

# **判据是 nginx 直发路径成立**：api 回的是 `X-Accel-Redirect`，字节由 nginx 从
# 挂进来的 workspace 读，api 进程一个字节都不经手。
#
# **绕开 nginx 直接问 api 容器**才看得到那个头 —— 经 nginx 拿到的是字节本身，
# 而「拿到了字节」证明不了它是谁发的。**要带会话 cookie**，否则拿到的是 401，
# 而 401 里当然也没有那个头（第一版就栽在这儿）
API_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
    "$(docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        --filter label=com.docker.compose.service=api)")"
# **cookie 要显式带，不能靠 -b。** curl 只把 cookie 发给域名匹配的主机，而 jar 里
# 那条是记在 127.0.0.1 名下的 —— 换成容器 IP 就不发了，于是拿到 401。
# awk 的条件也要留意：jar 里那行以 `#HttpOnly_` 开头，按「# 开头即注释」过滤会把它滤掉
COOKIE="$(awk 'NF>=7 && $0 !~ /^# / {print $6 "=" $7}' "$JAR" | tail -1)"
HEADER="$(curl -s -D - -o /dev/null -H "Cookie: $COOKIE" \
    --get --data-urlencode "path=outputs/p4.txt" "http://$API_IP:8000/api/threads/$THREAD/files/raw")"
STATUS="$(printf '%s' "$HEADER" | head -1)"
info "api 直答：$STATUS"
printf '%s' "$HEADER" | grep -qi '^X-Accel-Redirect: */workspace/' \
    && pass "api 回的是 X-Accel-Redirect，字节不经它的进程" \
    || fail "api 没有回 X-Accel-Redirect —— 直发没成立"

# 经 nginx 走一遍，确认那条内部跳转真的取得回字节 —— 只验头的话，
# nginx 那一侧配错（没挂卷、alias 写错）看不出来，而症状是每次下载都 404
BODY="$(curl -s -b "$JAR" --get --data-urlencode "path=outputs/p4.txt" "$BASE_URL/api/threads/$THREAD/files/raw")"
[[ $BODY == "p4-直发-判据" ]] \
    && pass "经 nginx 取回的字节与写进去的一致" \
    || fail "经 nginx 取回的不是原字节：$BODY"

# **`internal` 是那条 location 的全部安全性**：外部直接请求一律 404
LEAK="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/workspace/$THREAD/outputs/p4.txt")"
[[ $LEAK == 404 ]] \
    && pass "内部路径不对外：直接请求 /workspace/… 得到 404" \
    || fail "内部路径漏了：直接请求 /workspace/… 得到 $LEAK"
(( failed == before )) && VERDICT[2]=通过 || VERDICT[2]=未过

# ------------------------------------------------------------------ ⑦ resumed
log "⑦ resumed 语义对得上"
before="$failed"
# 「这不是第一次开跑」= 崩溃恢复 or 审批续跑。两个来源都验，缺一个就只验了一半。
# 判据取自库：queued 起跑那一程 start() 返回 FIRST，其余返回 RESUMED
RESUMED_OK="$(compose exec -T api python - <<'PY' 2>&1 | tail -1
import asyncio
from uuid import uuid4

from sqlalchemy import text

# **这一行不是多余的**：`runs.thread_id` 上有指向 `threads` 的外键，而只 import
# run.repository 的话那张表没在 SQLModel 的元数据里注册，第一次查询就会以
# NoReferencedTableError 炸掉 —— 报错指向外键，不指向 import
import thread.repository  # noqa: F401
from config import get_settings
from run.repository import RunRepository, RunStart
from store import postgres


async def main() -> None:
    engine = postgres.create_engine(get_settings().postgres_dsn())
    async with engine.connect() as connection:
        user = (await connection.execute(text('SELECT id FROM users LIMIT 1'))).first()
        thread = (await connection.execute(text('SELECT id FROM threads LIMIT 1'))).first()
    repository = RunRepository(engine)
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=thread[0].hex, user_id=user[0].hex)
    # queued 起跑 = 第一次；不改状态再来一次 = 重投接着跑；走到终态之后 = 不该再执行
    first = await repository.start(run_id)
    again = await repository.start(run_id)
    await repository.cancel(run_id)
    refused = await repository.start(run_id)
    await engine.dispose()
    print(first is RunStart.FIRST and again is RunStart.RESUMED and refused is RunStart.REFUSED)


asyncio.run(main())
PY
)"
[[ $RESUMED_OK == True ]] \
    && pass "queued 起跑报 FIRST，重投报 RESUMED，终态之后报 REFUSED" \
    || fail "resumed 的三态对不上（实得：$RESUMED_OK）"
(( failed == before )) && VERDICT[7]=通过 || VERDICT[7]=未过

# ------------------------------------------------------------------ ⑧ P3 回归
log "⑧ P3 验收七条不回归"
if [[ ${SKIP_P3:-0} == 1 ]]; then
    info "SKIP_P3=1，跳过"
    VERDICT[8]="未验（SKIP_P3=1）"
elif SKIP_LLM="${SKIP_LLM:-0}" BASE_URL="$BASE_URL" bash "$REPO_ROOT/deploy/test/p3.sh"; then
    VERDICT[8]=通过
else
    if [[ $? == 2 ]]; then
        VERDICT[8]="未验（P3 内部有条目被跳过）"
    else
        VERDICT[8]=未过; failed=$((failed + 1))
    fi
fi

# ------------------------------------------------------------------ 结果
log "P4 验收三条"
DESCRIPTION=(
    [2]="工作目录里的文件从 nginx 直发，api 碰不到字节"
    [7]="resumed 语义对得上"
    [8]="P3 验收七条不回归"
)
for index in 2 7 8; do
    case "${VERDICT[$index]:-未验}" in
        通过) printf '  \033[32m✅ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        未过) printf '  \033[31m❌ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        *) printf '  \033[33m⚠️  %s %s —— %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" "${VERDICT[$index]:-未验}" ;;
    esac
done

if (( failed )); then
    printf '\n\033[31mP4 验收未全过。\033[0m\n'
    exit 1
fi
for index in 2 7 8; do
    [[ ${VERDICT[$index]:-未验} == 通过 ]] && continue
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定 P4 验收通过。\033[0m\n'
    exit 2
done
printf '\n\033[32mP4 验收三条全过。\033[0m\n'
