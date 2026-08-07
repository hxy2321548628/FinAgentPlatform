#!/usr/bin/env bash
#
# P1 验收六条，一条命令跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/p1.sh
#
# 分工：③④⑤⑥ 本脚本自己验（全部免费、约三分钟）；① 委托 hostile.sh（要 sudo）；
# ② 委托 acceptance.sh（**真实调用 DeepSeek，约 30 万 token，有费用**）。
#
# 想省时省钱可以 SKIP_HOSTILE=1 / SKIP_LLM=1，但**跳过的条目在结果表里记「未验」
# 而不是「通过」** —— 静默跳过的门禁等于没有门禁。
#
# 本脚本以普通用户跑，只在调 hostile.sh 时提权。以 root 跑会让它建出的会话目录
# 属主变成 root，那正是 P1 栽过两次的那个坑。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"
WORK_DIR="$(mktemp -d)"

# 心跳观察窗口，秒。要明显超过 Nginx 默认的 proxy_read_timeout 60s ——
# 只等 30 秒的话，连接还活着说明不了任何问题
HEARTBEAT_WINDOW=150
# 心跳间隔 15s，90 秒的静默期该有 6 次。留够抖动余量
HEARTBEAT_EXPECTED=4
# 验心跳时临时把排队超时调小：默认 600 秒等不起，而放这个 run 真跑起来就要
# 多调一次 LLM。90 秒既够跨过 60s 那道坎，又能让 run 自己以排队超时收场
QUEUE_TIMEOUT=90
# 只留一个名额，才能用一个沙箱把池占满
MAX_CONTAINER=1

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=1; }
info() { printf '     %s\n' "$*"; }

failed=0
declare -A VERDICT=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
in_api() { compose exec -T api "$@"; }
in_broker() { compose exec -T broker "$@"; }

# broker 不对外暴露端口（ADR-0004），只能从它自己的容器里够着。
# 镜像里没有 curl，用现成的 httpx
broker_call() {
    local method="$1" path="$2"
    in_broker python -c "
import sys, httpx
with httpx.stream('$method', 'http://127.0.0.1:8100$path', timeout=None) as response:
    body = ''.join(response.iter_text())
if response.status_code >= 400:
    sys.exit(f'{response.status_code} {body}')
print(body)
"
}

sandbox_of() { docker ps --filter "label=zuel.thread=$1" --format '{{.ID}}' | head -1; }
managed_count() { docker ps -q --filter label=zuel.sandbox | wc -l; }

cleanup() {
    [[ -n ${THREAD_HELD:-} ]] && docker rm -f "$(sandbox_of "$THREAD_HELD")" >/dev/null 2>&1
    # ⑤ 换过 broker 的配置，跑完必须换回来，否则整台机器就剩一个沙箱名额
    [[ -n ${OVERRIDDEN:-} ]] && compose up -d --no-deps --force-recreate broker >/dev/null 2>&1
    for thread_id in ${THREAD_HELD:-} ${THREAD_QUEUED:-}; do
        rm -rf "${WORKSPACE_ROOT:?}/$thread_id"
    done
    rm -rf "$WORK_DIR"
    return 0
}

# ------------------------------------------------------------------ 前置检查
log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主。sudo 只在 ① 处按需提权" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done
# compose.yml 里 SANDBOX_USER 与 SANDBOX_WORKSPACE_ROOT 是必填插值，两个都没有的话
# 连 `docker compose ps` 都跑不起来。这里**从跑着的 broker 身上读回来**，而不是让人
# 记着 export，也不是在这里另猜一份默认值 —— 猜错的后果是 ⑤ 重建 broker 时挂载路径
# 与在跑的那套不一致，而那种错不会报错，只会让验收在错的目标上跑
#
# 用裸 docker ps 按 compose 标签找：这一步本身不能依赖 compose，否则就是先有鸡还是先有蛋
COMPOSE_PROJECT=zuel-platform
BROKER_ID="$(docker ps -q \
    --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    --filter label=com.docker.compose.service=broker)"
