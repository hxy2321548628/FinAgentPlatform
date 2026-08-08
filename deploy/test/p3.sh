#!/usr/bin/env bash
#
# P3 验收七条，一条命令跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/p3.sh
#
# 分工：③④⑤⑥ 本脚本自己验（全部免费）；① 与 ② 要**真实调用 DeepSeek**，有费用；
# ⑦ 委托 p2.sh 做 P2 回归（它自己再往下委托 p1.sh）。
#
#   SKIP_LLM=1 SKIP_P2=1 bash deploy/test/p3.sh   # 只跑免费的四条，约 2 分钟
#
# **跳过的条目在结果表里记「未验」而不是「通过」** —— 静默跳过的门禁等于没有门禁。
#
# 本脚本以普通用户跑，与 p1.sh / p2.sh 同一个理由：以 root 跑会把会话目录建成 root 属主。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"
COMPOSE_PROJECT=zuel-platform

# 一次真实分析跑完的观察窗口，秒
RUN_WINDOW=600

# 压测并发数（验收③）
CONCURRENCY=30

# 教师看到中断之后等多久点确认 —— 脚本这一侧不需要真等，取一个够 worker 落状态的数
SETTLE_WINDOW=120

# 一个 run 最多批几轮。**一次 run 可以中断多次**：教师改过参数之后 agent 可能再提一次
# 敏感调用。上限是防跑飞，不是判据 —— 到了上限还没终态就算未过
APPROVE_ROUND=4

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=$((failed + 1)); }
info() { printf '     %s\n' "$*"; }

failed=0
declare -A VERDICT=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
in_api_python() { compose exec -T api python -c "$1"; }
psql_query() { compose exec -T postgres psql -U "${POSTGRES_USER:-zuel}" -d "${POSTGRES_DB:-zuel}" -tAc "$1"; }

# ------------------------------------------------------------------ 前置检查
log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done

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

for service in nginx api worker postgres redis; do
    (( $(compose ps --status running --format '{{.Service}}' | grep -cx "$service") >= 1 )) || {
        echo "$service 没在跑：docker compose -f deploy/compose.yml up -d --build" >&2; exit 1
    }
done
curl -fsS "$BASE_URL/docs" >/dev/null || { echo "Nginx 没把 $BASE_URL 转发通" >&2; exit 1; }

# ------------------------------------------------------------------ 账号
# **每次跑都造一批新账号**：留着上一次的会让「今日已用 token」等状态跨轮次串味。
# 口令哈希由 api 容器里的 PasswordHasher 算，与登录用的是同一套参数
ADMIN_NAME="${ADMIN_NAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
STAMP="$(date +%s)"
TEACHER_A="p3-a-$STAMP"
TEACHER_B="p3-b-$STAMP"
SECRET="p3-secret-$STAMP"

# 造号与登录本身在 session.sh 里，四个验收脚本共用一份。这里只是把口令那一维绑成
# $SECRET —— 本脚本要按名字点名（A / B / 管理员），而 session.sh 的一站式入口发的是随机名
source "$REPO_ROOT/deploy/test/session.sh"

make_user() { zuel_make_user "$1" "$SECRET" "$2"; }
login() { zuel_login "$1" "$SECRET" "$2"; }

JAR_A="$(mktemp)"; JAR_B="$(mktemp)"; JAR_ADMIN="$(mktemp)"
trap 'rm -f "$JAR_A" "$JAR_B" "$JAR_ADMIN"' EXIT

make_user "$TEACHER_A" teacher
make_user "$TEACHER_B" teacher
login "$TEACHER_A" "$JAR_A" || { echo "A 登不进来" >&2; exit 1; }
login "$TEACHER_B" "$JAR_B" || { echo "B 登不进来" >&2; exit 1; }
UID_A="$(curl -fsS -b "$JAR_A" "$BASE_URL/api/auth/me" | jq -r .id)"
UID_B="$(curl -fsS -b "$JAR_B" "$BASE_URL/api/auth/me" | jq -r .id)"
info "教师 A=$TEACHER_A ｜ 教师 B=$TEACHER_B"

api() { curl -fsS -b "$1" "${@:2}"; }
code() { curl -s -o /dev/null -w '%{http_code}' -b "$1" "${@:2}"; }
body() { curl -s -b "$1" "${@:2}"; }

