#!/usr/bin/env bash
#
# 平台回归验收：P0–P4 的 22 条判据，一个文件跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   export SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$(pwd)/data/sandbox")"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/verify.sh
#
# 常用跑法：
#
#   bash deploy/test/verify.sh                             # 全部（要 sudo，有 LLM 费用）
#   SKIP_LLM=1 SKIP_HOSTILE=1 bash deploy/test/verify.sh   # 只跑免费的 14 条，约 12 分钟
#
# **默认全跑，不分 phase，也没有挑某一期跑的参数** —— P6 决策 §L2 的定案。
# 保留的是 `SKIP_LLM` / `SKIP_HOSTILE` 两个开关：它们分的是**成本**（要不要花钱、
# 要不要 root），不是期次。按期挑着跑，等于把刚拆掉的那层级联结构又装回来，
# 还多一条「以为全验了其实只验了一期」的路。
#
# 22 条里 **8 条要花钱或要 root**：P0 那五条各是一次完整分析上读出来的、
# P2① 与 P3① 各要一次真实分析、P1① 那四条破坏性测试要 root。其余 14 条全免费。
#
# ---------------------------------------------------------------------------
# **为什么合成一个文件**（2026-08-13，取代 p1/p2/p3/p4 + acceptance + hostile + session
# 七个）：原来是逐级转调 —— `p4.sh` 调 `p3.sh` 调 `p2.sh` 调 `p1.sh` 调
# `acceptance.sh` 与 `hostile.sh`。代价有三：
#
#   1. **六条「判据」其实只是转调**。P1②⑤、P2④⑤、P3⑦、P4⑧ 都是「去跑另一个脚本」，
#      它们在结果表里占着位置却不验任何东西。合并之后这六条消失 —— **不是删了判据，
#      是删了转调**：它们指向的那些判据仍逐条在下面跑。
#   2. **同一件事抄了四遍且各抄各的**。前置检查、插值回读、造号登录在四个脚本里
#      各有一份，而它们已经不一致了：查几个服务、BASE_URL 默认多少、要不要冒烟
#      `compose exec`，四份四个样。见下面「一并修掉的漂移」。
#   3. **转调层每多一级就多一次「未验」的翻译**。退出码 2 要在每一级重新解释一遍，
#      而中间任何一级漏掉这个翻译，「未验」就会被当成「通过」。
#
# **一并修掉的漂移**：
#
#   - `acceptance.sh` 的 `BASE_URL` 默认还是 `http://127.0.0.1:8000`，而 compose
#     根本不给 api 映射端口 —— 照 CLAUDE.md 抄那行命令一定在前置检查就退出。
#   - 前置检查四份四个样：`p1.sh` 只查 nginx 与 api（可它要读 worker 日志、要 broker），
#     `p2.sh` / `p3.sh` 查五个漏了 broker，只有 `p4.sh` 查全六个、也只有它冒烟
#     `compose exec`。现在一份，六个服务全查。
#   - `hostile.sh` 的 workspace 默认值是 `<仓库>/data/sandbox`，而 `.env.example`
#     写的是 `/data/sandbox` —— 两个默认值指着不同的地方。沙箱那几项配置现在一律
#     从跑着的 broker 身上读回来，不再有第二份默认值。
#   - **`p1.sh` 那句 `sudo -E bash hostile.sh` 在默认 sudoers 下必然当场失败**：
#     `env_reset` 而没有 SETENV 时，`sudo -E` 与 `sudo VAR=val` 一律被拒
#     （本机实测「抱歉，您无权保留环境」）—— 而失败会被结果表记成「未过」，
#     成了一条永远红的判据。破坏性那一组的参数改走命令行。
#   - `session.sh` 造号时 `ON CONFLICT (name) DO NOTHING` 而不回读，撞名时静默什么
#     都不做，失败要等到登录那一步 —— 报出来的是「登不进去」，指向登录而非造号。
#   - `p4.sh` 建会话时发 `{"title":"…"}`，而 `POST /api/threads` 根本不收请求体
#     （标题由第一次提问之后的一次轻量模型调用填上）—— 那个字段一直在空转。
#   - P3 的三道闸与取消两节会 `compose stop worker`，中途失败就把 worker 留在停止
#     状态，**污染之后每一次跑法**。现在收尾统一把它拉回来。
#
# ---------------------------------------------------------------------------
# **判据编号沿用各期计划 §4 的编号**（`P1③`、`P2①`…），好让结果表与计划文档对得上。
# 断号就是上面说的那六条转调，不是漏了。
#
# **跳过的条目在结果表里记「未验」而不是「通过」** —— 静默跳过的门禁等于没有门禁。
# 退出码：0 全过；1 有未过；2 已验的都过了但有条目未验。
#
# **本脚本以普通用户跑**，只在破坏性那一组用 sudo 重入自己。以 root 跑会把会话目录
# 建成 root 属主，那正是 P1 栽过两次的坑。
#
# **别与别的东西抢这套栈。** 下面几组会 kill broker、重启三个进程、停 worker、
# 压限流 —— 同时有人在用的话双方都红，且红在互不相干的地方。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yml"
COMPOSE_PROJECT=zuel-platform
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-80}}"

# 破坏性那四条要 root，其余一律不能用 root 跑。一个文件里同时满足两者的办法：
# 主流程跑到那一步时用 sudo 重入本文件，只跑那一段
HOSTILE_ENTRY=--hostile-only

# ---- P0：一次真实分析 ------------------------------------------------------
# 样例持仓数据。**`tmp/` 被 .gitignore 忽略**，新克隆的仓库里没有它 ——
# 缺了就把 P0 整组记「未验」，而不是让整轮验收退出
SAMPLE_CSV="${SAMPLE_CSV:-$REPO_ROOT/tmp/holdings.csv}"
QUESTION='读取 holdings.csv，按行业分组计算持仓市值占比和各行业月度收益率的年化波动率，画成图表保存到 outputs 目录，并说明缺失值是怎么处理的。'
# 一次完整分析实测几分钟。留足余量，超时即判失败而不是无限等下去
RUN_TIMEOUT=900
# 断线重连验证：先收这么多条就主动断开，剩下的靠 Last-Event-ID 补
CUT_AFTER_EVENT=12

# ---- P1：心跳与沙箱池 ------------------------------------------------------
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
# P3 步骤七给租约记了名：申请沙箱要说明「谁在用」。两次申请用同一个持有者 ——
# P1④ 验的正是 broker 重启认领之后同一个持有者再申请仍是原来那个容器
HOLDER='{"holder":"zuel-regression"}'

# ---- P2：崩溃恢复 ----------------------------------------------------------
# 崩溃恢复的观察窗口，秒。要大于 WORKER_CLAIM_IDLE_MILLISECOND（默认 60 秒）
# 再加一次沙箱申请与一轮模型调用的时间
RECOVER_WINDOW=300
# 探针用的任务条数。要多于 worker 副本数，才看得出「分给了谁」
PROBE_TASK=6
# 等第一条 tool_result 最多等多久，秒。等到它才动刀，见 P2① 处说明
KILL_WINDOW=180

# ---- P3：隔离、配额与审批 --------------------------------------------------
# 一次真实分析跑完的观察窗口，秒
RUN_WINDOW=600
# 压测并发数
CONCURRENCY=30
# 教师看到中断之后等多久点确认 —— 脚本这一侧不需要真等，取一个够 worker 落状态的数
SETTLE_WINDOW=120
# 一个 run 最多批几轮。**一次 run 可以中断多次**：教师改过参数之后 agent 可能再提
# 一次敏感调用。上限是防跑飞，不是判据 —— 到了上限还没终态就算未过
APPROVE_ROUND=4
# 限流窗口是滑动的（默认 60 秒）。压完限流要等它滑过去，免得后面几条被自己打的那波拦住
RATE_WINDOW_SETTLE=62

# ---- 破坏性四条 ------------------------------------------------------------
# 宿主机指标的容忍带。跑测试期间机器上还有别的东西在动，要求分毫不差只会得到假失败
MEMORY_TOLERANCE_MB=2048
DISK_TOLERANCE_MB=2048
PROCESS_TOLERANCE=100
# 每条测试用一个自己的 workspace，前缀统一好一起清 —— 只留一个变量的话，
# 每次覆盖它，最后只有最后一条的目录被清掉，前面的连同几 GB 数据留在盘上
WORKSPACE_PREFIX=zuel-hostile

# ===========================================================================
# 输出与记分
# ===========================================================================

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
# **累加而不是置 1**：每条判据都用「本段有没有新的失败」来定性，
# 置 1 的话，前面已经红过一次之后这个判断就永远成立，后面每一条都会被记成通过
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=$((failed + 1)); }
info() { printf '     %s\n' "$*"; }

failed=0
CHECK_ORDER=()
declare -A CHECK_NAME=()
declare -A CHECK_VERDICT=()
CURRENT=""
CURRENT_BASE=0

# 开一条判据。之后的 pass / fail 都算在它头上
begin() {
    CURRENT="$1"
    CHECK_ORDER+=("$1")
    CHECK_NAME[$1]="$2"
    CHECK_VERDICT[$1]=""
    CURRENT_BASE=$failed
    log "$1 $2"
}

# 这条没验着。**「未验」不是「通过」也不是「未过」** —— 记成通过等于这道门禁不存在，
# 记成未过会让人去查一个并不存在的 bug。
#
# **已经红过的条目不许改记未验**：那会把一次真实的失败洗成「没跑」。
# 这一条是 P2① 特有的形状 —— 它可能先断言失败、再发现这轮 kill 根本没砍到
undone() {
    if (( failed != CURRENT_BASE )); then
        info "本条已有失败，不改记未验（$1）"
        return 0
    fi
    CHECK_VERDICT[$CURRENT]="未验（$1）"
    info "未验：$1"
}

# 收一条判据。undone 已经定过性的就不覆盖
end() {
    [[ -n ${CHECK_VERDICT[$CURRENT]} ]] && return 0
    if (( failed == CURRENT_BASE )); then
        CHECK_VERDICT[$CURRENT]=通过
    else
        CHECK_VERDICT[$CURRENT]=未过
    fi
    return 0
}