[[ -n $BROKER_ID ]] || {
    cat >&2 <<'TIP'
broker 没在跑。先把栈起起来：

    export SANDBOX_USER="$(id -u):$(id -g)"
    export SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
    docker compose -f deploy/compose.yml up -d --build
TIP
    exit 1
}
BROKER_ENV="$(docker inspect "$BROKER_ID" --format '{{range .Config.Env}}{{println .}}{{end}}')"
export SANDBOX_USER="${SANDBOX_USER:-$(grep -m1 '^SANDBOX_USER=' <<<"$BROKER_ENV" | cut -d= -f2-)}"
export SANDBOX_WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$(grep -m1 '^SANDBOX_WORKSPACE_ROOT=' <<<"$BROKER_ENV" | cut -d= -f2-)}"
WORKSPACE_ROOT="$SANDBOX_WORKSPACE_ROOT"
[[ -n $SANDBOX_USER && -n $WORKSPACE_ROOT ]] || { echo "broker 容器里没有 SANDBOX_USER / SANDBOX_WORKSPACE_ROOT" >&2; exit 1; }

for service in nginx api; do
    [[ $(compose ps --status running --format '{{.Service}}' | grep -cx "$service") -eq 1 ]] || {
        echo "$service 没在跑：docker compose -f deploy/compose.yml up -d --build" >&2; exit 1
    }
done
curl -fsS "$BASE_URL/docs" >/dev/null || { echo "Nginx 没把 $BASE_URL 转发通" >&2; exit 1; }

# 提前把 sudo 凭据取到手。不然密码提示会在十分钟后、③④⑤⑥ 都跑完时才冒出来，
# 人早走开了，回来看到的是一个卡在半路的验收
[[ ${SKIP_HOSTILE:-0} == 1 ]] || sudo -v || { echo "① 需要 sudo，或用 SKIP_HOSTILE=1 跳过" >&2; exit 1; }

LOG_SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BASE_MANAGED=$(managed_count)
info "网关 $BASE_URL ｜ workspace $WORKSPACE_ROOT ｜ 已有沙箱 $BASE_MANAGED 个"
trap cleanup EXIT

# ------------------------------------------------------------------ ③ 边界
# 每条都配一个 broker 上的对照组。只验「api 上失败」的话，二进制不存在、
# 路径拼错、容器没起来都会让它通过 —— 那是三种与边界无关的原因
log "③ api 拿不到 docker.sock，也看不到宿主 workspace"

before=$failed
if in_broker test -S /var/run/docker.sock 2>/dev/null; then
    if in_api test -S /var/run/docker.sock 2>/dev/null; then
        fail "api 容器里有 docker.sock —— ADR-0004 的边界没立住"
    else
        pass "docker.sock：broker 有，api 没有"
    fi
else
    fail "对照组不成立：broker 容器里也没有 docker.sock，这条验不了"
fi

if in_broker docker ps -q >/dev/null 2>&1; then
    DENIED=$(in_api docker ps 2>&1)
    if grep -q 'Cannot connect to the Docker daemon' <<<"$DENIED"; then
        pass "api 里 docker ps 被拒：$(head -1 <<<"$DENIED" | cut -c1-60)…"
    else
        fail "api 里 docker ps 没有以「连不上守护进程」失败：$(tr '\n' ' ' <<<"$DENIED" | cut -c1-120)"
    fi
else
    fail "对照组不成立：broker 里 docker ps 也不通，说明是 CLI 的问题不是边界的问题"
fi

if in_broker test -d "$WORKSPACE_ROOT" 2>/dev/null; then
    if in_api test -d "$WORKSPACE_ROOT" 2>/dev/null; then
        fail "api 容器能看到宿主 workspace $WORKSPACE_ROOT，数据面没挡住"
    else
        pass "宿主 workspace：broker 挂了，api 没挂"
    fi
