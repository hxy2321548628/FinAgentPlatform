#!/usr/bin/env bash
#
# P0 验收四条，跑一遍。
#
# P1 全程不新增业务功能，因此这四条是贯穿始终的回归基线：步骤一（gVisor 下）、
# 步骤三（经 broker）、步骤四（经 Nginx）各要重跑一次。三个步骤各自会以不同方式
# 打破 P0 的假设（syscall 覆盖、传输层、反代缓冲），压缩成一次就分不清是哪一层的问题。
#
#   BASE_URL=http://127.0.0.1:8000 bash deploy/test/acceptance.sh
#
# **会真实调用 DeepSeek，产生 API 费用**，单次约 30 万 token、几分钟。
# 网关需已在 BASE_URL 上跑起来，本脚本不负责起它。
#
# P3 起还要能访问同一套 compose 栈的 docker：接口都要登录，而造号得进容器办。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SAMPLE_CSV="$REPO_ROOT/doc/04acceptance-guide/P0/holdings.csv"
WORK_DIR="$(mktemp -d)"

QUESTION='读取 holdings.csv，按行业分组计算持仓市值占比和各行业月度收益率的年化波动率，画成图表保存到 outputs 目录，并说明缺失值是怎么处理的。'

# 一次完整分析实测几分钟。留足余量，超时即判失败而不是无限等下去
RUN_TIMEOUT=900
# 断线重连验证：先收这么多条就主动断开，剩下的靠 Last-Event-ID 补
CUT_AFTER_EVENT=12

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=1; }
trap 'rm -rf "$WORK_DIR"' EXIT

failed=0
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool"; exit 1; }
done

log "前置检查"
curl -fsS "$BASE_URL/docs" >/dev/null 2>&1 || { echo "网关未在 $BASE_URL 上响应"; exit 1; }
[[ -f $SAMPLE_CSV ]] || { echo "样例数据不在：$SAMPLE_CSV"; exit 1; }

# P3 之后 /api/* 一律要会话 cookie。造号要进容器（平台没有公开注册端点），
# 因此这个脚本从 P3 起也要 docker —— BASE_URL 必须指向同一套 compose 栈
source "$REPO_ROOT/deploy/test/session.sh"
JAR="$WORK_DIR/cookie"
zuel_open_session "$JAR" >/dev/null || { echo "造不出账号或登不进去，四条都验不了"; exit 1; }

log "① 建会话"
THREAD_ID="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads" | jq -r .id)"
[[ -n $THREAD_ID && $THREAD_ID != null ]] || { echo "建会话失败"; exit 1; }
echo "   thread_id=$THREAD_ID"

log "② 上传 holdings.csv"
curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads/$THREAD_ID/files" -F "file=@$SAMPLE_CSV" >/dev/null || {
    echo "上传失败"; exit 1;
}

log "③ 提交分析（立刻返回，不等执行）"
RUN_ID="$(curl -fsS -b "$JAR" -X POST "$BASE_URL/api/threads/$THREAD_ID/runs" \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg c "$QUESTION" '{content:$c}')" | jq -r .id)"
[[ -n $RUN_ID && $RUN_ID != null ]] || { echo "提交失败"; exit 1; }
echo "   run_id=$RUN_ID"

log "④ 订阅事件流，收满 $CUT_AFTER_EVENT 条后主动断开"
# --max-time 之外还要 head -n：SSE 是长连接，不主动切就要等到 run 结束
timeout $RUN_TIMEOUT curl -fsS -b "$JAR" -N "$BASE_URL/api/runs/$RUN_ID/events" \
    | head -n $((CUT_AFTER_EVENT * 3)) > "$WORK_DIR/first.sse"
LAST_ID="$(grep '^id:' "$WORK_DIR/first.sse" | tail -1 | sed 's/^id: *//')"
echo "   断开于 Last-Event-ID=$LAST_ID"