new_thread() { api "$1" -X POST "$BASE_URL/api/threads" | jq -r .id; }
run_status() { api "$1" "$BASE_URL/api/runs/$2" | jq -r .status; }

wait_status() {
    local jar="$1" run_id="$2" want="$3" deadline=$((SECONDS + ${4:-$RUN_WINDOW}))
    while (( SECONDS < deadline )); do
        [[ $(run_status "$jar" "$run_id") == "$want" ]] && return 0
        sleep 3
    done
    return 1
}

# ------------------------------------------------------------------ ④ 越权一律 404
log "④ 越权一律 404（不是 403）—— 四条路径，管理员也不例外"

before=$failed
THREAD_A="$(new_thread "$JAR_A")"
# 直接写库造一个 A 的 run，避免为了验越权而烧一次真实分析。
# **id 在这一侧发**：psql 的 RETURNING 会把 `INSERT 0 1` 那行状态一起吐出来粘在后面
RUN_A="$(cat /proc/sys/kernel/random/uuid | tr -d -)"
psql_query "INSERT INTO runs (id, thread_id, user_id, status, tokens_cache_read, tokens_uncached, tokens_output, started_at)
    VALUES ('$RUN_A', '$THREAD_A', '$UID_A', 'succeeded', 0,0,0, now());" >/dev/null

for path in "/api/runs/$RUN_A" "/api/runs/$RUN_A/events" "/api/artifacts/$THREAD_A/chart.png"; do
    got="$(code "$JAR_B" "$BASE_URL$path")"
    [[ $got == 404 ]] && pass "B 读 A 的 $path → 404" || fail "B 读 A 的 $path → $got（403 也算未过）"
done
got="$(code "$JAR_B" -X POST "$BASE_URL/api/threads/$THREAD_A/runs" -H 'Content-Type: application/json' -d '{"content":"借你的会话一用"}')"
[[ $got == 404 ]] && pass "B 往 A 的会话提交 → 404" || fail "B 往 A 的会话提交 → $got"

if [[ -n $ADMIN_PASSWORD ]] && SECRET="$ADMIN_PASSWORD" login "$ADMIN_NAME" "$JAR_ADMIN" 2>/dev/null; then
    got="$(code "$JAR_ADMIN" "$BASE_URL/api/runs/$RUN_A")"
    [[ $got == 404 ]] && pass "管理员读 A 的 run → 404（管理员不例外）" \
        || fail "管理员读 A 的 run → $got —— 数据层出现了绕过过滤的旁路"
else
    info "没给 ADMIN_PASSWORD，改用一个新建的 admin 账号验「管理员不例外」"
    ADMIN_PROBE="p3-admin-$STAMP"
    make_user "$ADMIN_PROBE" admin
    login "$ADMIN_PROBE" "$JAR_ADMIN" && {
        got="$(code "$JAR_ADMIN" "$BASE_URL/api/runs/$RUN_A")"
        [[ $got == 404 ]] && pass "管理员读 A 的 run → 404（管理员不例外）" \
            || fail "管理员读 A 的 run → $got —— 数据层出现了绕过过滤的旁路"
    }
fi
(( failed == before )) && VERDICT[4]=通过 || VERDICT[4]=未过

# ------------------------------------------------------------------ ⑤ 三道闸
log "⑤ 三道闸都关得上，且三个 429 可区分"

before=$failed
# **整段先把 worker 停掉**：这一节里有一次提交会被放行（验 cache_read 不计入配额），
# worker 在跑的话它就是一次真实分析 —— 既花钱，又让紧接着那条「waiting_approval
# 不占并发」数到一个 running。这一节不需要 worker
compose stop worker >/dev/null 2>&1
THREAD_B="$(new_thread "$JAR_B")"

# token 配额：**预置用量**，不靠真烧。烧满一个真实日配额又慢又贵，
# 而这条要验的是闸门与扣减口径，不是模型
psql_query "INSERT INTO runs (id, thread_id, user_id, status, tokens_cache_read, tokens_uncached, tokens_output, started_at)
    VALUES (gen_random_uuid(), '$THREAD_B', '$UID_B', 'succeeded', 0, 9999999, 0, now());" >/dev/null
quota_body="$(body "$JAR_B" -X POST "$BASE_URL/api/threads/$THREAD_B/runs" -H 'Content-Type: application/json' -d '{"content":"这一条该被配额拦住"}')"
[[ $(jq -r .error.code <<<"$quota_body") == QUOTA_EXCEEDED ]] \
    && pass "token 日配额耗尽 → QUOTA_EXCEEDED" || fail "配额那道闸没关上：$quota_body"