else
    fail "对照组不成立：broker 里也没有 $WORKSPACE_ROOT，检查 SANDBOX_WORKSPACE_ROOT"
fi
VERDICT[3]=$([[ $failed -eq $before ]] && echo 通过 || echo 未过)

# ------------------------------------------------------------------ ④ 重启认领
log "④ broker 崩溃重启后按 label 认领已有容器，不泄漏孤儿"

before=$failed
THREAD_HELD="$(curl -fsS -X POST "$BASE_URL/api/threads" | jq -r .id)"
[[ -n $THREAD_HELD && $THREAD_HELD != null ]] || { fail "建会话失败"; THREAD_HELD=""; }

if [[ -n $THREAD_HELD ]]; then
    broker_call POST "/threads/$THREAD_HELD/sandbox" >/dev/null || fail "申请沙箱失败"
    CONTAINER_BEFORE="$(sandbox_of "$THREAD_HELD")"
    info "沙箱 ${CONTAINER_BEFORE:0:12} ｜ thread $THREAD_HELD"

    # kill -9 而不是 stop：优雅退出会走 pool.aclose() 把容器一并销毁，
    # 那样重启后无物可认，验的就成了「空池能不能启动」
    compose kill -s KILL broker >/dev/null 2>&1
    if [[ -n $(docker ps -q --filter "id=$CONTAINER_BEFORE") ]]; then
        pass "broker 被 kill -9 后沙箱容器仍在（--rm 不跟着 broker 走）"
    else
        fail "broker 一崩沙箱就没了，认领无从谈起"
    fi

    compose up -d --no-deps broker >/dev/null 2>&1
    for _ in $(seq 30); do
        in_broker python -c "import httpx; httpx.get('http://127.0.0.1:8100/docs', timeout=2)" 2>/dev/null && break
        sleep 1
    done

    # 用裸 grep 而不是 jq 取 .message：日志是不是 JSON 由 ⑥ 负责断言，
    # 这里再依赖它一次的话，日志格式一坏就会连带谎报「没认领」
    if compose logs broker --since "$LOG_SINCE" --no-log-prefix --no-color 2>/dev/null |
        grep -F '认领重启前的沙箱容器' | grep -q "$THREAD_HELD"; then
        pass "broker 日志里有对该 thread 的认领记录"
    else
        fail "broker 重启后没认领这个容器，它已经是孤儿了"
    fi

    broker_call POST "/threads/$THREAD_HELD/sandbox" >/dev/null || fail "认领后再申请失败"
    CONTAINER_AFTER="$(sandbox_of "$THREAD_HELD")"
    NOW_MANAGED=$(managed_count)
    if [[ $CONTAINER_AFTER == "$CONTAINER_BEFORE" ]] && (( NOW_MANAGED == BASE_MANAGED + 1 )); then
        pass "复用的是同一个容器，沙箱总数 $BASE_MANAGED → $NOW_MANAGED，没多出孤儿"
    else
        fail "容器 ${CONTAINER_BEFORE:0:12} → ${CONTAINER_AFTER:0:12}，沙箱总数 $BASE_MANAGED → $NOW_MANAGED"
    fi
fi
VERDICT[4]=$([[ $failed -eq $before ]] && echo 通过 || echo 未过)

# ------------------------------------------------------------------ ⑤ 心跳
log "⑤ 排队静默期 SSE 不被 Nginx 掐断"

before=$failed
cat > "$WORK_DIR/override.yml" <<YAML
services:
  broker:
    environment:
      SANDBOX_MAX_CONTAINER: "$MAX_CONTAINER"
      SANDBOX_QUEUE_TIMEOUT: "$QUEUE_TIMEOUT"
