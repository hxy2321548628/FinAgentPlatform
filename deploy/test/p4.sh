#!/usr/bin/env bash
#
# P4 验收六条，一条命令跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/p4.sh
#
# 分工：②⑤ 本脚本自己验（全部免费）；① 与 ⑥ 要**真实调用 DeepSeek**或**真的往
# 飞书发一条消息**；⑦ 复用 p2.sh 造的崩溃场景；⑧ 委托 p3.sh 做 P3 回归。
#
# **原来的 ③（旧形状产物 id）与 ④（产物列表偶发为空）已随产物存储一起撤掉** ——
# 那两条验的功能不在了，留着只会永远红。
#
#   SKIP_LLM=1 SKIP_FEISHU=1 SKIP_P3=1 bash deploy/test/p4.sh   # 只跑免费的两条
#
# **跳过的条目在结果表里记「未验」而不是「通过」** —— 静默跳过的门禁等于没有门禁。
#
# **⑥ 会真的往你配的飞书群里发一条消息**，因此单独给了 SKIP_FEISHU。发的内容明确
# 标着是自检，不是真实告警。
#
# **别与别的验收脚本同时跑。** 它们共用同一套 compose 栈，而 p2.sh 会 kill 掉进程、
# p3.sh 会压限流 —— 两边一起跑的结果是双方都红，且红在互不相干的地方。
# 实测踩过一次：p3.sh 正在重启 broker，这边的建会话就成了 500。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"
COMPOSE_PROJECT=zuel-platform

# 一次真实分析跑完的观察窗口，秒
RUN_WINDOW=600

# span 从进程发出到 Tempo 查得到要经过 collector 攒批与 ingester 落块，等这么久
TRACE_WINDOW=120

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=$((failed + 1)); }
info() { printf '     %s\n' "$*"; }

failed=0
declare -A VERDICT=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
psql_query() { compose exec -T postgres psql -U "${POSTGRES_USER:-zuel}" -d "${POSTGRES_DB:-zuel}" -tAc "$1"; }

# Tempo 与 Loki 都不映射宿主端口（只有 Grafana 够得着），因此从容器网络里问
in_network() { docker run --rm --network "${COMPOSE_PROJECT}_default" curlimages/curl:latest -s "$@" 2>/dev/null; }

grafana() {
    local password
    password="$(grep '^GF_SECURITY_ADMIN_PASSWORD=' "$REPO_ROOT/.env" | cut -d= -f2-)"
    curl -s -u "admin:$password" "$@"
}

# ------------------------------------------------------------------ 前置检查
log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done
for service in api broker worker prometheus grafana tempo loki otel-collector minio; do
    docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        --filter "label=com.docker.compose.service=$service" | grep -q . \
        || { echo "$service 没起来，先 docker compose up -d" >&2; exit 1; }
done
pass "九个服务都在跑"

# **compose.yml 里 SANDBOX_USER 是必填插值**，而本脚本靠 `compose exec` 查库、放产物、
# 判 resumed。没设的话每次 exec 都以插值失败告终，而判据只收到一个空输出 —— 症状是
# 「账对不上」「token 对不上」，指向看板与 trace 而不是指向这里。实测栽过一次。
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

# ------------------------------------------------------------------ ⑤ 成本看板
log "⑤ 成本看板答得出「谁花了多少」"
before="$failed"
ADMIN_JAR="$(mktemp)"; trap 'rm -f "$JAR" "$ADMIN_JAR"' EXIT
zuel_open_session "$ADMIN_JAR" admin >/dev/null || fail "建管理员失败"

USAGE="$(curl -fsS -b "$ADMIN_JAR" "$BASE_URL/api/admin/usage")"
echo "$USAGE" | jq -e '.users | length >= 0' >/dev/null && pass "端点答得出按用户的聚合" || fail "端点没给出 users"
echo "$USAGE" | jq -e '.daily | length >= 0' >/dev/null && pass "端点答得出按天的聚合" || fail "端点没给出 daily"