# ===========================================================================
# docker / compose 小工具
# ===========================================================================

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
in_api() { compose exec -T api "$@"; }
in_broker() { compose exec -T broker "$@"; }
# 在 api 容器里跑一段 Python。**用容器里的运行时而不是宿主机的**：连接串、库版本、
# 网络位置都要与真正跑着的进程一致，否则验的是另一套东西
in_api_python() { compose exec -T api python -c "$1"; }
psql_query() { compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"; }

# 按 compose 标签找容器。**不走 `docker compose`**：它一读配置就要求 SANDBOX_USER
# 等插值变量已经 export，而前置检查正是要从容器身上把那些值读回来 —— 走 compose
# 就成了先有鸡还是先有蛋
container_of() {
    docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        --filter "label=com.docker.compose.service=$1"
}
broker_container() { container_of broker | head -1; }
worker_ids() { container_of worker; }

# 从某个容器的环境里取一项。**平台真正在用的值只有这一个来源** ——
# 在脚本里另设默认值的话，猜错了不会报错，只会让验收在错的目标上跑
env_of() {
    local id="$1" key="$2"
    docker inspect "$id" --format '{{range .Config.Env}}{{println .}}{{end}}' |
        grep -m1 "^$key=" | cut -d= -f2-
}

sandbox_of() { docker ps --filter "label=zuel.thread=$1" --format '{{.ID}}' | head -1; }
managed_count() { docker ps -q --filter label=zuel.sandbox | wc -l; }

# broker 不对外暴露端口（ADR-0004），只能从它自己的容器里够着。镜像里没有 curl，
# 用现成的 httpx
broker_call() {
    local method="$1" path="$2" payload="${3:-}"
    in_broker python -c "
import sys, httpx
payload = '''$payload'''
extra = {'json': __import__('json').loads(payload)} if payload else {}
with httpx.stream('$method', 'http://127.0.0.1:8100$path', timeout=None, **extra) as response:
    body = ''.join(response.iter_text())
if response.status_code >= 400:
    sys.exit(f'{response.status_code} {body}')
print(body)
"
}

# 等 broker 真的能干活。`$1` 是不接受的旧容器 id：重建时旧容器要先优雅退出，
# 那段时间里它还在跑、`/docs` 还答得动 —— 只探端口的话会探到一个正在关闭的进程，
# 紧接着的请求就 500。这个坑让 P1⑤ 假失败过一次
wait_broker() {
    local stale="${1:-}" deadline=$((SECONDS + 60)) current
    while (( SECONDS < deadline )); do
        current="$(broker_container)"
        if [[ -n $current && $current != "$stale" ]] &&
            in_broker python -c "import httpx; httpx.get('http://127.0.0.1:8100/docs', timeout=2)" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# 等某个 worker 副本重新起来。**不能只数进程数**：被 kill -9 之后 compose 会立刻
# 重建，而重建中的容器已经能被 docker ps 数到，却还没连上 Redis
wait_worker() {
    local expect="$1" deadline=$((SECONDS + 120))
    while (( SECONDS < deadline )); do
        if [[ $(worker_ids | wc -l) -ge $expect ]] &&
            compose logs --since 2m worker 2>/dev/null | grep -q "worker 开始领任务"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# ===========================================================================
# 账号（原 session.sh）
# ===========================================================================
#
# **要 docker**：平台没有公开的注册端点（建号是管理员的事），所以造号得进 api 容器
# 算口令哈希、进 postgres 插行。BASE_URL 必须指向同一套 compose 栈。

# 口令哈希由 api 容器里的 PasswordHasher 算，与登录校验用的是同一套参数 ——
# 在外面另算一份就等于把参数抄了第二遍。
#
# **插完回读一次**：撞名时 ON CONFLICT 什么都不做而 psql 照样退 0，
# 失败要等到登录那一步才现形 —— 那时报出来的是「登不进去」，指向登录而不指向造号
make_user() {
    local name="$1" password="$2" role="${3:-teacher}" hashed exist
    hashed="$(in_api python -c "
from auth.password import PasswordHasher
print(PasswordHasher().hash('$password'))" | tr -d '\r')"
    [[ -n $hashed ]] || { echo "算不出口令哈希，api 容器有问题" >&2; return 1; }
    psql_query "INSERT INTO users (id, name, password_hash, role, is_active, created_at)
         VALUES (gen_random_uuid(), '$name', '$hashed', '$role', true, now())
         ON CONFLICT (name) DO NOTHING;" >/dev/null
    exist="$(psql_query "SELECT count(*) FROM users WHERE name = '$name';" | tr -d '[:space:]')"
    [[ $exist == 1 ]] || { echo "账号 $name 没建出来（库里有 ${exist:-?} 行）" >&2; return 1; }
}

login() {
    local name="$1" password="$2" jar="$3"
    curl -fsS -c "$jar" -o /dev/null -X POST "$BASE_URL/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$name" --arg p "$password" '{name:$n,password:$p}')"
}

# 造号 + 登录，cookie 落进 $1，标准输出是这个号的 user_id。
#
# 失败时返回非零且不输出 —— 调用方据此提前退出，而不是拿着空 id 一路验到底：
# 没有号的话后面每一条都会红成 401，红的原因看不出是「登录没成」还是「功能坏了」
open_session() {
    local jar="$1" role="${2:-teacher}" tag="${3:-any}"
    local name="zuel-$tag-$$-$(date +%s%N | tail -c 7)"
    local password="zuel-secret-$$"
    local user_id
    make_user "$name" "$password" "$role" || return 1
    login "$name" "$password" "$jar" || return 1
    # 管道的退出码是 jq 的：curl 挂了 jq 照样以 0 收场，只是吐出空串。
    # 不显式查一下的话，调用方会拿着空 id 一路走到某个不相干的地方才报错
    user_id="$(curl -fsS -b "$jar" "$BASE_URL/api/auth/me" | jq -r '.id // empty')"
    [[ -n $user_id ]] || return 1
    printf '%s\n' "$user_id"
}

# **每组一个新号**，不跨组复用：配额与限流都是按用户按天算的，共用一个号会让一组
# 用掉的余量落到另一组头上，而症状是莫名其妙的 429。
#
# **结果放全局而不是 echo 出来**：`x="$(session_for p2)"` 会把函数放进子 shell 跑，
# 缓存与 user_id 全丢在那里面 —— 调用方拿到 jar 却拿不到 user_id
declare -A GROUP_UID=()
SESSION_JAR=""
SESSION_UID=""
session_for() {
    # **两条 local，不能并成一条**：`local a=$1 b=$a` 里 `$a` 是在 local 执行**之前**
    # 就展开的（builtin 的参数先展开），set -u 下当场报「未绑定的变量」
    local group="$1"
    local jar="$WORK_DIR/cookie-$group"
    if [[ -z ${GROUP_UID[$group]:-} ]]; then
        GROUP_UID[$group]="$(open_session "$jar" teacher "$group")" || return 1
    fi
    SESSION_JAR="$jar"
    SESSION_UID="${GROUP_UID[$group]}"
}

# ===========================================================================
# 破坏性四条（要 root，由主流程用 sudo 重入本文件跑）
# ===========================================================================
#
# **验的是「宿主机没事」，不是「沙箱里的命令失败了」** —— 后者太容易蒙对：
# 命令因为任何理由报错都会让一个只看退出码的检查通过。因此每条都先记基线再跑，
# 跑完比对宿主机的可用内存、可用磁盘与进程数。

free_memory_mb() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }
free_disk_mb() { df -m --output=avail "$WORKSPACE_ROOT" | tail -1 | tr -d ' '; }
process_count() { ps -e --no-headers | wc -l; }

hostile_cleanup() {
    [[ -n ${CONTAINER:-} ]] && docker rm -f "$CONTAINER" >/dev/null 2>&1
    rm -rf "${WORKSPACE_ROOT:?}/$WORKSPACE_PREFIX"-*
    fstrim "$WORKSPACE_ROOT" >/dev/null 2>&1
    return 0
}

# 起一个与平台完全同款的沙箱：加固参数照 app/sandbox/container.py 的 Hardening
start_sandbox() {
    local thread_id="$1" projid
    WORKSPACE="$WORKSPACE_ROOT/$WORKSPACE_PREFIX-$thread_id"
    rm -rf "$WORKSPACE"; mkdir -p "$WORKSPACE"
    # 这一组以 root 跑，建出来的目录是 root 属主，而沙箱以调用者的 uid 跑 ——
    # 不改属主，容器里 dd 会得到 Permission denied，看起来像配额生效实际是没权限。
    # 平台自己跑时目录属主本就是平台用户，这是本组独有的问题
    chown "$SANDBOX_OWNER" "$WORKSPACE"

    # 配额照 app/sandbox/quota.py 的派生方式算，保证测的是平台真正会用的那个 id
    projid=$(python3 -c "import zlib,sys; print(zlib.crc32(sys.argv[1].encode()) % 0x7FFFFFFF + 1)" "$thread_id")
    xfs_quota -x -c "project -s -p $WORKSPACE $projid" "$WORKSPACE_ROOT" >/dev/null
    xfs_quota -x -c "limit -p bhard=$DISK_QUOTA $projid" "$WORKSPACE_ROOT" >/dev/null

    CONTAINER=$(docker run -d --rm --pull=never \
        --runtime=runsc --network=none --read-only \
        --tmpfs "/tmp:rw,noexec,nosuid,size=$TMP_SIZE" \
        --cap-drop=ALL --security-opt=no-new-privileges \
        --memory=2g --cpus=1 --pids-limit="$PIDS_LIMIT" \
        --user "$SANDBOX_OWNER" \
        -v "$WORKSPACE:/workspace" -w /workspace -e HOME=/tmp \
        "$SANDBOX_IMAGE" sleep infinity)
}

sandbox_exec() { timeout 180 docker exec "$CONTAINER" bash -o pipefail -c "$1" 2>&1 | head -c 4000; }

# 参数：workspace 根、镜像、磁盘限额、tmpfs 大小、pids 上限、沙箱属主。
#
# **一项都不走环境变量。** `sudo -E` 与 `sudo VAR=val` 都要 sudoers 里给 SETENV，
# 而默认的 `env_reset` 下两者一律被拒（本机实测：「抱歉，您无权保留环境」）——
# 原来 `p1.sh` 那句 `sudo -E bash hostile.sh` 因此在这类机器上必然当场失败，
# 而结果表把它记成「未过」，成了一条永远红的判据。命令行参数没有这个限制。
#
# **也一项默认值都不在这里设**：这几个数由主流程问 broker 自己的 Settings 要，
# 在这里另猜一份的话，验的可能是另一个目录、另一个限额，而它照样绿
run_hostile_group() {
    local mount_info base_memory base_disk base_process
    local now_memory now_disk now_process cpu out written_mb host_out again one

    WORKSPACE_ROOT="${1:-}"
    SANDBOX_IMAGE="${2:-}"
    DISK_QUOTA="${3:-}"
    TMP_SIZE="${4:-}"
    PIDS_LIMIT="${5:-}"
    SANDBOX_OWNER="${6:-}"
    CONTAINER=""
    WORKSPACE=""

    [[ $EUID -eq 0 ]] || { echo "破坏性四条要 root" >&2; return 1; }
    for one in WORKSPACE_ROOT SANDBOX_IMAGE DISK_QUOTA TMP_SIZE PIDS_LIMIT SANDBOX_OWNER; do
        [[ -n ${!one} ]] || { echo "缺参数 $one —— 这一组只能由主流程调起" >&2; return 1; }
    done
    command -v xfs_quota >/dev/null || { echo "缺 xfs_quota，先跑 deploy/setup-xfs.sh" >&2; return 1; }

    # 装了 xfsprogs 不等于 workspace 在带 prjquota 的 XFS 上 —— setup-xfs.sh 挂的 loop
    # 设备**重启后不会自动挂回来**，而那之后这里的每个 limit 都设不上。
    # 不拦的话 ③ 会照着 5g 的限额往宿主机根分区实写 20 GB（三次），最后报一句
    # 「没在限额处停下」—— 真因只出现在 xfs_quota 的 stderr 里，判据本身不指向它。
    # **不能用 `xfs_quota -c state` 探**：它探不到挂载点时照样退出 0，是一条永远绿的判据
    mount_info="$(findmnt -no FSTYPE,OPTIONS --target "$WORKSPACE_ROOT")"
    [[ $mount_info == xfs* && $mount_info == *prjquota* ]] || {
        echo "$WORKSPACE_ROOT 不在带 prjquota 的 XFS 上（现在是 ${mount_info:-未知}）" >&2
        echo "先跑 sudo bash deploy/setup-xfs.sh，再重启 broker 与 nginx 让它们看见新挂载" >&2
        return 1
    }
    docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1 || { echo "缺镜像 $SANDBOX_IMAGE" >&2; return 1; }

    trap hostile_cleanup EXIT

    log "记录宿主机基线"
    base_memory=$(free_memory_mb); base_disk=$(free_disk_mb); base_process=$(process_count)
    info "可用内存 ${base_memory}MB ｜ ${WORKSPACE_ROOT} 可用 ${base_disk}MB ｜ 进程数 ${base_process}"

    # ---------------------------------------------------------------- ① 死循环
    log "① 死循环：被 --cpus=1 限住，只烧掉自己那一份"
    start_sandbox busyloop
    docker exec -d "$CONTAINER" bash -c 'python -c "
while True: pass
"'
    sleep 6
    cpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$CONTAINER" | tr -d '%')
    # docker stats 里 100% 就是一个核；宿主机 16 核跑满会是 1600%
    if awk "BEGIN{exit !($cpu < 150)}"; then
        pass "CPU 占用 ${cpu}%（上限一个核）"
    else
        fail "CPU 占用 ${cpu}%，超出了一个核"
    fi
    docker rm -f "$CONTAINER" >/dev/null; CONTAINER=""

    # -------------------------------------------------------------- ② fork 炸弹
    log "② fork 炸弹：被 --pids-limit=$PIDS_LIMIT 挡住，不拖垮宿主机"
    start_sandbox forkbomb
    sandbox_exec 'python -c "
import os, time
n = 0
while n < 400:
    if os.fork() == 0:
        time.sleep(30)
        os._exit(0)
    n += 1
print(\"未被挡住，创建了\", n, \"个进程\")
"' | tail -2 | sed 's/^/     /'
    sleep 3
    now_process=$(process_count)
    if (( now_process < base_process + PROCESS_TOLERANCE )); then
        pass "宿主机进程数 ${base_process} → ${now_process}，未被拖垮"
    else
        fail "宿主机进程数 ${base_process} → ${now_process}，炸弹漏到宿主机了"
    fi
    docker rm -f "$CONTAINER" >/dev/null 2>&1; CONTAINER=""

    # --------------------------------------------------------- ③ 写满 workspace
    log "③ 写满 /workspace：在 $DISK_QUOTA 处得到 ENOSPC，宿主机磁盘不见少"
    start_sandbox disk
    # dd 的四行输出里，「No space left on device」在**第一行**，后三行是统计。
    # 这里不要再 tail —— 砍掉第一行就等于把唯一的判定依据丢了，配额明明生效也会判失败
    out=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/workspace/fill bs=1M count=20000 2>&1')
    written_mb=$(( $(stat -c %s "$WORKSPACE/fill" 2>/dev/null || echo 0) / 1024 / 1024 ))
    if grep -qi 'no space left' <<<"$out"; then
        pass "在 ${written_mb}MB 处得到 ENOSPC（限额 $DISK_QUOTA）"
    else
        fail "没在限额处停下：实写 ${written_mb}MB ｜ $(tr '\n' ' ' <<<"$out")"
    fi

    # 配额对**文件工具写入**同样生效。文件工具是宿主侧直接写、不进容器的，
    # 绕开了一切容器级限制 —— 这条能成立全靠 project quota 是对目录而非对容器生效
    rm -f "$WORKSPACE/fill"
    host_out=$(LC_ALL=C dd if=/dev/zero of="$WORKSPACE/host-written" bs=1M count=20000 2>&1)
    if grep -qi 'no space left' <<<"$host_out"; then
        pass "宿主侧直接写（文件工具走的这条路）同样被挡住"
    else
        fail "宿主侧直接写没被挡住 ｜ $(tr '\n' ' ' <<<"$host_out")"
    fi
    rm -f "$WORKSPACE/host-written"

    # 容器销毁重建后配额仍在。**重建时不能走 start_sandbox**：它会清掉 workspace
    # 并重设配额，那样验的就成了「刚设的配额生效吗」，而不是「配额熬过了重建吗」
    docker rm -f "$CONTAINER" >/dev/null
    CONTAINER=$(docker run -d --rm --pull=never --runtime=runsc --network=none \
        --user "$SANDBOX_OWNER" -v "$WORKSPACE:/workspace" -w /workspace \
        "$SANDBOX_IMAGE" sleep infinity)
    again=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/workspace/again bs=1M count=20000 2>&1')
    if grep -qi 'no space left' <<<"$again"; then
        pass "容器销毁重建后配额仍在"
    else
        fail "重建后配额没了 ｜ $(tr '\n' ' ' <<<"$again")"
    fi
    docker rm -f "$CONTAINER" >/dev/null 2>&1; CONTAINER=""

    # 先把测试自己写下的 5GB 清掉再量。不清就是拿「测试留下的占用」去指控平台漏磁盘，
    # 量出来的差值恰好等于配额本身
    rm -rf "$WORKSPACE"
    # loop 镜像是稀疏文件，XFS 里删了文件不会自动把洞还给宿主的 ext4。
    # 开发机特有，服务器上是真实分区没这一步
    fstrim "$WORKSPACE_ROOT" >/dev/null 2>&1 || true

    now_disk=$(free_disk_mb)
    if (( now_disk > base_disk - DISK_TOLERANCE_MB )); then
        pass "宿主机可用磁盘 ${base_disk}MB → ${now_disk}MB，回到基线"
    else
        fail "宿主机可用磁盘 ${base_disk}MB → ${now_disk}MB，掉得太多"
    fi

    # -------------------------------------------------------------- ④ 写满 /tmp
    log "④ 写满 /tmp：在 $TMP_SIZE 处得到 ENOSPC，宿主机内存不见少"
    start_sandbox tmp
    out=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/tmp/fill bs=1M count=4096 2>&1')
    if grep -qi 'no space left' <<<"$out"; then
        pass "在 $TMP_SIZE 处得到 ENOSPC（tmpfs 吃的是宿主机内存）"
    else
        fail "tmpfs 没在限额处停下 ｜ $(tr '\n' ' ' <<<"$out")"
    fi
    docker rm -f "$CONTAINER" >/dev/null; CONTAINER=""
    sleep 3

    now_memory=$(free_memory_mb)
    if (( now_memory > base_memory - MEMORY_TOLERANCE_MB )); then
        pass "宿主机可用内存 ${base_memory}MB → ${now_memory}MB，回到基线"
    else
        fail "宿主机可用内存 ${base_memory}MB → ${now_memory}MB，掉得太多"
    fi

    (( failed == 0 )) || return 1
    return 0
}

# 破坏性组是唯一以 root 跑的一段，走独立入口，绕开下面那句「别用 root 跑」
if [[ ${1:-} == "$HOSTILE_ENTRY" ]]; then
    shift
    run_hostile_group "$@"
    exit $?
fi

# ===========================================================================
# 前置检查
# ===========================================================================

log "前置检查"
[[ $EUID -ne 0 ]] || { echo "别用 root 跑：会把会话目录建成 root 属主。sudo 只在破坏性那一组按需提权" >&2; exit 1; }
for tool in jq curl docker; do
    command -v "$tool" >/dev/null || { echo "缺 $tool" >&2; exit 1; }
done

# compose.yml 里 SANDBOX_USER 与 SANDBOX_WORKSPACE_ROOT 是必填插值，两个都没有的话
# 连 `docker compose ps` 都跑不起来。这里**从跑着的 broker 身上读回来**，而不是让人
# 记着 export，也不是在这里另猜一份默认值 —— 猜错的后果是 P1④ 重建 broker 时挂载
# 路径与在跑的那套不一致，而那种错不会报错，只会让验收在错的目标上跑
BROKER_ID="$(broker_container)"
[[ -n $BROKER_ID ]] || {
    cat >&2 <<'TIP'
broker 没在跑。先把栈起起来：

    export SANDBOX_USER="$(id -u):$(id -g)"
    export SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
    export SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$(pwd)/data/sandbox")"
    docker compose -f deploy/compose.yml up -d --build
TIP
    exit 1
}
export SANDBOX_USER="${SANDBOX_USER:-$(env_of "$BROKER_ID" SANDBOX_USER)}"
export SANDBOX_WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$(env_of "$BROKER_ID" SANDBOX_WORKSPACE_ROOT)}"
WORKSPACE_ROOT="$SANDBOX_WORKSPACE_ROOT"
[[ -n $SANDBOX_USER && -n $WORKSPACE_ROOT ]] \
    || { echo "broker 容器里没有 SANDBOX_USER / SANDBOX_WORKSPACE_ROOT，栈不是按文档起的" >&2; exit 1; }

# **六个服务都要在**：原来四个脚本各查各的（有的只查两个、有的漏了 broker），
# 而缺哪一个都会让某几条判据红在与它无关的地方
for service in nginx api worker broker postgres redis; do
    container_of "$service" | grep -q . \
        || { echo "$service 没在跑：docker compose -f deploy/compose.yml up -d --build" >&2; exit 1; }
done
POSTGRES_ID="$(container_of postgres | head -1)"
POSTGRES_USER="${POSTGRES_USER:-$(env_of "$POSTGRES_ID" POSTGRES_USER)}"
POSTGRES_DB="${POSTGRES_DB:-$(env_of "$POSTGRES_ID" POSTGRES_DB)}"

curl -fsS "$BASE_URL/docs" >/dev/null || { echo "Nginx 没把 $BASE_URL 转发通" >&2; exit 1; }

# **`compose exec` 通不通要当场冒烟**：下面大量判据靠它查库、放产物、跑探针。
# 插值缺项时每次 exec 都失败而判据只收到一个空输出 —— 症状是「账对不上」，
# 指向被测的功能而不指向这里。实测栽过一次
compose exec -T postgres true >/dev/null 2>&1 \
    || { echo "compose exec 不通（插值或容器有问题），后面的判据会整片假红" >&2; exit 1; }

# 沙箱那四项**问 broker 自己的 Settings 要**，不去 env 里翻也不在这里另设默认值：
# 容器环境里没有那一项时它用的是代码里的默认值，而在脚本里抄一份代码默认值，
# 就是又开了一处会各自漂移的地方。破坏性那一组照着这几个数造沙箱、判限额，
# 抄错了它照样绿 —— 只是把限额写在提示里骗人
#
# **一行一项，不能挤在一行里按空格切**：`sandbox_disk_quota` 留空是合法配置
# （没挂 XFS 的机器就该留空），而那时一行式的输出会连续两个空格、被 read 折叠掉，
# 于是限额读成了 tmpfs 大小、pids 上限读成了空 —— 错位而不报错
SANDBOX_SETTING="$(in_broker python -c "
from config import get_settings
s = get_settings()
for one in (s.sandbox_image, s.sandbox_disk_quota, s.sandbox_tmp_size, s.sandbox_pids_limit):
    print(one)
")"
{
    read -r SANDBOX_IMAGE
    read -r SANDBOX_DISK_QUOTA
    read -r SANDBOX_TMP_SIZE
    read -r SANDBOX_PIDS_LIMIT
} <<<"$SANDBOX_SETTING"

WORK_DIR="$(mktemp -d)"
WORKER_COUNT="$(worker_ids | wc -l)"
LOG_SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 收尾。**worker 与 broker 都要还原**：P1④⑤ 会把沙箱名额压到 1，
# P3⑤⑥ 会把 worker 停掉 —— 中途失败时不还原的话，这台机器上此后每一次跑法
# 都在一个说不清的状态里起步，而症状不指向上一轮验收
cleanup() {
    [[ -n ${THREAD_HELD:-} ]] && docker rm -f "$(sandbox_of "$THREAD_HELD")" >/dev/null 2>&1
    [[ -n ${BROKER_OVERRIDDEN:-} ]] && compose up -d --no-deps --force-recreate broker >/dev/null 2>&1
    [[ -n ${WORKER_TOUCHED:-} ]] && compose up -d --no-recreate worker >/dev/null 2>&1
    for thread_id in ${THREAD_HELD:-} ${THREAD_QUEUED:-}; do
        rm -rf "${WORKSPACE_ROOT:?}/$thread_id"
    done
    rm -rf "$WORK_DIR"
    return 0
}
trap cleanup EXIT

# 提前把 sudo 凭据取到手。不然密码提示会在十几分钟后、免费的那些都跑完时才冒出来，
# 人早走开了，回来看到的是一个卡在半路的验收
if [[ ${SKIP_HOSTILE:-0} != 1 ]]; then
    sudo -v || { echo "破坏性那一组要 sudo，或用 SKIP_HOSTILE=1 跳过" >&2; exit 1; }
fi

info "网关 $BASE_URL ｜ workspace $WORKSPACE_ROOT ｜ worker 副本 $WORKER_COUNT 个"

# **冒烟造一个号、建一个会话再往下走。** 除破坏性那四条外，每一条判据的第一个动作
# 都是建会话，而它最容易在一个与被测功能毫无关系的地方失败 —— 不拦在这里的话，
# 十几条判据会一起红在各自不同的位置，没有一条指向真因（实测：P4② 会以
# 「api 没回 X-Accel-Redirect」收场，而真相是 thread_id 压根是空的）
session_for smoke || { echo "造不出账号或登不进去 —— 后面每一条都会红成 401" >&2; exit 1; }
SMOKE_THREAD="$(curl -fsS -b "$SESSION_JAR" -X POST "$BASE_URL/api/threads" 2>/dev/null | jq -r '.id // empty')"
[[ -n $SMOKE_THREAD ]] || {
    cat >&2 <<'TIP'
建会话失败（POST /api/threads 没给出 id）。**最常见的原因不是平台坏了**：
XFS prjquota 那个 loop 挂载重启之后不会自动挂回来，而 broker 对配额 fail-closed ——
这时它一律回 500，响应体里只有一句 Internal Server Error，QuotaError 只在日志里。

    sudo bash deploy/setup-xfs.sh
    export SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$(pwd)/data/sandbox")"
    docker compose -f deploy/compose.yml restart broker nginx
    docker ps -q --filter 'name=zuel-sandbox' | xargs -r docker rm -f
TIP
    exit 1
}
curl -fsS -b "$SESSION_JAR" -X DELETE "$BASE_URL/api/threads/$SMOKE_THREAD" >/dev/null 2>&1
info "冒烟：造号、登录、建会话、删会话都通"

# ===========================================================================
# P1：沙箱边界、重启认领、心跳、日志
# ===========================================================================


# ------------------------------------------------------------------ P1③ 边界
# 每条都配一个 broker 上的对照组。只验「api 上失败」的话，二进制不存在、
# 路径拼错、容器没起来都会让它通过 —— 那是三种与边界无关的原因
begin "P1③" "api 拿不到 docker.sock，也看不到宿主 workspace"

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
end

# P1④⑤ 要能用一个沙箱把池占满，所以先把名额压到 1、排队超时压到 90 秒。
#
# **一次性在这里改完，中途不再动 broker**：重建 broker 会让旧进程优雅退出，而优雅退出
# 会走 pool.aclose() 把沙箱全销毁。夹在 ④ 与 ⑤ 之间做这件事，等于在验收半途把
# ④ 刚认领好的容器毁掉，⑤ 再从一个说不清的状态起步
cat > "$WORK_DIR/broker-override.yml" <<YAML
services:
  broker:
    environment:
      SANDBOX_MAX_CONTAINER: "$MAX_CONTAINER"
      SANDBOX_QUEUE_TIMEOUT: "$QUEUE_TIMEOUT"
YAML
BROKER_OVERRIDDEN=1
docker compose -f "$COMPOSE_FILE" -f "$WORK_DIR/broker-override.yml" \
    up -d --no-deps --force-recreate broker >/dev/null 2>&1
wait_broker "$BROKER_ID" \
    || { echo "broker 换配置后没起来：docker compose -f deploy/compose.yml logs broker" >&2; exit 1; }

# 基线在换配置之后才量：上面那次重建会把先前留下的沙箱一并销毁，
# 在它之前量出来的数对不上后面的账
BASE_MANAGED=$(managed_count)
info "已有沙箱 $BASE_MANAGED 个 ｜ 名额临时压到 $MAX_CONTAINER"

session_for p1 || { echo "P1 造不出账号，④⑤ 验不了" >&2; exit 1; }
JAR_P1="$SESSION_JAR"

# -------------------------------------------------------------- P1④ 重启认领
begin "P1④" "broker 崩溃重启后按 label 认领已有容器，不泄漏孤儿"

THREAD_HELD="$(curl -fsS -b "$JAR_P1" -X POST "$BASE_URL/api/threads" | jq -r .id)"
[[ -n $THREAD_HELD && $THREAD_HELD != null ]] || { fail "建会话失败"; THREAD_HELD=""; }

if [[ -n $THREAD_HELD ]]; then
    broker_call POST "/threads/$THREAD_HELD/sandbox" "$HOLDER" >/dev/null || fail "申请沙箱失败"
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

    # start 而不是 up：up 会按 compose.yml 重新算一遍配置，把上面临时压下去的
    # 名额又还原成 20，⑤ 就再也占不满池子了。start 拉起的是同一个容器
    compose start broker >/dev/null 2>&1
    wait_broker || fail "broker 重启后没起来"

    # 用裸 grep 而不是 jq 取 .message：日志是不是 JSON 由 ⑥ 负责断言，
    # 这里再依赖它一次的话，日志格式一坏就会连带谎报「没认领」
    if compose logs broker --since "$LOG_SINCE" --no-log-prefix --no-color 2>/dev/null |
        grep -F '认领重启前的沙箱容器' | grep -q "$THREAD_HELD"; then
        pass "broker 日志里有对该 thread 的认领记录"
    else
        fail "broker 重启后没认领这个容器，它已经是孤儿了"
    fi

    broker_call POST "/threads/$THREAD_HELD/sandbox" "$HOLDER" >/dev/null || fail "认领后再申请失败"
    CONTAINER_AFTER="$(sandbox_of "$THREAD_HELD")"
    NOW_MANAGED=$(managed_count)
    if [[ $CONTAINER_AFTER == "$CONTAINER_BEFORE" ]] && (( NOW_MANAGED == BASE_MANAGED + 1 )); then
        pass "复用的是同一个容器，沙箱总数 $BASE_MANAGED → $NOW_MANAGED，没多出孤儿"
    else
        fail "容器 ${CONTAINER_BEFORE:0:12} → ${CONTAINER_AFTER:0:12}，沙箱总数 $BASE_MANAGED → $NOW_MANAGED"
    fi
fi
end

# ------------------------------------------------------------------ P1⑤ 心跳
begin "P1⑤" "排队静默期 SSE 不被 Nginx 掐断"

RUN_ID=""
# ④ 末尾那次申请已经把唯一的名额占住了（lease=1），这里不必再动 broker。
# 前置任何一步不成，就地判未过收工 —— 硬着头皮往下跑只会拿一个空的 run_id
# 去撞后面三条断言，吐出一串指错方向的红字，还会把 ⑥ 一起拖下水
QUEUED_READY=1
if [[ $(managed_count) -ne $(( BASE_MANAGED + 1 )) ]]; then
    fail "池子没被占满（沙箱 $(managed_count) 个，名额 $MAX_CONTAINER），造不出排队"
    QUEUED_READY=0
fi

if (( QUEUED_READY )); then
    THREAD_QUEUED="$(curl -fsS -b "$JAR_P1" -X POST "$BASE_URL/api/threads" | jq -r .id)"
    RUN_ID="$(curl -fsS -b "$JAR_P1" -X POST "$BASE_URL/api/threads/$THREAD_QUEUED/runs" \
        -H 'Content-Type: application/json' \
        -d '{"content":"这个 run 只用来占住排队位，不会真跑起来。"}' | jq -r .id)"
    [[ -n $RUN_ID && $RUN_ID != null ]] || { fail "提交排队用的 run 失败"; QUEUED_READY=0; RUN_ID=""; }
fi

if (( QUEUED_READY )); then
    info "排队中的 run $RUN_ID，将静默等待约 ${QUEUE_TIMEOUT}s"

    STARTED=$(date +%s)
    timeout "$HEARTBEAT_WINDOW" curl -sS -b "$JAR_P1" -N "$BASE_URL/api/runs/$RUN_ID/events" > "$WORK_DIR/queued.sse"
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
fi
end

# ------------------------------------------------------------------ P1⑥ 日志
begin "P1⑥" "日志是结构化行且带 run_id / thread_id"

# **worker 必须在列**：P2 把执行搬出了 api，一个 run 的绝大多数日志现在产在那边。
# 只看 api 的话，这一条会在平台可观测性完好时照样绿，也会在它坏掉时照样绿
for service in api worker broker; do
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

# 「按 run_id 过滤得出来」要有个 run 才验得了。⑤ 没造出 run 时这里报红的话，
# 红字指向的是日志，真正的毛病却在上一条 —— 那种误导比不报还糟
if [[ -z $RUN_ID ]]; then
    undone "缺 P1⑤ 造出来的 run，按 run_id 过滤这一半无从验起"
else
    # 一个 run 现在跨两个进程：api 收提交与订阅，worker 驱动智能体。任一侧过滤不出行，
    # 「按 run_id 追一次 run 的全过程」就断在进程边界上 —— 而断在哪一侧，排障时天差地别
    for service in api worker; do
        FILTERED=$(jq -sr --arg run "$RUN_ID" '[.[] | select(.run_id == $run)] | length' \
            "$WORK_DIR/$service.log" 2>/dev/null)
        if [[ ${FILTERED:-0} -gt 0 ]]; then
            pass "$service 里按 run_id 过滤出这一次 run 的 $FILTERED 行"
        else
            fail "$service 日志里按 run_id=$RUN_ID 过滤不出任何行"
        fi
    done

    # thread_id 要长在**同一批行**上。分开验的话，某个进程只带 run_id 不带 thread_id 也会全绿，
    # 而「这个会话下的几次 run 都怎么了」正是靠它串起来的
    if jq -se --arg run "$RUN_ID" 'map(select(.run_id == $run)) | length > 0 and all(has("thread_id"))' \
        "$WORK_DIR/api.log" "$WORK_DIR/worker.log" >/dev/null 2>&1; then
        pass "过滤出来的行都带 thread_id"
    else
        fail "按 run_id 过滤出的行里有不带 thread_id 的"
    fi
fi
info "token 按 cache 拆分那半条由 P0⑤ 断言"
end

# 后面几组要用干净的池子，把占位的沙箱与临时配置还回去
[[ -n ${THREAD_HELD:-} ]] && docker rm -f "$(sandbox_of "$THREAD_HELD")" >/dev/null 2>&1
for thread_id in ${THREAD_HELD:-} ${THREAD_QUEUED:-}; do
    rm -rf "${WORKSPACE_ROOT:?}/$thread_id"
done
compose up -d --no-deps --force-recreate broker >/dev/null 2>&1
THREAD_HELD=""; THREAD_QUEUED=""; BROKER_OVERRIDDEN=""

# **必须等 broker 起完再往下走**：上面把它强制重建了，而后面每一组的第一个动作
# 都是建会话 —— api 建会话要调 broker 建目录，打在正启动的 broker 上就是 500。
# 实测这条让 P0 整组红过一次，而报错只说「建会话失败」，不指向重建时序
wait_broker || info "broker 重建后没在 60 秒内应答，后面几组可能会以「建会话失败」收场"


# ===========================================================================
# P2：事件 id 契约、消费语义、重启、崩溃续跑
# ===========================================================================


# -------------------------------------------------------------- P2⑥ 事件 id
# 放在最前面：它最便宜，而且后面几条都建立在「id 还是那个形状」之上
begin "P2⑥" "换成真 Redis Stream 之后，事件 id 的形状没变"

ID_PROBE=$(in_api_python '
import asyncio, uuid
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
else
    fail "事件 id 契约变了：${ID_PROBE:-探针没跑起来}"
fi
end

# ------------------------------------------------------------ P2③ 消费语义
# **不投真任务**：真任务会触发 LLM，六条就是六份钱。这里用一个独立的 group 与独立的
# 流做探针，跑的是 TaskQueue 那几十行本身 —— ADR-0005 点名要自己保证正确性的正是它们。
# 带 LLM 的端到端由 P0 那次完整分析覆盖
begin "P2③" "两个消费者并行领任务：不重复、不丢"

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
else
    fail "消费语义不对：领到 $took 条、去重后 $distinct 条、丢了 $missing 条"
fi
end

session_for p2 || { echo "P2 造不出账号，①② 验不了" >&2; exit 1; }
JAR_P2="$SESSION_JAR"; UID_P2="$SESSION_UID"
p2_status() { curl -fsS -b "$JAR_P2" "$BASE_URL/api/runs/$1" 2>/dev/null | jq -r .status; }

# ---------------------------------------------------------- P2② 三进程重启
# 「会话历史能接上追问」那一半要真实模型，并进 ① 一起验；这里验免费的两样：
# run 的终态与事件流的补齐。这两样正是 P2 从 api 内存里搬走的东西
begin "P2②" "三个进程全部重启后，run 的终态与事件流都还在"

# **会话行要真建，不能随手编一个 id**：P3 给 runs 加了指向 users 与 threads 的外键，
# 编出来的 id 会被数据库当场拒掉。这里走接口建，与教师用的是同一条路径
SEED_THREAD="$(curl -fsS -b "$JAR_P2" -X POST "$BASE_URL/api/threads" | jq -r .id)"
[[ -n $SEED_THREAD && $SEED_THREAD != null ]] || SEED_THREAD=""

SEED=""
[[ -z $SEED_THREAD ]] || SEED=$(in_api_python "
import asyncio, uuid
from api.platform import build_platform
from config import get_settings
from event.model import RunFinishedData, RunFinishedEvent, TokenData, TokenEvent, TokenUsage

async def main():
    platform = await build_platform(get_settings())
    run_id, thread_id = uuid.uuid4().hex, '$SEED_THREAD'
    await platform.repository.create(run_id=run_id, thread_id=thread_id, user_id='$UID_P2')
    first = await platform.log.append(
        TokenEvent(ts=1, run_id=run_id, path=(), data=TokenData(text='重启前'))
    )
    await platform.log.append(RunFinishedEvent(ts=2, run_id=run_id, path=(), data=RunFinishedData()))
    await platform.repository.succeed(run_id, tokens=TokenUsage())
    await platform.engine.dispose()
    await platform.cache.aclose()
    print(run_id, first.id)

asyncio.run(main())
") || SEED=""

read -r SEED_RUN SEED_CURSOR <<<"${SEED:-}"
if [[ -z ${SEED_RUN:-} ]]; then
    fail "种子 run 没造出来，② 验不了"
else
    info "种子 run $SEED_RUN，游标 $SEED_CURSOR"
    WORKER_TOUCHED=1
    compose restart api worker broker >/dev/null 2>&1
    wait_worker "$WORKER_COUNT" || info "worker 重启后没在日志里报「开始领任务」，继续验但结果存疑"
    for _ in $(seq 30); do curl -fsS "$BASE_URL/docs" >/dev/null 2>&1 && break; sleep 2; done

    status="$(p2_status "$SEED_RUN")"
    [[ $status == succeeded ]] && pass "GET /runs/{id} 仍答得出终态：$status" \
        || fail "重启后 run 的终态丢了：${status:-查不到}"

    # 带上游标重连：补齐的应该只有游标之后那一条，一条不多一条不少
    replayed="$(curl -fsS -b "$JAR_P2" -N -H "Last-Event-ID: $SEED_CURSOR" \
        "$BASE_URL/api/runs/$SEED_RUN/events" 2>/dev/null | grep -c '^event:')"
    [[ $replayed == 1 ]] && pass "Last-Event-ID 仍能补齐：补了 $replayed 条，正是游标之后那一条" \
        || fail "重启后事件流补不齐：补了 ${replayed:-0} 条，应为 1 条"
fi
end

# ------------------------------------------------------- P2① kill -9 后续跑
begin "P2①" "kill -9 worker 之后，任务从 checkpoint 续跑而不是重跑"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要真实调用 DeepSeek"
else
    THREAD_P2="$(curl -fsS -b "$JAR_P2" -X POST "$BASE_URL/api/threads" | jq -r .id)"
    RUN_P2="$(curl -fsS -b "$JAR_P2" -X POST "$BASE_URL/api/threads/$THREAD_P2/runs" \
        -H 'Content-Type: application/json' \
        -d '{"content":"用 Python 生成 200 个正态分布随机数，算均值与标准差，再画一张直方图存到 outputs/"}' \
        | jq -r .id)"
    info "run $RUN_P2 已提交，等它真的开跑再动手"

    # 等到 running 才 kill：还在 queued 时杀掉，验的是「重投」而不是「续跑」
    for _ in $(seq 60); do
        [[ $(p2_status "$RUN_P2") == running ]] && break
        sleep 2
    done

    # **等第一条 tool_result 出现再动手，不用固定 sleep。** 这一刻两个条件同时成立：
    # 至少有一个 checkpoint 可以续，而 run 还没跑完 —— 刀正好落在中间。
    #
    # 固定 sleep 赌不赢：这道题在 prompt 缓存热的时候十几秒就跑完了，2026-08-08
    # 实测等满 20 秒与等满 10 秒各有一次砍空。**砍空不会报错**，它只会让这条验收
    # 什么都没验着，而判据若不识别这种情况就会把它记成通过
    timeout "$KILL_WINDOW" curl -fsS -b "$JAR_P2" -N "$BASE_URL/api/runs/$RUN_P2/events" 2>/dev/null \
        | grep -q -m1 '^event: tool_result'

    # **要砍到真正在跑它的那个副本。** 有两个副本，砍「第一个」是在赌五成 ——
    # 2026-08-09 实测赌输一次：刀落在闲着的那个身上，run 在另一个副本上一路跑完，
    # 判据只能记「未验」。结构化日志里带 run_id，按它挑就不必赌
    VICTIM=""
    for candidate in $(worker_ids); do
        if docker logs --since 10m "$candidate" 2>&1 | grep -q "$RUN_P2"; then
            VICTIM="$candidate"
            break
        fi
    done
    if [[ -z $VICTIM ]]; then
        VICTIM="$(worker_ids | head -1)"
        info "日志里认不出哪个副本在跑它，退回砍第一个 —— 这一轮可能砍空"
    fi
    WORKER_TOUCHED=1
    docker kill -s KILL "$VICTIM" >/dev/null 2>&1
    info "已 kill -9 worker $VICTIM，等另一个副本认领（阈值 60 秒）"

    deadline=$((SECONDS + RECOVER_WINDOW))
    final=""
    while (( SECONDS < deadline )); do
        final="$(p2_status "$RUN_P2")"
        [[ $final == succeeded || $final == failed ]] && break
        sleep 5
    done
    [[ $final == succeeded ]] && pass "崩溃后 run 仍跑到 succeeded" || fail "崩溃后 run 没跑完：${final:-无状态}"

    EVENTS="$(curl -fsS -b "$JAR_P2" -N "$BASE_URL/api/runs/$RUN_P2/events" 2>/dev/null \
        | grep '^data: ' | sed 's/^data: //')"

    # **判据不数 `run.started` 的条数。** 数条数（无论数总数还是数 `"resumed":false`）
    # 都是代理指标，而它两头都会骗人，2026-08-08 一次验收里两种错都撞上了：
    #
    # - **假过**：run 在 kill 真正生效前就跑完了，重投撞上「已经有终态」的守卫、不再发
    #   `run.started` —— 于是只有 1 条，判据记通过。可这次**根本没崩到**，什么都没验着。
    # - **假红**：真崩了并且正确续跑（崩溃前四次工具调用一次都没重跑，续跑那程只花了
    #   1529 未命中 token），但重投照样发一条 `run.started`，且 `resumed` 那时的定义是
    #   `task.decisions is not None` —— 它只标「审批之后的续跑」，崩溃恢复本来就是 false。
    #   **P4 步骤三已把 `resumed` 改成「这不是第一次开跑」**，崩溃重投从此报 true；
    #   但判据仍不数条数 —— 数条数的毛病是「假过」那一头，与 resumed 的定义无关。
    #
    # 改成直接断言那件要验的事，并且**先证明崩到了**：没崩到就记未验，不许记通过
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

    # 观察项，不设门槛：崩溃恢复时工具重复执行了几次
    tool_call="$(jq -s '[.[] | select(.type == "tool_call")] | length' <<<"$EVENTS")"
    tool_result="$(jq -s '[.[] | select(.type == "tool_result")] | length' <<<"$EVENTS")"
    info "【观察项】工具调用 $tool_call 次、返回 $tool_result 次 —— 差值即崩在工具执行途中的重跑次数"
    info "【观察项】这个数是 P2 §7 那项「幂等键先量后定」的输入，请记进计划文档"

    # **`docker kill` 不会触发 restart 策略**：守护进程把外部下的 kill 记成「人为停止」，
    # 从此不再自动拉起。真崩溃（进程自己死在容器里）走的是另一条路，`unless-stopped` 照常生效 ——
    # 所以这里副本没回来不说明策略有问题，手工拉一把，好让后面几组仍在满编下跑
    compose up -d --no-recreate worker >/dev/null 2>&1
    wait_worker "$WORKER_COUNT" || info "worker 没回到 $WORKER_COUNT 个副本，后面几组会在减员状态下跑"

    # **砍空记「未验」而不是「未过」。** 与「跳过的条目记未验」是同一条规矩的另一半：
    # 没触发到要测的场景，既算不上失败，更算不上通过 —— 记成失败会让人去查一个
    # 并不存在的 bug，记成通过则等于这条门禁不存在
    if (( starts < 2 )); then
        info "这一次 kill 没砍到：run 在它生效前就跑完了（run.started 只有 $starts 条）"
        undone "这轮 kill 没砍到，重跑一次即可"
    elif (( repeated == 0 )); then
        pass "真崩了（run.started $starts 条）且崩前已完成的工具一次都没重跑"
    else
        fail "崩溃后重跑了 $repeated 次崩前就已经成功的工具调用 —— 这是重跑不是续跑"
    fi
fi
end


# ===========================================================================
# P3：越权、配额、取消、并发、审批、幂等键
# ===========================================================================


# **A / B / 管理员三个号**：越权那条要两个互不相干的教师，「管理员不例外」要一个
# 管理员。口令那一维绑成同一个，好按名字点名
STAMP="$(date +%s)"
TEACHER_A="zuel-p3-a-$STAMP"
TEACHER_B="zuel-p3-b-$STAMP"
ADMIN_PROBE="zuel-p3-admin-$STAMP"
SECRET="zuel-p3-secret-$STAMP"
JAR_A="$WORK_DIR/cookie-p3-a"; JAR_B="$WORK_DIR/cookie-p3-b"; JAR_ADMIN="$WORK_DIR/cookie-p3-admin"

make_user "$TEACHER_A" "$SECRET" teacher || { echo "P3 造不出教师 A" >&2; exit 1; }
make_user "$TEACHER_B" "$SECRET" teacher || { echo "P3 造不出教师 B" >&2; exit 1; }
login "$TEACHER_A" "$SECRET" "$JAR_A" || { echo "A 登不进来" >&2; exit 1; }
login "$TEACHER_B" "$SECRET" "$JAR_B" || { echo "B 登不进来" >&2; exit 1; }
UID_A="$(curl -fsS -b "$JAR_A" "$BASE_URL/api/auth/me" | jq -r .id)"
UID_B="$(curl -fsS -b "$JAR_B" "$BASE_URL/api/auth/me" | jq -r .id)"
info "教师 A=$TEACHER_A ｜ 教师 B=$TEACHER_B"

api() { curl -fsS -b "$1" "${@:2}"; }
code() { curl -s -o /dev/null -w '%{http_code}' -b "$1" "${@:2}"; }
body() { curl -s -b "$1" "${@:2}"; }
new_thread() { api "$1" -X POST "$BASE_URL/api/threads" | jq -r .id; }
run_status() { api "$1" "$BASE_URL/api/runs/$2" | jq -r .status; }

wait_status() {
    local jar="$1" run_id="$2" expect="$3" deadline=$((SECONDS + ${4:-$RUN_WINDOW}))
    while (( SECONDS < deadline )); do
        [[ $(run_status "$jar" "$run_id") == "$expect" ]] && return 0
        sleep 3
    done
    return 1
}

# ------------------------------------------------------------- P3④ 越权 404
begin "P3④" "越权一律 404（不是 403）—— 四条路径，管理员也不例外"

THREAD_A="$(new_thread "$JAR_A")"
# 直接写库造一个 A 的 run，避免为了验越权而烧一次真实分析。
# **id 在这一侧发**：psql 的 RETURNING 会把 `INSERT 0 1` 那行状态一起吐出来粘在后面
RUN_A="$(tr -d - < /proc/sys/kernel/random/uuid)"
psql_query "INSERT INTO runs (id, thread_id, user_id, status, tokens_cache_read, tokens_uncached, tokens_output, started_at)
    VALUES ('$RUN_A', '$THREAD_A', '$UID_A', 'succeeded', 0,0,0, now());" >/dev/null

for path in "/api/runs/$RUN_A" "/api/runs/$RUN_A/events" "/api/threads/$THREAD_A/files/raw?path=outputs/chart.png"; do
    got="$(code "$JAR_B" "$BASE_URL$path")"
    [[ $got == 404 ]] && pass "B 读 A 的 $path → 404" || fail "B 读 A 的 $path → $got（403 也算未过）"
done
got="$(code "$JAR_B" -X POST "$BASE_URL/api/threads/$THREAD_A/runs" -H 'Content-Type: application/json' -d '{"content":"借你的会话一用"}')"
[[ $got == 404 ]] && pass "B 往 A 的会话提交 → 404" || fail "B 往 A 的会话提交 → $got"

# **另建一个 admin，不用 .env 里那个首个管理员**：那个号的口令在真部署上是被改过的，
# 而这条要验的是角色本身没有旁路，与是哪一个管理员无关
if make_user "$ADMIN_PROBE" "$SECRET" admin && login "$ADMIN_PROBE" "$SECRET" "$JAR_ADMIN"; then
    got="$(code "$JAR_ADMIN" "$BASE_URL/api/runs/$RUN_A")"
    [[ $got == 404 ]] && pass "管理员读 A 的 run → 404（管理员不例外）" \
        || fail "管理员读 A 的 run → $got —— 数据层出现了绕过过滤的旁路"
else
    fail "造不出管理员账号，「管理员不例外」这半条验不了"
fi
end

# --------------------------------------------------------------- P3⑤ 三道闸
begin "P3⑤" "三道闸都关得上，且三个 429 可区分"

# **整段先把 worker 停掉**：这一节里有一次提交会被放行（验 cache_read 不计入配额），
# worker 在跑的话它就是一次真实分析 —— 既花钱，又让紧接着那条「waiting_approval
# 不占并发」数到一个 running。这一节不需要 worker
WORKER_TOUCHED=1
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
end

# 限流窗口是滑动的，等它滑过去再往下跑，免得后面几条被自己刚打的那波拦住
sleep "$RATE_WINDOW_SETTLE"

# --------------------------------------------------------------- P3⑥ 取消
begin "P3⑥" "主动取消停得下来，且 checkpoint 保住"

# **先停 worker 再提交**：让 run 停在 queued，这条就不必烧一次真实分析。
# 「跑到一半取消」由 test/run/executor_test.py 精确覆盖（定点在 step 边界上）
WORKER_TOUCHED=1
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
end

# --------------------------------------------------------------- P3③ 并发
begin "P3③" "$CONCURRENCY 并发不崩溃、不串数据"

# **不投真任务**：$CONCURRENCY 次真实分析就是 $CONCURRENCY 份钱。这里压的是隔离与
# 会话创建这条链路 —— 「不串数据」正是这一条的重点，而它与模型无关
CONCURRENT_OUT="$WORK_DIR/concurrent"
mkdir -p "$CONCURRENT_OUT"
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

leaked="$(code "$JAR_B" "$BASE_URL/api/threads/$(head -1 "$CONCURRENT_OUT/thread-1")/files/raw?path=outputs/chart.png")"
[[ $leaked == 404 ]] && pass "并发之后 B 仍够不着 A 的会话" || fail "并发之后越权检查失效：$leaked"
rm -rf "$CONCURRENT_OUT"
end

# --------------------------------------------------------------- P3② 幂等键
begin "P3②" "定点注入的崩溃：恢复后写操作不重复执行"

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
else
    fail "幂等键没起作用：$IDEMPOTENT（期望「同 有错」）"
fi
end

# --------------------------------------------------------------- P3① 审批
begin "P3①" "四种决策各走一遍，run 都跑到终态"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要真实调用 DeepSeek"
else
    # **脚本得知道自己在造场景**：P0 实测 agent 一次都没自发调过 delete，
    # 等它自己撞上来是等不到的。
    #
    # **要删的那个文件必须真的在**。原来上传的是仓库根的 `README.md` —— 那个文件
    # 压根不存在，curl 当场失败，而后面跟着的 `|| true` 把失败咽了。于是工作目录
    # 一直是空的，这条判据只在「agent 不先 ls 就直接调 delete」时才成立：实测
    # 一轮里 edit 那次 agent 先 ls、看到 No files found 就收工，run 直奔 succeeded。
    # 现造一个文件，并用 `;filename=` 把名字定成提示词里说的那个
    PROBE_FILE="$WORK_DIR/probe-readme"
    printf 'P3 ① 用来给 delete 造场景的文件，删掉它是预期行为。\n' > "$PROBE_FILE"

    for decision in approve reject edit respond; do
        thread="$(new_thread "$JAR_A")"
        # **不能 `|| true`**：造场景失败必须当场说出来，否则这条判据测的是
        # 「agent 会不会对着一个不存在的文件调 delete」，而那要看模型的一念之间
        curl -fsS -b "$JAR_A" -X POST "$BASE_URL/api/threads/$thread/files" \
            -F "file=@$PROBE_FILE;filename=README.md" >/dev/null 2>&1 \
            || { fail "$decision：造场景的 README.md 没上传上去，这一轮什么都没验着"; continue; }
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
        # 「把 README.md 删掉」，实测两三百，而一次完整分析是十万量级。
        # **别拿这组数去校准分析量级**，会把它压低两个数量级；
        # 校准要用的样本是 P0⑤ 那行「token 口径按 cache 拆分」
        used="$(psql_query "SELECT tokens_uncached, tokens_output FROM runs WHERE id='$run_id';" | tr -d '[:space:]')"
        info "【观察项】$decision 这次审批探针的未命中 token / output：$used（探针量级，非分析量级）"
    done

    # index 校验：重复的 index 要 VALIDATION_ERROR
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
fi
end


# ===========================================================================
# P4：文件直发与 resumed 语义
# ===========================================================================


session_for p4 || { echo "P4 造不出账号" >&2; exit 1; }
JAR_P4="$SESSION_JAR"

# ------------------------------------------------------------- P4② 文件直发
begin "P4②" "工作目录里的文件从 nginx 直发，api 进程碰不到字节"

# **不带请求体**：`POST /api/threads` 不收任何字段，标题由第一次提问之后的一次轻量
# 模型调用填上 —— 原来这里发的 `{"title":"…"}` 一直在空转
THREAD_P4="$(curl -fsS -b "$JAR_P4" -X POST "$BASE_URL/api/threads" | jq -r .id)"

# 直接往会话工作目录里放一个文件，不必先跑一次真实分析 —— 这一条验的是取回那条路
compose exec -T broker sh -c "
    mkdir -p '$WORKSPACE_ROOT/$THREAD_P4/outputs' &&
    echo 'p4-直发-判据' > '$WORKSPACE_ROOT/$THREAD_P4/outputs/p4.txt'" >/dev/null 2>&1 \
    && pass "文件已放进会话工作目录" || fail "文件放不进会话工作目录"

# **判据是 nginx 直发路径成立**：api 回的是 `X-Accel-Redirect`，字节由 nginx 从
# 挂进来的 workspace 读，api 进程一个字节都不经手。
#
# **绕开 nginx 直接问 api 容器**才看得到那个头 —— 经 nginx 拿到的是字节本身，
# 而「拿到了字节」证明不了它是谁发的。**要带会话 cookie**，否则拿到的是 401，
# 而 401 里当然也没有那个头（第一版就栽在这儿）
API_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(container_of api | head -1)")"
# **cookie 要显式带，不能靠 -b。** curl 只把 cookie 发给域名匹配的主机，而 jar 里
# 那条是记在 127.0.0.1 名下的 —— 换成容器 IP 就不发了，于是拿到 401。
# awk 的条件也要留意：jar 里那行以 `#HttpOnly_` 开头，按「# 开头即注释」过滤会把它滤掉
COOKIE="$(awk 'NF>=7 && $0 !~ /^# / {print $6 "=" $7}' "$JAR_P4" | tail -1)"
HEADER="$(curl -s -D - -o /dev/null -H "Cookie: $COOKIE" \
    --get --data-urlencode "path=outputs/p4.txt" "http://$API_IP:8000/api/threads/$THREAD_P4/files/raw")"
info "api 直答：$(head -1 <<<"$HEADER")"
grep -qi '^X-Accel-Redirect: */workspace/' <<<"$HEADER" \
    && pass "api 回的是 X-Accel-Redirect，字节不经它的进程" \
    || fail "api 没有回 X-Accel-Redirect —— 直发没成立"

# 经 nginx 走一遍，确认那条内部跳转真的取得回字节 —— 只验头的话，
# nginx 那一侧配错（没挂卷、alias 写错）看不出来，而症状是每次下载都 404
BODY="$(curl -s -b "$JAR_P4" --get --data-urlencode "path=outputs/p4.txt" "$BASE_URL/api/threads/$THREAD_P4/files/raw")"
[[ $BODY == "p4-直发-判据" ]] \
    && pass "经 nginx 取回的字节与写进去的一致" \
    || fail "经 nginx 取回的不是原字节：$BODY"

# **`internal` 是那条 location 的全部安全性**：外部直接请求一律 404
LEAK="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/workspace/$THREAD_P4/outputs/p4.txt")"
[[ $LEAK == 404 ]] \
    && pass "内部路径不对外：直接请求 /workspace/… 得到 404" \
    || fail "内部路径漏了：直接请求 /workspace/… 得到 $LEAK"
end

# --------------------------------------------------------------- P4⑦ resumed
begin "P4⑦" "resumed 语义对得上"

# 「这不是第一次开跑」= 崩溃恢复 or 审批续跑。两个来源都验，缺一个就只验了一半。
# 判据取自库：queued 起跑那一程 start() 返回 FIRST，其余返回 RESUMED
RESUMED_OK="$(in_api python - <<'PY' 2>&1 | tail -1
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
end


# ===========================================================================
# P0：一次完整的真实分析（要 LLM，有费用）
# ===========================================================================
#
# **贯穿始终的回归基线。** 走的是教师真正走的那条路：建会话、上传数据、提问、
# 订阅事件流、中途断线重连、取回图表。**单次约 30 万 token、几分钟。**
#
# 分析只跑一次，五条判据都从它的产出上读 —— 因此先跑，跑不成就五条一起记未验。


log "P0 一次完整的真实分析（要 LLM，有费用）"
P0_READY=0
P0_BLOCKED=""
if [[ ${SKIP_LLM:-0} == 1 ]]; then
    P0_BLOCKED="SKIP_LLM=1，这一组要真实调用 DeepSeek"
elif [[ ! -f $SAMPLE_CSV ]]; then
    # **`tmp/` 不入库**，新克隆的仓库里没有这个文件。整组记未验而不是让验收退出 ——
    # 另外十七条与它无关，没有理由陪着一起不跑
    P0_BLOCKED="缺样例数据 $SAMPLE_CSV（放一份持仓 csv 过去，或 SAMPLE_CSV=... 指到别处）"
elif ! session_for p0; then
    P0_BLOCKED="造不出账号"
fi

if [[ -z $P0_BLOCKED ]]; then
    JAR_P0="$SESSION_JAR"
    THREAD_P0="$(curl -fsS -b "$JAR_P0" -X POST "$BASE_URL/api/threads" | jq -r .id)"
    info "thread_id=$THREAD_P0"
    if ! curl -fsS -b "$JAR_P0" -X POST "$BASE_URL/api/threads/$THREAD_P0/files" -F "file=@$SAMPLE_CSV" >/dev/null; then
        P0_BLOCKED="holdings.csv 上传失败，分析没有输入"
    else
        RUN_P0="$(curl -fsS -b "$JAR_P0" -X POST "$BASE_URL/api/threads/$THREAD_P0/runs" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg c "$QUESTION" '{content:$c}')" | jq -r .id)"
        if [[ -z $RUN_P0 || $RUN_P0 == null ]]; then
            P0_BLOCKED="提交分析失败"
        else
            info "run_id=$RUN_P0，订阅事件流，收满 $CUT_AFTER_EVENT 条后主动断开"
            # --max-time 之外还要 head -n：SSE 是长连接，不主动切就要等到 run 结束
            timeout $RUN_TIMEOUT curl -fsS -b "$JAR_P0" -N "$BASE_URL/api/runs/$RUN_P0/events" \
                | head -n $((CUT_AFTER_EVENT * 3)) > "$WORK_DIR/first.sse"
            LAST_ID="$(grep '^id:' "$WORK_DIR/first.sse" | tail -1 | sed 's/^id: *//')"
            info "断开于 Last-Event-ID=$LAST_ID，带它重连补齐剩下的"
            timeout $RUN_TIMEOUT curl -fsS -b "$JAR_P0" -N "$BASE_URL/api/runs/$RUN_P0/events" \
                -H "Last-Event-ID: $LAST_ID" > "$WORK_DIR/rest.sse"

            cat "$WORK_DIR/first.sse" "$WORK_DIR/rest.sse" > "$WORK_DIR/all.sse"
            grep '^data:' "$WORK_DIR/all.sse" | sed 's/^data: *//' | jq -c . > "$WORK_DIR/all.json" 2>/dev/null
            P0_READY=1
        fi
    fi
fi
p0_types() { jq -r .type < "$WORK_DIR/all.json"; }

begin "P0①" "事件流完整：run.started 开头，run.finished 收尾"
if (( P0_READY )); then
    if [[ $(p0_types | head -1) == run.started ]] && p0_types | grep -q '^run.finished$'; then
        pass "事件流完整：run.started 开头，run.finished 收尾"
    else
        fail "事件流不完整：首=$(p0_types | head -1) 末=$(p0_types | tail -1)"
    fi
else
    undone "$P0_BLOCKED"
fi
end

begin "P0②" "agent 自写脚本并 execute"
if (( P0_READY )); then
    WROTE=$(jq -r 'select(.type=="tool_call") | .data.name' < "$WORK_DIR/all.json" | grep -cE '^(write_file|execute)$')
    if (( WROTE >= 2 )); then
        pass "agent 自写脚本并执行（write_file / execute 共 $WROTE 次）"
    else
        fail "没看到 agent 自己写脚本并执行，相关 tool_call 只有 $WROTE 次"
    fi
else
    undone "$P0_BLOCKED"
fi
end

begin "P0③" "断线重连补齐不重不漏"
if (( P0_READY )); then
    # id 严格递增且无重复
    IDS=$(grep '^id:' "$WORK_DIR/all.sse" | sed 's/^id: *//')
    TOTAL=$(wc -l <<<"$IDS"); UNIQUE=$(sort -u <<<"$IDS" | wc -l)
    SORTED=$(sort -t- -k1,1n -k2,2n <<<"$IDS")
    if [[ $TOTAL -eq $UNIQUE && $IDS == "$SORTED" ]]; then
        pass "断线重连补齐不重不漏（$TOTAL 条，id 严格递增）"
    else
        fail "重连有重复或乱序：共 $TOTAL 条、去重后 $UNIQUE 条"
    fi
else
    undone "$P0_BLOCKED"
fi
end

begin "P0④" "产物取回且是一张能显示的图"
if (( P0_READY )); then
    # 产物不再有独立的身份与端点：agent 把图写进会话工作目录的 outputs/，
    # 教师从侧边栏那套端点取回。这里照着教师的路径走一遍 —— 列目录，挑一张图，下载
    CHART="$(curl -fsS -b "$JAR_P0" "$BASE_URL/api/threads/$THREAD_P0/files" \
        | jq -r '.entries[] | select(.is_dir == false) | select(.path | test("\\.(png|jpg|jpeg|svg)$")) | .path' | head -1)"
    if [[ -n $CHART ]]; then
        curl -fsS -b "$JAR_P0" --get --data-urlencode "path=$CHART" \
            "$BASE_URL/api/threads/$THREAD_P0/files/raw" -o "$WORK_DIR/artifact.bin"
        KIND="$(file -b --mime-type "$WORK_DIR/artifact.bin")"
        SIZE=$(stat -c %s "$WORK_DIR/artifact.bin")
        if [[ $KIND == image/* ]] && (( SIZE > 1024 )); then
            pass "产物取回正常：$CHART（$KIND，$SIZE 字节）"
            # 「能显示」这条最终要靠人眼看一次，给出原图路径
            info "原图：$BASE_URL/api/threads/$THREAD_P0/files/raw?path=$CHART"
        else
            fail "产物不是一张正常的图：$KIND，$SIZE 字节"
        fi
    else
        fail "会话工作目录里没有任何图片"
    fi
else
    undone "$P0_BLOCKED"
fi
end

begin "P0⑤" "token 口径按 cache 拆分"
if (( P0_READY )); then
    # 两个数都要在。这是校准「一次分析多少 token」唯一可信的样本
    TOKENS="$(jq -c 'select(.type=="run.finished") | .data.tokens' < "$WORK_DIR/all.json" | head -1)"
    if [[ -n $TOKENS ]] && jq -e 'has("input_cache_read") and has("input_uncached")' <<<"$TOKENS" >/dev/null; then
        pass "token 口径按 cache 拆分：$TOKENS"
    else
        fail "run.finished 未按 cache 拆分给出 token：$TOKENS"
    fi
else
    undone "$P0_BLOCKED"
fi
end


# ===========================================================================
# 破坏性四条（要 sudo）
# ===========================================================================

begin "P1①" "四条破坏性测试宿主机不受影响"
if [[ ${SKIP_HOSTILE:-0} == 1 ]]; then
    undone "SKIP_HOSTILE=1，这一组要 root"
# **参数走命令行，不走环境变量** —— 见 run_hostile_group 上方那段：`sudo -E` 在
# 默认的 env_reset 下是被拒的，靠它传值等于这一组永远跑不起来
elif sudo bash "${BASH_SOURCE[0]}" "$HOSTILE_ENTRY" \
    "$SANDBOX_WORKSPACE_ROOT" "$SANDBOX_IMAGE" "$SANDBOX_DISK_QUOTA" \
    "$SANDBOX_TMP_SIZE" "$SANDBOX_PIDS_LIMIT" "$(id -u):$(id -g)"; then
    pass "四条全过：宿主机的内存、磁盘与进程数都回到了基线"
else
    fail "破坏性测试未全过，详见上面的输出"
fi
end

# ===========================================================================
# 结果
# ===========================================================================

log "回归验收结果"
for id in "${CHECK_ORDER[@]}"; do
    case "${CHECK_VERDICT[$id]:-未验}" in
        通过) printf '  \033[32m✅ %s %s\033[0m\n' "$id" "${CHECK_NAME[$id]}" ;;
        未过) printf '  \033[31m❌ %s %s\033[0m\n' "$id" "${CHECK_NAME[$id]}" ;;
        *) printf '  \033[33m⚠️  %s %s —— %s\033[0m\n' "$id" "${CHECK_NAME[$id]}" "${CHECK_VERDICT[$id]:-未验}" ;;
    esac
done

if (( failed )); then
    printf '\n\033[31m回归验收未全过（%d 处断言出错）。\033[0m\n' "$failed"
    exit 1
fi
for id in "${CHECK_ORDER[@]}"; do
    [[ ${CHECK_VERDICT[$id]:-未验} == 通过 ]] && continue
    printf '\n\033[33m已验的都过了，但有条目未验 —— 不能据此判定回归验收通过。\033[0m\n'
    exit 2
done
printf '\n\033[32m回归验收 %d 条全过。\033[0m\n' "${#CHECK_ORDER[@]}"