YAML
OVERRIDDEN=1
docker compose -f "$COMPOSE_FILE" -f "$WORK_DIR/override.yml" up -d --no-deps --force-recreate broker >/dev/null 2>&1
for _ in $(seq 30); do
    in_broker python -c "import httpx; httpx.get('http://127.0.0.1:8100/docs', timeout=2)" 2>/dev/null && break
    sleep 1
done

# 占住唯一的名额。重启后认领回来的容器 lease=0，要再申请一次才算被占用
broker_call POST "/threads/$THREAD_HELD/sandbox" >/dev/null || fail "占位申请失败"

THREAD_QUEUED="$(curl -fsS -X POST "$BASE_URL/api/threads" | jq -r .id)"
RUN_ID="$(curl -fsS -X POST "$BASE_URL/api/threads/$THREAD_QUEUED/runs" \
    -H 'Content-Type: application/json' \
    -d '{"content":"这个 run 只用来占住排队位，不会真跑起来。"}' | jq -r .id)"
info "排队中的 run $RUN_ID，将静默等待约 ${QUEUE_TIMEOUT}s"

STARTED=$(date +%s)
timeout "$HEARTBEAT_WINDOW" curl -sS -N "$BASE_URL/api/runs/$RUN_ID/events" > "$WORK_DIR/queued.sse"
ELAPSED=$(( $(date +%s) - STARTED ))
HEARTBEAT=$(grep -c '^:heartbeat' "$WORK_DIR/queued.sse")

# 说清这条证明了什么：nginx.conf 已经把 /api/runs/ 的 proxy_read_timeout 抬到 3600s，
# 所以「没被掐断」主要是那条配置的功劳，不是心跳的。心跳防的是浏览器、公司代理这些
# 我们改不到配置的中间环节 —— 因此下面两条断言缺一不可，只看连接活着会把话说过头
if (( ELAPSED >= 75 )); then
    pass "连接静默存活 ${ELAPSED}s，越过了 60s 这道常见的空闲上限"
else
    fail "连接只活了 ${ELAPSED}s，没到能说明问题的时长"
fi

if (( HEARTBEAT >= HEARTBEAT_EXPECTED )); then
    pass "收到 $HEARTBEAT 个心跳帧"
else
    fail "只收到 $HEARTBEAT 个心跳帧，少于预期的 $HEARTBEAT_EXPECTED 个"
fi

# 心跳带 id 的话，客户端会把它记成 Last-Event-ID，重连时中间的真事件全被跳过
ID_LINE=$(grep -c '^id:' "$WORK_DIR/queued.sse")
EVENT_LINE=$(grep -c '^event:' "$WORK_DIR/queued.sse")
if (( ID_LINE == EVENT_LINE )); then
    pass "心跳不占事件 id（id 行 $ID_LINE = event 行 $EVENT_LINE）"
else
    fail "id 行 $ID_LINE ≠ event 行 $EVENT_LINE，心跳污染了 Last-Event-ID"
fi

if grep -q 'sandbox.queued' "$WORK_DIR/queued.sse" &&
    grep '^data:' "$WORK_DIR/queued.sse" | sed 's/^data: *//' |
    jq -e -s 'map(select(.type=="run.failed")) | .[0].data.code == "SANDBOX_QUEUE_TIMEOUT"' >/dev/null 2>&1; then
    pass "确实排在队里，并以排队超时收场（这条没花任何 token）"
else
    fail "这个 run 没走排队超时那条路，静默期的成因存疑：$(grep -o 'run\.[a-z]*' "$WORK_DIR/queued.sse" | tail -1)"
fi
VERDICT[5]=$([[ $failed -eq $before ]] && echo 通过 || echo 未过)

# ------------------------------------------------------------------ ⑥ 日志
log "⑥ 日志是结构化行且带 run_id / thread_id"