# 账要对得上：端点的未命中总和 = 直接查库
ENDPOINT_SUM="$(echo "$USAGE" | jq '[.users[].uncached] | add // 0')"
DAYS="$(echo "$USAGE" | jq -r .days)"
# **必须与端点同一个口径**：那边是 runs 内连 users（`report/usage.py`），
# 没有主人的 run 不进报表。少了这个 join 会把它们算进来，于是「账对不上」——
# 而对不上的是判据，不是看板。第一版就是这么红的
DB_SUM="$(psql_query "SELECT COALESCE(SUM(r.tokens_uncached), 0)
    FROM runs r JOIN users u ON u.id = r.user_id
    WHERE r.started_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
                          - INTERVAL '$((DAYS - 1)) days';" | tr -d ' ')"
info "端点 $ENDPOINT_SUM / 直接查库 $DB_SUM"
[[ $ENDPOINT_SUM == "$DB_SUM" ]] && pass "账对得上" || fail "账对不上 —— 看板在误导成本判断"

# 边界：教师打不开，未登录打不开
CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$BASE_URL/api/admin/usage")"
[[ $CODE == 403 ]] && pass "教师打不开（403）" || fail "教师拿到了 $CODE，本该 403"
CODE="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/admin/usage")"
[[ $CODE == 401 ]] && pass "未登录打不开（401）" || fail "未登录拿到了 $CODE，本该 401"

# **管理员看得到用量，看不到会话内容**（架构 §6.3）
if echo "$USAGE" | grep -qiE '"(title|content|question|answer|thread_id|run_id)"'; then
    fail "响应里出现了会话相关字段 —— §6.3 的边界被这个端点绕开了"
else
    pass "响应里只有数字，没有会话内容"
fi
(( failed == before )) && VERDICT[5]=通过 || VERDICT[5]=未过

# ------------------------------------------------------------------ ① 完整 trace
log "① 能定位单个 run 的完整 trace 与 token 花费（要 LLM，有费用）"
if [[ ${SKIP_LLM:-0} == 1 ]]; then
    info "SKIP_LLM=1，跳过"
    VERDICT[1]="未验（SKIP_LLM=1）"
else
    before="$failed"
    TRACE_THREAD="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads" \
        -H 'Content-Type: application/json' -d '{"title":"p4-trace"}' | jq -r .id)"
    RUN="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads/$TRACE_THREAD/runs" \
        -H 'Content-Type: application/json' \
        -d '{"content":"用 python 算 1 到 10 的平方和，直接给出结果，不要画图不要存文件。"}' | jq -r .id)"
    info "run=$RUN，等它跑完"
    timeout "$RUN_WINDOW" curl -fsS -N -b "$JAR" "$BASE_URL/api/runs/$RUN/events" \
        | grep -m1 -E '"type": ?"run\.(finished|failed)"' >/dev/null

    info "等 span 落到 Tempo（最多 ${TRACE_WINDOW}s）"
    deadline=$((SECONDS + TRACE_WINDOW))
    TRACE_ID=""
    while (( SECONDS < deadline )); do
        TRACE_ID="$(in_network --get "http://tempo:3200/api/search" \
            --data-urlencode "q={ .zuel.run_id = \"$RUN\" }" | jq -r '.traces[0].traceID // empty')"
        [[ -n $TRACE_ID ]] && break
        sleep 5
    done
    [[ -n $TRACE_ID ]] && pass "按 run_id 检索到 trace：$TRACE_ID" || fail "按 run_id 检索不到 trace"

    if [[ -n $TRACE_ID ]]; then
        DUMP="$(in_network "http://tempo:3200/api/traces/$TRACE_ID")"
        # **四段都要在**：少一段就不叫「完整 trace」
        for segment in zuel-api zuel-worker zuel-broker; do
            echo "$DUMP" | grep -q "$segment" \
                && pass "trace 里有 $segment 那一段" || fail "trace 里没有 $segment"
        done
        echo "$DUMP" | grep -q "llm.call" && pass "trace 里有 LLM 调用那一段" || fail "trace 里没有 llm.call"

        # token 三元组要在同一个 span 上，且与 runs 表对得上
        UNCACHED="$(echo "$DUMP" | jq -r '[.. | objects | select(.key? == "zuel.token.input_uncached") | .value.intValue] | first // empty')"
        DB_UNCACHED="$(psql_query "SELECT tokens_uncached FROM runs WHERE id = '$RUN';" | tr -d ' ')"
        info "trace 上 $UNCACHED / runs 表 $DB_UNCACHED"
        [[ -n $UNCACHED && $UNCACHED == "$DB_UNCACHED" ]] \
            && pass "token 三元组在 span 上，且与 runs 表一致" \
            || fail "token 对不上 —— trace 上的花费不可信"
    fi

    # 「能定位」要落到一个具体页面上，不能是「自己 grep」
    grafana "http://127.0.0.1:3000/api/dashboards/uid/zuel-run" | jq -e '.dashboard.title' >/dev/null \
        && pass "「按 run 查链路」看板在 Grafana 里" || fail "看板不在 —— 「能定位」没有落到页面上"
    (( failed == before )) && VERDICT[1]=通过 || VERDICT[1]=未过