# cache_read 不计入：把同样大的用量改成「命中」，同一次提交就该放行。
# 按 input 总数扣会高估约 1.6 倍，且方向性地惩罚长会话 —— 扣错方向比扣错数值严重
psql_query "UPDATE runs SET tokens_cache_read = tokens_uncached, tokens_uncached = 0
            WHERE user_id='$UID_B' AND tokens_uncached > 1000000;" >/dev/null
got="$(code "$JAR_B" -X POST "$BASE_URL/api/threads/$THREAD_B/runs" -H 'Content-Type: application/json' -d '{"content":"命中的那份不该算进配额"}')"
[[ $got == 202 ]] && pass "cache_read 不计入配额（改成命中后同一次提交放行）" \
    || fail "cache_read 被算进了配额：提交返回 $got"
psql_query "UPDATE runs SET tokens_cache_read = 0 WHERE user_id='$UID_B';" >/dev/null

# 并发：塞满 teacher 档位（默认 3）
for _ in 1 2 3; do
    psql_query "INSERT INTO runs (id, thread_id, user_id, status, tokens_cache_read, tokens_uncached, tokens_output, started_at)
        VALUES (gen_random_uuid(), '$THREAD_B', '$UID_B', 'queued', 0,0,0, now());" >/dev/null
done
concurrency_body="$(body "$JAR_B" -X POST "$BASE_URL/api/threads/$THREAD_B/runs" -H 'Content-Type: application/json' -d '{"content":"这一条该被并发拦住"}')"
[[ $(jq -r .error.code <<<"$concurrency_body") == CONCURRENCY_LIMIT ]] \
    && pass "并发 run 超限 → CONCURRENCY_LIMIT" || fail "并发那道闸没关上：$concurrency_body"

# waiting_approval 不占并发（架构 §5.4）
psql_query "UPDATE runs SET status='waiting_approval' WHERE user_id='$UID_B' AND status='queued';" >/dev/null
active="$(psql_query "SELECT count(*) FROM runs WHERE user_id='$UID_B' AND status IN ('queued','running');" | tr -d '[:space:]')"
[[ $active == 0 ]] && pass "waiting_approval 不占并发配额（活跃计数 0）" \
    || fail "waiting_approval 占了并发：活跃计数 $active"
psql_query "UPDATE runs SET status='cancelled' WHERE user_id='$UID_B' AND status='waiting_approval';" >/dev/null

# 接口频率：默认 120 次/分钟
rate_code=""
for _ in $(seq 1 140); do
    rate_code="$(code "$JAR_B" "$BASE_URL/api/runs/00000000000000000000000000000000")"
    [[ $rate_code == 429 ]] && break
done
rate_body="$(body "$JAR_B" "$BASE_URL/api/runs/00000000000000000000000000000000")"
[[ $(jq -r .error.code <<<"$rate_body") == RATE_LIMITED ]] \
    && pass "接口频率超限 → RATE_LIMITED" || fail "限流那道闸没关上：$rate_body"

info "【观察项】三个 429 的 code 各自出现过才算通过 —— 只给 HTTP 429 前端分不出该做哪一件事"

# 收尾：把这一节造的行清干净，否则它们会占着 B 的名额影响后面几条
psql_query "DELETE FROM runs WHERE user_id='$UID_B';" >/dev/null
(( failed == before )) && VERDICT[5]=通过 || VERDICT[5]=未过

# 限流窗口是滑动的，等它滑过去再往下跑，免得后面几条被自己刚打的那波拦住
sleep 62

# ------------------------------------------------------------------ ⑥ 主动取消
log "⑥ 主动取消停得下来，且 checkpoint 保住"

before=$failed
# **先停 worker 再提交**：让 run 停在 queued，这条就不必烧一次真实分析。
# 「跑到一半取消」由 test/run/executor_test.py 精确覆盖（定点在 step 边界上）
compose stop worker >/dev/null 2>&1
THREAD_C="$(new_thread "$JAR_A")"
RUN_C="$(api "$JAR_A" -X POST "$BASE_URL/api/threads/$THREAD_C/runs" -H 'Content-Type: application/json' \
    -d '{"content":"取消验收：worker 已停，这一条停在 queued"}' | jq -r .id)"