before=$failed
for service in api broker; do
    compose logs "$service" --since "$LOG_SINCE" --no-log-prefix --no-color 2>/dev/null |
        grep -v '^[[:space:]]*$' > "$WORK_DIR/$service.log"
    TOTAL=$(wc -l < "$WORK_DIR/$service.log")
    if (( TOTAL > 0 )) && jq -e . "$WORK_DIR/$service.log" >/dev/null 2>&1; then
        pass "$service 的 $TOTAL 行日志全部可被 jq 逐行解析"
    else
        fail "$service 的日志不是逐行 JSON（共 $TOTAL 行）"
        # 只在失败时逐行找，好把真正坏掉的那几行指出来
        while IFS= read -r line; do
            jq -e . >/dev/null 2>&1 <<<"$line" || printf '       %s\n' "${line:0:120}"
        done < "$WORK_DIR/$service.log" | head -3
    fi
done

FILTERED=$(jq -sr --arg run "$RUN_ID" '[.[] | select(.run_id == $run)] | length' "$WORK_DIR/api.log" 2>/dev/null)
if [[ ${FILTERED:-0} -gt 0 ]]; then
    pass "按 run_id 能把这一次 run 的 $FILTERED 行日志过滤出来"
else
    fail "api 日志里按 run_id=$RUN_ID 过滤不出任何行"
fi

if jq -se 'any(.[]; has("thread_id"))' "$WORK_DIR/api.log" >/dev/null 2>&1; then
    pass "日志带 thread_id"
else
    fail "api 日志里没有一行带 thread_id"
fi
info "token 按 cache 拆分那半条由 ② 断言（acceptance.sh 末尾）"
VERDICT[6]=$([[ $failed -eq $before ]] && echo 通过 || echo 未过)

# 后面两条要用干净的池子，先把占位的沙箱和临时配置还回去
cleanup
trap - EXIT
THREAD_HELD=""; THREAD_QUEUED=""; OVERRIDDEN=""
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# ------------------------------------------------------------------ ① 破坏性测试
log "① 四条破坏性测试（要 sudo）"
if [[ ${SKIP_HOSTILE:-0} == 1 ]]; then
    VERDICT[1]="未验（SKIP_HOSTILE=1）"
    info "已跳过"
elif sudo -E bash "$REPO_ROOT/deploy/test/hostile.sh"; then
    VERDICT[1]=通过
else
    VERDICT[1]=未过; failed=1
fi

# ------------------------------------------------------------------ ② P0 回归
log "② P0 验收四条经 Nginx 重跑"
if [[ ${SKIP_LLM:-0} == 1 ]]; then
    VERDICT[2]="未验（SKIP_LLM=1）"
    info "已跳过 —— 这条要真实调用 DeepSeek"
elif BASE_URL="$BASE_URL" bash "$REPO_ROOT/deploy/test/acceptance.sh"; then
    VERDICT[2]=通过
else
    VERDICT[2]=未过; failed=1
fi

# ------------------------------------------------------------------ 结果
log "P1 验收六条"
DESCRIPTION=(
    [1]="四条破坏性测试宿主机不受影响"
    [2]="P0 验收四条在 gVisor + Nginx 下全过"
    [3]="api 拿不到 docker.sock 与宿主 workspace"
    [4]="broker 重启按 label 认领，不泄漏孤儿"
    [5]="排队静默期 SSE 不被 Nginx 掐断"
    [6]="日志结构化且带 run_id / thread_id"
)
for index in 1 2 3 4 5 6; do
    case "${VERDICT[$index]}" in
        通过) printf '  \033[32m✅ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        未过) printf '  \033[31m❌ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        *) printf '  \033[33m⚠️  %s %s —— %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" "${VERDICT[$index]}" ;;
    esac
done

if (( failed )); then
    printf '\n\033[31mP1 验收未全过。\033[0m\n'
    exit 1
fi
if [[ ${VERDICT[1]} != 通过 || ${VERDICT[2]} != 通过 ]]; then
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定 P1 验收通过。\033[0m\n'
    exit 2
fi
printf '\n\033[32mP1 验收六条全过。\033[0m\n'