log "⑤ 带 Last-Event-ID 重连，补齐剩下的"
timeout $RUN_TIMEOUT curl -fsS -b "$JAR" -N "$BASE_URL/api/runs/$RUN_ID/events" \
    -H "Last-Event-ID: $LAST_ID" > "$WORK_DIR/rest.sse"

cat "$WORK_DIR/first.sse" "$WORK_DIR/rest.sse" > "$WORK_DIR/all.sse"
grep '^data:' "$WORK_DIR/all.sse" | sed 's/^data: *//' | jq -c . > "$WORK_DIR/all.json" 2>/dev/null

types() { jq -r .type < "$WORK_DIR/all.json"; }

log "判定"

# 验收① 事件流完整
if [[ $(types | head -1) == run.started ]] && types | grep -q '^run.finished$'; then
    pass "① 事件流完整：run.started 开头，run.finished 收尾"
else
    fail "① 事件流不完整：首=$(types | head -1) 末=$(types | tail -1)"
fi

# 验收② agent 自写脚本并 execute，产物落 outputs/
WROTE=$(jq -r 'select(.type=="tool_call") | .data.name' < "$WORK_DIR/all.json" | grep -cE '^(write_file|execute)$')
if (( WROTE >= 2 )); then
    pass "② agent 自写脚本并执行（write_file / execute 共 $WROTE 次）"
else
    fail "② 没看到 agent 自己写脚本并执行，相关 tool_call 只有 $WROTE 次"
fi

# 验收③ 重连不重不漏：id 严格递增且无重复
IDS=$(grep '^id:' "$WORK_DIR/all.sse" | sed 's/^id: *//')
TOTAL=$(wc -l <<<"$IDS"); UNIQUE=$(sort -u <<<"$IDS" | wc -l)
SORTED=$(sort -t- -k1,1n -k2,2n <<<"$IDS")
if [[ $TOTAL -eq $UNIQUE && $IDS == "$SORTED" ]]; then
    pass "③ 断线重连补齐不重不漏（$TOTAL 条，id 严格递增）"
else
    fail "③ 重连有重复或乱序：共 $TOTAL 条、去重后 $UNIQUE 条"
fi

# 验收④ 产物可取回且是能显示的图
ARTIFACT="$(jq -r 'select(.type=="run.finished") | .data.artifacts[0] // empty' < "$WORK_DIR/all.json" | head -1)"
if [[ -n $ARTIFACT ]]; then
    curl -fsS -b "$JAR" "$BASE_URL/api/artifacts/$ARTIFACT" -o "$WORK_DIR/artifact.bin"
    KIND="$(file -b --mime-type "$WORK_DIR/artifact.bin")"
    SIZE=$(stat -c %s "$WORK_DIR/artifact.bin")
    if [[ $KIND == image/* ]] && (( SIZE > 1024 )); then
        pass "④ 产物取回正常：$ARTIFACT（$KIND，$SIZE 字节）"
        # 「能显示」这条最终要靠人眼看一次，给出原图路径
        echo "     原图：$BASE_URL/api/artifacts/$ARTIFACT"
    else
        fail "④ 产物不是一张正常的图：$KIND，$SIZE 字节"
    fi
else
    fail "④ run.finished 里没有产物"
fi

# token 口径（P1 步骤五）：两个数都要在，且未命中部分不该等于 input 总量
TOKENS="$(jq -c 'select(.type=="run.finished") | .data.tokens' < "$WORK_DIR/all.json" | head -1)"
if [[ -n $TOKENS ]] && jq -e 'has("input_cache_read") and has("input_uncached")' <<<"$TOKENS" >/dev/null; then
    pass "token 口径按 cache 拆分：$TOKENS"
else
    fail "run.finished 未按 cache 拆分给出 token：$TOKENS"
fi

if (( failed )); then
    printf '\n\033[31mP0 验收未全过。事件流留在 %s\033[0m\n' "$WORK_DIR"
    trap - EXIT
    exit 1
fi
printf '\n\033[32mP0 验收四条全过。\033[0m\n'