cancel_body="$(body "$JAR_A" -X POST "$BASE_URL/api/runs/$RUN_C/cancel")"
[[ $(jq -r .status <<<"$cancel_body") == cancelled ]] && pass "排队中的 run 取消后转 cancelled" \
    || fail "取消没生效：$cancel_body"

flag="$(compose exec -T redis redis-cli EXISTS "zuel:cancel:$RUN_C" | tr -d '[:space:]')"
[[ $flag == 1 ]] && pass "取消标志已写进 Redis（worker 在 step 边界上读它）" || fail "取消标志没写上"

cancelled_events="$(timeout 20 curl -fsS -N -b "$JAR_A" "$BASE_URL/api/runs/$RUN_C/events" | grep -c '^event: run.cancelled')"
[[ $cancelled_events == 1 ]] && pass "推出且只推出一条 run.cancelled" || fail "run.cancelled 有 $cancelled_events 条"

# 幂等：再取消一次不报错，也不多推一条事件
again="$(code "$JAR_A" -X POST "$BASE_URL/api/runs/$RUN_C/cancel")"
[[ $again == 202 ]] && pass "重复取消是幂等的（202）" || fail "重复取消返回 $again"

# worker 起来之后不该再跑它 —— 任务消息还躺在队列里
compose start worker >/dev/null 2>&1
sleep 20
final="$(run_status "$JAR_A" "$RUN_C")"
burned="$(psql_query "SELECT tokens_uncached + tokens_output FROM runs WHERE id='$RUN_C';" | tr -d '[:space:]')"
[[ $final == cancelled && $burned == 0 ]] \
    && pass "worker 领到那条消息后直接收手：仍是 cancelled，token 消耗为 0" \
    || fail "取消的 run 又被跑了：状态 $final，消耗 $burned"
(( failed == before )) && VERDICT[6]=通过 || VERDICT[6]=未过

# ------------------------------------------------------------------ ③ 并发不串数据
log "③ $CONCURRENCY 并发不崩溃、不串数据"

before=$failed
# **不投真任务**：$CONCURRENCY 次真实分析就是 $CONCURRENCY 份钱。这里压的是隔离与
# 会话创建这条链路 —— 「不串数据」正是这一条的重点，而它与模型无关
CONCURRENT_OUT="$(mktemp -d)"
for index in $(seq 1 "$CONCURRENCY"); do
    (
        jar="$CONCURRENT_OUT/jar-$index"
        cp "$JAR_A" "$jar"
        thread="$(curl -fsS -b "$jar" -X POST "$BASE_URL/api/threads" | jq -r .id)"
        echo "$thread" > "$CONCURRENT_OUT/thread-$index"
    ) &
done
wait

created="$(cat "$CONCURRENT_OUT"/thread-* 2>/dev/null | grep -c . || true)"
unique="$(cat "$CONCURRENT_OUT"/thread-* 2>/dev/null | sort -u | wc -l)"
[[ $created == "$CONCURRENCY" && $unique == "$CONCURRENCY" ]] \
    && pass "$CONCURRENCY 并发建会话：全部成功且互不相同" \
    || fail "并发建会话：成功 $created 个、互异 $unique 个（期望各 $CONCURRENCY）"

owner_count="$(psql_query "SELECT count(DISTINCT user_id) FROM threads WHERE id IN ($(cat "$CONCURRENT_OUT"/thread-* | sed "s/.*/'&'/" | paste -sd,));" | tr -d '[:space:]')"
[[ $owner_count == 1 ]] && pass "并发下每个会话都只挂在一个主人身上（没串）" \
    || fail "并发建出的会话分属 $owner_count 个主人 —— 数据串了"

leaked="$(code "$JAR_B" "$BASE_URL/api/artifacts/$(head -1 "$CONCURRENT_OUT/thread-1")/chart.png")"
[[ $leaked == 404 ]] && pass "并发之后 B 仍够不着 A 的会话" || fail "并发之后越权检查失效：$leaked"
rm -rf "$CONCURRENT_OUT"
(( failed == before )) && VERDICT[3]=通过 || VERDICT[3]=未过

# ------------------------------------------------------------------ ① 审批四种决策
log "① 四种决策各走一遍（要 LLM，有费用）"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    info "SKIP_LLM=1，跳过"
    VERDICT[1]="未验（SKIP_LLM=1）"
