#!/usr/bin/env bash
#
# P2 验收六条，一条命令跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/p2.sh
#
# 分工：②③⑥ 本脚本自己验（全部免费）；① 与 ④ 要**真实调用 DeepSeek**，有费用；
# ⑤ 委托 p1.sh 做 P1 回归（它自己再往下委托 hostile.sh 与 acceptance.sh）。
#
# 想省时省钱可以 SKIP_LLM=1 / SKIP_P1=1，但**跳过的条目在结果表里记「未验」
# 而不是「通过」** —— 静默跳过的门禁等于没有门禁。
#
# 本脚本以普通用户跑，与 p1.sh 同一个理由：以 root 跑会把会话目录建成 root 属主。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"
COMPOSE_PROJECT=zuel-platform

# 崩溃恢复的观察窗口，秒。要大于 WORKER_CLAIM_IDLE_MILLISECOND（默认 60 秒）
# 再加一次沙箱申请与一轮模型调用的时间
RECOVER_WINDOW=300

# 探针用的任务条数。要多于 worker 副本数，才看得出「分给了谁」
PROBE_TASK=6

# 等第一条 tool_result 最多等多久，秒。等到它才动刀，见 ① 处说明
KILL_WINDOW=180

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
# **累加而不是置 1**：下面每段都用 `before=$failed` 判断「本段有没有新的失败」，
# 置 1 的话，前面已经红过一次之后这个判断就永远成立，后面每一段都会被记成通过
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=$((failed + 1)); }
info() { printf '     %s\n' "$*"; }

failed=0
declare -A VERDICT=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# 在 api 容器里跑一段 Python。**用容器里的运行时而不是宿主机的**：连接串、库版本、
# 网络位置都要与真正跑着的进程一致，否则验的是另一套东西
in_api_python() { compose exec -T api python -c "$1"; }

worker_ids() {
    docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        --filter label=com.docker.compose.service=worker
}