fi

# ------------------------------------------------------------------ ⑥ 告警
log "⑥ 告警真的会响（会往飞书发一条自检消息）"
if [[ ${SKIP_FEISHU:-0} == 1 ]]; then
    info "SKIP_FEISHU=1，跳过"
    VERDICT[6]="未验（SKIP_FEISHU=1）"
else
    before="$failed"
    HOOK="$(grep '^FEISHU_WEBHOOK_URL=' "$REPO_ROOT/.env" | cut -d= -f2-)"
    [[ -n $HOOK ]] || fail "没配 FEISHU_WEBHOOK_URL"

    if [[ -n $HOOK ]]; then
        # 第一层：飞书认不认 Grafana 将要发的那种正文
        GOOD='{"msg_type":"text","content":{"text":"【智能体平台】p4.sh 通道自检，非真实告警"}}'
        CODE="$(curl -s -X POST "$HOOK" -H 'Content-Type: application/json' -d "$GOOD" | jq -r '.code // 1')"
        [[ $CODE == 0 ]] && pass "飞书收下了自检消息（code=0）" || fail "飞书拒了自检消息（code=$CODE）"

        # **第二层：证明这个判据分得开对错。** 飞书对形状不对的正文回的是 HTTP 200
        # 加一个业务错误码 —— 不读那个码的话，用默认正文也「成功」，而群里什么都没有
        BAD='{"receiver":"x","status":"firing","alerts":[]}'
        CODE="$(curl -s -X POST "$HOOK" -H 'Content-Type: application/json' -d "$BAD" | jq -r '.code // 0')"
        [[ $CODE != 0 ]] \
            && pass "默认正文被飞书拒掉（code=$CODE）—— 判据分得开对错" \
            || fail "默认正文也被收下了 —— 这个判据证明不了任何事"
    fi

    # 第三层：规则与通道在 Grafana 里都装上了
    RULES="$(grafana "http://127.0.0.1:3000/api/v1/provisioning/alert-rules" | jq -r '[.[].uid] | join(",")')"
    info "已装规则：$RULES"
    for uid in zuel-target-down zuel-llm-failure zuel-queue-backlog zuel-sandbox-full; do
        [[ $RULES == *"$uid"* ]] && pass "规则 $uid 已装" || fail "规则 $uid 没装上"
    done
    grafana "http://127.0.0.1:3000/api/v1/provisioning/contact-points" | jq -e '.[] | select(.name == "feishu")' >/dev/null \
        && pass "飞书通道已装" || fail "飞书通道没装上"
    (( failed == before )) && VERDICT[6]=通过 || VERDICT[6]=未过
fi

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
log "P4 验收六条"
DESCRIPTION=(
    [1]="能定位单个 run 的完整 trace 与 token 花费"
    [2]="工作目录里的文件从 nginx 直发，api 碰不到字节"
    [5]="成本看板答得出「谁花了多少」"
    [6]="告警真的会响"
    [7]="resumed 语义对得上"
    [8]="P3 验收七条不回归"
)
for index in 1 2 5 6 7 8; do
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
for index in 1 2 5 6 7 8; do
    [[ ${VERDICT[$index]:-未验} == 通过 ]] && continue
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定 P4 验收通过。\033[0m\n'
    exit 2
done
printf '\n\033[32mP4 验收六条全过。\033[0m\n'