else
    before=$failed
    # **脚本得知道自己在造场景**：P0 实测 agent 一次都没自发调过 delete，
    # 等它自己撞上来是等不到的
    for decision in approve reject edit respond; do
        thread="$(new_thread "$JAR_A")"
        curl -fsS -b "$JAR_A" -X POST "$BASE_URL/api/threads/$thread/files" \
            -F "file=@$REPO_ROOT/README.md" >/dev/null 2>&1 || true
        run_id="$(api "$JAR_A" -X POST "$BASE_URL/api/threads/$thread/runs" -H 'Content-Type: application/json' \
            -d '{"content":"请把工作目录下的 README.md 删掉，用 delete 工具，删完告诉我一声就行。"}' | jq -r .id)"

        if ! wait_status "$JAR_A" "$run_id" waiting_approval "$SETTLE_WINDOW"; then
            fail "$decision：run 没停在 waiting_approval（当前 $(run_status "$JAR_A" "$run_id")）"
            continue
        fi
        case $decision in
            approve) payload='{"decisions":[{"index":0,"type":"approve"}]}' ;;
            reject) payload='{"decisions":[{"index":0,"type":"reject","message":"这个文件不能删"}]}' ;;
            edit) payload='{"decisions":[{"index":0,"type":"edit","edited_action":{"name":"delete","args":{"file_path":"/workspace/outputs/nothing.txt"}}}]}' ;;
            respond) payload='{"decisions":[{"index":0,"type":"respond","message":"我已经手工删过了"}]}' ;;
        esac
        # **批到终态为止，不是只批一轮。** 一次 run 可以中断多次 —— 实测 `edit` 就是：
        # 教师把删除目标改成一个不存在的文件，agent 拿到结果之后又提了一次删除请求。
        # 第一轮用被测的那种决策，之后若还有中断一律 approve，让它走到终态；
        # 被测的仍是那一种决策的恢复路径
        round=0
        while (( round < APPROVE_ROUND )); do
            [[ $(run_status "$JAR_A" "$run_id") == waiting_approval ]] || break
            (( round == 0 )) && this="$payload" || this='{"decisions":[{"index":0,"type":"approve"}]}'
            got="$(code "$JAR_A" -X POST "$BASE_URL/api/runs/$run_id/approve" -H 'Content-Type: application/json' -d "$this")"
            [[ $got == 202 ]] || { fail "$decision：第 $((round + 1)) 轮审批回传返回 $got"; break; }
            round=$((round + 1))
            # 等它离开 waiting_approval：要么跑到终态，要么再提一次审批
            deadline=$((SECONDS + RUN_WINDOW))
            while (( SECONDS < deadline )); do
                [[ $(run_status "$JAR_A" "$run_id") == queued || $(run_status "$JAR_A" "$run_id") == running ]] || break
                sleep 3
            done
        done

        settled="$(run_status "$JAR_A" "$run_id")"
        if [[ $settled == succeeded ]]; then
            pass "$decision：审批 $round 轮之后跑到 succeeded"
        else
            fail "$decision：审批 $round 轮之后仍是 $settled（上限 $APPROVE_ROUND 轮）"
        fi

        # 【观察项】记的是**审批探针**的量，不是一次完整分析的量 —— 这一条提交的只是
        # 「把 README.md 删掉」，实测两三百，而 ANALYSIS_TOKEN 是十万量级。
        # **别拿这组数去校准 ANALYSIS_TOKEN**，会把它压低两个数量级；
        # 校准要用的样本是 acceptance.sh 末尾那行「token 口径按 cache 拆分」
        used="$(psql_query "SELECT tokens_uncached, tokens_output FROM runs WHERE id='$run_id';" | tr -d '[:space:]')"
        info "【观察项】$decision 这次审批探针的未命中 token / output：$used（探针量级，非分析量级）"
    done

    # index 校验：缺失与重复都要 VALIDATION_ERROR
    thread="$(new_thread "$JAR_A")"
    run_id="$(api "$JAR_A" -X POST "$BASE_URL/api/threads/$thread/runs" -H 'Content-Type: application/json' \
        -d '{"content":"请用 delete 工具删掉 /workspace/nothing.txt。"}' | jq -r .id)"
    if wait_status "$JAR_A" "$run_id" waiting_approval "$SETTLE_WINDOW"; then
        dup="$(body "$JAR_A" -X POST "$BASE_URL/api/runs/$run_id/approve" -H 'Content-Type: application/json' \
            -d '{"decisions":[{"index":0,"type":"approve"},{"index":0,"type":"approve"}]}')"
        [[ $(jq -r .error.code <<<"$dup") == VALIDATION_ERROR ]] \
            && pass "重复的 index → VALIDATION_ERROR" || fail "重复的 index 没被拒：$dup"
        curl -fsS -b "$JAR_A" -X POST "$BASE_URL/api/runs/$run_id/cancel" >/dev/null
    else
        fail "index 校验：run 没停在 waiting_approval"
    fi
    (( failed == before )) && VERDICT[1]=通过 || VERDICT[1]=未过