# 等到某个 worker 副本重新起来。**不能只数进程数**：被 kill -9 之后 compose 会立刻
# 重建，而重建中的容器已经能被 docker ps 数到，却还没连上 Redis
wait_worker() {
    local want="$1" deadline=$((SECONDS + 120))
    while (( SECONDS < deadline )); do
        if [[ $(worker_ids | wc -l) -ge $want ]] &&
            compose logs --since 2m worker 2>/dev/null | grep -q "worker 开始领任务"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

run_status() { curl -fsS -b "$JAR" "$BASE_URL/api/runs/$1" | jq -r .status; }

# ------------------------------------------------------------------ 前置检查
log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done

# 与 p1.sh 同一套：从跑着的 broker 身上读回 compose 的必填插值，不让人记着 export
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

# P3 之后 /api/* 一律要会话 cookie。**重启不影响它**：session 存在 Redis 里，
# 而 ② 重启的是 api / worker / broker 三个进程，Redis 不在其中
source "$REPO_ROOT/deploy/test/session.sh"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT
USER_ID="$(zuel_open_session "$JAR")" || { echo "造不出账号或登不进去，①② 验不了" >&2; exit 1; }

WORKER_COUNT="$(worker_ids | wc -l)"
(( WORKER_COUNT >= 2 )) || { echo "worker 副本不足两个（当前 $WORKER_COUNT），③ 验不了" >&2; exit 1; }
info "网关 $BASE_URL ｜ worker 副本 $WORKER_COUNT 个"

# ------------------------------------------------------------------ ⑥ 事件 id 契约
# 放在最前面：它最便宜，而且后面几条都建立在「id 还是那个形状」之上
log "⑥ 换成真 Redis Stream 之后，事件 id 的形状没变"

ID_PROBE=$(in_api_python '
import asyncio, re, uuid
from api.platform import build_platform
from config import get_settings
from event.model import TokenData, TokenEvent

async def main():
    platform = await build_platform(get_settings())
    run_id = uuid.uuid4().hex
    logged = await platform.log.append(TokenEvent(ts=1, run_id=run_id, path=(), data=TokenData(text="探针")))
    replayed = await platform.log.read(run_id, after=logged.id)
    await platform.engine.dispose()
    await platform.cache.aclose()
    print(logged.id, "空" if not replayed else "非空")

asyncio.run(main())
') || ID_PROBE=""

if [[ $ID_PROBE =~ ^[0-9]+-[0-9]+\ 空$ ]]; then
    pass "id 仍是 {毫秒}-{序号}，且「读 id 之后」返回空 —— Last-Event-ID 的语义没变：$ID_PROBE"
    VERDICT[6]=通过
else
    fail "事件 id 契约变了：${ID_PROBE:-探针没跑起来}"
    VERDICT[6]=未过
fi

# ------------------------------------------------------------------ ③ 两副本的消费语义
# **不投真任务**：真任务会触发 LLM，六条就是六份钱。这里用一个独立的 group 与独立的
# 流做探针，跑的是 TaskQueue 那几十行本身 —— ADR-0005 点名要自己保证正确性的正是它们。
# 带 LLM 的端到端并发由 ④ 覆盖
log "③ 两个消费者并行领任务：不重复、不丢"

CONSUME_PROBE=$(in_api_python "
import asyncio, uuid
from config import get_settings
from store import redis as store_redis
from task import queue as q

async def main():
    settings = get_settings()
    client = store_redis.create_client(settings.redis_url)
    stream, group = q.TASK_STREAM, q.CONSUMER_GROUP
    # 换掉模块常量，探针因此走完全同一份代码，却不碰生产的那条流
    q.TASK_STREAM = f'zuel:probe:task:{uuid.uuid4().hex}'
    q.CONSUMER_GROUP = 'zuel:probe'
    try:
        first = q.TaskQueue(client, consumer='probe-a', block_millisecond=100)
        second = q.TaskQueue(client, consumer='probe-b', block_millisecond=100)
        await first.ensure_group()
        published = [q.RunTask(run_id=uuid.uuid4().hex, thread_id=uuid.uuid4().hex, content=str(i))
                     for i in range($PROBE_TASK)]
        for task in published:
            await first.publish(task)
        taken = []
        for _ in range($PROBE_TASK):
            for one in (first, second):
                got = await one.reserve()
                if got is not None:
                    taken.append(got.task.run_id)
                    await one.ack(got.id)
        await client.delete(q.TASK_STREAM)
        print(len(taken), len(set(taken)), len({t.run_id for t in published} - set(taken)))
    finally:
        q.TASK_STREAM, q.CONSUMER_GROUP = stream, group
        await client.aclose()

asyncio.run(main())
") || CONSUME_PROBE=""

read -r took distinct missing <<<"${CONSUME_PROBE:-0 0 $PROBE_TASK}"
if [[ $took == "$PROBE_TASK" && $distinct == "$PROBE_TASK" && $missing == 0 ]]; then
    pass "$PROBE_TASK 条任务分给两个消费者：领到 $took 条、互不重复、一条不丢"
    VERDICT[3]=通过
else
    fail "消费语义不对：领到 $took 条、去重后 $distinct 条、丢了 $missing 条"
    VERDICT[3]=未过
fi

# ------------------------------------------------------------------ ② 三个进程全部重启
# 「会话历史能接上追问」那一半要真实模型，并进 ① 一起验；这里验免费的两样：
# run 的终态与事件流的补齐。这两样正是本期从 api 内存里搬走的东西
log "② 三个进程全部重启后，run 的终态与事件流都还在"

# **会话行要真建，不能随手编一个 id**：P3 给 runs 加了指向 users 与 threads 的外键，
# 编出来的 id 会被数据库当场拒掉。这里走接口建，与教师用的是同一条路径
SEED_THREAD="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads" | jq -r .id)"
[[ -n $SEED_THREAD && $SEED_THREAD != null ]] || SEED_THREAD=""

SEED=""
[[ -z $SEED_THREAD ]] || SEED=$(in_api_python "
import asyncio, uuid
from api.platform import build_platform
from config import get_settings
from event.model import RunFinishedData, RunFinishedEvent, TokenData, TokenEvent

async def main():
    platform = await build_platform(get_settings())
    run_id, thread_id = uuid.uuid4().hex, '$SEED_THREAD'
    await platform.repository.create(run_id=run_id, thread_id=thread_id, user_id='$USER_ID')
    first = await platform.log.append(
        TokenEvent(ts=1, run_id=run_id, path=(), data=TokenData(text='重启前'))
    )
    await platform.log.append(RunFinishedEvent(ts=2, run_id=run_id, path=(), data=RunFinishedData()))
    from event.model import TokenUsage
    await platform.repository.succeed(run_id, tokens=TokenUsage())
    await platform.engine.dispose()
    await platform.cache.aclose()
    print(run_id, first.id)

asyncio.run(main())
") || SEED=""

read -r SEED_RUN SEED_CURSOR <<<"${SEED:-}"
if [[ -z ${SEED_RUN:-} ]]; then
    fail "种子 run 没造出来，② 验不了"
    VERDICT[2]=未过
else
    info "种子 run $SEED_RUN，游标 $SEED_CURSOR"
    compose restart api worker broker >/dev/null 2>&1
    wait_worker "$WORKER_COUNT" || info "worker 重启后没在日志里报「开始领任务」，继续验但结果存疑"
    for _ in $(seq 30); do curl -fsS "$BASE_URL/docs" >/dev/null 2>&1 && break; sleep 2; done

    before=$failed
    status="$(run_status "$SEED_RUN" 2>/dev/null)"
    [[ $status == succeeded ]] && pass "GET /runs/{id} 仍答得出终态：$status" \
        || fail "重启后 run 的终态丢了：${status:-查不到}"

    # 带上游标重连：补齐的应该只有游标之后那一条，一条不多一条不少
    replayed="$(curl -fsS -b "$JAR" -N -H "Last-Event-ID: $SEED_CURSOR" \
        "$BASE_URL/api/runs/$SEED_RUN/events" 2>/dev/null | grep -c '^event:')"
    [[ $replayed == 1 ]] && pass "Last-Event-ID 仍能补齐：补了 $replayed 条，正是游标之后那一条" \
        || fail "重启后事件流补不齐：补了 ${replayed:-0} 条，应为 1 条"

    (( failed == before )) && VERDICT[2]=通过 || VERDICT[2]=未过
fi

# ------------------------------------------------------------------ ① kill -9 worker 后续跑
log "① kill -9 worker 之后，任务从 checkpoint 续跑而不是重跑"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    VERDICT[1]="未验（SKIP_LLM=1）"
    info "已跳过 —— 这条要真实调用 DeepSeek"
else
    THREAD_ID="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads" | jq -r .id)"
    RUN_ID="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads/$THREAD_ID/runs" \
        -H 'Content-Type: application/json' \
        -d '{"content":"用 Python 生成 200 个正态分布随机数，算均值与标准差，再画一张直方图存到 outputs/"}' \
        | jq -r .id)"
    info "run $RUN_ID 已提交，等它真的开跑再动手"

    # 等到 running 才 kill：还在 queued 时杀掉，验的是「重投」而不是「续跑」
    for _ in $(seq 60); do
        [[ $(run_status "$RUN_ID") == running ]] && break
        sleep 2
    done

    # **等第一条 tool_result 出现再动手，不用固定 sleep。** 这一刻两个条件同时成立：
    # 至少有一个 checkpoint 可以续，而 run 还没跑完 —— 刀正好落在中间。
    #
    # 固定 sleep 赌不赢：这道题在 prompt 缓存热的时候十几秒就跑完了，2026-08-08
    # 实测等满 20 秒与等满 10 秒各有一次砍空。**砍空不会报错**，它只会让这条验收
    # 什么都没验着，而判据若不识别这种情况就会把它记成通过
    timeout "$KILL_WINDOW" curl -fsS -b "$JAR" -N "$BASE_URL/api/runs/$RUN_ID/events" 2>/dev/null \
        | grep -q -m1 '^event: tool_result'

    VICTIM="$(worker_ids | head -1)"
    docker kill -s KILL "$VICTIM" >/dev/null 2>&1
    info "已 kill -9 worker $VICTIM，等另一个副本认领（阈值 60 秒）"

    before=$failed
    deadline=$((SECONDS + RECOVER_WINDOW))
    final=""
    while (( SECONDS < deadline )); do
        final="$(run_status "$RUN_ID" 2>/dev/null)"
        [[ $final == succeeded || $final == failed ]] && break
        sleep 5
    done
    [[ $final == succeeded ]] && pass "崩溃后 run 仍跑到 succeeded" || fail "崩溃后 run 没跑完：${final:-无状态}"

    EVENTS="$(curl -fsS -b "$JAR" -N "$BASE_URL/api/runs/$RUN_ID/events" 2>/dev/null \
        | grep '^data: ' | sed 's/^data: //')"

    # **判据不再数 `run.started` 的条数。** 数条数（无论数总数还是数 `"resumed":false`）
    # 都是代理指标，而它两头都会骗人，2026-08-08 一次验收里两种错都撞上了：
    #
    # - **假过**：run 在 kill 真正生效前就跑完了，重投撞上「已经有终态」的守卫、不再发
    #   `run.started` —— 于是只有 1 条，判据记通过。可这次**根本没崩到**，什么都没验着。
    # - **假红**：真崩了并且正确续跑（崩溃前四次工具调用一次都没重跑，续跑那程只花了
    #   1529 未命中 token），但重投照样发一条 `run.started`，且 `resumed` 按定义是
    #   `task.decisions is not None` —— 它只标「审批之后的续跑」，崩溃恢复本来就是 false。
    #
    # 改成直接断言那件要验的事，并且**先证明崩到了**：没崩到就记未验，不许记通过。
    starts="$(jq -s '[.[] | select(.type=="run.started")] | length' <<<"$EVENTS")"

    # 崩溃前已经成功返回过的 (工具名, 参数)，在崩溃之后不得再出现一次 ——
    # 这就是「已完成的步骤不重跑」的字面意思，不经任何代理
    repeated="$(jq -s '
        . as $all
        | [$all | to_entries[] | select(.value.type == "run.started") | .key] as $starts
        | if ($starts | length) < 2 then -1
          else
            $starts[1] as $cut
            | [$all[:$cut][] | select(.type == "tool_result") | .data.tool_call_id] as $done
            | [$all[:$cut][]
               | select(.type == "tool_call" and (.data.id | IN($done[])))
               | {name: .data.name, args: (.data.args | tostring)}] as $finished
            | [$all[$cut:][]
               | select(.type == "tool_call")
               | {name: .data.name, args: (.data.args | tostring)}]
            | map(select(IN($finished[])))
            | length
          end' <<<"$EVENTS")"

    # **砍空记「未验」而不是「未过」。** 与「跳过的条目记未验」是同一条规矩的另一半：
    # 没触发到要测的场景，既算不上失败，更算不上通过 —— 记成失败会让人去查一个
    # 并不存在的 bug，记成通过则等于这条门禁不存在
    NOT_LANDED=0
    if (( starts < 2 )); then
        NOT_LANDED=1
        info "这一次 kill 没砍到：run 在它生效前就跑完了（run.started 只有 $starts 条）"
        info "崩溃恢复没发生，这条**没验着**（既不是通过也不是失败）—— 重跑一次即可"
    elif (( repeated == 0 )); then
        pass "真崩了（run.started $starts 条）且崩前已完成的工具一次都没重跑"
    else
        fail "崩溃后重跑了 $repeated 次崩前就已经成功的工具调用 —— 这是重跑不是续跑"
    fi

    # 观察项，不设门槛（计划 §4）：崩溃恢复时工具重复执行了几次
    tool_call="$(jq -s '[.[] | select(.type == "tool_call")] | length' <<<"$EVENTS")"
    tool_result="$(jq -s '[.[] | select(.type == "tool_result")] | length' <<<"$EVENTS")"
    info "【观察项】工具调用 $tool_call 次、返回 $tool_result 次 —— 差值即崩在工具执行途中的重跑次数"
    info "【观察项】这个数是 P2 §7 那项「幂等键先量后定」的输入，请记进计划文档"

    # **`docker kill` 不会触发 restart 策略**：守护进程把外部下的 kill 记成「人为停止」，
    # 从此不再自动拉起。真崩溃（进程自己死在容器里）走的是另一条路，`unless-stopped` 照常生效 ——
    # 所以这里副本没回来不说明策略有问题，手工拉一把，好让后面几条仍在满编下跑
    compose up -d --no-recreate worker >/dev/null 2>&1
    wait_worker "$WORKER_COUNT" || info "worker 没回到 $WORKER_COUNT 个副本，后面几条会在减员状态下跑"
    if (( failed != before )); then
        VERDICT[1]=未过
    elif (( NOT_LANDED )); then
        VERDICT[1]="未验（这轮 kill 没砍到，重跑一次）"
    else
        VERDICT[1]=通过
    fi
fi

# ------------------------------------------------------------------ ④ P0 回归
log "④ P0 验收四条经新架构重跑"
if [[ ${SKIP_LLM:-0} == 1 ]]; then
    VERDICT[4]="未验（SKIP_LLM=1）"
    info "已跳过 —— 这条要真实调用 DeepSeek"
elif BASE_URL="$BASE_URL" bash "$REPO_ROOT/deploy/test/acceptance.sh"; then
    VERDICT[4]=通过
else
    VERDICT[4]=未过; failed=1
fi

# ------------------------------------------------------------------ ⑤ P1 回归
log "⑤ P1 验收六条不回归"
if [[ ${SKIP_P1:-0} == 1 ]]; then
    VERDICT[5]="未验（SKIP_P1=1）"
    info "已跳过"
elif SKIP_LLM="${SKIP_LLM:-0}" SKIP_HOSTILE="${SKIP_HOSTILE:-0}" \
    BASE_URL="$BASE_URL" bash "$REPO_ROOT/deploy/test/p1.sh"; then
    VERDICT[5]=通过
else
    # p1.sh 用退出码 2 表示「已验的都过了，但有条目未验」
    if [[ $? == 2 ]]; then
        VERDICT[5]="未验（P1 内部有条目被跳过）"
    else
        VERDICT[5]=未过; failed=1
    fi
fi

# ------------------------------------------------------------------ 结果
log "P2 验收六条"
DESCRIPTION=(
    [1]="kill -9 worker 后从 checkpoint 续跑，不是重跑"
    [2]="三进程重启后 run 终态与事件流都还在"
    [3]="两个消费者并行不重复也不丢"
    [4]="P0 验收四条经新架构全过"
    [5]="P1 验收六条不回归"
    [6]="事件 id 契约不变"
)
for index in 1 2 3 4 5 6; do
    case "${VERDICT[$index]}" in
        通过) printf '  \033[32m✅ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        未过) printf '  \033[31m❌ %s %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" ;;
        *) printf '  \033[33m⚠️  %s %s —— %s\033[0m\n' "$index" "${DESCRIPTION[$index]}" "${VERDICT[$index]}" ;;
    esac
done

if (( failed )); then
    printf '\n\033[31mP2 验收未全过。\033[0m\n'
    exit 1
fi
for index in 1 2 3 4 5 6; do
    [[ ${VERDICT[$index]} == 通过 ]] && continue
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定 P2 验收通过。\033[0m\n'
    exit 2
done
printf '\n\033[32mP2 验收六条全过。\033[0m\n'