fi

# ------------------------------------------------------------------ ② 幂等键
log "② 定点注入的崩溃：恢复后写操作不重复执行"

before=$failed
# **定点注入而不是随机时机**：P2 量了两轮，两轮的刀都落在两次工具之间，
# 差值都是 0 —— 那证明不了幂等键有效，只证明没砍到。
# 这里直接对 broker 重放同一个 (thread_id, checkpoint_ns)，那正是崩溃恢复会做的事
IDEMPOTENT="$(in_api_python '
import httpx, uuid

thread = uuid.uuid4().hex
ns = "tools:" + uuid.uuid4().hex
with httpx.Client(base_url="http://broker:8100", timeout=60) as c:
    c.post("/threads", json={"thread_id": thread}).raise_for_status()
    c.post(f"/threads/{thread}/tool/write", json={"file_path": "/workspace/x.csv", "content": "a,b\n"}).raise_for_status()
    keyed = {"file_path": "/workspace/x.csv", "checkpoint_ns": ns}
    first = c.post(f"/threads/{thread}/tool/delete", json=keyed).json()
    replayed = c.post(f"/threads/{thread}/tool/delete", json=keyed).json()
    bare = c.post(f"/threads/{thread}/tool/delete", json={"file_path": "/workspace/x.csv"}).json()
print("同" if first == replayed else "异", "有错" if bare["error"] else "无错")
' | tr -d '\r')"

if [[ $IDEMPOTENT == "同 有错" ]]; then
    pass "带幂等键重放拿到首次的结果；不带键重放则拿到首次执行没有的错误 —— 去重确实在起作用"
    VERDICT[2]=通过
else
    fail "幂等键没起作用：$IDEMPOTENT（期望「同 有错」）"
    VERDICT[2]=未过
fi

# ------------------------------------------------------------------ ⑦ P2 回归
log "⑦ P2 验收六条不回归"

if [[ ${SKIP_P2:-0} == 1 ]]; then
    info "SKIP_P2=1，跳过"
    VERDICT[7]="未验（SKIP_P2=1）"
elif SKIP_LLM="${SKIP_LLM:-0}" BASE_URL="$BASE_URL" bash "$REPO_ROOT/deploy/test/p2.sh"; then
    VERDICT[7]=通过
else
    if [[ $? == 2 ]]; then
        VERDICT[7]="未验（P2 内部有条目被跳过）"
    else
        VERDICT[7]=未过; failed=$((failed + 1))
    fi
fi

# ------------------------------------------------------------------ 结果
log "P3 验收七条"
DESCRIPTION=(
    [1]="四种决策各走一遍，run 都跑到终态"
    [2]="定点注入的崩溃：写操作不重复执行"
    [3]="$CONCURRENCY 并发不崩溃、不串数据"
    [4]="越权一律 404（管理员不例外）"
    [5]="三道闸关得上且三个 429 可区分"
    [6]="主动取消停得下来"
    [7]="P2 验收六条不回归"
)
for index in 1 2 3 4 5 6 7; do
    case "${VERDICT[$index]:-未验}" in
        通过) printf '  \033[32m✅ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        未过) printf '  \033[31m❌ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        *) printf '  \033[33m⚠️  %s %s —— %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" "${VERDICT[$index]:-未验}" ;;
    esac
done

if (( failed )); then
    printf '\n\033[31mP3 验收未全过。\033[0m\n'
    exit 1
fi
for index in 1 2 3 4 5 6 7; do
    [[ ${VERDICT[$index]:-未验} == 通过 ]] && continue
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定 P3 验收通过。\033[0m\n'
    exit 2
done
printf '\n\033[32mP3 验收七条全过。\033[0m\n'
