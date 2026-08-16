#!/usr/bin/env bash
#
# 平台回归验收：P0–P11 当前 61 条判据，一个文件跑完。
#
#   export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
#   export SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$(pwd)/data/sandbox")"
#   docker compose -f deploy/compose.yml up -d --build
#   bash deploy/test/verify.sh
#
# 常用跑法：
#
#   bash deploy/test/verify.sh                             # 全部（要 sudo，有 LLM 费用）
#   SKIP_LLM=1 SKIP_HOSTILE=1 bash deploy/test/verify.sh   # 只跑免费的 42 条，约 30 分钟
#
# **默认全跑，不分 phase，也没有挑某一期跑的参数** —— P6 决策 §L2 的定案。
# 保留的是 `SKIP_LLM` / `SKIP_HOSTILE` 两个开关：它们分的是**成本**（要不要花钱、
# 要不要 root），不是期次。按期挑着跑，等于把刚拆掉的那层级联结构又装回来，
# 还多一条「以为全验了其实只验了一期」的路。
#
# 61 条里 **19 条要花钱或要 root**：P0 那五条各是一次完整分析上读出来的、
# P2① 与 P3① 各要一次真实分析，P6①、P7③、P8① 与 P8③ 各要两次真实分析，
# P9①与 P9② 共用两次真实分析，P9⑤另要一次便宜分析，P10① 要两次、P10⑦ 要一次，
# P1① 那四条破坏性测试要 root。其余 42 条全免费。
#
# ---------------------------------------------------------------------------
# **P7 那一组是 2026-08-14 随本期开发一起加的**，六条：三档可见性、审核闸门、
# 引用真的改变行为、版本冻结、`reviewer` 的边界，以及一条 playwright 走查。
#
# **P7⑥、P8⑥、P9⑥ 与 P10⑥ 是四条要浏览器的判据**，缺 chromium 二进制时记「未验」——
# 与沙箱镜像缺失同一套规矩。它们不进 `make all`：那是纯本地门禁，跑它不需要任何服务
# 起着，而这四条要六个服务、真账号、真库。
#
# ---------------------------------------------------------------------------
# **P10 那一组是 2026-08-16 随本期开发一起加的**，七条。它需要一样前九期都不需要的
# 东西：**一台在跑的 MCP server**。夹具跑在宿主机上（`deploy/test/mcp/server.py`，
# 由本脚本自己起停），api 与 worker 两个容器靠 `host.docker.internal` 够着它 ——
# 真实的 MCP 全在校外用不上那一行，用得上它的是验收。
#
# **`P10⑦` 会因为对方（mcp.deepwiki.com）下线而红，那是它的功能不是缺陷。** 红的
# 时候先确认是不是对方挂了 —— 装配探针连不上就记「未验」而不是「未过」，与「没触发
# 到要测的场景」同一条规矩。
#
# ---------------------------------------------------------------------------
# **P5 那一组是 2026-08-14 补的**（P6 开工前的最后一件事）。P5 期是唯一一期没留下
# 验收脚本的（P5 计划 §4），而它改了 `UploadResponse` 的形状、给 `/threads` 加了
# 一条单段路由、动了事件流的收尾条件 —— 每一条都有打穿历史脚本的形状。四条判据
# 一次跑过，且**没打穿任何一条历史判据**（同一轮里旧的 16 条免费判据全过）。
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
#   - **`p1.sh` 重建 broker 时会把磁盘配额悄悄关掉**：它推导了 `SANDBOX_USER` 与
#     `SANDBOX_WORKSPACE_ROOT`，**唯独漏了 `SANDBOX_QUOTA_DEVICE`** —— 而 compose 的
#     `devices:` 取 `${SANDBOX_QUOTA_DEVICE:-/dev/null}`，于是重建出来的 broker 拿到
#     `/dev/null`，配额一个都设不上，broker fail-closed，此后每次建会话都 500。
#     症状全落在配额、越权、限流那几条判据上，没有一条指向 broker 被重建过。
#     现在这一项也从跑着的 broker 身上读回来，另在两处重建之后各加一次建会话冒烟。
#   - `session.sh` 造号时 `ON CONFLICT (name) DO NOTHING` 而不回读，撞名时静默什么
#     都不做，失败要等到登录那一步 —— 报出来的是「登不进去」，指向登录而非造号。
#   - `p4.sh` 建会话时发 `{"title":"…"}`，而 `POST /api/threads` 根本不收请求体
#     （标题由第一次提问之后的一次轻量模型调用填上）—— 那个字段一直在空转。
#   - P3 的三道闸与取消两节会 `compose stop worker`，中途失败就把 worker 留在停止
#     状态，**污染之后每一次跑法**。现在收尾统一把它拉回来。
#   - **同两节的 `compose stop worker` 不给 `-t`，会静默干等最多 30 分钟**：
#     worker 的 `stop_grace_period` 是 30m（生产滚动重启不该掐断在跑的分析），
#     而这两节要的是「立刻别跑」。实测卡了 18 分钟，期间脚本一行输出都没有。
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
    # **email 是 P11 的 0015 加的 NOT NULL 列**，不给就整条插不进去，
    # 而症状会出现在后面的登录那一步（「登不进去」），不指向造号。
    # 用户名本身全库唯一，拼出来的邮箱因此也唯一。
    #
    # **域名不能用 `.local` / `.test` / `.example`**：那几个是保留 TLD，`EmailStr`
    # 一律拒绝。这里走 SQL 绕过了校验所以看着没事，而 `/api/auth/register`
    # 那条路会 422 —— 两处用同一个域名才不会一处能跑一处不能
    psql_query "INSERT INTO users (id, name, email, password_hash, role, is_active, created_at)
         VALUES (gen_random_uuid(), '$name', '$name@verify.zuel.edu.cn', '$hashed', '$role', true, now())
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

# **配额设备也要继承，理由比上面两个更隐蔽。** P1④⑤ 会重建 broker，而 compose 的
# `devices:` 取的是 `${SANDBOX_QUOTA_DEVICE:-/dev/null}` —— 这个变量不在本脚本的环境里
# （它是 loop 设备号，每次挂载都换，因此只 export 不写文件），重建出来的 broker 就
# 拿到 `/dev/null`。于是 xfs_quota 每条命令往 stderr 打一句然后**退出 0**，配额一个都
# 设不上，broker fail-closed，**此后每一次建会话都 500**。
#
# **症状全落在与它无关的判据上**：2026-08-13 实测那一轮报的是「配额那道闸没关上」
# 「cache_read 被算进了配额」「并发那道闸没关上」，还往 psql 里插了空的 thread_id ——
# 没有一条指向「broker 刚才被重建过」。
#
# 取正在跑的那个 broker 身上的值：它就是当前正确的那一个
export SANDBOX_QUOTA_DEVICE="${SANDBOX_QUOTA_DEVICE:-$(docker inspect "$BROKER_ID" \
    --format '{{range .HostConfig.Devices}}{{println .PathOnHost}}{{end}}' | head -1)}"
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

# 停着 worker 提交的 queued run 必须先取消、再恢复 worker。这个函数既走正常路径，
# 也走 EXIT trap：脚本在两步之间被打断时，不能让清理动作反而把付费分析跑起来。
#
# **P6③ 与 P7④ 共用这一份**，不各写一份 —— 两份 fail-closed 迟早只有一处是对的，
# 而错的那一处的症状是「一条免费判据在收尾时变成一次付费分析」，账单上才看得见。
#
# 登记的是「thread jar」对：两条判据用的是不同的账号，取消要拿本人的 cookie 打。
SNAPSHOT_PENDING=()

register_snapshot_thread() {
    SNAPSHOT_PENDING+=("$1 $2")
}

cancel_snapshot_runs() {
    local require_cancelled="${1:-0}"
    local entry thread jar run_id response status discovered failed=0 stuck
    local kept=()

    for entry in ${SNAPSHOT_PENDING[@]+"${SNAPSHOT_PENDING[@]}"}; do
        read -r thread jar <<<"$entry"
        [[ -n $thread && -n $jar ]] || continue
        # 不能只信 POST 响应里的 id：服务端可能已经落库、客户端却在收到响应前断了。
        # 按这条判据专用的 thread 回查，才能保证恢复 worker 前没有漏网的付费任务。
        if ! discovered="$(psql_query "SELECT id FROM runs
            WHERE thread_id='$thread'
              AND status IN ('queued', 'running', 'waiting_approval');")"; then
            failed=1
            kept+=("$entry")
            continue
        fi
        stuck=0
        for run_id in $discovered; do
            if ! response="$(curl -sS --connect-timeout 5 --max-time 20 -b "$jar" \
                -X POST "$BASE_URL/api/runs/$run_id/cancel")"; then
                stuck=1
                continue
            fi
            status="$(jq -r '.status // empty' <<<"$response" 2>/dev/null)"
            case "$status" in
                cancelled) ;;
                # 已经跑完的那条不是「取消成功」：它意味着 worker 真的领走跑了一次，
                # 而这两条判据本该一分钱都不花
                succeeded|failed) (( require_cancelled == 0 )) || stuck=1 ;;
                *) stuck=1 ;;
            esac
        done
        if (( stuck )); then
            failed=1
            kept+=("$entry")
        fi
    done
    SNAPSHOT_PENDING=(${kept[@]+"${kept[@]}"})
    (( failed == 0 ))
}

restore_workers() {
    compose up -d --no-recreate worker >/dev/null 2>&1 || return 1
    wait_worker "$WORKER_COUNT"
}

# 收尾。**worker 与 broker 都要还原**：P1④⑤ 会把沙箱名额压到 1，
# P3⑤⑥ 与 P6③ 会把 worker 停掉 —— 中途失败时不还原的话，这台机器上此后每一次
# 跑法都在一个说不清的状态里起步，而症状不指向上一轮验收
cleanup() {
    local uncertain="${SNAPSHOT_PENDING[*]:-未知}"
    [[ -n ${THREAD_HELD:-} ]] && docker rm -f "$(sandbox_of "$THREAD_HELD")" >/dev/null 2>&1
    [[ -n ${BROKER_OVERRIDDEN:-} ]] && compose up -d --no-deps --force-recreate broker >/dev/null 2>&1
    if [[ -n ${WORKER_TOUCHED:-} ]]; then
        # 客户端超时/被中断时，服务端可能仍在提交；一次“查不到”不能证明稍后不会入队。
        if (( ${SNAPSHOT_POST_IN_FLIGHT:-0} )); then
            cancel_snapshot_runs || true
            echo "停 worker 期间的 POST 结果不确定，worker 保持停止；待查 thread=$uncertain，请人工确认后再启动" >&2
        elif cancel_snapshot_runs; then
            restore_workers \
                || echo "worker 清理后仍未恢复到 $WORKER_COUNT 个副本，请人工检查" >&2
        else
            echo "停 worker 期间的 queued run 没能全部取消，worker 保持停止；请人工取消后再启动" >&2
        fi
    fi
    # 夹具 MCP server 跑在宿主机上，中途失败时不停掉的话它会一直占着端口，
    # 而下一轮验收起它时报的是「Address already in use」——那条错不指向上一轮
    [[ -n ${P10_FIXTURE_PID:-} ]] && kill "$P10_FIXTURE_PID" >/dev/null 2>&1
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
# 都是建会话，而它最容易在一个与被测功能毫无关系的地方失败 —— 不拦的话，十几条判据
# 会一起红在各自不同的位置，没有一条指向真因（实测：P4② 以「api 没回
# X-Accel-Redirect」收场而真相是 thread_id 是空的；P3⑤ 以「配额那道闸没关上」
# 收场而真相是 broker 刚被重建、配额设备丢了）。
#
# **不只在开头冒一次**：broker 每次被重建之后都要再冒一次 —— 上面那第二种真因
# 正是重建带来的，开头那次冒烟拦不住它
smoke_thread() {
    local id
    id="$(curl -fsS -b "$SESSION_JAR" -X POST "$BASE_URL/api/threads" 2>/dev/null | jq -r '.id // empty')"
    [[ -n $id ]] || return 1
    curl -fsS -b "$SESSION_JAR" -X DELETE "$BASE_URL/api/threads/$id" >/dev/null 2>&1
    return 0
}

smoke_or_die() {
    smoke_thread && { info "冒烟通过（$1）：建会话、删会话都成"; return 0; }
    echo "建会话失败（POST /api/threads 没给出 id）—— 位置：$1" >&2
    cat >&2 <<'TIP'

**两个常见真因，都不在被测的功能上：**

1. XFS prjquota 那个 loop 挂载重启之后不会自动挂回来，broker 对配额 fail-closed，
   一律回 500，响应体里只有一句 Internal Server Error，QuotaError 只在日志里。

2. **broker 被重建时丢了配额设备**：compose 的 devices: 取
   ${SANDBOX_QUOTA_DEVICE:-/dev/null}，这个变量不在环境里就退化成 /dev/null。
   核对：docker inspect zuel-platform-broker-1 \
           --format '{{range .HostConfig.Devices}}{{.PathOnHost}}{{end}}'

两种都这么修（broker 必须 force-recreate，restart 不会重新解析 devices:）：

    sudo bash deploy/setup-xfs.sh
    export SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$(pwd)/data/sandbox")"
    docker compose -f deploy/compose.yml up -d --no-deps --force-recreate broker
    docker compose -f deploy/compose.yml restart nginx
    docker ps -q --filter 'name=zuel-sandbox' | xargs -r docker rm -f
    sudo xfs_quota -x -c 'report -p -N' "$(pwd)/data/sandbox" | tail -3   # 回读，别信退出码
TIP
    exit 1
}

session_for smoke || { echo "造不出账号或登不进去 —— 后面每一条都会红成 401" >&2; exit 1; }
smoke_or_die "前置检查"

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
# 刚重建过，立刻再冒一次 —— 「起来了」与「还能建会话」是两回事
smoke_or_die "P1 压名额、重建 broker 之后"

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
wait_broker || info "broker 重建后没在 60 秒内应答，后面几条可能会以「建会话失败」收场"
smoke_or_die "P1 收尾、还原 broker 之后"


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
p2_consumer() {
    local run_id="$1"
    in_api_python "
import asyncio
from config import get_settings
from store import redis as store_redis
from task.queue import CONSUMER_GROUP, PAYLOAD_FIELD, TASK_STREAM, RunTask

async def main():
    client = store_redis.create_client(get_settings().redis_url)
    try:
        pending = await client.xpending_range(
            TASK_STREAM, CONSUMER_GROUP, min='-', max='+', count=10_000
        )
        for one in pending:
            entry = await client.xrange(
                TASK_STREAM, min=one['message_id'], max=one['message_id'], count=1
            )
            if not entry:
                continue
            task = RunTask.model_validate_json(entry[0][1][PAYLOAD_FIELD])
            if task.run_id == '$run_id':
                print(one['consumer'])
                return
    finally:
        await client.aclose()

asyncio.run(main())
"
}

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

    # pending owner 就是当前执行这个 run 的 worker。consumer 名由
    # worker.runtime.consumer_name() 生成，形状为「容器短 id-pid」，可以无歧义映射回
    # compose 的两个副本。先在等 checkpoint 之前定位，避免 tool_result 出现后再扫日志
    # 的那一两秒里 run 已经收尾，最后退化成随机砍一个副本。
    P2_CONSUMER=""
    for _ in $(seq 10); do
        P2_CONSUMER="$(p2_consumer "$RUN_P2" 2>/dev/null)"
        [[ -n $P2_CONSUMER ]] && break
        sleep 1
    done
    VICTIM=""
    for candidate in $(worker_ids); do
        [[ $P2_CONSUMER == "${candidate:0:12}"-* ]] || continue
        VICTIM="$candidate"
        break
    done

    # **等第一条 tool_result 出现再动手，不用固定 sleep。** 这一刻两个条件同时成立：
    # 至少有一个 checkpoint 可以续，而 run 还没跑完 —— 刀正好落在中间。
    #
    # 固定 sleep 赌不赢：这道题在 prompt 缓存热的时候十几秒就跑完了，2026-08-08
    # 实测等满 20 秒与等满 10 秒各有一次砍空。**砍空不会报错**，它只会让这条验收
    # 什么都没验着，而判据若不识别这种情况就会把它记成通过
    #
    # **判据不能是管道的退出码**（2026-08-14 修）。本脚本开着 `set -o pipefail`，
    # 而原来那句 `curl -N … | grep -q -m1` 里，grep 一匹配上就退出，上游 curl 随即
    # 吃一个 SIGPIPE —— 管道退出码变成 141，**「匹配成功」这件事本身把判据判成了
    # 失败**。方向还正好是反的：流还开着（run 在跑，唯一砍得到的场景）必然判失败；
    # 流自然收尾（run 已跑完，砍了也是砍空）反而判成立。实测两种情形各得 141 与 0。
    #
    # 这就是这条判据反复记「未验」的根子，而它伪装成了「等太短」：2026-08-14 那轮
    # 报的是「等待 180s 未观察到 tool_result」，可库里那条 tool_result 在第 11.35 秒
    # 就落了，nginx 日志里那次订阅也正好在同一秒结束 —— grep 明明匹配上了。
    #
    # 改成 curl 后台落盘、主循环轮询文件：判据是「那一行到底出现没有」，不是任何一
    # 个进程的退出码。轮询要密 —— 从 tool_result 到 run 收尾可能只隔几秒。
    CHECKPOINT_READY=0
    P2_SSE="$WORK_DIR/p2_events.sse"
    : > "$P2_SSE"
    timeout "$KILL_WINDOW" curl -fsS -b "$JAR_P2" -N \
        "$BASE_URL/api/runs/$RUN_P2/events" > "$P2_SSE" 2>/dev/null &
    P2_SSE_PID=$!
    P2_ENDED_EARLY=0
    p2_deadline=$((SECONDS + KILL_WINDOW))
    while :; do
        if grep -q '^event: tool_result' "$P2_SSE" 2>/dev/null; then
            CHECKPOINT_READY=1
            break
        fi
        # run 自己先走到了终态：流马上收尾，再等下去只是白等满窗口，而且这一刻
        # 已经砍不到途中了 —— 要与「等超时」分开报，两者该做的事不一样
        if grep -qE '^event: run\.(finished|failed|cancelled)' "$P2_SSE" 2>/dev/null; then
            P2_ENDED_EARLY=1
            break
        fi
        (( SECONDS < p2_deadline )) || break
        sleep 0.5
    done
    kill "$P2_SSE_PID" 2>/dev/null
    wait "$P2_SSE_PID" 2>/dev/null

    if [[ -z $VICTIM ]]; then
        fail "队列 pending owner 无法映射到 worker：${P2_CONSUMER:-查不到 consumer}"
        curl -s --connect-timeout 5 --max-time 20 -b "$JAR_P2" -X POST \
            "$BASE_URL/api/runs/$RUN_P2/cancel" >/dev/null 2>&1
    elif (( ! CHECKPOINT_READY )); then
        final="$(p2_status "$RUN_P2")"
        if [[ $final == failed ]]; then
            fail "第一条 tool_result 出现前 run 已失败，造不出可续跑的 checkpoint"
        elif (( P2_ENDED_EARLY )); then
            undone "run 在第一条 tool_result 之前就走到终态（$final），砍不到途中，无法验证 checkpoint 续跑"
        else
            undone "等待 ${KILL_WINDOW}s 未观察到 tool_result，无法验证 checkpoint 续跑"
        fi
        [[ $final == running || $final == queued ]] &&
            curl -s --connect-timeout 5 --max-time 20 -b "$JAR_P2" -X POST \
                "$BASE_URL/api/runs/$RUN_P2/cancel" >/dev/null 2>&1
    else
        info "队列确认 run 由 consumer $P2_CONSUMER 执行"
        WORKER_TOUCHED=1
        docker kill -s KILL "$VICTIM" >/dev/null 2>&1
        info "已 kill -9 worker $VICTIM，等另一个副本认领（阈值 60 秒）"
    fi

    if (( CHECKPOINT_READY )) && [[ -n $VICTIM ]]; then
        deadline=$((SECONDS + RECOVER_WINDOW))
        final=""
        while (( SECONDS < deadline )); do
            final="$(p2_status "$RUN_P2")"
            [[ $final == succeeded || $final == failed ]] && break
            sleep 5
        done
        [[ $final == succeeded ]] && pass "崩溃后 run 仍跑到 succeeded" || fail "崩溃后 run 没跑完：${final:-无状态}"
    fi

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
    if (( ! CHECKPOINT_READY )) || [[ -z $VICTIM ]]; then
        : # 上面已经记过未验或失败，不能再用未发生的恢复过程定性
    elif (( starts < 2 )); then
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
# **必须给 `-t`。** compose.yml 给 worker 设了 `stop_grace_period: 30m`，那是为**生产
# 滚动重启**留的 —— 一次分析几十分钟，掐掉等于把烧过的 token 扔了，`WorkerLoop.stop()`
# 因此会 `await` 所有在跑的 run 再退出。
#
# 而这里要的恰恰相反：让 worker **立刻别跑任何东西**。手上只要还有一个 run，
# 不给 `-t` 就会干等最多 30 分钟，**期间脚本一行输出都没有，看起来就是死了**
# （2026-08-14 实测卡了 18 分钟才被人发现，而 P3⑤ 与 P3⑥ 各停一次，最坏一小时）。
compose stop -t 30 worker >/dev/null 2>&1
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
# **必须给 `-t`。** compose.yml 给 worker 设了 `stop_grace_period: 30m`，那是为**生产
# 滚动重启**留的 —— 一次分析几十分钟，掐掉等于把烧过的 token 扔了，`WorkerLoop.stop()`
# 因此会 `await` 所有在跑的 run 再退出。
#
# 而这里要的恰恰相反：让 worker **立刻别跑任何东西**。手上只要还有一个 run，
# 不给 `-t` 就会干等最多 30 分钟，**期间脚本一行输出都没有，看起来就是死了**
# （2026-08-14 实测卡了 18 分钟才被人发现，而 P3⑤ 与 P3⑥ 各停一次，最坏一小时）。
compose stop -t 30 worker >/dev/null 2>&1
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
# P5：账号与课题组、工作目录、会话与历史（四条全免费）
# ===========================================================================
#
# **这四条是 P5 期欠下的债。** 前四期每期都留了一条能跑的验收，唯独 P5 没有
# （P5 计划 §4）—— 而那一期改了 `UploadResponse` 的形状、给 `/threads` 加了一条
# 单段路由、动了事件流的收尾条件，**每一条都有打穿历史脚本的形状**，却没有任何
# 一次跨期重跑证明它们没有。
#
# **补法在 2026-08-13 的合并之后变了，债本身没变**：不再新写一个 `p5.sh` 逐级转调，
# 而是在这里加一组，判据编号跟在 p4 后面。
#
# **一次模型调用都不花，因此不挂 SKIP_LLM。** P5 改的全是接口层，与模型无关。
# P5③ 要一条真 run 才有历史可读，但它提交完立刻取消，且**提交前先把标题填上** ——
# 标题为空时 `POST /runs` 会挂一个后台任务去调轻量模型起名（route/thread.py 的
# submit_run），填过就不挂了。

P5_TAG="$$-$(date +%s%N | tail -c 5)"
P5_SECRET="zuel-secret-$$"
P5_JAR_READY=0
if session_for p5; then
    JAR_P5="$SESSION_JAR"
    UID_P5="$SESSION_UID"
    P5_JAR_READY=1
fi

# ------------------------------------------------------ P5① 注册、入组、审批
begin "P5①" "自助注册与入组审批走得通，且邀请码不跟着公开列表外泄"

JAR_P5_ADMIN="$WORK_DIR/cookie-p5-admin"
JAR_P5_OWNER="$WORK_DIR/cookie-p5-owner"
JAR_P5_STUDENT="$WORK_DIR/cookie-p5-student"
# **用户名上限 32 字符**（schema.MAX_NAME_LENGTH），前缀因此要短
P5_ADMIN="zuel-p5-adm-$P5_TAG"
P5_OWNER="zuel-p5-own-$P5_TAG"
P5_STUDENT="zuel-p5-stu-$P5_TAG"
P5_LONER="zuel-p5-lon-$P5_TAG"

# 建组是管理员的事，组主是教师。**另造一个管理员而不是用 .env 里那个首个管理员** ——
# 与 P3④ 同一条理由：那个号的口令在真部署上是被改过的
if ! { make_user "$P5_ADMIN" "$P5_SECRET" admin && login "$P5_ADMIN" "$P5_SECRET" "$JAR_P5_ADMIN" &&
    make_user "$P5_OWNER" "$P5_SECRET" teacher && login "$P5_OWNER" "$P5_SECRET" "$JAR_P5_OWNER"; }; then
    fail "造不出管理员或组主，这一条整条验不了"
else
    OWNER_UID="$(api "$JAR_P5_OWNER" "$BASE_URL/api/auth/me" | jq -r '.id // empty')"

    # **建两个组**：一个用来验「凭邀请码注册直接进组」，另一个用来验「申请 → 审批」。
    # 一个组做不了两件事 —— 学生凭码进了组之后，再申请同一个组会被「你已经在里面了」挡掉
    GROUP_ONE_BODY="$(body "$JAR_P5_ADMIN" -X POST "$BASE_URL/api/admin/groups" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "zuel-p5-码组-$P5_TAG" --arg o "$OWNER_UID" '{name:$n,owner_id:$o}')")"
    GROUP_TWO_BODY="$(body "$JAR_P5_ADMIN" -X POST "$BASE_URL/api/admin/groups" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "zuel-p5-审组-$P5_TAG" --arg o "$OWNER_UID" '{name:$n,owner_id:$o}')")"
    GROUP_ONE="$(jq -r '.id // empty' <<<"$GROUP_ONE_BODY")"
    GROUP_TWO="$(jq -r '.id // empty' <<<"$GROUP_TWO_BODY")"
    INVITE_ONE="$(jq -r '.invite_code // empty' <<<"$GROUP_ONE_BODY")"
    [[ -n $GROUP_ONE && -n $GROUP_TWO && -n $INVITE_ONE ]] \
        && pass "管理员建出两个组，响应里带着邀请码" \
        || fail "建组没成：$GROUP_ONE_BODY ｜ $GROUP_TWO_BODY"

    # **三处注册都要带 email**：P11 起它是必填且全库唯一的第二把登录钥匙。
    # 不带的话这一整段红成「注册结果不对」，指向的是注册流程而不是缺字段
    #
    # 凭码注册：账号当场可用，且回话里说得出进了哪个组 —— `is_active` 决定使用者
    # 接下来该去登录还是该去等管理员，说错一句就是一通电话
    REG_JOINED="$(curl -s -X POST "$BASE_URL/api/auth/register" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$P5_STUDENT" --arg p "$P5_SECRET" --arg c "$INVITE_ONE" \
            '{name:$n,email:($n + "@verify.zuel.edu.cn"),password:$p,invite_code:$c}')")"
    [[ $(jq -r .is_active <<<"$REG_JOINED") == true && $(jq -r '.group_name // empty' <<<"$REG_JOINED") == "zuel-p5-码组-$P5_TAG" ]] \
        && pass "凭邀请码注册：账号当场可用，且带出了进的那个组" \
        || fail "凭码注册的结果不对：$REG_JOINED"
    # **注册出来的一律是学生** —— 能自选角色等于能自选配额档
    [[ $(jq -r .role <<<"$REG_JOINED") == student ]] \
        && pass "注册出来的角色是 student（配额档不可自选）" \
        || fail "注册出来的角色是 $(jq -r .role <<<"$REG_JOINED")"

    # 不填码注册：账号先停用，而「停用」要真的登不上 —— 只看字段的话，
    # 一个把 is_active 当摆设的实现照样绿
    REG_LONER="$(curl -s -X POST "$BASE_URL/api/auth/register" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$P5_LONER" --arg p "$P5_SECRET" '{name:$n,email:($n + "@verify.zuel.edu.cn"),password:$p}')")"
    LONER_LOGIN="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$P5_LONER" --arg p "$P5_SECRET" '{name:$n,password:$p}')")"
    [[ $(jq -r .is_active <<<"$REG_LONER") == false && $LONER_LOGIN == 401 ]] \
        && pass "不填码注册：账号先停用，且真的登不上（401）" \
        || fail "不填码那条路不对：is_active=$(jq -r .is_active <<<"$REG_LONER") 登录=$LONER_LOGIN"
    # 填错码不是「当没填」：那会留下一个自己登不上、管理员也不认识的账号
    BAD_INVITE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/register" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "zuel-p5-bad-$P5_TAG" --arg p "$P5_SECRET" '{name:$n,email:($n + "@verify.zuel.edu.cn"),password:$p,invite_code:"这不是一个码"}')")"
    [[ $BAD_INVITE == 422 ]] && pass "邀请码填错 → 422，号根本不建" || fail "填错码得到 $BAD_INVITE"

    if ! login "$P5_STUDENT" "$P5_SECRET" "$JAR_P5_STUDENT"; then
        fail "凭码注册的学生登不进来，后面半条验不了"
    else
        STUDENT_UID="$(api "$JAR_P5_STUDENT" "$BASE_URL/api/auth/me" | jq -r '.id // empty')"

        # **邀请码是准入凭证**：浏览列表对所有登录用户开放，码跟着它发出去就等于没有准入。
        # 在整份响应文本里搜一次而不是只看字段名 —— 换个字段名照样是泄露
        BROWSE="$(api "$JAR_P5_STUDENT" "$BASE_URL/api/groups")"
        grep -qF "$INVITE_ONE" <<<"$BROWSE" \
            && fail "邀请码跟着公开的组列表发出去了 —— 任何登录用户都能把自己塞进任何组" \
            || pass "公开的组列表里搜不到邀请码"

        # 同一个端点、同一个组，组主看得到码而组员看不到 —— 这是这条判据里
        # 唯一「可见地不同」的地方，只验其中一半等于没验
        OWNER_CODE="$(api "$JAR_P5_OWNER" "$BASE_URL/api/groups/mine" | jq -r --arg g "$GROUP_ONE" '.[] | select(.id == $g) | .invite_code')"
        MEMBER_CODE="$(api "$JAR_P5_STUDENT" "$BASE_URL/api/groups/mine" | jq -r --arg g "$GROUP_ONE" '.[] | select(.id == $g) | .invite_code')"
        [[ $OWNER_CODE == "$INVITE_ONE" && $MEMBER_CODE == null ]] \
            && pass "/groups/mine：组主拿得到码，同组的组员拿到的是空" \
            || fail "码的可见范围不对：组主看到 $OWNER_CODE，组员看到 $MEMBER_CODE"

        # 申请 → 审批。**判据是名册在批准前后可见地不同**，不是端点回了 204
        APPLY="$(body "$JAR_P5_STUDENT" -X POST "$BASE_URL/api/groups/$GROUP_TWO/requests")"
        REQUEST_ID="$(jq -r '.id // empty' <<<"$APPLY")"
        member_count() {
            api "$JAR_P5_OWNER" "$BASE_URL/api/groups/$GROUP_TWO/members" |
                jq -r --arg u "$STUDENT_UID" 'map(select(.user_id == $u)) | length'
        }
        PENDING="$(api "$JAR_P5_OWNER" "$BASE_URL/api/groups/$GROUP_TWO/requests" | jq -r --arg r "$REQUEST_ID" 'map(select(.id == $r)) | length')"
        [[ -n $REQUEST_ID && $PENDING == 1 && $(member_count) == 0 ]] \
            && pass "申请挂进了组主的待办，而人还没进名册" \
            || fail "申请那一步不对：request_id=$REQUEST_ID 待办里 $PENDING 条，名册里已有 $(member_count) 人"

        DECIDED="$(code "$JAR_P5_OWNER" -X POST "$BASE_URL/api/groups/$GROUP_TWO/requests/$REQUEST_ID" \
            -H 'Content-Type: application/json' -d '{"approved":true}')"
        [[ $DECIDED == 204 && $(member_count) == 1 ]] \
            && pass "批准之后当场进名册（同一个端点，前 0 人后 1 人）" \
            || fail "批准没生效：返回 $DECIDED，名册里 $(member_count) 人"

        # **两个标签页各点一次**：第二次该是「已经处理过了」，而不是把批准改成否决。
        # 状态是条件 UPDATE 而不是「先读再写」，这一条验的就是那个条件
        REDECIDE="$(body "$JAR_P5_OWNER" -X POST "$BASE_URL/api/groups/$GROUP_TWO/requests/$REQUEST_ID" \
            -H 'Content-Type: application/json' -d '{"approved":false}')"
        [[ $(jq -r '.error.code // empty' <<<"$REDECIDE") == VALIDATION_ERROR && $(member_count) == 1 ]] \
            && pass "同一条申请处理两次：第二次被挡住，名册没被改回去" \
            || fail "重复审批没挡住：$REDECIDE ｜ 名册里 $(member_count) 人"

        # 非组主碰管理动作一律 404 —— 403 等于确认了「你猜的这个组是我的」
        INTRUDE="$(code "$JAR_P5_STUDENT" "$BASE_URL/api/groups/$GROUP_TWO/members")"
        [[ $INTRUDE == 404 ]] && pass "组员看名册 → 404（不是 403）" || fail "组员看名册得到 $INTRUDE"
    fi
fi
end

# ------------------------------------------------------------ P5② 工作目录
begin "P5②" "工作目录五个端点走得通，符号链接与越界路径都进不来"

if (( ! P5_JAR_READY )); then
    fail "造不出账号，这一条验不了"
else
    THREAD_P5="$(new_thread "$JAR_P5")"
    # **文件名带中文**：`path` 一律走查询参数正是为它 —— 塞进路径段要两侧各转义一遍，
    # 错一次就是一个打不开的文件
    P5_FILE="持仓-$P5_TAG.csv"
    printf '代码,市值\n600000,1200\n000001,3400\n' > "$WORK_DIR/$P5_FILE"

    UPLOADED="$(body "$JAR_P5" -X POST "$BASE_URL/api/threads/$THREAD_P5/files" -F "file=@$WORK_DIR/$P5_FILE")"
    UP_PATH="$(jq -r '.path // empty' <<<"$UPLOADED")"
    # **要守的不是「取哪个文件」而是「响应里的 path 与磁盘对得上」** —— 调用方拿它去
    # 预览与下载，说的那个必须就是落盘的那个
    if [[ -n $UP_PATH ]] && compose exec -T broker test -f "$WORKSPACE_ROOT/$THREAD_P5/$UP_PATH"; then
        pass "传：响应给的 path（$UP_PATH）与磁盘上的文件对得上"
    else
        fail "上传响应里的 path 与磁盘对不上：$UPLOADED"
    fi

    TREE="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5/files")"
    [[ $(jq -r --arg p "$UP_PATH" '.entries | map(select(.path == $p and .is_dir == false and .size > 0)) | length' <<<"$TREE") == 1 ]] \
        && pass "列：目录树里有它，is_dir 为假、size 不为零" \
        || fail "目录树里找不到 $UP_PATH：$TREE"

    # 读的是**按行分页**那条路，不是整个文件发过来
    CONTENT="$(api "$JAR_P5" --get --data-urlencode "path=$UP_PATH" "$BASE_URL/api/threads/$THREAD_P5/files/content")"
    [[ $(jq -r .total_line <<<"$CONTENT") == 3 && $(jq -r .is_binary <<<"$CONTENT") == false ]] \
        && pass "读：三行中文文本按行取回，没被当成二进制" \
        || fail "读回来的不对：$CONTENT"

    DOWNLOADED="$(api "$JAR_P5" --get --data-urlencode "path=$UP_PATH" "$BASE_URL/api/threads/$THREAD_P5/files/raw")"
    [[ $DOWNLOADED == "$(cat "$WORK_DIR/$P5_FILE")" ]] \
        && pass "下：取回的字节与传上去的一模一样" \
        || fail "取回的字节对不上：$DOWNLOADED"

    # **符号链接一个都不列，也不走进去**：agent 在沙箱里建得出链接，列进树里就等于
    # 把宿主文件摆上货架，而下一步就是可下载的
    compose exec -T broker ln -s /etc/passwd "$WORKSPACE_ROOT/$THREAD_P5/passwd.txt" >/dev/null 2>&1
    if compose exec -T broker test -L "$WORKSPACE_ROOT/$THREAD_P5/passwd.txt"; then
        [[ $(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5/files" | jq -r '.entries | map(select(.path == "passwd.txt")) | length') == 0 ]] \
            && pass "符号链接建得出来，但一条都不进目录树" \
            || fail "符号链接被列进了目录树 —— 宿主文件摆上了货架"
    else
        # 链接没建成的话，上面那条断言会因为「本来就没有」而通过 —— 那是假绿
        fail "链接没建成，「符号链接不列」这半条没触发到要测的场景"
    fi

    # 越界与不存在给同一个回答，否则这个端点就成了探测宿主机文件的工具
    ESCAPED="$(code "$JAR_P5" --get --data-urlencode "path=../../etc/passwd" "$BASE_URL/api/threads/$THREAD_P5/files/content")"
    [[ $ESCAPED == 404 ]] && pass "路径越界 → 404（与「不存在」同一个回答）" || fail "越界得到 $ESCAPED"

    # 指向目录则不必伪装成 404 —— 目录在树里本来就看得见
    compose exec -T broker mkdir -p "$WORKSPACE_ROOT/$THREAD_P5/outputs" >/dev/null 2>&1
    ON_DIR="$(code "$JAR_P5" --get --data-urlencode "path=outputs" "$BASE_URL/api/threads/$THREAD_P5/files/content")"
    [[ $ON_DIR == 422 ]] && pass "读一个目录 → 422（不伪装成 404）" || fail "读目录得到 $ON_DIR"

    # DELETE 带查询参数不能用 `--get`（它会把方法改回 GET），路径自己编一次
    ENCODED_PATH="$(jq -rn --arg s "$UP_PATH" '$s|@uri')"
    DELETED="$(code "$JAR_P5" -X DELETE "$BASE_URL/api/threads/$THREAD_P5/files?path=$ENCODED_PATH")"
    STILL="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5/files" | jq -r --arg p "$UP_PATH" '.entries | map(select(.path == $p)) | length')"
    [[ $DELETED == 204 && $STILL == 0 ]] \
        && pass "删：204，且文件从目录树里消失" \
        || fail "删没生效：返回 $DELETED，树里还有 $STILL 条"

    # 目录删不了 —— 那会连着里面的东西一起没，而侧边栏上的一下点击看不出这个后果
    DEL_DIR="$(code "$JAR_P5" -X DELETE "$BASE_URL/api/threads/$THREAD_P5/files?path=outputs")"
    [[ $DEL_DIR == 422 ]] && pass "删一个目录 → 422（挡住了）" || fail "删目录得到 $DEL_DIR"
fi
end

# --------------------------------------------------------- P5③ 会话与历史
begin "P5③" "会话增删改查与聊天历史走得通，提问原文一字不差地读得回来"

if (( ! P5_JAR_READY )); then
    fail "造不出账号，这一条验不了"
else
    THREAD_P5C="$(new_thread "$JAR_P5")"
    IN_LIST="$(api "$JAR_P5" "$BASE_URL/api/threads" | jq -r --arg t "$THREAD_P5C" '.items | map(select(.id == $t)) | length')"
    [[ -n $THREAD_P5C && $IN_LIST == 1 ]] \
        && pass "开会话：新建的那个当场出现在列表里" \
        || fail "新建的会话不在列表里：thread=$THREAD_P5C 命中 $IN_LIST 条"

    # 改。**标题这一改还有第二个作用**：填过之后 `POST /runs` 不再挂那个起标题的
    # 后台模型调用 —— 这一条因此一次模型往返都不花
    P5_TITLE="P5 回归 $P5_TAG"
    api "$JAR_P5" -X PATCH "$BASE_URL/api/threads/$THREAD_P5C" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "$P5_TITLE" '{title:$t,agent_config:{system_prompt:"回归占位"}}')" >/dev/null
    DETAIL="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5C")"
    # **这里只验存取，不验它对 agent 有没有用。** `agent_config` 从 0003 起就写得进、
    # 读得出、有测试覆盖，而装配层从来没读过它一次 —— 「配与不配，输出可见地不同」
    # 是 P6 的判据，不是这一条的。写在这里是为了别把这条绿当成那件事已经成立
    [[ $(jq -r .title <<<"$DETAIL") == "$P5_TITLE" && $(jq -r '.agent_config.system_prompt // empty' <<<"$DETAIL") == "回归占位" ]] \
        && pass "改：标题与 agent_config 都改得进、读得出（只验存取）" \
        || fail "改完读回来的不对：$DETAIL"

    # **两个字段各自可选**：只传标题时配置要原样留着 —— 一次改名把 agent 配置清空，
    # 是那种改完当时没事、下次跑分析才发现的故障
    api "$JAR_P5" -X PATCH "$BASE_URL/api/threads/$THREAD_P5C" -H 'Content-Type: application/json' \
        -d '{"title":"只改名"}' >/dev/null
    KEPT_CONFIG="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5C" | jq -r '.agent_config.system_prompt // empty')"
    [[ $KEPT_CONFIG == "回归占位" ]] \
        && pass "只改标题不动配置（改名没把 agent_config 清空）" \
        || fail "改名把配置带走了：agent_config.system_prompt=$KEPT_CONFIG"

    # 提交一条真 run，立刻取消。**判据是提问原文读得回来** —— P5 挖得最深的一处
    # 正是「教师的提问原文根本没落过库」，那时聊天历史打开就是空的
    P5_QUESTION="这条只为验历史，提交完立刻取消"
    RUN_P5="$(body "$JAR_P5" -X POST "$BASE_URL/api/threads/$THREAD_P5C/runs" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg c "$P5_QUESTION" '{content:$c}')" | jq -r '.id // empty')"
    if [[ -z $RUN_P5 ]]; then
        fail "提交不成，历史这半条验不了"
    else
        # **立刻取消**：worker 领到消息的第一件事就是看取消标志（executor 的入口处），
        # 因此这一条最多花掉一次尚未开始的领取，不是一次分析
        api "$JAR_P5" -X POST "$BASE_URL/api/runs/$RUN_P5/cancel" >/dev/null 2>&1

        # 再补一条更早的，用来验倒序与游标分页。**这条直接写库** —— 为了翻页
        # 而烧第二次分析不值当，与 P3④ 造 run 是同一条理由
        OLD_RUN="$(tr -d - < /proc/sys/kernel/random/uuid)"
        psql_query "INSERT INTO runs (id, thread_id, user_id, status, content, tokens_cache_read, tokens_uncached, tokens_output, started_at)
            VALUES ('$OLD_RUN', '$THREAD_P5C', '$UID_P5', 'succeeded', '更早的那一轮', 0,0,0, now() - interval '1 hour');" >/dev/null

        HISTORY="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5C/runs")"
        [[ $(jq -r '.items[0].content // empty' <<<"$HISTORY") == "$P5_QUESTION" ]] \
            && pass "历史：最近一轮排在最前，提问原文一字不差地读得回来" \
            || fail "历史里读不到提问原文：$(jq -c '.items' <<<"$HISTORY")"
        [[ $(jq -r '.items | length' <<<"$HISTORY") == 2 && $(jq -r '.items[1].content // empty' <<<"$HISTORY") == "更早的那一轮" ]] \
            && pass "历史：两轮都在，且按开跑时间倒序" \
            || fail "历史的条数或顺序不对：$(jq -c '[.items[].content]' <<<"$HISTORY")"

        # 游标是不透明的 (时间, 标识) 复合值。只用时间的话，同一微秒提交的两条会在
        # 翻页边界上互相顶掉 —— 这里验的是两页各一条、接得上、不重不漏
        PAGE_ONE="$(api "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5C/runs?limit=1")"
        P5_CURSOR="$(jq -r '.next_cursor // empty' <<<"$PAGE_ONE")"
        PAGE_TWO="$(api "$JAR_P5" --get --data-urlencode "cursor=$P5_CURSOR" \
            "$BASE_URL/api/threads/$THREAD_P5C/runs?limit=1")"
        [[ $(jq -r '.items[0].id // empty' <<<"$PAGE_ONE") == "$RUN_P5" && $(jq -r '.items[0].id // empty' <<<"$PAGE_TWO") == "$OLD_RUN" ]] \
            && pass "游标分页：两页各一条，接得上且不重不漏" \
            || fail "翻页对不上：第一页 $(jq -r '.items[0].id' <<<"$PAGE_ONE")，第二页 $(jq -r '.items[0].id' <<<"$PAGE_TWO")"

        # **解析不了的游标一律 422，不当成「从头开始」** —— 那会让客户端收到一整页
        # 重复数据，而它看不出发生了什么
        BAD_CURSOR="$(code "$JAR_P5" --get --data-urlencode "cursor=这不是一个游标" \
            "$BASE_URL/api/threads/$THREAD_P5C/runs")"
        [[ $BAD_CURSOR == 422 ]] && pass "解析不了的游标 → 422（不静默从头开始）" || fail "坏游标得到 $BAD_CURSOR"
    fi
fi
end

# ----------------------------------------------------------- P5④ 删会话
begin "P5④" "删会话之后工作目录真的没了，而 runs 那几行留着"

if (( ! P5_JAR_READY )); then
    fail "造不出账号，这一条验不了"
else
    THREAD_P5D="$(new_thread "$JAR_P5")"
    api "$JAR_P5" -X POST "$BASE_URL/api/threads/$THREAD_P5D/files" -F "file=@$WORK_DIR/$P5_FILE" >/dev/null 2>&1
    # **删之前先确认目录真的在**：不确认的话，一个从来没建出目录的会话删完也「没了」，
    # 这条判据会以假绿收场
    compose exec -T broker test -d "$WORKSPACE_ROOT/$THREAD_P5D" \
        && pass "删之前：工作目录在磁盘上" \
        || fail "会话的工作目录压根没建出来，这一条没触发到要测的场景"

    # runs 是成本账本，删会话不该往历史里挖洞
    KEPT_RUN="$(tr -d - < /proc/sys/kernel/random/uuid)"
    psql_query "INSERT INTO runs (id, thread_id, user_id, status, content, tokens_cache_read, tokens_uncached, tokens_output, started_at)
        VALUES ('$KEPT_RUN', '$THREAD_P5D', '$UID_P5', 'succeeded', '删会话之前的一轮', 0, 4321, 0, now());" >/dev/null

    DELETED_THREAD="$(code "$JAR_P5" -X DELETE "$BASE_URL/api/threads/$THREAD_P5D")"
    [[ $DELETED_THREAD == 204 ]] && pass "删会话 → 204" || fail "删会话得到 $DELETED_THREAD"

    AFTER_LIST="$(api "$JAR_P5" "$BASE_URL/api/threads" | jq -r --arg t "$THREAD_P5D" '.items | map(select(.id == $t)) | length')"
    AFTER_GET="$(code "$JAR_P5" "$BASE_URL/api/threads/$THREAD_P5D")"
    [[ $AFTER_LIST == 0 && $AFTER_GET == 404 ]] \
        && pass "删之后：列表里没有了，再读是 404" \
        || fail "删完还在：列表命中 $AFTER_LIST 条，详情返回 $AFTER_GET"

    # **判据不是「列表里消失」而是「磁盘上真的没了」** —— 教师要的两件事里，
    # 「别再占磁盘」这件只有这里验得到。销毁失败时端点照样答 204（那是有意的），
    # 因此光看状态码永远看不出孤儿目录
    if compose exec -T broker test -d "$WORKSPACE_ROOT/$THREAD_P5D"; then
        fail "会话删了而工作目录还在（$WORKSPACE_ROOT/$THREAD_P5D）—— 磁盘没释放，且端点答的是 204"
    else
        pass "删之后：工作目录真的从磁盘上没了"
    fi

    KEPT_COUNT="$(psql_query "SELECT count(*) FROM runs WHERE id='$KEPT_RUN';" | tr -d '[:space:]')"
    [[ $KEPT_COUNT == 1 ]] \
        && pass "runs 那一行留着：成本账本没被删会话挖出洞" \
        || fail "删会话把 runs 的历史也带走了（剩 ${KEPT_COUNT:-?} 行）"
fi
end


# ===========================================================================
# P6：真前端底座与自定义智能体（两条免费，一条要 LLM）
# ===========================================================================
#
# ① 用两个没有 checkpoint 交叉影响的会话跑同一句便宜问题，做双向断言。
# ② 直接查 prompt 拼接，不跑模型。③ 停着 worker 查 run 级快照，两条
# queued run 在恢复 worker 之前必须都取消，不然一条“免费验收”会在收尾时变成付费分析。

P6_TAG="$$-$(date +%s%N | tail -c 5)"
P6_JAR_READY=0
if session_for p6; then
    JAR_P6="$SESSION_JAR"
    P6_JAR_READY=1
fi

# 跑一句简单分析并从 SSE 里拼回主 agent 的正式答复。结果放在
# P6_LAST_* 里，不用 command substitution：答复可能有换行，拿制表符之类的分隔符
# 来回传会把“以喵开头”这条判据自己改掉。
p6_analyse() {
    local jar="$1" thread_id="$2" stem="$3" window="${4:-$RUN_WINDOW}" run_body
    P6_LAST_RUN=""
    P6_LAST_STATUS=""
    P6_LAST_ANSWER=""

    run_body="$(body "$jar" -X POST "$BASE_URL/api/threads/$thread_id/runs" \
        -H 'Content-Type: application/json' -d "$(jq -nc --arg c "$P6_QUESTION" '{content:$c}')")"
    P6_LAST_RUN="$(jq -r '.id // empty' <<<"$run_body")"
    [[ -n $P6_LAST_RUN ]] || return 1

    if ! timeout "$window" curl -fsS -b "$jar" -N \
        "$BASE_URL/api/runs/$P6_LAST_RUN/events" > "$WORK_DIR/$stem.sse"; then
        curl -s --connect-timeout 5 --max-time 20 -b "$jar" -X POST \
            "$BASE_URL/api/runs/$P6_LAST_RUN/cancel" >/dev/null 2>&1
        P6_LAST_STATUS="$(run_status "$jar" "$P6_LAST_RUN" 2>/dev/null)"
        return 1
    fi
    if ! grep '^data:' "$WORK_DIR/$stem.sse" | sed 's/^data: *//' |
        jq -c . > "$WORK_DIR/$stem.json" 2>/dev/null; then
        return 1
    fi

    P6_LAST_STATUS="$(run_status "$jar" "$P6_LAST_RUN" 2>/dev/null)"
    [[ $P6_LAST_STATUS == succeeded ]] || return 1
    P6_LAST_ANSWER="$(jq -rs \
        '[.[] | select(.type == "token" and (.path | length == 0)) | .data.text] | join("")' \
        "$WORK_DIR/$stem.json")"
    [[ -n $P6_LAST_ANSWER ]]
}

# ---------------------------------------------- P6① 配与不配，输出可见地不同
begin "P6①" "配与不配自定义提示词，同一问题的输出可见地不同"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次便宜的真实分析"
elif (( ! P6_JAR_READY )); then
    fail "造不出账号，两次真实分析验不了"
else
    THREAD_P6_PLAIN="$(new_thread "$JAR_P6")"
    THREAD_P6_CAT="$(new_thread "$JAR_P6")"
    P6_CAT_PROMPT="回答任何问题时，正式答复的第一个字符必须是「喵」，在它之前不要输出空格、标点或 Markdown。"
    P6_QUESTION="二加二等于几？请只回答答案，不要调用工具。"

    # 先填标题再 POST run：空标题会另起一次轻量模型调用，不仅多花钱，
    # 还会让“两次真实分析”的调用数不再是两次。
    P6_PLAIN_PATCHED=0
    P6_CAT_PATCHED=0
    api "$JAR_P6" -X PATCH "$BASE_URL/api/threads/$THREAD_P6_PLAIN" \
        -H 'Content-Type: application/json' -d "$(jq -nc --arg t "P6 默认 $P6_TAG" '{title:$t}')" \
        >/dev/null 2>&1 && P6_PLAIN_PATCHED=1
    api "$JAR_P6" -X PATCH "$BASE_URL/api/threads/$THREAD_P6_CAT" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P6 自定义 $P6_TAG" --arg p "$P6_CAT_PROMPT" \
            '{title:$t,agent_config:{system_prompt:$p}}')" >/dev/null 2>&1 && P6_CAT_PATCHED=1

    P6_PLAIN_OK=0
    P6_CAT_OK=0
    if (( P6_PLAIN_PATCHED )) && p6_analyse "$JAR_P6" "$THREAD_P6_PLAIN" p6-plain; then
        P6_PLAIN_OK=1
        P6_PLAIN_ANSWER="$P6_LAST_ANSWER"
        P6_PLAIN_STATUS="$P6_LAST_STATUS"
    else
        P6_PLAIN_ANSWER="${P6_LAST_ANSWER:-}"
        P6_PLAIN_STATUS="${P6_LAST_STATUS:-提交失败}"
    fi
    if (( P6_CAT_PATCHED )) && p6_analyse "$JAR_P6" "$THREAD_P6_CAT" p6-cat; then
        P6_CAT_OK=1
        P6_CAT_ANSWER="$P6_LAST_ANSWER"
        P6_CAT_STATUS="$P6_LAST_STATUS"
    else
        P6_CAT_ANSWER="${P6_LAST_ANSWER:-}"
        P6_CAT_STATUS="${P6_LAST_STATUS:-提交失败}"
    fi

    if (( ! P6_PLAIN_PATCHED || ! P6_CAT_PATCHED )); then
        fail "两个会话没都在提交前设好标题与配置"
    elif (( ! P6_PLAIN_OK || ! P6_CAT_OK )); then
        fail "两条 run 没都跑到 succeeded：默认=$P6_PLAIN_STATUS，自定义=$P6_CAT_STATUS"
    elif [[ $P6_PLAIN_ANSWER == 喵* ]]; then
        fail "默认会话也以「喵」开头，配置可能串进了全局：$P6_PLAIN_ANSWER"
    elif [[ $P6_CAT_ANSWER != 喵* ]]; then
        fail "自定义会话没以「喵」开头，配置没生效：$P6_CAT_ANSWER"
    else
        pass "双向断言成立：默认不以「喵」开头，自定义以「喵」开头"
    fi
fi
end

# ------------------------------------------------ P6② 用户覆盖不了环境契约
begin "P6②" "平台的环境契约排在最末，且用户覆盖不掉"

P6_PROMPT_CHECK="$(in_api_python "
import json
from agent.config import AgentConfig
from agent.prompt import ANALYSIS_SEGMENT, ENVIRONMENT_SEGMENT, OUTPUT_PATH, compose_prompt

custom = '把图保存到当前目录'
prompt = compose_prompt(AgentConfig(system_prompt=custom))
checks = {
    'user': custom in prompt,
    'workdir': '/workspace' in ENVIRONMENT_SEGMENT,
    'write_execute': all(part in ENVIRONMENT_SEGMENT for part in ('write_file', 'execute')),
    'output': OUTPUT_PATH in ENVIRONMENT_SEGMENT,
    'offline_pip': all(part in ENVIRONMENT_SEGMENT for part in ('公网', 'pip')),
    'font': all(part in ENVIRONMENT_SEGMENT for part in ('字体', 'rcParams')),
    'order': prompt.index(custom) < prompt.index(ANALYSIS_SEGMENT) < prompt.index(ENVIRONMENT_SEGMENT),
    'suffix': prompt.endswith(ENVIRONMENT_SEGMENT),
}
print(json.dumps(checks, ensure_ascii=False))
" 2>/dev/null)" || P6_PROMPT_CHECK=""

if jq -e '
    .user and .workdir and .write_execute and .output and .offline_pip and .font and .order and .suffix
' >/dev/null 2>&1 <<<"$P6_PROMPT_CHECK"; then
    pass "用户句保留，五条环境契约全在，顺序为用户 → 分析 → 环境且环境整段收尾"
else
    fail "prompt 拼接契约不完整：${P6_PROMPT_CHECK:-拼接函数调用失败}"
fi
end

# ---------------------------------------------- P6③ thread 改动不改历史快照
begin "P6③" "run 级快照：thread 默认改了，历史 run 仍记着当时那份"

if (( ! P6_JAR_READY )); then
    fail "造不出账号，快照链路验不了"
else
    THREAD_P6_SNAPSHOT="$(new_thread "$JAR_P6")"
    register_snapshot_thread "$THREAD_P6_SNAPSHOT" "$JAR_P6"
    P6_CONFIG_A="P6-snapshot-A-$P6_TAG"
    P6_CONFIG_B="P6-snapshot-B-$P6_TAG"
    WORKER_TOUCHED=1
    P6_STOPPED_WORKERS=""
    if ! compose stop -t 30 worker >/dev/null 2>&1 \
        || ! P6_STOPPED_WORKERS="$(worker_ids)" \
        || [[ -n $P6_STOPPED_WORKERS ]]; then
        fail "worker 没停干净，不提交本来应该免费的快照 run"
        if restore_workers; then
            WORKER_TOUCHED=""
        else
            fail "worker 停止失败后也没恢复到 $WORKER_COUNT 个副本，终止后续判据"
            end
            exit 1
        fi
    else

    # A 与 B 都在提交前把标题填上，免得这条纯查库的判据偷偷起一次标题模型。
    P6_SNAPSHOT_TITLE="P6 快照 $P6_TAG"
    P6_PATCH_RESPONSE_A=""
    if ! P6_PATCH_RESPONSE_A="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P6" \
        -X PATCH "$BASE_URL/api/threads/$THREAD_P6_SNAPSHOT" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "$P6_SNAPSHOT_TITLE" --arg p "$P6_CONFIG_A" \
            '{title:$t,agent_config:{system_prompt:$p}}')")" \
        || ! jq -e --arg t "$P6_SNAPSHOT_TITLE" --arg p "$P6_CONFIG_A" \
            '.title == $t and .agent_config.system_prompt == $p' \
            >/dev/null 2>&1 <<<"$P6_PATCH_RESPONSE_A"; then
        fail "提交前没能确认标题与配置 A 已保存，不冒险触发标题模型"
        end
        exit 1
    fi
    SNAPSHOT_POST_IN_FLIGHT=1
    P6_POST_RESPONSE_A=""
    if P6_POST_RESPONSE_A="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P6" \
        -X POST "$BASE_URL/api/threads/$THREAD_P6_SNAPSHOT/runs" \
        -H 'Content-Type: application/json' -d '{"content":"P6 快照 A"}')"; then
        SNAPSHOT_POST_IN_FLIGHT=0
    else
        fail "第一条快照 run 的提交结果不确定，worker 保持停止并终止后续判据"
        end
        exit 1
    fi
    RUN_P6_SNAPSHOT_A="$(jq -r '.id // empty' <<<"$P6_POST_RESPONSE_A")"
    P6_OLD_INITIAL=""
    if [[ -n $RUN_P6_SNAPSHOT_A ]]; then
        P6_OLD_INITIAL="$(psql_query \
            "SELECT COALESCE(agent_config->>'system_prompt', '') FROM runs WHERE id='$RUN_P6_SNAPSHOT_A';" | tr -d '\r\n')"
    fi

    P6_PATCH_RESPONSE_B=""
    if ! P6_PATCH_RESPONSE_B="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P6" \
        -X PATCH "$BASE_URL/api/threads/$THREAD_P6_SNAPSHOT" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg p "$P6_CONFIG_B" '{agent_config:{system_prompt:$p}}')")" \
        || ! jq -e --arg t "$P6_SNAPSHOT_TITLE" --arg p "$P6_CONFIG_B" \
            '.title == $t and .agent_config.system_prompt == $p' \
            >/dev/null 2>&1 <<<"$P6_PATCH_RESPONSE_B"; then
        fail "没能确认配置 B 已保存，不提交一条已知会让快照判据失败的 run"
        end
        exit 1
    fi
    P6_OLD_AFTER_PATCH=""
    if [[ -n $RUN_P6_SNAPSHOT_A ]]; then
        P6_OLD_AFTER_PATCH="$(psql_query \
            "SELECT COALESCE(agent_config->>'system_prompt', '') FROM runs WHERE id='$RUN_P6_SNAPSHOT_A';" | tr -d '\r\n')"
    fi

    SNAPSHOT_POST_IN_FLIGHT=1
    P6_POST_RESPONSE_B=""
    if P6_POST_RESPONSE_B="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P6" \
        -X POST "$BASE_URL/api/threads/$THREAD_P6_SNAPSHOT/runs" \
        -H 'Content-Type: application/json' -d '{"content":"P6 快照 B"}')"; then
        SNAPSHOT_POST_IN_FLIGHT=0
    else
        fail "第二条快照 run 的提交结果不确定，worker 保持停止并终止后续判据"
        end
        exit 1
    fi
    RUN_P6_SNAPSHOT_B="$(jq -r '.id // empty' <<<"$P6_POST_RESPONSE_B")"
    P6_NEW_SNAPSHOT=""
    if [[ -n $RUN_P6_SNAPSHOT_B ]]; then
        P6_NEW_SNAPSHOT="$(psql_query \
            "SELECT COALESCE(agent_config->>'system_prompt', '') FROM runs WHERE id='$RUN_P6_SNAPSHOT_B';" | tr -d '\r\n')"
    fi

    [[ -n $RUN_P6_SNAPSHOT_A && $P6_OLD_INITIAL == "$P6_CONFIG_A" ]] \
        && pass "第一条 run 在 queued 时已快照 A" \
        || fail "第一条 run 没快照 A：run=${RUN_P6_SNAPSHOT_A:-空} snapshot=$P6_OLD_INITIAL"
    [[ $P6_OLD_AFTER_PATCH == "$P6_CONFIG_A" ]] \
        && pass "thread 改成 B 后，老 run 仍是 A" \
        || fail "thread 改动污染了老 run：$P6_OLD_AFTER_PATCH"
    [[ -n $RUN_P6_SNAPSHOT_B && $P6_NEW_SNAPSHOT == "$P6_CONFIG_B" ]] \
        && pass "改动后新提交的 run 快照 B" \
        || fail "新 run 没快照 B：run=${RUN_P6_SNAPSHOT_B:-空} snapshot=$P6_NEW_SNAPSHOT"

    # 这是安全边界，不只是验收的一个 pass：取消失败就不得恢复 worker。
    # EXIT trap 会再试一次；仍失败则保持 worker 停止，留给人工处理。
    P6_SUBMITTED_BOTH=0
    [[ -n $RUN_P6_SNAPSHOT_A && -n $RUN_P6_SNAPSHOT_B ]] && P6_SUBMITTED_BOTH=1
    if cancel_snapshot_runs 1; then
        if (( P6_SUBMITTED_BOTH )); then
            pass "两条 queued run 都已取消，现在才恢复 worker"
        else
            fail "没有成功提交两条 run；已取消实际提交的那些，现在才恢复 worker"
        fi
        if restore_workers; then
            WORKER_TOUCHED=""
        else
            fail "worker 没恢复到 $WORKER_COUNT 个副本，终止后续判据"
            end
            exit 1
        fi
    else
        fail "两条 queued run 没能全部取消，worker 保持停止"
        end
        exit 1
    fi
    fi
fi
end


# ===========================================================================
# P7：智能体目录、三档可见性与审核（五条免费，一条要 LLM）
# ===========================================================================
#
# **本期唯一会安静失效的缺陷是「多看见了一条」** —— 别组的老师在列表里刷到一个
# 不该看到的提示词，既不报错也不会有人来报。因此这一组每一条可见性断言都是**双向**的，
# 且「能不能引用」与「列表里看不看得见」**分开各断一次**：列表过滤对了而提交侧忘了查，
# 是最典型的漏洞形状。
#
# **三个账号必须真的分属不同组**，否则「别组看不见」那一半根本没被触发过 ——
# 下面回读 `user_groups` 确认这一条，不靠「我建组时是这么写的」。

P7_TAG="$$-$(date +%s%N | tail -c 5)"
P7_SECRET="zuel-p7-$$"
P7_READY=0
P7_SETUP_NOTE="未开始"

# 造一个号并登录。**名字要留得住** —— 加人进组走的是用户名而不是 uuid，
# `open_session` 只回 id，这里另起一份
p7_open() {
    local slot="$1" role="$2" name jar uid
    name="zuel-p7-$slot-$P7_TAG"
    jar="$WORK_DIR/cookie-p7-$slot"
    make_user "$name" "$P7_SECRET" "$role" || return 1
    login "$name" "$P7_SECRET" "$jar" || return 1
    uid="$(curl -fsS -b "$jar" "$BASE_URL/api/auth/me" | jq -r '.id // empty')"
    [[ -n $uid ]] || return 1
    printf '%s %s %s\n' "$jar" "$uid" "$name"
}

p7_setup() {
    read -r JAR_P7_A UID_P7_A NAME_P7_A <<<"$(p7_open a teacher)" || { P7_SETUP_NOTE="造不出作者 A"; return 1; }
    read -r JAR_P7_B UID_P7_B NAME_P7_B <<<"$(p7_open b teacher)" || { P7_SETUP_NOTE="造不出同组 B"; return 1; }
    read -r JAR_P7_C UID_P7_C NAME_P7_C <<<"$(p7_open c teacher)" || { P7_SETUP_NOTE="造不出别组 C"; return 1; }
    read -r JAR_P7_R UID_P7_R NAME_P7_R <<<"$(p7_open r reviewer)" || { P7_SETUP_NOTE="造不出审核员"; return 1; }
    read -r JAR_P7_ADMIN UID_P7_ADMIN NAME_P7_ADMIN <<<"$(p7_open admin admin)" || { P7_SETUP_NOTE="造不出管理员"; return 1; }

    GROUP_P7_1="$(api "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/admin/groups" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "P7-G1-$P7_TAG" --arg o "$UID_P7_A" '{name:$n,owner_id:$o}')" | jq -r '.id // empty')"
    GROUP_P7_2="$(api "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/admin/groups" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "P7-G2-$P7_TAG" --arg o "$UID_P7_C" '{name:$n,owner_id:$o}')" | jq -r '.id // empty')"
    [[ -n $GROUP_P7_1 && -n $GROUP_P7_2 ]] || { P7_SETUP_NOTE="两个课题组没建出来"; return 1; }

    api "$JAR_P7_A" -X POST "$BASE_URL/api/groups/$GROUP_P7_1/members" \
        -H 'Content-Type: application/json' -d "$(jq -nc --arg n "$NAME_P7_B" '{name:$n}')" >/dev/null || {
        P7_SETUP_NOTE="B 没加进 G1"; return 1; }

    # **回读 user_groups**：三个人真的分属不同组，这一条不成立的话
    # 「别组看不见」那一半根本没被触发过，而判据照样会绿
    local both same
    both="$(psql_query "SELECT count(*) FROM user_groups
        WHERE group_id = '$GROUP_P7_1' AND user_id IN ('$UID_P7_A', '$UID_P7_B');" | tr -d '[:space:]')"
    same="$(psql_query "SELECT count(*) FROM user_groups a JOIN user_groups b USING (group_id)
        WHERE a.user_id = '$UID_P7_A' AND b.user_id = '$UID_P7_C';" | tr -d '[:space:]')"
    [[ $both == 2 ]] || { P7_SETUP_NOTE="A 与 B 不在同一个组里（G1 里只有 ${both:-?} 人）"; return 1; }
    [[ $same == 0 ]] || { P7_SETUP_NOTE="C 与 A 竟然同组，「别组看不见」这一半验不了"; return 1; }
    P7_SETUP_NOTE="三个账号两个组已就绪"
    return 0
}

# 建一个 agent 并发布 v1，标准输出是 agent_id
p7_new_agent() {
    local jar="$1" name="$2" prompt="$3" agent_id
    agent_id="$(api "$jar" -X POST "$BASE_URL/api/agents" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$name" --arg p "$prompt" \
            '{name:$n,description:"P7 验收用",subject:"金融学",system_prompt:$p}')" | jq -r '.id // empty')"
    [[ -n $agent_id ]] || return 1
    api "$jar" -X POST "$BASE_URL/api/agents/$agent_id/versions" >/dev/null || return 1
    printf '%s\n' "$agent_id"
}

# 改内容再发布一版，标准输出是新的版本号
p7_release_next() {
    local jar="$1" agent_id="$2" prompt="$3" body
    api "$jar" -X PUT "$BASE_URL/api/agents/$agent_id/draft" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg p "$prompt" '{system_prompt:$p}')" >/dev/null || return 1
    body="$(api "$jar" -X POST "$BASE_URL/api/agents/$agent_id/versions")" || return 1
    jq -r '[.versions[] | select(.status == "released") | .version] | max' <<<"$body"
}

p7_share() {
    api "$1" -X PUT "$BASE_URL/api/agents/$2/sharing" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg g "$3" '{visibility:"group",group_ids:[$g]}')" >/dev/null
}

p7_unshare() {
    api "$1" -X PUT "$BASE_URL/api/agents/$2/sharing" -H 'Content-Type: application/json' \
        -d '{"visibility":"private","group_ids":[]}' >/dev/null
}

# 提审最新已发布的那一版，标准输出是这条审核记录的 id
p7_submit_review() {
    local jar="$1" agent_id="$2" body
    body="$(api "$jar" -X POST "$BASE_URL/api/agents/$agent_id/reviews" -H 'Content-Type: application/json' \
        -d '{"responsibility_confirmed":true}')" || return 1
    jq -r 'first(.versions[] | select(.review_status == "pending") | .review_id) // empty' <<<"$body"
}

# 某个人的「我能引用的」里有没有它
p7_available_has() {
    api "$1" "$BASE_URL/api/agents/available" | jq -e --arg id "$2" 'any(.[]; .id == $id)' >/dev/null 2>&1
}

# 广场上有没有它
p7_catalog_has() {
    api "$1" "$BASE_URL/api/agents" | jq -e --arg id "$2" 'any(.[]; .id == $id)' >/dev/null 2>&1
}

# 广场上展示的是哪一版
p7_catalog_version() {
    api "$1" "$BASE_URL/api/agents" | jq -r --arg id "$2" 'first(.[] | select(.id == $id) | .version) // empty'
}

# 这个会话里现在有几条 run。422 那几条断言全靠它 —— 只看状态码的话，
# 一个「先落库再校验」的实现照样会绿，而它已经把别人的提示词跑起来了
p7_run_count() {
    psql_query "SELECT count(*) FROM runs WHERE thread_id = '$1';" | tr -d '[:space:]'
}

if p7_setup; then
    P7_READY=1
fi
log "P7 前置：$P7_SETUP_NOTE"

# ------------------------------------------- P7① 组内共享同组看得见、别组看不见
begin "P7①" "组内共享同组看得见、别组看不见，撤回之后立刻收得回"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），可见性验不了"
else
    AGENT_P7_SHARE="$(p7_new_agent "$JAR_P7_A" "P7 共享 $P7_TAG" "每一句都以「喵」开头。")" || AGENT_P7_SHARE=""
    if [[ -z $AGENT_P7_SHARE ]]; then
        fail "A 没能建出并发布一个 agent"
    else
        p7_share "$JAR_P7_A" "$AGENT_P7_SHARE" "$GROUP_P7_1" || fail "A 没能把它共享给 G1"

        # **双向断言。** 只断 B 看得见是不够的：C 也看得见说明过滤漏了，
        # 两个都看不见说明共享压根没写进去
        p7_available_has "$JAR_P7_B" "$AGENT_P7_SHARE" \
            && pass "同组 B 在「我能引用的」里看得见它" \
            || fail "同组 B 看不见它 —— 共享没写进去"
        p7_available_has "$JAR_P7_C" "$AGENT_P7_SHARE" \
            && fail "别组 C 也看得见它 —— 可见性过滤漏了条件" \
            || pass "别组 C 看不见它"

        # 越权走 404 不是 403：403 等于确认了「你猜的这个 id 存在」
        P7_MINE_CODE="$(code "$JAR_P7_C" "$BASE_URL/api/agents/mine/$AGENT_P7_SHARE")"
        [[ $P7_MINE_CODE == 404 ]] \
            && pass "别组 C 打 /agents/mine/{id} 得到 404" \
            || fail "别组 C 打 /agents/mine/{id} 得到 $P7_MINE_CODE，应该是 404"

        # **不止查列表，还要试着用。** 列表过滤对了而提交侧忘了查，
        # 是最典型的漏洞形状：C 从别处拿到 id 就能引用 A 的提示词
        THREAD_P7_C="$(new_thread "$JAR_P7_C")"
        P7_C_SUBMIT="$(code "$JAR_P7_C" -X POST "$BASE_URL/api/threads/$THREAD_P7_C/runs" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg id "$AGENT_P7_SHARE" '{content:"P7 越权引用",agent_config:{agent_id:$id}}')")"
        P7_C_RUNS="$(p7_run_count "$THREAD_P7_C")"
        [[ $P7_C_SUBMIT == 422 && $P7_C_RUNS == 0 ]] \
            && pass "别组 C 拿着 id 提交得到 422，且库里一行 run 都没多出来" \
            || fail "别组 C 引用别人的 agent：状态码 $P7_C_SUBMIT，库里多出 $P7_C_RUNS 行 run"

        # 撤回之后 B 存着这个引用的会话，下一次提问必须硬失败而不是回退默认
        THREAD_P7_B="$(new_thread "$JAR_P7_B")"
        api "$JAR_P7_B" -X PATCH "$BASE_URL/api/threads/$THREAD_P7_B" -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg id "$AGENT_P7_SHARE" '{title:"P7 引用会话",agent_config:{agent_id:$id}}')" \
            >/dev/null || fail "B 没能把这个引用存进会话默认"

        p7_unshare "$JAR_P7_A" "$AGENT_P7_SHARE" || fail "A 没能把它改回私有"

        p7_available_has "$JAR_P7_B" "$AGENT_P7_SHARE" \
            && fail "改回私有之后 B 还看得见它 —— 撤回没生效" \
            || pass "改回私有之后 B 立刻看不见它了"

        P7_B_SUBMIT="$(code "$JAR_P7_B" -X POST "$BASE_URL/api/threads/$THREAD_P7_B/runs" \
            -H 'Content-Type: application/json' -d '{"content":"P7 撤回后提问"}')"
        P7_B_RUNS="$(p7_run_count "$THREAD_P7_B")"
        # **422 不是「回退默认」。** 静默回退跑得完、不报错，唯一的症状是回答变了味 ——
        # 判据必须把这两者分开，因此同时看状态码与库里有没有多出一行
        [[ $P7_B_SUBMIT == 422 && $P7_B_RUNS == 0 ]] \
            && pass "撤回之后 B 的会话提问得到 422，没有静默用默认提示词跑起来" \
            || fail "撤回之后 B 仍能提交：状态码 $P7_B_SUBMIT，库里多出 $P7_B_RUNS 行 run"
    fi
fi
end

# ------------------------------------------------- P7② 未过审的进不了广场
begin "P7②" "未过审的进不了广场；拒绝理由回得来；改一版要重审一版"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），审核闸门验不了"
else
    AGENT_P7_REVIEW="$(p7_new_agent "$JAR_P7_A" "P7 审核 $P7_TAG" "第一版：每一句都以「喵」开头。")" || AGENT_P7_REVIEW=""
    if [[ -z $AGENT_P7_REVIEW ]]; then
        fail "A 没能建出并发布一个待审的 agent"
    else
        p7_share "$JAR_P7_A" "$AGENT_P7_REVIEW" "$GROUP_P7_1" || fail "A 没能把待审的这个共享给 G1"

        # 后端也校验责任确认：只靠前端拦的话，直接打接口就绕过了
        P7_NO_CONFIRM="$(code "$JAR_P7_A" -X POST "$BASE_URL/api/agents/$AGENT_P7_REVIEW/reviews" \
            -H 'Content-Type: application/json' -d '{"responsibility_confirmed":false}')"
        [[ $P7_NO_CONFIRM == 422 ]] \
            && pass "没勾责任确认提审得到 422" \
            || fail "没勾责任确认竟然提审成功了：$P7_NO_CONFIRM"

        REVIEW_P7_ONE="$(p7_submit_review "$JAR_P7_A" "$AGENT_P7_REVIEW")"
        [[ -n $REVIEW_P7_ONE ]] || fail "提审没留下一条待审记录"

        p7_catalog_has "$JAR_P7_C" "$AGENT_P7_REVIEW" \
            && fail "还没审就进了广场" \
            || pass "提审但没审时，C 在广场上看不到它"

        # 拒绝不填理由要被后端挡下 —— 作者看到的不能是「被拒了，没说为什么」
        P7_NO_REASON="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P7_ONE" \
            -H 'Content-Type: application/json' -d '{"approved":false}')"
        [[ $P7_NO_REASON == 422 ]] \
            && pass "拒绝不填理由得到 422" \
            || fail "拒绝不填理由竟然成功了：$P7_NO_REASON"

        P7_REASON="提示词过于宽泛"
        api "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P7_ONE" -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg r "$P7_REASON" '{approved:false,reason:$r}')" >/dev/null \
            || fail "审核员没能拒绝它"

        p7_catalog_has "$JAR_P7_C" "$AGENT_P7_REVIEW" \
            && fail "被拒之后仍然在广场上" \
            || pass "被拒之后 C 在广场上仍然看不到它"

        P7_SEEN_REASON="$(api "$JAR_P7_A" "$BASE_URL/api/agents/mine/$AGENT_P7_REVIEW" |
            jq -r 'first(.versions[] | select(.review_status == "rejected") | .review_reason) // empty')"
        [[ $P7_SEEN_REASON == "$P7_REASON" ]] \
            && pass "作者读得到那句拒绝理由，一字不差" \
            || fail "作者读到的理由是「${P7_SEEN_REASON:-空}」，应该是「$P7_REASON」"

        # 被拒不影响组内：审核管的是别人能不能看见，不是作者能不能用
        p7_available_has "$JAR_P7_B" "$AGENT_P7_REVIEW" \
            && pass "被拒之后同组 B 照常用得到它" \
            || fail "被拒之后同组 B 也用不了了 —— 审核越权管到了组内"

        P7_V2="$(p7_release_next "$JAR_P7_A" "$AGENT_P7_REVIEW" "第二版：每一句都以「汪」开头。")"
        REVIEW_P7_TWO="$(p7_submit_review "$JAR_P7_A" "$AGENT_P7_REVIEW")"
        if [[ -z $REVIEW_P7_TWO ]]; then
            fail "改后重新提审没留下待审记录"
        else
            api "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P7_TWO" \
                -H 'Content-Type: application/json' -d '{"approved":true}' >/dev/null \
                || fail "审核员没能通过 v$P7_V2"
            P7_SHOWN="$(p7_catalog_version "$JAR_P7_C" "$AGENT_P7_REVIEW")"
            [[ $P7_SHOWN == "$P7_V2" ]] \
                && pass "通过之后 C 在广场上看得见它，展示的是 v$P7_V2" \
                || fail "广场上展示的是 v${P7_SHOWN:-空}，应该是 v$P7_V2"
        fi

        # **这一步是这条判据的核心。** 少了它，一个「审一次之后随便改」的实现
        # 照样全绿 —— 而那等于没有审核
        P7_V3="$(p7_release_next "$JAR_P7_A" "$AGENT_P7_REVIEW" "第三版：每一句都以「哞」开头。")"
        p7_submit_review "$JAR_P7_A" "$AGENT_P7_REVIEW" >/dev/null
        P7_STILL="$(p7_catalog_version "$JAR_P7_C" "$AGENT_P7_REVIEW")"
        [[ $P7_STILL == "$P7_V2" ]] \
            && pass "发了 v$P7_V3 但没审，广场上仍是 v$P7_V2 —— 审核拦住了每一次变更" \
            || fail "没审过的 v$P7_V3 溜进了广场：广场上现在是 v${P7_STILL:-空}"
    fi
fi
end

# ------------------------------------------ P7③ 选与不选同一个 agent，输出不同
begin "P7③" "选与不选同一个 agent，同一问题的输出可见地不同"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次便宜的真实分析"
elif (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），两次真实分析验不了"
else
    P7_QUESTION="二加二等于几？请只回答答案，不要调用工具。"
    AGENT_P7_CAT="$(p7_new_agent "$JAR_P7_A" "P7 喵语老师 $P7_TAG" \
        "回答任何问题时，正式答复的第一个字符必须是「喵」，在它之前不要输出空格、标点或 Markdown。")" || AGENT_P7_CAT=""

    if [[ -z $AGENT_P7_CAT ]]; then
        fail "没能建出并发布喵语老师"
    else
        # **仍然是两个会话**，不是同一个会话问两次 —— checkpoint 里的历史会污染第二次。
        # 两边都在提交前填好标题：空标题会另起一次轻量模型调用
        THREAD_P7_PLAIN="$(new_thread "$JAR_P7_A")"
        THREAD_P7_AGENT="$(new_thread "$JAR_P7_A")"
        P7_PLAIN_SET=0
        P7_AGENT_SET=0
        api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P7_PLAIN" -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg t "P7 默认 $P7_TAG" '{title:$t}')" >/dev/null 2>&1 && P7_PLAIN_SET=1
        api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P7_AGENT" -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg t "P7 引用 $P7_TAG" --arg id "$AGENT_P7_CAT" \
                '{title:$t,agent_config:{agent_id:$id}}')" >/dev/null 2>&1 && P7_AGENT_SET=1

        P7_PLAIN_OK=0
        P7_AGENT_OK=0
        P6_QUESTION="$P7_QUESTION"
        if (( P7_PLAIN_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P7_PLAIN" p7-plain; then
            P7_PLAIN_OK=1
            P7_PLAIN_ANSWER="$P6_LAST_ANSWER"
            P7_PLAIN_STATUS="$P6_LAST_STATUS"
        else
            P7_PLAIN_ANSWER="${P6_LAST_ANSWER:-}"
            P7_PLAIN_STATUS="${P6_LAST_STATUS:-提交失败}"
        fi
        if (( P7_AGENT_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P7_AGENT" p7-agent; then
            P7_AGENT_OK=1
            P7_AGENT_ANSWER="$P6_LAST_ANSWER"
            P7_AGENT_STATUS="$P6_LAST_STATUS"
            P7_AGENT_RUN="$P6_LAST_RUN"
        else
            P7_AGENT_ANSWER="${P6_LAST_ANSWER:-}"
            P7_AGENT_STATUS="${P6_LAST_STATUS:-提交失败}"
            P7_AGENT_RUN="${P6_LAST_RUN:-}"
        fi

        if (( ! P7_PLAIN_SET || ! P7_AGENT_SET )); then
            fail "两个会话没都在提交前设好标题与配置"
        elif (( ! P7_PLAIN_OK || ! P7_AGENT_OK )); then
            fail "两条 run 没都跑到 succeeded：默认=$P7_PLAIN_STATUS，引用=$P7_AGENT_STATUS"
        elif [[ $P7_PLAIN_ANSWER == 喵* ]]; then
            fail "默认会话也以「喵」开头，引用可能串进了全局：$P7_PLAIN_ANSWER"
        elif [[ $P7_AGENT_ANSWER != 喵* ]]; then
            fail "引用会话没以「喵」开头，引用没生效：$P7_AGENT_ANSWER"
        else
            pass "双向断言成立：不选 agent 不以「喵」开头，选了以「喵」开头"
        fi

        # **只看输出的话分不清是引用生效了还是模型碰巧这么答的** —— 快照里三样都要有
        if [[ -n $P7_AGENT_RUN ]]; then
            P7_SNAPSHOT="$(psql_query "SELECT COALESCE(agent_config->>'agent_id','')
                || '|' || COALESCE(agent_config->>'agent_version','')
                || '|' || COALESCE(agent_config->>'system_prompt','')
                FROM runs WHERE id='$P7_AGENT_RUN';" | tr -d '\r')"
            P7_WANT_PROMPT="$(api "$JAR_P7_A" "$BASE_URL/api/agents/mine/$AGENT_P7_CAT" |
                jq -r 'first(.versions[] | select(.status == "released") | .system_prompt) // empty')"
            [[ $P7_SNAPSHOT == "$AGENT_P7_CAT|1|$P7_WANT_PROMPT" ]] \
                && pass "快照里 agent_id、agent_version 与那一版的原文都在" \
                || fail "快照对不上：$P7_SNAPSHOT"
        else
            fail "拿不到引用那条 run 的 id，快照验不了"
        fi
    fi
fi
end

# ------------------------------------------------------- P7④ 版本冻结
begin "P7④" "版本冻结：作者发了 v2，历史 run 的快照仍是 v1"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），版本冻结验不了"
else
    AGENT_P7_FREEZE="$(p7_new_agent "$JAR_P7_A" "P7 冻结 $P7_TAG" "喵：第一版")" || AGENT_P7_FREEZE=""
    if [[ -z $AGENT_P7_FREEZE ]]; then
        fail "A 没能建出并发布一个用来冻结的 agent"
    else
        THREAD_P7_FREEZE="$(new_thread "$JAR_P7_A")"
        register_snapshot_thread "$THREAD_P7_FREEZE" "$JAR_P7_A"
        WORKER_TOUCHED=1
        P7_STOPPED=""
        if ! compose stop -t 30 worker >/dev/null 2>&1 \
            || ! P7_STOPPED="$(worker_ids)" \
            || [[ -n $P7_STOPPED ]]; then
            fail "worker 没停干净，不提交本来应该免费的快照 run"
            if restore_workers; then
                WORKER_TOUCHED=""
            else
                fail "worker 停止失败后也没恢复到 $WORKER_COUNT 个副本，终止后续判据"
                end
                exit 1
            fi
        else
            # 提交前把标题填上，免得这条纯查库的判据偷偷起一次标题模型
            if ! api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P7_FREEZE" \
                -H 'Content-Type: application/json' \
                -d "$(jq -nc --arg t "P7 冻结 $P7_TAG" '{title:$t}')" >/dev/null 2>&1; then
                fail "提交前没能确认标题已保存，不冒险触发标题模型"
                end
                exit 1
            fi

            SNAPSHOT_POST_IN_FLIGHT=1
            P7_OLD_BODY=""
            if P7_OLD_BODY="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P7_A" \
                -X POST "$BASE_URL/api/threads/$THREAD_P7_FREEZE/runs" -H 'Content-Type: application/json' \
                -d "$(jq -nc --arg id "$AGENT_P7_FREEZE" '{content:"P7 冻结 v1",agent_config:{agent_id:$id}}')")"; then
                SNAPSHOT_POST_IN_FLIGHT=0
            else
                fail "第一条冻结 run 的提交结果不确定，worker 保持停止并终止后续判据"
                end
                exit 1
            fi
            RUN_P7_OLD="$(jq -r '.id // empty' <<<"$P7_OLD_BODY")"

            P7_OLD_BEFORE="$(psql_query "SELECT COALESCE(agent_config->>'agent_version','')
                || '|' || COALESCE(agent_config->>'system_prompt','')
                FROM runs WHERE id='$RUN_P7_OLD';" | tr -d '\r')"

            P7_FREEZE_V2="$(p7_release_next "$JAR_P7_A" "$AGENT_P7_FREEZE" "汪：第二版")"

            P7_OLD_AFTER="$(psql_query "SELECT COALESCE(agent_config->>'agent_version','')
                || '|' || COALESCE(agent_config->>'system_prompt','')
                FROM runs WHERE id='$RUN_P7_OLD';" | tr -d '\r')"

            SNAPSHOT_POST_IN_FLIGHT=1
            P7_NEW_BODY=""
            if P7_NEW_BODY="$(curl -fsS --connect-timeout 5 --max-time 20 -b "$JAR_P7_A" \
                -X POST "$BASE_URL/api/threads/$THREAD_P7_FREEZE/runs" -H 'Content-Type: application/json' \
                -d "$(jq -nc --arg id "$AGENT_P7_FREEZE" '{content:"P7 冻结 v2",agent_config:{agent_id:$id}}')")"; then
                SNAPSHOT_POST_IN_FLIGHT=0
            else
                fail "第二条冻结 run 的提交结果不确定，worker 保持停止并终止后续判据"
                end
                exit 1
            fi
            RUN_P7_NEW="$(jq -r '.id // empty' <<<"$P7_NEW_BODY")"
            P7_NEW_SNAPSHOT="$(psql_query "SELECT COALESCE(agent_config->>'agent_version','')
                || '|' || COALESCE(agent_config->>'system_prompt','')
                FROM runs WHERE id='$RUN_P7_NEW';" | tr -d '\r')"

            [[ -n $RUN_P7_OLD && $P7_OLD_BEFORE == "1|喵：第一版" ]] \
                && pass "第一条 run 在 queued 时已冻结 v1 与它的原文" \
                || fail "第一条 run 的快照不是 v1：run=${RUN_P7_OLD:-空} snapshot=$P7_OLD_BEFORE"
            [[ $P7_FREEZE_V2 == 2 ]] \
                && pass "作者发布了 v2" \
                || fail "第二版没发出来：版本号是 ${P7_FREEZE_V2:-空}"
            [[ $P7_OLD_AFTER == "1|喵：第一版" ]] \
                && pass "发了 v2 之后，历史 run 的快照仍是 v1 的原文" \
                || fail "发新版本污染了历史 run：$P7_OLD_AFTER"
            [[ -n $RUN_P7_NEW && $P7_NEW_SNAPSHOT == "2|汪：第二版" ]] \
                && pass "之后新提交的 run 冻结的是 v2" \
                || fail "新 run 没冻结 v2：run=${RUN_P7_NEW:-空} snapshot=$P7_NEW_SNAPSHOT"

            # 这是安全边界，不只是验收的一个 pass：取消失败就不得恢复 worker
            if cancel_snapshot_runs 1; then
                pass "两条 queued run 都已取消，现在才恢复 worker"
                if restore_workers; then
                    WORKER_TOUCHED=""
                else
                    fail "worker 没恢复到 $WORKER_COUNT 个副本，终止后续判据"
                    end
                    exit 1
                fi
            else
                fail "两条 queued run 没能全部取消，worker 保持停止"
                end
                exit 1
            fi
        fi
    fi
fi
end

# ---------------------------------------------------- P7⑤ reviewer 的边界
begin "P7⑤" "reviewer 的边界：审得了，建不了号"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），角色边界验不了"
else
    # **这里给 403 而不是 404**：管理端点存不存在本来就写在 /docs 上，
    # 「你的角色不够」不泄露任何东西
    P7_R_QUEUE="$(code "$JAR_P7_R" "$BASE_URL/api/reviews")"
    P7_R_CREATE="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/admin/users" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "p7-越权-$P7_TAG" '{name:$n,password:"口令-p7-test",role:"teacher"}')")"
    P7_R_PATCH="$(code "$JAR_P7_R" -X PATCH "$BASE_URL/api/admin/users/$UID_P7_B" \
        -H 'Content-Type: application/json' -d '{"is_active":false}')"
    P7_T_QUEUE="$(code "$JAR_P7_A" "$BASE_URL/api/reviews")"
    P7_ADMIN_QUEUE="$(code "$JAR_P7_ADMIN" "$BASE_URL/api/reviews")"

    [[ $P7_R_QUEUE == 200 ]] && pass "reviewer 打得开审核队列" || fail "reviewer 打审核队列得到 $P7_R_QUEUE"
    [[ $P7_R_CREATE == 403 ]] && pass "reviewer 建不了账号（403）" || fail "reviewer 建账号得到 $P7_R_CREATE，应该是 403"
    [[ $P7_R_PATCH == 403 ]] && pass "reviewer 改不了账号（403）" || fail "reviewer 改账号得到 $P7_R_PATCH，应该是 403"
    [[ $P7_T_QUEUE == 403 ]] && pass "普通教师打不开审核队列（403）" || fail "教师打审核队列得到 $P7_T_QUEUE，应该是 403"
    [[ $P7_ADMIN_QUEUE == 200 ]] && pass "admin 同时满足 reviewer" || fail "admin 打审核队列得到 $P7_ADMIN_QUEUE"

    # **MCP 的边界 2026-08-16 改过一次**：批与拒放给了 reviewer（与 agent、skill 同一档），
    # 而启停与探活仍归 admin —— 线从「按资源类型分」改成「按审核与运维分」。
    # 这里不需要一条真的 MCP 记录：准入是依赖注入，在查库之前就判完了，
    # 因此拿一个不存在的 id 也能验出 403 与 404 的分野
    P7_GHOST_MCP="00000000-0000-4000-8000-000000000000"
    P7_R_MCP_QUEUE="$(code "$JAR_P7_R" "$BASE_URL/api/mcp/admin")"
    P7_R_MCP_TOGGLE="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/mcp/admin/$P7_GHOST_MCP/enabled" \
        -H 'Content-Type: application/json' -d '{"enabled":false,"reason":"越权试探"}')"
    P7_T_MCP_QUEUE="$(code "$JAR_P7_A" "$BASE_URL/api/mcp/admin")"

    [[ $P7_R_MCP_QUEUE == 200 ]] && pass "reviewer 打得开 MCP 审核队列" || fail "reviewer 打 MCP 队列得到 $P7_R_MCP_QUEUE"
    [[ $P7_R_MCP_TOGGLE == 403 ]] && pass "reviewer 停不了 MCP（403，运维仍归 admin）" || fail "reviewer 停 MCP 得到 $P7_R_MCP_TOGGLE，应该是 403"
    [[ $P7_T_MCP_QUEUE == 403 ]] && pass "普通教师打不开 MCP 审核队列（403）" || fail "教师打 MCP 队列得到 $P7_T_MCP_QUEUE，应该是 403"

    # 建号那一下若真的成功了，库里就多了一个越权造出来的账号 —— 顺手核一下
    P7_LEAKED="$(psql_query "SELECT count(*) FROM users WHERE name = 'p7-越权-$P7_TAG';" | tr -d '[:space:]')"
    [[ $P7_LEAKED == 0 ]] && pass "库里没有越权造出来的账号" || fail "库里多出了 $P7_LEAKED 个越权造出来的账号"
fi
end

# ------------------------------------------------- P7⑥ 浏览器里走一遍可见性
begin "P7⑥" "浏览器里把可见性主链路走完（playwright）"

# **不进 `make all`。** 那是纯本地门禁，跑它不需要任何服务起着；而这条要六个服务、
# 真账号、真库。塞进去等于让每一次 git push 都依赖一整套 compose 栈。
# 缺浏览器二进制时记「未验」，与沙箱镜像缺失同一套规矩
if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），浏览器链路验不了"
elif ! command -v pnpm >/dev/null 2>&1; then
    undone "没有 pnpm，跑不了 playwright"
elif [[ ! -d $REPO_ROOT/web/node_modules/@playwright ]]; then
    undone "web/ 没装 @playwright/test：cd web && pnpm install"
elif ! (cd "$REPO_ROOT/web" && pnpm exec playwright install --dry-run chromium >/dev/null 2>&1); then
    undone "查不到 chromium 二进制：cd web && pnpm exec playwright install chromium"
else
    P7_E2E_LOG="$WORK_DIR/p7-e2e.log"
    if (cd "$REPO_ROOT/web" && \
        E2E_BASE_URL="$BASE_URL" \
        E2E_PASSWORD="$P7_SECRET" \
        E2E_AUTHOR="$NAME_P7_A" \
        E2E_TEAMMATE="$NAME_P7_B" \
        E2E_OUTSIDER="$NAME_P7_C" \
        E2E_REVIEWER="$NAME_P7_R" \
        E2E_GROUP="P7-G1-$P7_TAG" \
        E2E_TAG="$P7_TAG" \
        pnpm exec playwright test e2e/visibility.spec.ts >"$P7_E2E_LOG" 2>&1); then
        pass "三个账号在浏览器里走完了建、发布、共享、审核、上广场这条链路"
    else
        fail "playwright 未全过，详见 $P7_E2E_LOG"
        tail -30 "$P7_E2E_LOG" >&2 || true
    fi
fi
end

# ===========================================================================
# P8：Skill 校验、装配、热更新、对齐与审核
# ===========================================================================
#
# 账号与课题组复用 P7 的 A/B/C/reviewer/admin；P8 自己只新建 Skill。这样 P8⑤
# 验的是同一套可见性与审核基础设施换成 target_kind=skill 后是否仍成立，不把重复的
# 造号流程算成被测内容。

P8_FIXTURE="$REPO_ROOT/deploy/test/skill/annualized-naming/SKILL.md"
P8_READY=0
P8_SETUP_NOTE="未开始"
SKILL_P8_BASE=""

# 上传单个 Markdown 并发布 v1，标准输出是 skill_id。
p8_new_skill() {
    local jar="$1" file="$2" filename="$3" response skill_id
    response="$(api "$jar" -X POST "$BASE_URL/api/skills" \
        -F "file=@$file;filename=$filename" -F 'subject=金融学')" || return 1
    skill_id="$(jq -r '.id // empty' <<<"$response")"
    [[ -n $skill_id ]] || return 1
    api "$jar" -X POST "$BASE_URL/api/skills/$skill_id/versions" >/dev/null || return 1
    printf '%s\n' "$skill_id"
}

p8_submit_review() {
    local jar="$1" skill_id="$2" response
    response="$(api "$jar" -X POST "$BASE_URL/api/skills/$skill_id/reviews" \
        -H 'Content-Type: application/json' -d '{"responsibility_confirmed":true}')" || return 1
    jq -r 'first(.versions[] | select(.review_status == "pending") | .review_id) // empty' <<<"$response"
}

p8_available_has() {
    api "$1" "$BASE_URL/api/skills/available" |
        jq -e --arg id "$2" 'any(.[]; .id == $id)' >/dev/null
}

p8_catalog_has() {
    api "$1" "$BASE_URL/api/skills" |
        jq -e --arg id "$2" 'any(.[]; .id == $id)' >/dev/null
}

p8_skill_root_count() {
    in_broker python -c '
from config import get_settings
root = get_settings().skill_root
print(sum(1 for one in root.iterdir() if one.is_dir()) if root.exists() else 0)
'
}

if (( P7_READY )); then
    if [[ ! -f $P8_FIXTURE ]]; then
        P8_SETUP_NOTE="缺 Skill 夹具 $P8_FIXTURE"
    elif SKILL_P8_BASE="$(p8_new_skill "$JAR_P7_A" "$P8_FIXTURE" annualized-naming.md)" &&
        [[ -n $SKILL_P8_BASE ]]; then
        P8_READY=1
        P8_SETUP_NOTE="annualized-naming v1 已发布"
    else
        P8_SETUP_NOTE="annualized-naming 没上传并发布成功"
    fi
else
    P8_SETUP_NOTE="P7 账号前置没就绪（$P7_SETUP_NOTE）"
fi

# ------------------------------------------ P8① 挂与不挂，产物名不同
begin "P8①" "挂与不挂同一个 Skill，产物文件名可见地不同"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次真实分析"
elif (( ! P8_READY )); then
    fail "前置没就绪（$P8_SETUP_NOTE），两次真实分析验不了"
else
    THREAD_P8_PLAIN="$(new_thread "$JAR_P7_A")"
    THREAD_P8_SKILL="$(new_thread "$JAR_P7_A")"
    P8_PLAIN_SET=0
    P8_SKILL_SET=0
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P8_PLAIN" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P8 无 Skill $P7_TAG" '{title:$t}')" >/dev/null 2>&1 && P8_PLAIN_SET=1
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P8_SKILL" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P8 有 Skill $P7_TAG" --arg id "$SKILL_P8_BASE" \
            '{title:$t,agent_config:{skills:[$id]}}')" >/dev/null 2>&1 && P8_SKILL_SET=1

    P6_QUESTION='只做这一件事：用一个 Python 脚本读取固定收益率数组 [0.01,-0.005,0.008,-0.002,0.006]，按你采用的年化口径计算波动率并画一张柱状图，保存到 outputs/。如果系统列出了与年化有关的 skill，先读取并严格遵守；没有就直接按默认做法。不要查资料、不要写计划、不要请求确认、不要创建图以外的产物；最后只说明数值和文件名。'
    P8_PLAIN_OK=0
    P8_SKILL_OK=0
    if (( P8_PLAIN_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P8_PLAIN" p8-plain "$RUN_TIMEOUT"; then
        P8_PLAIN_OK=1
        RUN_P8_PLAIN="$P6_LAST_RUN"
        STATUS_P8_PLAIN="$P6_LAST_STATUS"
    else
        RUN_P8_PLAIN="${P6_LAST_RUN:-}"
        STATUS_P8_PLAIN="${P6_LAST_STATUS:-提交失败}"
    fi
    if (( P8_SKILL_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P8_SKILL" p8-skill "$RUN_TIMEOUT"; then
        P8_SKILL_OK=1
        RUN_P8_SKILL="$P6_LAST_RUN"
        STATUS_P8_SKILL="$P6_LAST_STATUS"
    else
        RUN_P8_SKILL="${P6_LAST_RUN:-}"
        STATUS_P8_SKILL="${P6_LAST_STATUS:-提交失败}"
    fi

    if (( ! P8_PLAIN_SET || ! P8_SKILL_SET )); then
        fail "两个会话没都在提交前设好标题与配置"
    elif (( ! P8_PLAIN_OK || ! P8_SKILL_OK )); then
        fail "两条 run 没都跑到 succeeded：不挂=$STATUS_P8_PLAIN，挂上=$STATUS_P8_SKILL"
    else
        TREE_P8_PLAIN="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P8_PLAIN/files")"
        TREE_P8_SKILL="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P8_SKILL/files")"
        P8_PLAIN_IMAGES="$(jq '[.entries[] | select(.is_dir == false) | select(.path | test("^outputs/.*\\.(png|jpg|jpeg|svg)$"; "i"))] | length' <<<"$TREE_P8_PLAIN")"
        P8_PLAIN_PREFIX="$(jq '[.entries[] | select(.is_dir == false) | select(.path | test("^outputs/.*\\.(png|jpg|jpeg|svg)$"; "i")) | select((.path | split("/") | last) | startswith("ANNUALIZED-252-"))] | length' <<<"$TREE_P8_PLAIN")"
        P8_SKILL_IMAGES="$(jq '[.entries[] | select(.is_dir == false) | select(.path | test("^outputs/.*\\.(png|jpg|jpeg|svg)$"; "i"))] | length' <<<"$TREE_P8_SKILL")"
        P8_SKILL_PREFIX="$(jq '[.entries[] | select(.is_dir == false) | select(.path | test("^outputs/.*\\.(png|jpg|jpeg|svg)$"; "i")) | select((.path | split("/") | last) | startswith("ANNUALIZED-252-"))] | length' <<<"$TREE_P8_SKILL")"

        if (( P8_PLAIN_IMAGES > 0 && P8_PLAIN_PREFIX == 0 && P8_SKILL_IMAGES > 0 && P8_SKILL_PREFIX == P8_SKILL_IMAGES )); then
            pass "双向断言成立：不挂 Skill 的图无前缀，挂上后全部带 ANNUALIZED-252- 前缀"
        else
            fail "产物名不符合双向断言：不挂图=$P8_PLAIN_IMAGES/带前缀=$P8_PLAIN_PREFIX，挂上图=$P8_SKILL_IMAGES/带前缀=$P8_SKILL_PREFIX"
        fi

        if jq -e 'all(.entries[]; (.path != "skill" and (.path | startswith("skill/") | not)))' \
            <<<"$TREE_P8_PLAIN" >/dev/null &&
            jq -e 'any(.entries[]; .path == "skill/annualized-naming/SKILL.md" and .is_dir == false)' \
                <<<"$TREE_P8_SKILL" >/dev/null; then
            pass "物化边界成立：A 没有 skill/，B 有 annualized-naming/SKILL.md"
        else
            fail "两个会话的 Skill 文件树不符合预期"
        fi

        P8_SKILL_SNAPSHOT="$(psql_query "SELECT COALESCE(agent_config->'skills', '[]'::jsonb)::text
            FROM runs WHERE id='$RUN_P8_SKILL';" | tr -d '\r')"
        if jq -e --arg id "$SKILL_P8_BASE" \
            'length == 1 and .[0].skill_id == $id and .[0].version == 1 and .[0].name == "annualized-naming"' \
            <<<"$P8_SKILL_SNAPSHOT" >/dev/null; then
            pass "挂 Skill 的 run 快照冻结了 skill_id、version 与 name"
        else
            fail "Skill 快照不完整：$P8_SKILL_SNAPSHOT"
        fi

        TOKENS_P8_PLAIN="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
            FROM runs WHERE id='$RUN_P8_PLAIN';" | tr -d '[:space:]')"
        TOKENS_P8_SKILL="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
            FROM runs WHERE id='$RUN_P8_SKILL';" | tr -d '[:space:]')"
        info "第 15 个 token 样本（P8① 不挂 Skill，cache|uncached|output）：$TOKENS_P8_PLAIN；run=$RUN_P8_PLAIN"
        info "第 16 个 token 样本（P8① 挂 Skill，cache|uncached|output）：$TOKENS_P8_SKILL；run=$RUN_P8_SKILL"
    fi
fi
end

# ------------------------------------------ P8② 八个真实恶意 ZIP
begin "P8②" "八条上传校验逐包拒绝，理由可区分且磁盘无残留"

if (( ! P8_READY )); then
    fail "前置没就绪（$P8_SETUP_NOTE），恶意包验不了"
else
    P8_BAD_DIR="$WORK_DIR/p8-hostile"
    mkdir -p "$P8_BAD_DIR"
    if ! python3 - "$P8_BAD_DIR" <<'PY'
import stat
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
name = "annualized-naming"
skill = b"---\nname: annualized-naming\ndescription: p8 validation\n---\nrule\n"

with ZipFile(root / "path.zip", "w", ZIP_STORED) as archive:
    archive.writestr("../../etc/passwd.txt", b"x")

with ZipFile(root / "symlink.zip", "w", ZIP_STORED) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    link = ZipInfo(f"{name}/link.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive.writestr(link, "/etc/passwd")

max_total = 5 * 1024 * 1024
with ZipFile(root / "total.zip", "w", ZIP_STORED) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    remaining = max_total + 1 - len(skill)
    index = 0
    while remaining:
        size = min(1024 * 1024, remaining)
        archive.writestr(f"{name}/part-{index}.txt", b"x" * size)
        remaining -= size
        index += 1

with ZipFile(root / "count.zip", "w", ZIP_STORED) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    for index in range(100):
        archive.writestr(f"{name}/file-{index}.txt", b"x")

with ZipFile(root / "ratio.zip", "w", ZIP_DEFLATED, compresslevel=9) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    with archive.open(f"{name}/bomb.txt", "w", force_zip64=True) as member:
        chunk = b"0" * (1024 * 1024)
        for _ in range(500):
            member.write(chunk)

with ZipFile(root / "extension.zip", "w", ZIP_STORED) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    archive.writestr(f"{name}/scripts/run.sh", b"echo nope\n")

with ZipFile(root / "single.zip", "w", ZIP_STORED) as archive:
    archive.writestr(f"{name}/SKILL.md", skill)
    archive.writestr(f"{name}/large.txt", b"x" * (1024 * 1024 + 1))

with ZipFile(root / "name.zip", "w", ZIP_STORED) as archive:
    archive.writestr(
        f"{name}/SKILL.md",
        b"---\nname: another-name\ndescription: mismatch\n---\nrule\n",
    )
PY
    then
        fail "八个恶意 ZIP 没造出来"
    else
        P8_ROOT_BEFORE="$(p8_skill_root_count | tr -d '[:space:]')"
        P8_BAD_CASES=(
            "path.zip|路径不合法"
            "symlink.zip|符号链接"
            "total.zip|解压后总大小"
            "count.zip|文件数量"
            "ratio.zip|压缩比"
            "extension.zip|扩展名不允许"
            "single.zip|单文件超过上限"
            "name.zip|name"
        )
        for P8_BAD_CASE in "${P8_BAD_CASES[@]}"; do
            IFS='|' read -r P8_BAD_FILE P8_BAD_REASON <<<"$P8_BAD_CASE"
            P8_BAD_RESPONSE="$WORK_DIR/p8-${P8_BAD_FILE%.zip}.json"
            P8_BAD_STARTED="$(date +%s%N)"
            P8_BAD_CODE="$(curl -sS -o "$P8_BAD_RESPONSE" -w '%{http_code}' -b "$JAR_P7_A" \
                -X POST "$BASE_URL/api/skills" -F "file=@$P8_BAD_DIR/$P8_BAD_FILE;filename=$P8_BAD_FILE" \
                -F 'subject=金融学')"
            P8_BAD_ELAPSED=$(( ($(date +%s%N) - P8_BAD_STARTED) / 1000000 ))
            P8_BAD_MESSAGE="$(jq -r '.error.message // empty' "$P8_BAD_RESPONSE" 2>/dev/null)"
            P8_ROOT_AFTER="$(p8_skill_root_count | tr -d '[:space:]')"

            [[ $P8_BAD_CODE == 422 ]] \
                && pass "$P8_BAD_FILE 被 422 拒绝" \
                || fail "$P8_BAD_FILE 返回 $P8_BAD_CODE，不是 422：$P8_BAD_MESSAGE"
            [[ $P8_BAD_MESSAGE == *"$P8_BAD_REASON"* ]] \
                && pass "$P8_BAD_FILE 的理由明确指向「$P8_BAD_REASON」" \
                || fail "$P8_BAD_FILE 的理由分不清：$P8_BAD_MESSAGE"
            [[ $P8_ROOT_AFTER == "$P8_ROOT_BEFORE" ]] \
                && pass "$P8_BAD_FILE 被拒后 SKILL_ROOT 目录数仍是 $P8_ROOT_BEFORE" \
                || fail "$P8_BAD_FILE 在磁盘留下了目录：$P8_ROOT_BEFORE → $P8_ROOT_AFTER"
            if [[ $P8_BAD_FILE == ratio.zip ]]; then
                (( P8_BAD_ELAPSED < 2000 )) \
                    && pass "500 MB 高压缩比包在 ${P8_BAD_ELAPSED}ms 内、解压前被拒" \
                    || fail "500 MB 高压缩比包用了 ${P8_BAD_ELAPSED}ms，未证明在解压前拒绝"
            fi
        done
    fi
fi
end

# ------------------------------------------ P8③ 同会话中途挂 Skill
begin "P8③" "同一个会话中途挂上 Skill，下一次 run 立即生效"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次便宜的真实分析"
elif (( ! P8_READY )); then
    fail "前置没就绪（$P8_SETUP_NOTE），热更新验不了"
else
    THREAD_P8_RELOAD="$(new_thread "$JAR_P7_A")"
    P8_RELOAD_SET=0
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P8_RELOAD" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P8 热更新 $P7_TAG" '{title:$t}')" >/dev/null 2>&1 && P8_RELOAD_SET=1
    P6_QUESTION='你现在有哪些 skill 可用？请只列出名称；如果没有就回答“没有”。不要调用工具。'

    P8_RELOAD_FIRST_OK=0
    if (( P8_RELOAD_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P8_RELOAD" p8-reload-before; then
        P8_RELOAD_FIRST_OK=1
        RUN_P8_RELOAD_FIRST="$P6_LAST_RUN"
        ANSWER_P8_RELOAD_FIRST="$P6_LAST_ANSWER"
    else
        RUN_P8_RELOAD_FIRST="${P6_LAST_RUN:-}"
        ANSWER_P8_RELOAD_FIRST="${P6_LAST_ANSWER:-}"
    fi
    CHECKPOINT_P8_FIRST="$(psql_query "SELECT count(*) FROM checkpoints WHERE thread_id='$THREAD_P8_RELOAD';" | tr -d '[:space:]')"
    TREE_P8_RELOAD_FIRST="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P8_RELOAD/files")"

    P8_RELOAD_PATCHED=0
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P8_RELOAD" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg id "$SKILL_P8_BASE" '{agent_config:{skills:[$id]}}')" >/dev/null 2>&1 && P8_RELOAD_PATCHED=1

    P8_RELOAD_SECOND_OK=0
    if (( P8_RELOAD_PATCHED )) && p6_analyse "$JAR_P7_A" "$THREAD_P8_RELOAD" p8-reload-after; then
        P8_RELOAD_SECOND_OK=1
        RUN_P8_RELOAD_SECOND="$P6_LAST_RUN"
        ANSWER_P8_RELOAD_SECOND="$P6_LAST_ANSWER"
    else
        RUN_P8_RELOAD_SECOND="${P6_LAST_RUN:-}"
        ANSWER_P8_RELOAD_SECOND="${P6_LAST_ANSWER:-}"
    fi
    CHECKPOINT_P8_SECOND="$(psql_query "SELECT count(*) FROM checkpoints WHERE thread_id='$THREAD_P8_RELOAD';" | tr -d '[:space:]')"
    TREE_P8_RELOAD_SECOND="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P8_RELOAD/files")"

    if (( ! P8_RELOAD_SET || ! P8_RELOAD_PATCHED || ! P8_RELOAD_FIRST_OK || ! P8_RELOAD_SECOND_OK )); then
        fail "同会话两轮没都成功：初始配置=$P8_RELOAD_SET，PATCH=$P8_RELOAD_PATCHED，第一轮=$P8_RELOAD_FIRST_OK，第二轮=$P8_RELOAD_SECOND_OK"
    elif [[ $ANSWER_P8_RELOAD_FIRST == *annualized-naming* ]]; then
        fail "挂载前就答出了 annualized-naming，Skill 串进了默认会话：$ANSWER_P8_RELOAD_FIRST"
    elif [[ $ANSWER_P8_RELOAD_SECOND != *annualized-naming* ]]; then
        fail "挂载后仍没答出 annualized-naming，热更新没生效：$ANSWER_P8_RELOAD_SECOND"
    else
        pass "同一会话双向断言成立：第一轮无 annualized-naming，PATCH 后第二轮立即出现"
    fi

    if jq -e 'all(.entries[]; (.path != "skill" and (.path | startswith("skill/") | not)))' \
        <<<"$TREE_P8_RELOAD_FIRST" >/dev/null &&
        jq -e 'any(.entries[]; .path == "skill/annualized-naming/SKILL.md" and .is_dir == false)' \
            <<<"$TREE_P8_RELOAD_SECOND" >/dev/null; then
        pass "同一 workspace 第一轮无 skill/，第二轮已物化 SKILL.md"
    else
        fail "同一 workspace 的 Skill 文件树没有随配置变化"
    fi

    SNAPSHOT_P8_RELOAD_FIRST="$(psql_query "SELECT COALESCE(agent_config->'skills', '[]'::jsonb)::text FROM runs WHERE id='$RUN_P8_RELOAD_FIRST';" | tr -d '\r')"
    SNAPSHOT_P8_RELOAD_SECOND="$(psql_query "SELECT COALESCE(agent_config->'skills', '[]'::jsonb)::text FROM runs WHERE id='$RUN_P8_RELOAD_SECOND';" | tr -d '\r')"
    if jq -e 'length == 0' <<<"$SNAPSHOT_P8_RELOAD_FIRST" >/dev/null &&
        jq -e --arg id "$SKILL_P8_BASE" \
            'length == 1 and .[0].skill_id == $id and .[0].version == 1 and .[0].name == "annualized-naming"' \
            <<<"$SNAPSHOT_P8_RELOAD_SECOND" >/dev/null &&
        (( CHECKPOINT_P8_FIRST > 0 && CHECKPOINT_P8_SECOND > CHECKPOINT_P8_FIRST )); then
        pass "两次 run 快照由空变为 v1 引用，checkpoint 数 $CHECKPOINT_P8_FIRST → $CHECKPOINT_P8_SECOND"
    else
        fail "快照或 checkpoint 没随第二轮变化：first=$SNAPSHOT_P8_RELOAD_FIRST second=$SNAPSHOT_P8_RELOAD_SECOND checkpoints=$CHECKPOINT_P8_FIRST→$CHECKPOINT_P8_SECOND"
    fi
fi
end

# ------------------------------------------ P8④ 全量覆盖对齐
begin "P8④" "Skill 对齐覆盖改坏内容，并删除清单外文件"

if (( ! P8_READY )); then
    fail "前置没就绪（$P8_SETUP_NOTE），全量对齐验不了"
else
    THREAD_P8_ALIGN="$(new_thread "$JAR_P7_A")"
    PAYLOAD_P8_ALIGN="$(jq -nc --arg id "$SKILL_P8_BASE" \
        '{skills:[{skill_id:$id,version:1,name:"annualized-naming"}]}')"
    P8_ALIGN_INITIAL=0
    broker_call POST "/threads/$THREAD_P8_ALIGN/skill/align" "$PAYLOAD_P8_ALIGN" >/dev/null 2>&1 && P8_ALIGN_INITIAL=1
    HASH_P8_EXPECTED="$(sha256sum "$P8_FIXTURE" | cut -d' ' -f1)"
    HASH_P8_INITIAL="$(in_broker python -c "
from hashlib import sha256
from config import get_settings
path = get_settings().sandbox_workspace_root / '$THREAD_P8_ALIGN' / 'skill' / 'annualized-naming' / 'SKILL.md'
print(sha256(path.read_bytes()).hexdigest() if path.is_file() else '')
" | tr -d '[:space:]')"

    P8_ALIGN_MUTATED=0
    in_broker python -c "
from config import get_settings
root = get_settings().sandbox_workspace_root / '$THREAD_P8_ALIGN' / 'skill'
target = root / 'annualized-naming' / 'SKILL.md'
target.write_text('BROKEN BY P8\n', encoding='utf-8')
extra = root / 'not-in-manifest'
extra.mkdir(parents=True, exist_ok=True)
(extra / 'README.md').write_text('orphan\n', encoding='utf-8')
" >/dev/null 2>&1 && P8_ALIGN_MUTATED=1

    P8_ALIGN_RESTORED=0
    broker_call POST "/threads/$THREAD_P8_ALIGN/skill/align" "$PAYLOAD_P8_ALIGN" >/dev/null 2>&1 && P8_ALIGN_RESTORED=1
    PROBE_P8_ALIGN="$(in_broker python -c "
from hashlib import sha256
from config import get_settings
root = get_settings().sandbox_workspace_root / '$THREAD_P8_ALIGN' / 'skill'
target = root / 'annualized-naming' / 'SKILL.md'
print((sha256(target.read_bytes()).hexdigest() if target.is_file() else '') + '|' + str((root / 'not-in-manifest').exists()).lower())
" | tr -d '[:space:]')"

    if (( P8_ALIGN_INITIAL )) && [[ $HASH_P8_INITIAL == "$HASH_P8_EXPECTED" ]]; then
        pass "首次对齐逐字节物化了 annualized-naming/SKILL.md"
    else
        fail "首次对齐内容不对：initial=$P8_ALIGN_INITIAL hash=$HASH_P8_INITIAL expected=$HASH_P8_EXPECTED"
    fi
    if (( P8_ALIGN_MUTATED && P8_ALIGN_RESTORED )) && [[ $PROBE_P8_ALIGN == "$HASH_P8_EXPECTED|false" ]]; then
        pass "再次对齐覆盖了改坏内容，并删除 not-in-manifest/"
    else
        fail "全量覆盖失败：mutated=$P8_ALIGN_MUTATED restored=$P8_ALIGN_RESTORED probe=$PROBE_P8_ALIGN"
    fi
fi
end

# ------------------------------------------ P8⑤ 共享与审核
begin "P8⑤" "Skill 复用共享与审核；别组拿着 id 也挂不上"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），Skill 共享审核验不了"
else
    NAME_P8_SHARE="p8-sharing-$P7_TAG"
    FILE_P8_SHARE="$WORK_DIR/$NAME_P8_SHARE.md"
    cat > "$FILE_P8_SHARE" <<EOF_SKILL
---
name: $NAME_P8_SHARE
description: P8 共享与审核验收用 Skill。
---
共享验收规则。
EOF_SKILL
    SKILL_P8_SHARE="$(p8_new_skill "$JAR_P7_A" "$FILE_P8_SHARE" "$NAME_P8_SHARE.md")" || SKILL_P8_SHARE=""

    if [[ -z $SKILL_P8_SHARE ]]; then
        fail "A 没能上传并发布共享验收 Skill"
    else
        P8_SHARE_SET=0
        api "$JAR_P7_A" -X PUT "$BASE_URL/api/skills/$SKILL_P8_SHARE/sharing" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg g "$GROUP_P7_1" '{visibility:"group",group_ids:[$g]}')" \
            >/dev/null 2>&1 && P8_SHARE_SET=1

        (( P8_SHARE_SET )) && p8_available_has "$JAR_P7_B" "$SKILL_P8_SHARE" \
            && pass "A 共享给 G1 后，同组 B 的可用列表有它" \
            || fail "共享后 B 的可用列表没有 Skill"
        if ! p8_available_has "$JAR_P7_C" "$SKILL_P8_SHARE" && ! p8_catalog_has "$JAR_P7_C" "$SKILL_P8_SHARE"; then
            pass "别组 C 的可用列表与平台目录都没有未过审 Skill"
        else
            fail "别组 C 提前看到了组内或未过审 Skill"
        fi

        THREAD_P8_C="$(new_thread "$JAR_P7_C")"
        RUN_COUNT_P8_C_BEFORE="$(psql_query "SELECT count(*) FROM runs WHERE user_id='$UID_P7_C';" | tr -d '[:space:]')"
        RESPONSE_P8_C="$WORK_DIR/p8-c-invisible.json"
        CODE_P8_C="$(curl -sS -o "$RESPONSE_P8_C" -w '%{http_code}' -b "$JAR_P7_C" \
            -X POST "$BASE_URL/api/threads/$THREAD_P8_C/runs" -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg id "$SKILL_P8_SHARE" '{content:"越权引用 Skill",agent_config:{skills:[$id]}}')")"
        RUN_COUNT_P8_C_AFTER="$(psql_query "SELECT count(*) FROM runs WHERE user_id='$UID_P7_C';" | tr -d '[:space:]')"
        if [[ $CODE_P8_C == 422 && $RUN_COUNT_P8_C_AFTER == "$RUN_COUNT_P8_C_BEFORE" ]]; then
            pass "C 拿着 skill_id 提交仍是 422，runs 行数保持 $RUN_COUNT_P8_C_BEFORE"
        else
            fail "C 的越权引用没有 fail-closed：code=$CODE_P8_C runs=$RUN_COUNT_P8_C_BEFORE→$RUN_COUNT_P8_C_AFTER body=$(cat "$RESPONSE_P8_C")"
        fi

        REVIEW_P8_ONE="$(p8_submit_review "$JAR_P7_A" "$SKILL_P8_SHARE")"
        P8_NO_REASON="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P8_ONE" \
            -H 'Content-Type: application/json' -d '{"approved":false}')"
        P8_REJECT_REASON="请补充来源与适用边界"
        P8_REJECT="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P8_ONE" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc --arg r "$P8_REJECT_REASON" '{approved:false,reason:$r}')")"
        P8_AUTHOR_REASON="$(api "$JAR_P7_A" "$BASE_URL/api/skills/mine/$SKILL_P8_SHARE" |
            jq -r 'first(.versions[] | select(.review_status == "rejected") | .review_reason) // empty')"
        if [[ $P8_NO_REASON == 422 && $P8_REJECT == 202 && $P8_AUTHOR_REASON == "$P8_REJECT_REASON" ]]; then
            pass "reviewer 无理由拒绝被 422 挡住；写理由后作者逐字可见"
        else
            fail "拒绝理由闸门不完整：无理由=$P8_NO_REASON 有理由=$P8_REJECT 作者看到=$P8_AUTHOR_REASON"
        fi

        if ! p8_catalog_has "$JAR_P7_C" "$SKILL_P8_SHARE" && p8_available_has "$JAR_P7_B" "$SKILL_P8_SHARE"; then
            pass "被拒后 C 的平台目录仍没有，组内 B 仍可用"
        else
            fail "拒绝错误地撤回了组内可见性，或泄露进平台目录"
        fi

        REVIEW_P8_TWO="$(p8_submit_review "$JAR_P7_A" "$SKILL_P8_SHARE")"
        P8_APPROVE="$(code "$JAR_P7_R" -X POST "$BASE_URL/api/reviews/$REVIEW_P8_TWO" \
            -H 'Content-Type: application/json' -d '{"approved":true}')"
        if [[ $P8_APPROVE == 202 ]] && p8_catalog_has "$JAR_P7_C" "$SKILL_P8_SHARE"; then
            pass "同一版本重新提审并通过后，C 的平台目录出现该 Skill"
        else
            fail "通过后平台目录仍不可见：review=$P8_APPROVE"
        fi

        KINDS_P8="$(psql_query "SELECT count(DISTINCT r.target_kind)
            FROM reviews r
            WHERE (r.target_kind='agent' AND EXISTS (
                SELECT 1 FROM agent_versions v JOIN agents a ON a.id=v.agent_id
                WHERE v.id=r.target_id AND a.owner_id='$UID_P7_A'))
               OR (r.target_kind='skill' AND EXISTS (
                SELECT 1 FROM skill_versions v JOIN skills s ON s.id=v.skill_id
                WHERE v.id=r.target_id AND s.owner_id='$UID_P7_A'));" | tr -d '[:space:]')"
        [[ $KINDS_P8 == 2 ]] \
            && pass "同一作者的 reviews 行同时覆盖 agent 与 skill 两种 target_kind" \
            || fail "reviews 没同时存住两种 target_kind：count=${KINDS_P8:-空}"
    fi
fi
end

# ------------------------------------------ P8⑥ 浏览器上传与校验链路
begin "P8⑥" "浏览器里走完 Skill 上传校验、发布、提审与通过"

# 账号复用 P7 前置：这条只需要一名作者与一名 reviewer，不另造两份相同身份。
if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），Skill 浏览器链路验不了"
elif ! command -v pnpm >/dev/null 2>&1; then
    undone "没有 pnpm，跑不了 playwright"
elif [[ ! -d $REPO_ROOT/web/node_modules/@playwright ]]; then
    undone "web/ 没装 @playwright/test：cd web && pnpm install"
elif ! (cd "$REPO_ROOT/web" && pnpm exec playwright install --dry-run chromium >/dev/null 2>&1); then
    undone "查不到 chromium 二进制：cd web && pnpm exec playwright install chromium"
else
    P8_E2E_LOG="$WORK_DIR/p8-e2e.log"
    if (cd "$REPO_ROOT/web" && \
        E2E_BASE_URL="$BASE_URL" \
        E2E_PASSWORD="$P7_SECRET" \
        E2E_AUTHOR="$NAME_P7_A" \
        E2E_REVIEWER="$NAME_P7_R" \
        E2E_TAG="$P7_TAG" \
        pnpm exec playwright test e2e/skill-upload.spec.ts >"$P8_E2E_LOG" 2>&1); then
        pass "越界包被拒且不新增，合法包从 frontmatter 建成、发布、提审并审核通过"
    else
        fail "Skill playwright 未全过，详见 $P8_E2E_LOG"
        tail -30 "$P8_E2E_LOG" >&2 || true
    fi
fi
end


# ===========================================================================
# P9：子智能体主判据与 token 汇总
# ===========================================================================

P9_FIXTURE="$REPO_ROOT/deploy/test/subagent/volatility-expert.json"
P9_DELETE_FIXTURE="$REPO_ROOT/deploy/test/subagent/delete-expert.json"
P9_READY=0
P9_HITL_READY=0
P9_SETUP_NOTE="未开始"
P9_HITL_SETUP_NOTE="未开始"
P9_RUNS_READY=0
AGENT_P9_VOLATILITY=""
AGENT_P9_DELETE=""

p9_new_fixture_agent() {
    local jar="$1" fixture="$2" name description prompt response agent_id
    name="$(jq -r '.name // empty' "$fixture")"
    description="$(jq -r '.description // empty' "$fixture")"
    prompt="$(jq -r '.prompt // empty' "$fixture")"
    [[ -n $name && -n $description && -n $prompt ]] || return 1
    response="$(api "$jar" -X POST "$BASE_URL/api/agents" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$name" --arg d "$description" --arg p "$prompt" \
            '{name:$n,description:$d,subject:"金融学",system_prompt:$p}')")" || return 1
    agent_id="$(jq -r '.id // empty' <<<"$response")"
    [[ -n $agent_id ]] || return 1
    api "$jar" -X POST "$BASE_URL/api/agents/$agent_id/versions" >/dev/null || return 1
    printf '%s\n' "$agent_id"
}

if (( P7_READY )); then
    if [[ ! -f $P9_FIXTURE ]]; then
        P9_SETUP_NOTE="缺子智能体夹具 $P9_FIXTURE"
    elif ! jq -e '
        .name == "volatility-expert"
        and (.description | type == "string" and length > 0)
        and (.prompt | type == "string" and length > 0)
    ' "$P9_FIXTURE" >/dev/null; then
        P9_SETUP_NOTE="volatility-expert 夹具形状不合法"
    elif AGENT_P9_VOLATILITY="$(p9_new_fixture_agent "$JAR_P7_A" "$P9_FIXTURE")" &&
        [[ -n $AGENT_P9_VOLATILITY ]]; then
        P9_READY=1
        P9_SETUP_NOTE="volatility-expert v1 已发布"
    else
        P9_SETUP_NOTE="volatility-expert 没创建并发布成功"
    fi
else
    P9_SETUP_NOTE="P7 账号前置没就绪（$P7_SETUP_NOTE）"
fi

if (( P7_READY )); then
    if [[ ! -f $P9_DELETE_FIXTURE ]]; then
        P9_HITL_SETUP_NOTE="缺子智能体夹具 $P9_DELETE_FIXTURE"
    elif ! jq -e '
        .name == "delete-expert"
        and (.description | type == "string" and length > 0)
        and (.prompt | type == "string" and length > 0)
    ' "$P9_DELETE_FIXTURE" >/dev/null; then
        P9_HITL_SETUP_NOTE="delete-expert 夹具形状不合法"
    elif AGENT_P9_DELETE="$(p9_new_fixture_agent "$JAR_P7_A" "$P9_DELETE_FIXTURE")" &&
        [[ -n $AGENT_P9_DELETE ]]; then
        P9_HITL_READY=1
        P9_HITL_SETUP_NOTE="delete-expert v1 已发布"
    else
        P9_HITL_SETUP_NOTE="delete-expert 没创建并发布成功"
    fi
else
    P9_HITL_SETUP_NOTE="P7 账号前置没就绪（$P7_SETUP_NOTE）"
fi

# ------------------------------------------ P9① 主判据：真进子图并写文件
begin "P9①" "挂与不挂子智能体，事件 path、文件与快照可见地不同"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次真实分析"
elif (( ! P9_READY )); then
    fail "前置没就绪（$P9_SETUP_NOTE），子智能体主判据验不了"
else
    THREAD_P9_PLAIN="$(new_thread "$JAR_P7_A")"
    THREAD_P9_CHILD="$(new_thread "$JAR_P7_A")"
    P9_PLAIN_SET=0
    P9_CHILD_SET=0
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P9_PLAIN" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P9 无子智能体 $P7_TAG" '{title:$t}')" >/dev/null 2>&1 && P9_PLAIN_SET=1
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P9_CHILD" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P9 有子智能体 $P7_TAG" --arg id "$AGENT_P9_VOLATILITY" \
            '{title:$t,agent_config:{subagents:[$id]}}')" >/dev/null 2>&1 && P9_CHILD_SET=1

    P6_QUESTION='只做这一件事：固定收益率数组 [0.01,-0.005,0.008,-0.002,0.006] 的样本标准差是 0.00654217089351845，乘以 sqrt(252) 后年化波动率是 0.10385374331241026。不要复核或执行代码，只调用一次 write_file，把这段计算写进 outputs/volatility-result.txt。如果存在名为 volatility-expert 的可委派子智能体，必须把整项工作委派给它，自己不得代做；不存在时才自行写文件。不调用其他工具，不创建临时文件，不删除、移动或覆盖任何已有文件；完成后只回答输出文件名。'
    P9_PLAIN_OK=0
    P9_CHILD_OK=0
    if (( P9_PLAIN_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P9_PLAIN" p9-plain "$RUN_TIMEOUT"; then
        P9_PLAIN_OK=1
        RUN_P9_PLAIN="$P6_LAST_RUN"
        STATUS_P9_PLAIN="$P6_LAST_STATUS"
    else
        RUN_P9_PLAIN="${P6_LAST_RUN:-}"
        STATUS_P9_PLAIN="${P6_LAST_STATUS:-提交失败}"
    fi
    if (( P9_CHILD_SET )) && p6_analyse "$JAR_P7_A" "$THREAD_P9_CHILD" p9-child "$RUN_TIMEOUT"; then
        P9_CHILD_OK=1
        RUN_P9_CHILD="$P6_LAST_RUN"
        STATUS_P9_CHILD="$P6_LAST_STATUS"
    else
        RUN_P9_CHILD="${P6_LAST_RUN:-}"
        STATUS_P9_CHILD="${P6_LAST_STATUS:-提交失败}"
    fi

    if (( ! P9_PLAIN_SET || ! P9_CHILD_SET )); then
        fail "两个独立会话没都在提交前设好配置"
    elif (( ! P9_PLAIN_OK || ! P9_CHILD_OK )); then
        fail "两条 run 没都跑到 succeeded：不挂=$STATUS_P9_PLAIN，挂上=$STATUS_P9_CHILD"
    else
        P9_RUNS_READY=1
        P9_PLAIN_NESTED="$(jq -s '[.[] | select(.path | length > 0)] | length' "$WORK_DIR/p9-plain.json")"
        P9_CHILD_NAMED="$(jq -s '[.[] | select(.path == ["volatility-expert"])] | length' "$WORK_DIR/p9-child.json")"
        if (( P9_PLAIN_NESTED == 0 && P9_CHILD_NAMED > 0 )); then
            pass "双向 path 断言成立：A 全为空，B 有 $P9_CHILD_NAMED 条 volatility-expert 事件"
        else
            fail "path 没形成对照：A 非空=$P9_PLAIN_NESTED，B 命名事件=$P9_CHILD_NAMED"
        fi

        TREE_P9_CHILD="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P9_CHILD/files")"
        P9_OUTPUTS="$(jq '[.entries[] | select(.is_dir == false and (.path | startswith("outputs/")))] | length' \
            <<<"$TREE_P9_CHILD")"
        P9_NESTED_FILE_CALLS="$(jq -s '[.[]
            | select(.type == "tool_call" and .path == ["volatility-expert"])
            | select(.data.name | test("^(write_file|edit_file|execute)$"))] | length' \
            "$WORK_DIR/p9-child.json")"
        if (( P9_OUTPUTS > 0 && P9_NESTED_FILE_CALLS > 0 )); then
            pass "子智能体通过文件工具工作并在 outputs/ 留下了 $P9_OUTPUTS 个文件"
        else
            fail "未证明子智能体真的干活：outputs 文件=$P9_OUTPUTS，嵌套文件工具=$P9_NESTED_FILE_CALLS"
        fi

        SNAPSHOT_P9_CHILD="$(psql_query "SELECT COALESCE(agent_config->'subagents', '[]'::jsonb)::text
            FROM runs WHERE id='$RUN_P9_CHILD';" | tr -d '\r')"
        if jq -e --arg id "$AGENT_P9_VOLATILITY" '
            length == 1
            and .[0].agent_id == $id
            and .[0].version == 1
            and .[0].name == "volatility-expert"
        ' <<<"$SNAPSHOT_P9_CHILD" >/dev/null; then
            pass "run 快照冻结了 agent_id、version 与 name"
        else
            fail "子智能体快照不完整：$SNAPSHOT_P9_CHILD"
        fi

        TASK_CALLS_P9="$(jq -s '[.[]
            | select(.type == "tool_call" and (.path | length == 0))
            | select(.data.name == "task" and .data.args.subagent_type == "volatility-expert")
        ] | length' "$WORK_DIR/p9-child.json")"
        info "【观察项】P9① task 调用了 $TASK_CALLS_P9 次；run=$RUN_P9_CHILD"
        (( TASK_CALLS_P9 > 0 )) \
            && pass "主智能体确实调用了 task(volatility-expert)" \
            || fail "事件流里没有主智能体的 task(volatility-expert) 调用"
    fi
fi
end

# ------------------------------------------ P9② 子图 token 汇总
begin "P9②" "子智能体消耗计进同一条 run 的 token"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1；这条复用 P9① 的两次真实分析"
elif (( ! P9_RUNS_READY )); then
    fail "P9① 两条 run 没都成功，无法比较 token"
else
    TOKENS_P9_PLAIN="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
        FROM runs WHERE id='$RUN_P9_PLAIN';" | tr -d '[:space:]')"
    TOKENS_P9_CHILD="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
        FROM runs WHERE id='$RUN_P9_CHILD';" | tr -d '[:space:]')"
    IFS='|' read -r P9_PLAIN_CACHE P9_PLAIN_UNCACHED P9_PLAIN_OUTPUT <<<"$TOKENS_P9_PLAIN"
    IFS='|' read -r P9_CHILD_CACHE P9_CHILD_UNCACHED P9_CHILD_OUTPUT <<<"$TOKENS_P9_CHILD"
    TOTAL_P9_PLAIN=$(( P9_PLAIN_CACHE + P9_PLAIN_UNCACHED + P9_PLAIN_OUTPUT ))
    TOTAL_P9_CHILD=$(( P9_CHILD_CACHE + P9_CHILD_UNCACHED + P9_CHILD_OUTPUT ))

    info "第 17 个 token 样本（P9① 不挂子智能体，cache|uncached|output）：$TOKENS_P9_PLAIN；run=$RUN_P9_PLAIN"
    info "第 18 个 token 样本（P9① 挂子智能体，cache|uncached|output）：$TOKENS_P9_CHILD；run=$RUN_P9_CHILD"
    info "【人工核对】请用这两个 run 的 UTC 时间窗与 DeepSeek 后台账单对账，并把结果记进 P9 计划 §8"
    if (( TOTAL_P9_CHILD > TOTAL_P9_PLAIN )); then
        pass "挂子智能体的总 token $TOTAL_P9_CHILD > 对照组 $TOTAL_P9_PLAIN"
    else
        fail "子图 token 疑似漏计：挂子智能体=$TOTAL_P9_CHILD，对照组=$TOTAL_P9_PLAIN"
    fi
fi
end

# ------------------------------------------ P9③ 一层限制
begin "P9③" "子智能体候选过滤、嵌套提交、数量与同名闸门全部生效"

if (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），子智能体配置闸门验不了"
elif (( ! P9_READY )); then
    fail "前置没就绪（$P9_SETUP_NOTE），子智能体候选验不了"
else
    THREAD_P9_GUARD="$(new_thread "$JAR_P7_A")"
    P9_SCENE_ID=""
    P9_SCENE_CREATED=0
    P9_SCENE_RELEASED=0
    P9_SCENE_RESPONSE="$(api "$JAR_P7_A" -X POST "$BASE_URL/api/agents" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "p9-scene-$P7_TAG" --arg id "$AGENT_P9_VOLATILITY" \
            '{name:$n,description:"P9 一层限制场景",subject:"金融学",system_prompt:"负责调度子智能体。",subagents:[$id]}')")" && \
        P9_SCENE_ID="$(jq -r '.id // empty' <<<"$P9_SCENE_RESPONSE")"
    [[ -n $P9_SCENE_ID ]] && P9_SCENE_CREATED=1
    if (( P9_SCENE_CREATED )) && api "$JAR_P7_A" -X POST "$BASE_URL/api/agents/$P9_SCENE_ID/versions" >/dev/null 2>&1; then
        P9_SCENE_RELEASED=1
    fi

    P9_CANDIDATES="$(api "$JAR_P7_A" "$BASE_URL/api/agents/subagent-candidates" 2>/dev/null || true)"
    P9_CANDIDATE_CHILD=0
    P9_CANDIDATE_SCENE=0
    if [[ -n $P9_CANDIDATES ]]; then
        jq -e --arg id "$AGENT_P9_VOLATILITY" 'any(.[]; .id == $id)' <<<"$P9_CANDIDATES" >/dev/null 2>&1 && P9_CANDIDATE_CHILD=1
        (( P9_SCENE_RELEASED )) && jq -e --arg id "$P9_SCENE_ID" 'any(.[]; .id == $id)' <<<"$P9_CANDIDATES" >/dev/null 2>&1 && P9_CANDIDATE_SCENE=1
    fi
    if (( P9_CANDIDATE_CHILD && ! P9_CANDIDATE_SCENE )); then
        pass "候选列表保留无子智能体的 child，过滤掉已挂子智能体的 scene"
    else
        fail "候选列表过滤错误：child=$P9_CANDIDATE_CHILD scene_included=$P9_CANDIDATE_SCENE"
    fi

    P9_GUARD_RUNS_BEFORE="$(p7_run_count "$THREAD_P9_GUARD")"
    P9_NESTED_CODE=0
    (( P9_SCENE_RELEASED )) && P9_NESTED_CODE="$(code "$JAR_P7_A" -X POST "$BASE_URL/api/threads/$THREAD_P9_GUARD/runs" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg id "$P9_SCENE_ID" '{content:"P9 嵌套提交",agent_config:{subagents:[$id]}}')")"
    P9_GUARD_RUNS_AFTER="$(p7_run_count "$THREAD_P9_GUARD")"
    if [[ $P9_NESTED_CODE == 422 && $P9_GUARD_RUNS_AFTER == "$P9_GUARD_RUNS_BEFORE" ]]; then
        pass "带 subagent_refs 的 scene 提交返回 422，且未新增 run"
    else
        fail "嵌套提交闸门失效：code=$P9_NESTED_CODE runs=$P9_GUARD_RUNS_BEFORE→$P9_GUARD_RUNS_AFTER"
    fi

    P9_DUPLICATE_ID="$(p7_new_agent "$JAR_P7_B" "volatility-expert" "P9 同名冲突探针")" || P9_DUPLICATE_ID=""
    P9_DUPLICATE_SHARED=0
    if [[ -n $P9_DUPLICATE_ID ]] && p7_share "$JAR_P7_B" "$P9_DUPLICATE_ID" "$GROUP_P7_1" >/dev/null 2>&1; then
        P9_DUPLICATE_SHARED=1
    fi
    P9_DUPLICATE_VISIBLE=0
    (( P9_DUPLICATE_SHARED )) && p7_available_has "$JAR_P7_A" "$P9_DUPLICATE_ID" && P9_DUPLICATE_VISIBLE=1
    P9_DUPLICATE_RUNS_BEFORE="$(p7_run_count "$THREAD_P9_GUARD")"
    P9_DUPLICATE_CODE=0
    (( P9_DUPLICATE_VISIBLE )) && P9_DUPLICATE_CODE="$(code "$JAR_P7_A" -X POST "$BASE_URL/api/threads/$THREAD_P9_GUARD/runs" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg a "$AGENT_P9_VOLATILITY" --arg b "$P9_DUPLICATE_ID" \
            '{content:"P9 同名提交",agent_config:{subagents:[$a,$b]}}')")"
    P9_DUPLICATE_RUNS_AFTER="$(p7_run_count "$THREAD_P9_GUARD")"
    if (( P9_DUPLICATE_VISIBLE )) && [[ $P9_DUPLICATE_CODE == 422 && $P9_DUPLICATE_RUNS_AFTER == "$P9_DUPLICATE_RUNS_BEFORE" ]]; then
        pass "两个不同 agent 的同名子智能体提交返回 422，且未新增 run"
    else
        fail "同名子智能体闸门失效：visible=$P9_DUPLICATE_VISIBLE code=$P9_DUPLICATE_CODE runs=$P9_DUPLICATE_RUNS_BEFORE→$P9_DUPLICATE_RUNS_AFTER"
    fi

    P9_MANY_IDS=()
    for P9_INDEX in 1 2 3 4 5 6; do
        P9_MANY_ID="$(p7_new_agent "$JAR_P7_A" "p9-many-$P9_INDEX-$P7_TAG" "P9 数量上限探针 $P9_INDEX")" || P9_MANY_ID=""
        [[ -n $P9_MANY_ID ]] && P9_MANY_IDS+=("$P9_MANY_ID")
    done
    P9_MANY_RUNS_BEFORE="$(p7_run_count "$THREAD_P9_GUARD")"
    P9_MANY_CODE=0
    if (( ${#P9_MANY_IDS[@]} == 6 )); then
        P9_MANY_JSON="$(printf '%s\n' "${P9_MANY_IDS[@]}" | jq -R -s 'split("\n") | map(select(length > 0))')"
        P9_MANY_CODE="$(code "$JAR_P7_A" -X POST "$BASE_URL/api/threads/$THREAD_P9_GUARD/runs" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc --argjson ids "$P9_MANY_JSON" '{content:"P9 六个子智能体",agent_config:{subagents:$ids}}')")"
    fi
    P9_MANY_RUNS_AFTER="$(p7_run_count "$THREAD_P9_GUARD")"
    if (( ${#P9_MANY_IDS[@]} == 6 )) && [[ $P9_MANY_CODE == 422 && $P9_MANY_RUNS_AFTER == "$P9_MANY_RUNS_BEFORE" ]]; then
        pass "挂 6 个子智能体返回 422，且未新增 run"
    else
        fail "数量上限闸门失效：created=${#P9_MANY_IDS[@]} code=$P9_MANY_CODE runs=$P9_MANY_RUNS_BEFORE→$P9_MANY_RUNS_AFTER"
    fi
fi
end

# ------------------------------------------ P9④ 子图递归上限
begin "P9④" "循环子智能体在平台递归额度停止，而不是 9999"

P9_RECURSION_LOG="$WORK_DIR/p9-recursion.log"
if [[ ! -x $REPO_ROOT/app/.venv/bin/pytest ]]; then
    undone "app/.venv/bin/pytest 不存在，无法运行本地受限子图探针"
elif (cd "$REPO_ROOT/app" && UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q test/agent/subagent_test.py -k test_the_bound_limit_stops_a_real_looping_subgraph >"$P9_RECURSION_LOG" 2>&1); then
    pass "真实循环子图按 SUBAGENT_RECURSION_LIMIT 停止；测试未落回 9999"
else
    fail "循环子图递归上限探针失败，详见 $P9_RECURSION_LOG"
    tail -30 "$P9_RECURSION_LOG" >&2 || true
fi
end

# ------------------------------------------ P9⑤ 嵌套 HITL
begin "P9⑤" "子智能体的 delete 能中断，批准后从子图继续并成功"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要一次便宜的真实分析"
elif (( ! P9_HITL_READY )); then
    fail "前置没就绪（$P9_HITL_SETUP_NOTE），嵌套审批验不了"
else
    THREAD_P9_HITL="$(new_thread "$JAR_P7_A")"
    P9_HITL_FILE="$WORK_DIR/nested-hitl.txt"
    printf 'P9⑤ 子智能体审批探针；批准 delete 后应消失。\n' > "$P9_HITL_FILE"
    P9_HITL_CONFIGURED=0
    P9_HITL_UPLOADED=0
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P9_HITL" \
        -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg t "P9 嵌套审批 $P7_TAG" --arg id "$AGENT_P9_DELETE" \
            '{title:$t,agent_config:{subagents:[$id]}}')" >/dev/null 2>&1 && P9_HITL_CONFIGURED=1
    api "$JAR_P7_A" -X POST "$BASE_URL/api/threads/$THREAD_P9_HITL/files" \
        -F "file=@$P9_HITL_FILE;filename=nested-hitl.txt" >/dev/null 2>&1 && P9_HITL_UPLOADED=1

    if (( ! P9_HITL_CONFIGURED || ! P9_HITL_UPLOADED )); then
        fail "会话配置或探针文件没准备好：configured=$P9_HITL_CONFIGURED uploaded=$P9_HITL_UPLOADED"
    else
        RUN_P9_HITL="$(api "$JAR_P7_A" -X POST "$BASE_URL/api/threads/$THREAD_P9_HITL/runs" \
            -H 'Content-Type: application/json' \
            -d '{"content":"必须把删除 /workspace/nested-hitl.txt 的整项工作委派给 delete-expert；你自己不得调用任何文件工具。子智能体完成后只回答已完成。"}' | jq -r '.id // empty')"
        if [[ -z $RUN_P9_HITL ]] || ! wait_status "$JAR_P7_A" "$RUN_P9_HITL" waiting_approval "$RUN_TIMEOUT"; then
            fail "run 没停在 waiting_approval（当前 $(run_status "$JAR_P7_A" "$RUN_P9_HITL" 2>/dev/null || echo 未提交)）"
            [[ -n $RUN_P9_HITL ]] && api "$JAR_P7_A" -X POST "$BASE_URL/api/runs/$RUN_P9_HITL/cancel" >/dev/null 2>&1 || true
        else
            timeout 10 curl -fsS -b "$JAR_P7_A" -N "$BASE_URL/api/runs/$RUN_P9_HITL/events" \
                > "$WORK_DIR/p9-hitl-before.sse" 2>/dev/null || true
            grep '^data:' "$WORK_DIR/p9-hitl-before.sse" | sed 's/^data: *//' | jq -c . \
                > "$WORK_DIR/p9-hitl-before.json"
            P9_HITL_TASKS="$(jq -s '[.[]
                | select(.type == "tool_call" and (.path | length == 0))
                | select(.data.name == "task" and .data.args.subagent_type == "delete-expert")
            ] | length' "$WORK_DIR/p9-hitl-before.json")"
            P9_HITL_INTERRUPTS="$(jq -s '[.[]
                | select(.type == "interrupt" and .path == ["delete-expert"])
                | .data.actions[]
                | select(.tool_name == "delete" and .args.file_path == "/workspace/nested-hitl.txt")
            ] | length' "$WORK_DIR/p9-hitl-before.json")"
            if (( P9_HITL_TASKS > 0 && P9_HITL_INTERRUPTS == 1 )); then
                pass "delete 来自 delete-expert 子图，目标路径准确"
            else
                fail "没拿到准确的嵌套中断：task=$P9_HITL_TASKS interrupt=$P9_HITL_INTERRUPTS"
            fi

            APPROVE_P9_HITL="$(code "$JAR_P7_A" -X POST "$BASE_URL/api/runs/$RUN_P9_HITL/approve" \
                -H 'Content-Type: application/json' -d '{"decisions":[{"index":0,"type":"approve"}]}')"
            if [[ $APPROVE_P9_HITL != 202 ]] || ! wait_status "$JAR_P7_A" "$RUN_P9_HITL" succeeded "$RUN_TIMEOUT"; then
                fail "批准后没成功：approve=$APPROVE_P9_HITL status=$(run_status "$JAR_P7_A" "$RUN_P9_HITL")"
                api "$JAR_P7_A" -X POST "$BASE_URL/api/runs/$RUN_P9_HITL/cancel" >/dev/null 2>&1 || true
            else
                timeout "$RUN_TIMEOUT" curl -fsS -b "$JAR_P7_A" -N \
                    "$BASE_URL/api/runs/$RUN_P9_HITL/events" > "$WORK_DIR/p9-hitl.sse"
                grep '^data:' "$WORK_DIR/p9-hitl.sse" | sed 's/^data: *//' | jq -c . \
                    > "$WORK_DIR/p9-hitl.json"
                P9_HITL_STARTS_INITIAL="$(jq -s '[.[]
                    | select(.type == "run.started" and .data.resumed == false)
                ] | length' "$WORK_DIR/p9-hitl.json")"
                P9_HITL_STARTS_RESUMED="$(jq -s '[.[]
                    | select(.type == "run.started" and .data.resumed == true)
                ] | length' "$WORK_DIR/p9-hitl.json")"
                P9_HITL_TASKS_FINAL="$(jq -s '[.[]
                    | select(.type == "tool_call" and (.path | length == 0))
                    | select(.data.name == "task" and .data.args.subagent_type == "delete-expert")
                ] | length' "$WORK_DIR/p9-hitl.json")"
                P9_HITL_RESULTS="$(jq -s '[.[]
                    | select(.type == "tool_result" and .path == ["delete-expert"])
                    | select(.data.name == "delete")
                ] | length' "$WORK_DIR/p9-hitl.json")"
                P9_HITL_FILE_LEFT="$(api "$JAR_P7_A" "$BASE_URL/api/threads/$THREAD_P9_HITL/files" |
                    jq '[.entries[] | select(.path == "nested-hitl.txt")] | length')"
                if (( P9_HITL_STARTS_INITIAL == 1
                    && P9_HITL_STARTS_RESUMED == 1
                    && P9_HITL_TASKS_FINAL == 1
                    && P9_HITL_RESULTS == 1
                    && P9_HITL_FILE_LEFT == 0 )); then
                    pass "批准后从子图断点续跑：首跑/续跑各 1 次，task 未重放，目标文件已删除"
                else
                    fail "恢复语义不对：initial=$P9_HITL_STARTS_INITIAL resumed=$P9_HITL_STARTS_RESUMED task=$P9_HITL_TASKS_FINAL result=$P9_HITL_RESULTS file_left=$P9_HITL_FILE_LEFT"
                fi
            fi
        fi
    fi
fi
end

# ------------------------------------------ P9⑥ 浏览器嵌套事件链路
begin "P9⑥" "浏览器里看得见命名嵌套折叠块并展开工具过程"

if (( ! P9_READY )); then
    undone "前置没就绪（$P9_SETUP_NOTE），浏览器主链路没有可用子智能体"
elif ! command -v pnpm >/dev/null 2>&1; then
    undone "没有 pnpm，跑不了 playwright"
elif [[ ! -d $REPO_ROOT/web/node_modules/@playwright ]]; then
    undone "web/ 没装 @playwright/test：cd web && pnpm install"
elif ! (cd "$REPO_ROOT/web" && pnpm exec playwright install --dry-run chromium >/dev/null 2>&1); then
    undone "查不到 chromium 二进制：cd web && pnpm exec playwright install chromium"
else
    P9_E2E_LOG="$WORK_DIR/p9-e2e.log"
    if (cd "$REPO_ROOT/web" && \
        E2E_API_TARGET="$BASE_URL" \
        E2E_PASSWORD="$P7_SECRET" \
        E2E_AUTHOR="$NAME_P7_A" \
        E2E_SUBAGENT_NAME="volatility-expert" \
        E2E_SUBAGENT_QUESTION="${P6_QUESTION:-只做这一件事：固定收益率数组 [0.01,-0.005,0.008,-0.002,0.006] 的样本标准差是 0.00654217089351845，乘以 sqrt(252) 后年化波动率是 0.10385374331241026。如果存在名为 volatility-expert 的可委派子智能体，必须把整项工作委派给它，只调用一次 write_file，把结果写进 outputs/p9-browser.txt。}" \
        pnpm exec playwright test e2e/subagent-workspace.spec.ts >"$P9_E2E_LOG" 2>&1); then
        pass "子智能体浏览器链路通过：选择、真实事件、命名折叠与 write_file 均可见"
    else
        fail "子智能体 playwright 未全过，详见 $P9_E2E_LOG"
        tail -30 "$P9_E2E_LOG" >&2 || true
    fi
fi
end


# ===========================================================================
# P10：外网 MCP —— 目录、超时、撞名、熔断与外发标注
# ===========================================================================
#
# **这一期第一次出现「一次分析的成败取决于一台校外机器」。** 因此这一组里有三条
# 判据要的是**真的连一次**，不是断言我们传了什么参数：框架换一种连接实现之后，
# 那种单测照样绿。
#
# 夹具 MCP server 跑在**宿主机**上（`deploy/test/mcp/server.py`），api 与 worker
# 两个容器都靠 `host.docker.internal` 够着它 —— 真实的 MCP 全在校外，用不上那一行，
# 用得上它的是验收。它默认只听回环，这里显式让它听所有网卡，否则容器连不上。

P10_FIXTURE_PORT="${P10_FIXTURE_PORT:-8931}"
P10_FIXTURE_URL="http://host.docker.internal:$P10_FIXTURE_PORT/mcp"
P10_FIXTURE_SCRIPT="$REPO_ROOT/deploy/test/mcp/server.py"
P10_VENV_PYTHON="$REPO_ROOT/app/.venv/bin/python"
P10_FIXTURE_PID=""
P10_READY=0
P10_SETUP_NOTE="未开始"
SERVER_P10=""
AGENT_P10_SCENE=""
P10_MCP_NAME="p10-paper-$P7_TAG"
P10_SCENE_NAME="p10-scene-$P7_TAG"

# 起夹具。**用 venv 里的 python 而不是 `uv run`** —— 后者是父进程套子进程，
# kill 父的留下子的，端口一直占着，而下一轮报的是「Address already in use」。
#
# **起之前先确认那个端口上没有别人。** 开发时留下的一个夹具进程会让这里彻底跑偏：
# 我们自己那个绑不上端口当场退出，而就绪探测探到的是**别人那一个**，于是一路绿到
# `P10⑤` —— 那条要把夹具停掉，而 kill 我们那个早就死了的 PID 什么也不会发生，
# 探活照常连得上，判据红在「没自动停用」上，**没有一处指向端口被占**。实测踩过一次
p10_start_fixture() {
    [[ -x $P10_VENV_PYTHON ]] || return 1
    p10_port_free || return 1
    env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
        MCP_FIXTURE_HOST=0.0.0.0 MCP_FIXTURE_PORT="$P10_FIXTURE_PORT" \
        "$P10_VENV_PYTHON" "$P10_FIXTURE_SCRIPT" >>"$WORK_DIR/p10-fixture.log" 2>&1 &
    P10_FIXTURE_PID=$!
    p10_wait_fixture || return 1
    # 起来了还要确认那个 405 是**我们这个进程**答的，不是端口上别的什么东西
    kill -0 "$P10_FIXTURE_PID" 2>/dev/null
}

# 端口上此刻没有人应答。空着时 curl 连不上，`%{http_code}` 是 000
p10_port_free() {
    local code
    code="$(curl -s --noproxy '*' --connect-timeout 2 -o /dev/null -w '%{http_code}' -I \
        "http://127.0.0.1:$P10_FIXTURE_PORT/mcp" 2>/dev/null)"
    [[ $code == 000 ]]
}

# 405 就够了：它说明端口上跑着的确实是这个应用，而不是随便一个监听者
p10_wait_fixture() {
    local deadline=$((SECONDS + 30)) code
    while (( SECONDS < deadline )); do
        code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' -I \
            "http://127.0.0.1:$P10_FIXTURE_PORT/mcp" 2>/dev/null)"
        [[ $code == 405 ]] && return 0
        sleep 0.5
    done
    return 1
}

# 停夹具，**并等到端口真的空出来**：紧接着 `P10⑤` 还要把它起回来，
# 而端口还没释放时新进程绑不上，症状会落在「一次都不连」那条断言上
p10_stop_fixture() {
    local deadline
    [[ -n $P10_FIXTURE_PID ]] || return 0
    kill "$P10_FIXTURE_PID" >/dev/null 2>&1
    wait "$P10_FIXTURE_PID" 2>/dev/null
    P10_FIXTURE_PID=""
    deadline=$((SECONDS + 15))
    while (( SECONDS < deadline )); do
        p10_port_free && return 0
        sleep 0.5
    done
    return 1
}

# 一条目录记录的当前状态与停用原因，直接读库 —— 端点回的是同一份，但库是真相
p10_status() {
    psql_query "SELECT status || '|' || COALESCE(disabled_reason, '') FROM mcp_servers WHERE id = '$1';" |
        tr -d '\r'
}

p10_apply() {
    local jar="$1" name="$2" url="$3" write="${4:-false}"
    api "$jar" -X POST "$BASE_URL/api/mcp" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$name" --arg u "$url" --argjson w "$write" '{
            name: $n,
            description: "验收夹具：按关键词检索论文",
            url: $u,
            transport: "streamable_http",
            tool_names: ["search_paper", "slow_query", "boom"],
            latency_note: "典型 40 毫秒",
            stores_user_data: false,
            sends_data_out: true,
            has_write_operation: $w
        }')" | jq -r '.id // empty'
}

# 目录里有没有它
p10_catalog_has() {
    api "$1" "$BASE_URL/api/mcp" | jq -e --arg id "$2" 'any(.[]; .id == $id)' >/dev/null 2>&1
}

# 提交一条挂了这些 MCP 的 run，返回 HTTP 状态码
p10_submit_code() {
    local jar="$1" thread_id="$2" ids="$3"
    curl -s -o /dev/null -w '%{http_code}' -b "$jar" \
        -X POST "$BASE_URL/api/threads/$thread_id/runs" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg c "查一篇随机波动率的论文" --argjson m "$ids" '{content:$c, agent_config:{mcps:$m}}')"
}

if (( ! P7_READY )); then
    P10_SETUP_NOTE="P7 账号前置没就绪（$P7_SETUP_NOTE）"
elif [[ ! -f $P10_FIXTURE_SCRIPT ]]; then
    P10_SETUP_NOTE="缺夹具 $P10_FIXTURE_SCRIPT"
elif [[ ! -x $P10_VENV_PYTHON ]]; then
    P10_SETUP_NOTE="缺 app/.venv（cd app && uv sync），起不了夹具 MCP server"
elif ! p10_port_free; then
    P10_SETUP_NOTE=":$P10_FIXTURE_PORT 上已经有人在应答 —— 先停掉它（开发时手工起的夹具最常见），或换 P10_FIXTURE_PORT"
elif ! p10_start_fixture; then
    P10_SETUP_NOTE="夹具 MCP server 没起来，详见 $WORK_DIR/p10-fixture.log"
elif ! SERVER_P10="$(p10_apply "$JAR_P7_A" "$P10_MCP_NAME" "$P10_FIXTURE_URL")" || [[ -z $SERVER_P10 ]]; then
    P10_SETUP_NOTE="MCP 申请没提上去"
else
    P10_READY=1
    P10_SETUP_NOTE="夹具在 :$P10_FIXTURE_PORT，申请 server_id=$SERVER_P10 待审"
fi
log "P10 前置：$P10_SETUP_NOTE"

# ------------------------------------------ P10② 申请流程的两道关
begin "P10②" "申请 → 管理员放行 → 目录里出现、勾得上；未放行的两道关都拦住"

if (( ! P10_READY )); then
    fail "前置没就绪（$P10_SETUP_NOTE），申请流程验不了"
else
    THREAD_P10_GATE="$(new_thread "$JAR_P7_A")"

    # 第一道关：目录列表里看不到它
    P10_HIDDEN=0
    p10_catalog_has "$JAR_P7_A" "$SERVER_P10" || P10_HIDDEN=1
    # 第二道关：提交侧也解析不出来，且**一行 run 都不许多出来**
    P10_BEFORE="$(p7_run_count "$THREAD_P10_GATE")"
    P10_PENDING_CODE="$(p10_submit_code "$JAR_P7_A" "$THREAD_P10_GATE" "$(jq -nc --arg id "$SERVER_P10" '[$id]')")"
    P10_AFTER="$(p7_run_count "$THREAD_P10_GATE")"
    if (( P10_HIDDEN )) && [[ $P10_PENDING_CODE == 422 ]] && [[ $P10_BEFORE == "$P10_AFTER" ]]; then
        pass "未放行的两道关都拦住：目录里没有它，提交 422 且没多出 run"
    else
        fail "未放行的没拦住：目录隐藏=$P10_HIDDEN 提交=$P10_PENDING_CODE run $P10_BEFORE→$P10_AFTER"
    fi

    # **这里探的是启停，不再是审批**（2026-08-16 边界重划）：批与拒放给了 reviewer，
    # 而启停与探活仍归 admin —— 线从「按资源类型分」改成「按审核与运维分」。
    #
    # 探针必须**不消耗这条待审申请**：让 reviewer 真去批一次的话它就变成已处理，
    # 下面那段「管理员放行」拿到的是 422，而这条判据的正题恰恰是管理员放行。
    # 启停正好合适 —— 准入是依赖注入，在「这条还没放行」那一步之前就判完了。
    # reviewer 批得了这件事由 P7⑤ 与后端用例各自钉住
    P10_REVIEWER_CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR_P7_R" \
        -X POST "$BASE_URL/api/mcp/admin/$SERVER_P10/enabled" \
        -H 'Content-Type: application/json' -d '{"enabled":false,"reason":"越权试探"}')"
    if [[ $P10_REVIEWER_CODE == 403 ]]; then
        pass "reviewer 停不了 MCP（403）：审得了不等于运维得了"
    else
        fail "reviewer 居然停得了 MCP：HTTP $P10_REVIEWER_CODE"
    fi

    # 声明有写操作的一律不批。**这是本期唯一一条「不能靠人记住」的规则**
    P10_WRITE_ID="$(p10_apply "$JAR_P7_A" "$P10_MCP_NAME-write" "$P10_FIXTURE_URL" true)"
    if [[ -n $P10_WRITE_ID ]]; then
        P10_WRITE_CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR_P7_ADMIN" \
            -X POST "$BASE_URL/api/mcp/admin/$P10_WRITE_ID/decision" \
            -H 'Content-Type: application/json' -d '{"approved":true}')"
        P10_WRITE_STATUS="$(p10_status "$P10_WRITE_ID")"
        if [[ $P10_WRITE_CODE == 422 && $P10_WRITE_STATUS == pending\|* ]]; then
            pass "声明有写操作的管理员也批不了（422），且状态仍是 pending"
        else
            fail "写操作硬闸门没生效：HTTP $P10_WRITE_CODE 状态=$P10_WRITE_STATUS"
        fi
    else
        fail "带写操作声明的申请没提上去，硬闸门验不了"
    fi

    # 管理员放行之后两道关都要开
    P10_APPROVE_CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR_P7_ADMIN" \
        -X POST "$BASE_URL/api/mcp/admin/$SERVER_P10/decision" \
        -H 'Content-Type: application/json' -d '{"approved":true}')"
    P10_VISIBLE=0
    p10_catalog_has "$JAR_P7_A" "$SERVER_P10" && P10_VISIBLE=1
    P10_OK_CODE="$(p10_submit_code "$JAR_P7_A" "$THREAD_P10_GATE" "$(jq -nc --arg id "$SERVER_P10" '[$id]')")"
    if [[ $P10_APPROVE_CODE == 202 ]] && (( P10_VISIBLE )) && [[ $P10_OK_CODE == 202 ]]; then
        pass "放行之后两道关都开：目录里出现，提交也过（202）"
    else
        fail "放行之后没都开：审批=$P10_APPROVE_CODE 目录可见=$P10_VISIBLE 提交=$P10_OK_CODE"
    fi

    # 一次挂 4 个 —— MAX_MCP_SERVER 是闸门不是提示
    P10_EXTRA=()
    for slot in 2 3 4; do
        one="$(p10_apply "$JAR_P7_A" "$P10_MCP_NAME-$slot" "$P10_FIXTURE_URL")"
        [[ -n $one ]] || continue
        curl -s -o /dev/null -b "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/mcp/admin/$one/decision" \
            -H 'Content-Type: application/json' -d '{"approved":true}'
        P10_EXTRA+=("$one")
    done
    if (( ${#P10_EXTRA[@]} == 3 )); then
        P10_FOUR="$(jq -nc --args '$ARGS.positional' "$SERVER_P10" "${P10_EXTRA[@]}")"
        P10_FOUR_CODE="$(p10_submit_code "$JAR_P7_A" "$THREAD_P10_GATE" "$P10_FOUR")"
        if [[ $P10_FOUR_CODE == 422 ]]; then
            pass "一次挂 4 个当场 422：MAX_MCP_SERVER 是闸门不是提示"
        else
            fail "挂 4 个居然过了：HTTP $P10_FOUR_CODE"
        fi
    else
        fail "凑不齐 4 条已放行的 MCP，数量闸门验不了"
    fi
fi
end

# ------------------------------------------ P10③ 一台卡住的服务掀不掉一次装配
begin "P10③" "hang 住的服务在平台设的秒数上被掐断，且不拖垮同一次装配里别的服务"

if (( ! P10_READY )); then
    fail "前置没就绪（$P10_SETUP_NOTE），超时降级验不了"
else
    # **在 api 容器里跑，用它真正在用的那份运行时。** 断言的是**真实耗时**，
    # 不是「我们给 asyncio.timeout 传了 30」—— 后者验的是意图，框架换一种连接
    # 实现之后照样绿。黑洞端口只 listen 不 accept：握手由内核完成，请求发得出去，
    # 然后一直等，正是「服务卡住了」那种最难查的形态
    P10_HANG_OUT="$(in_api_python "
import asyncio, json, socket, time
from agent.mcp import MCP_CONNECT_TIMEOUT, McpTarget, load_mcp_tools
from agent.config import McpReference

listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(1)
hang_port = listener.getsockname()[1]


def target(server_id, url):
    return McpTarget(
        server_id=server_id, name=server_id, url=url, transport='streamable_http',
        credential=None, declared_tool_name=['search_paper'], enabled=True, disabled_reason=None,
    )


targets = {
    'hang': target('hang', f'http://127.0.0.1:{hang_port}/mcp'),
    'good': target('good', '$P10_FIXTURE_URL'),
}


class Loader:
    async def load_mcp_target(self, server_id):
        return targets.get(server_id)


async def main():
    started = time.monotonic()
    tools = await load_mcp_tools(
        [McpReference(server_id='hang', name='hang'), McpReference(server_id='good', name='good')],
        loader=Loader(),
    )
    elapsed = time.monotonic() - started
    again = await load_mcp_tools([McpReference(server_id='good', name='good')], loader=Loader())
    print(json.dumps({
        'elapsed': round(elapsed, 2),
        'budget': MCP_CONNECT_TIMEOUT,
        'tools': sorted(one.name for one in tools),
        'after': sorted(one.name for one in again),
    }))

asyncio.run(main())
" 2>"$WORK_DIR/p10-hang.err")"

    if [[ -z $P10_HANG_OUT ]]; then
        fail "装配探针没跑起来，详见 $WORK_DIR/p10-hang.err"
        tail -20 "$WORK_DIR/p10-hang.err" >&2 || true
    else
        P10_ELAPSED="$(jq -r '.elapsed' <<<"$P10_HANG_OUT")"
        P10_BUDGET="$(jq -r '.budget' <<<"$P10_HANG_OUT")"
        # 掐在平台设的那个数上，而不是 sse_read_timeout 的 300 秒。
        # 下界一并断言：秒数远小于预算说明它是当场失败而不是被我们掐断的
        if jq -e '.elapsed >= (.budget * 0.5) and .elapsed <= (.budget + 20)' <<<"$P10_HANG_OUT" >/dev/null; then
            pass "在平台设的 ${P10_BUDGET} 秒上被掐断（实测 ${P10_ELAPSED} 秒），不是框架默认的 300 秒"
        else
            fail "掐断的秒数不对：实测 ${P10_ELAPSED} 秒，平台预算 ${P10_BUDGET} 秒"
        fi
        if jq -e '(.tools | index("search_paper")) != null and (.tools | index("read_file")) == null' \
            <<<"$P10_HANG_OUT" >/dev/null; then
            pass "一个坏服务不拖垮同一次装配里的好服务：夹具的工具照常拿到"
        else
            fail "好服务被拖下水了：拿到的工具 $(jq -c .tools <<<"$P10_HANG_OUT")"
        fi
        if jq -e '(.after | index("search_paper")) != null' <<<"$P10_HANG_OUT" >/dev/null; then
            pass "掐断没弄脏进程：同一个事件循环里后续连接照常成功"
        else
            fail "掐断之后连不上夹具了：$(jq -c .after <<<"$P10_HANG_OUT")"
        fi
    fi
fi
end

# ------------------------------------------ P10④ 外部工具顶不掉内置的
begin "P10④" "外部工具顶不掉平台内置的 read_file"

if (( ! P10_READY )); then
    fail "前置没就绪（$P10_SETUP_NOTE），撞名剔除验不了"
else
    # 夹具**故意**提供一个叫 read_file 的工具。实测里外部那个会静默顶掉内置的，
    # 内置那个从工具列表里消失 —— 于是 agent 以为在读沙箱，实际把路径与后续内容
    # 发去了校外。**断言的是真的连了一次之后拿到的那份列表**
    P10_CLASH_OUT="$(in_api_python "
import asyncio, json
from agent.mcp import RESERVED_TOOL_NAME, McpTarget, load_mcp_tools
from agent.config import McpReference


class Loader:
    async def load_mcp_target(self, server_id):
        return McpTarget(
            server_id='fixture', name='fixture', url='$P10_FIXTURE_URL', transport='streamable_http',
            credential=None, declared_tool_name=['search_paper'], enabled=True, disabled_reason=None,
        )


async def main():
    tools = await load_mcp_tools([McpReference(server_id='fixture', name='fixture')], loader=Loader())
    print(json.dumps({
        'tools': sorted(one.name for one in tools),
        'reserved': sorted(RESERVED_TOOL_NAME),
    }))

asyncio.run(main())
" 2>"$WORK_DIR/p10-clash.err")"

    if [[ -z $P10_CLASH_OUT ]]; then
        fail "撞名探针没跑起来，详见 $WORK_DIR/p10-clash.err"
        tail -20 "$WORK_DIR/p10-clash.err" >&2 || true
    elif jq -e '
        (.tools | index("read_file")) == null
        and (.tools | index("search_paper")) != null
        and (.reserved | index("read_file")) != null
    ' <<<"$P10_CLASH_OUT" >/dev/null; then
        pass "夹具的 read_file 被剔除，search_paper 照常拿到：内置工具顶不掉"
        info "这一次拿到的外部工具：$(jq -c .tools <<<"$P10_CLASH_OUT")"
    else
        fail "撞名剔除没生效：$(jq -c .tools <<<"$P10_CLASH_OUT")"
    fi
fi
end

# ------------------------------------------ P10⑤ 连续失败 5 次真的自动停用
begin "P10⑤" "连续 5 次传输失败自动停用，之后装配一次都不再连它"

if (( ! P10_READY )); then
    fail "前置没就绪（$P10_SETUP_NOTE），熔断验不了"
else
    # **走探活这条路**：它是真实场景（管理员点「测试连接」），不是为测试造的后门；
    # 免费且确定 —— 跑 5 次真实分析既贵又不受控（模型这次会不会调那个工具是运气）。
    # 三条路共用同一个计数器这件事由 `make all` 里那条单测钉住，见 P10 计划 §4.4
    P10_THRESHOLD="$(in_api_python 'from agent.circuit import MCP_FAILURE_THRESHOLD; print(MCP_FAILURE_THRESHOLD)' | tr -d '[:space:]')"
    p10_stop_fixture
    P10_PROBE_LAST=""
    for _ in $(seq 1 "${P10_THRESHOLD:-5}"); do
        P10_PROBE_LAST="$(api "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/mcp/admin/$SERVER_P10/probe" 2>/dev/null)"
    done
    P10_DISABLED="$(p10_status "$SERVER_P10")"

    if [[ $P10_DISABLED == disabled\|*连续失败* && $P10_DISABLED == *"$P10_THRESHOLD"* ]]; then
        pass "连续 $P10_THRESHOLD 次失败之后自动停用，原因写进了库：${P10_DISABLED#disabled|}"
    else
        fail "没自动停用或原因不完整：$P10_DISABLED"
    fi

    if compose logs --since 10m api 2>/dev/null | grep -q '"level": "WARNING".*MCP 达到失败阈值'; then
        pass "日志里有那条 WARNING：管理员唯一的知情渠道还在"
    else
        fail "日志里找不到自动停用的 WARNING"
    fi

    # **把夹具重新起回来再验「一次都不连」** —— 服务停着的时候「没连上」证明不了
    # 任何事。起回来之后装配仍然拿到空列表，才说明它真的一次连接都没发起
    if p10_start_fixture; then
        P10_SKIP_OUT="$(in_api_python "
import asyncio, json
from agent.config import McpReference
from agent.mcp import load_mcp_tools
from config import Settings
from preset.mcp import McpRepository, McpTargetLoader
from store import postgres

async def main():
    engine = postgres.create_engine(Settings().postgres_dsn())
    loader = McpTargetLoader(McpRepository(engine), {})
    target = await loader.load_mcp_target('$SERVER_P10')
    tools = await load_mcp_tools([McpReference(server_id='$SERVER_P10', name='p10')], loader=loader)
    await engine.dispose()
    print(json.dumps({'enabled': target.enabled, 'tools': sorted(one.name for one in tools)}))

asyncio.run(main())
" 2>"$WORK_DIR/p10-skip.err")"
        if [[ -n $P10_SKIP_OUT ]] && jq -e '.enabled == false and (.tools | length) == 0' <<<"$P10_SKIP_OUT" >/dev/null; then
            pass "夹具已经起回来了，装配仍然一个工具都不要：停用的服务一次都不连"
        else
            fail "停用之后仍然连了它：$P10_SKIP_OUT"
            tail -20 "$WORK_DIR/p10-skip.err" >&2 || true
        fi
    else
        fail "夹具没能重新起来，「一次都不连」验不了"
    fi

    # 管理员手动恢复：状态回 enabled，计数清零
    P10_RESTORE="$(api "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/mcp/admin/$SERVER_P10/enabled" \
        -H 'Content-Type: application/json' -d '{"enabled":true}' 2>/dev/null)"
    P10_RESTORED="$(p10_status "$SERVER_P10")"
    if [[ $P10_RESTORED == "enabled|" ]] && jq -e '.failure_count == 0' <<<"$P10_RESTORE" >/dev/null; then
        pass "管理员手动恢复：状态回 enabled，失败计数清零"
    else
        fail "手动恢复不干净：状态=$P10_RESTORED 计数=$(jq -r '.failure_count // "?"' <<<"$P10_RESTORE")"
    fi
    info "停用前最后一次探活：$(jq -c '{reachable, failure_count}' <<<"${P10_PROBE_LAST:-null}" 2>/dev/null || echo 未取到)"
fi
end

# ------------------------------------------ P10⑥ 浏览器里两条路径都看得见外发标注
begin "P10⑥" "浏览器里两条路径都看得见外发标注（直接勾、以及场景自带）"

if (( ! P10_READY )); then
    undone "前置没就绪（$P10_SETUP_NOTE），浏览器链路没有可用的 MCP"
elif ! command -v pnpm >/dev/null 2>&1; then
    undone "没有 pnpm，跑不了 playwright"
elif [[ ! -d $REPO_ROOT/web/node_modules/@playwright ]]; then
    undone "web/ 没装 @playwright/test：cd web && pnpm install"
elif ! (cd "$REPO_ROOT/web" && pnpm exec playwright install --dry-run chromium >/dev/null 2>&1); then
    undone "查不到 chromium 二进制：cd web && pnpm exec playwright install chromium"
else
    # 场景要在这里现建：它自带那条 MCP，而第二条链路验的正是「一个都没勾也看得见」
    AGENT_P10_SCENE="$(api "$JAR_P7_A" -X POST "$BASE_URL/api/agents" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$P10_SCENE_NAME" --arg id "$SERVER_P10" '{
            name: $n, description: "会连校外论文库的场景", subject: "金融学",
            system_prompt: "你在需要检索论文时使用外部检索工具。", mcps: [$id]}')" | jq -r '.id // empty')"
    if [[ -n $AGENT_P10_SCENE ]]; then
        api "$JAR_P7_A" -X POST "$BASE_URL/api/agents/$AGENT_P10_SCENE/versions" >/dev/null 2>&1
    fi
    P10_E2E_LOG="$WORK_DIR/p10-e2e.log"
    if [[ -z $AGENT_P10_SCENE ]]; then
        fail "自带 MCP 的场景没建出来，第二条链路验不了"
    elif (cd "$REPO_ROOT/web" && \
        E2E_API_TARGET="$BASE_URL" \
        E2E_PASSWORD="$P7_SECRET" \
        E2E_AUTHOR="$NAME_P7_A" \
        E2E_MCP_NAME="$P10_MCP_NAME" \
        E2E_MCP_SCENE_NAME="$P10_SCENE_NAME" \
        pnpm exec playwright test e2e/mcp-outbound.spec.ts >"$P10_E2E_LOG" 2>&1); then
        pass "两条路径都看得见外发标注：直接勾一个 MCP，以及只选一个自带 MCP 的场景"
    else
        fail "外发标注 playwright 未全过，详见 $P10_E2E_LOG"
        tail -30 "$P10_E2E_LOG" >&2 || true
    fi
fi
end

# ------------------------------------------ P10① 主判据：外网工具真被调用
begin "P10①" "挂与不挂同一个 MCP，事件流与产物里看得出差别"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要两次真实分析"
elif (( ! P10_READY )); then
    fail "前置没就绪（$P10_SETUP_NOTE），主判据验不了"
else
    THREAD_P10_PLAIN="$(new_thread "$JAR_P7_A")"
    THREAD_P10_MCP="$(new_thread "$JAR_P7_A")"
    # **两个会话，不是同一个会话问两次** —— checkpoint 里的历史会污染第二次
    api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P10_MCP" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg id "$SERVER_P10" '{agent_config:{mcps:[$id]}}')" >/dev/null 2>&1

    P6_QUESTION='请检索关键词「随机波动率」的论文，并把检索工具原样返回的那一行结果写进 outputs/paper.txt。不要自己编造论文标题；如果没有可用的检索工具，就在文件里写 NO-TOOL。做完只回一句话。'
    P10_PLAIN_OK=0
    P10_MCP_OK=0
    if p6_analyse "$JAR_P7_A" "$THREAD_P10_PLAIN" p10-plain "$RUN_TIMEOUT"; then
        P10_PLAIN_OK=1
        RUN_P10_PLAIN="$P6_LAST_RUN"
    else
        RUN_P10_PLAIN="${P6_LAST_RUN:-}"
        STATUS_P10_PLAIN="${P6_LAST_STATUS:-提交失败}"
    fi
    if p6_analyse "$JAR_P7_A" "$THREAD_P10_MCP" p10-mcp "$RUN_TIMEOUT"; then
        P10_MCP_OK=1
        RUN_P10_MCP="$P6_LAST_RUN"
    else
        RUN_P10_MCP="${P6_LAST_RUN:-}"
        STATUS_P10_MCP="${P6_LAST_STATUS:-提交失败}"
    fi

    if (( ! P10_PLAIN_OK || ! P10_MCP_OK )); then
        fail "两条 run 没都跑到 succeeded：不挂=${STATUS_P10_PLAIN:-succeeded}，挂上=${STATUS_P10_MCP:-succeeded}"
    else
        # **断言的是 tool_call 事件里的工具名，不只是回答文本** —— 模型完全可以
        # 照着工具描述编一句 PAPER-HIT 出来
        P10_PLAIN_CALLS="$(jq -s '[.[] | select(.type == "tool_call") | .data.name] | unique' "$WORK_DIR/p10-plain.json")"
        P10_MCP_CALLS="$(jq -s '[.[] | select(.type == "tool_call") | .data.name] | unique' "$WORK_DIR/p10-mcp.json")"
        if jq -e 'index("search_paper") == null' <<<"$P10_PLAIN_CALLS" >/dev/null &&
            jq -e 'index("search_paper") != null' <<<"$P10_MCP_CALLS" >/dev/null; then
            pass "双向断言成立：不挂时没有 search_paper，挂上后事件流里真有它的 tool_call"
        else
            fail "工具调用不符合双向断言：不挂=$P10_PLAIN_CALLS 挂上=$P10_MCP_CALLS"
        fi

        P10_PLAIN_TEXT="$(api "$JAR_P7_A" --get --data-urlencode 'path=outputs/paper.txt' \
            "$BASE_URL/api/threads/$THREAD_P10_PLAIN/files/raw" 2>/dev/null || true)"
        P10_MCP_TEXT="$(api "$JAR_P7_A" --get --data-urlencode 'path=outputs/paper.txt' \
            "$BASE_URL/api/threads/$THREAD_P10_MCP/files/raw" 2>/dev/null || true)"
        if [[ $P10_PLAIN_TEXT != *PAPER-HIT* && $P10_MCP_TEXT == *PAPER-HIT* ]]; then
            pass "产物里看得出差别：不挂时没有 PAPER-HIT，挂上后有"
        else
            fail "产物不符合双向断言：不挂=$(head -c 80 <<<"$P10_PLAIN_TEXT") 挂上=$(head -c 80 <<<"$P10_MCP_TEXT")"
        fi

        P10_SNAPSHOT="$(psql_query "SELECT COALESCE(agent_config->'mcps', '[]'::jsonb)::text
            FROM runs WHERE id='$RUN_P10_MCP';" | tr -d '\r')"
        if jq -e --arg id "$SERVER_P10" --arg name "$P10_MCP_NAME" \
            'length == 1 and .[0].server_id == $id and .[0].name == $name' <<<"$P10_SNAPSHOT" >/dev/null; then
            pass "run 快照冻结了 server_id 与 name"
        else
            fail "MCP 快照不完整：$P10_SNAPSHOT"
        fi

        # 三个观察项（P10 计划 §4.2 第 5 条）
        P10_IS_ERROR="$(jq -s '[.[] | select(.type == "tool_result" and .data.status == "error")] | length' "$WORK_DIR/p10-mcp.json")"
        info "观察项 1：挂 MCP 那次 tool_result 里 status=error 出现 $P10_IS_ERROR 次（长期为 0 说明熔断口径可以收紧）"
        TOKENS_P10_PLAIN="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
            FROM runs WHERE id='$RUN_P10_PLAIN';" | tr -d '[:space:]')"
        TOKENS_P10_MCP="$(psql_query "SELECT COALESCE(tokens_cache_read,0) || '|' || COALESCE(tokens_uncached,0) || '|' || COALESCE(tokens_output,0)
            FROM runs WHERE id='$RUN_P10_MCP';" | tr -d '[:space:]')"
        info "第 19 个 token 样本（P10① 不挂 MCP，cache|uncached|output）：$TOKENS_P10_PLAIN；run=$RUN_P10_PLAIN"
        info "第 20 个 token 样本（P10① 挂 MCP，cache|uncached|output）：$TOKENS_P10_MCP；run=$RUN_P10_MCP"
    fi
fi
end

# ------------------------------------------ P10⑦ 真外网服务的工具被真调用一次
begin "P10⑦" "真外网 MCP（mcp.deepwiki.com）的工具被真调用一次"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要一次真实分析"
elif (( ! P7_READY )); then
    fail "前置没就绪（$P7_SETUP_NOTE），真外网判据验不了"
else
    # **这条与 P10① 的分工**：P10① 验平台的机制（挂与不挂有差别），用本地夹具，
    # 快、可控、可造故障；这一条验的是 F3「全外网」这个前提本身 —— 出网、DNS、TLS、
    # 真实延迟、真实的 MCP 实现而不是我们自己写的夹具。
    #
    # **它会因为对方下线而红，那是它的功能不是缺陷。** 红的时候先确认是不是对方挂了：
    # 装配探针连不上就记「未验」而不是「未过」，与「没触发到要测的场景」同一条规矩
    P10_REMOTE_NAME="p10-deepwiki-$P7_TAG"
    P10_REMOTE_ID="$(api "$JAR_P7_A" -X POST "$BASE_URL/api/mcp" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg n "$P10_REMOTE_NAME" '{
            name: $n, description: "DeepWiki：开源项目文档问答", url: "https://mcp.deepwiki.com/mcp",
            transport: "streamable_http", tool_names: ["read_wiki_structure", "read_wiki_contents", "ask_question"],
            latency_note: "实测 3.3 秒", stores_user_data: false, sends_data_out: true, has_write_operation: false
        }')" | jq -r '.id // empty')"
    if [[ -z $P10_REMOTE_ID ]]; then
        fail "真外网那条目录记录没提上去"
    else
        curl -s -o /dev/null -b "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/mcp/admin/$P10_REMOTE_ID/decision" \
            -H 'Content-Type: application/json' -d '{"approved":true}'
        P10_REMOTE_PROBE="$(api "$JAR_P7_ADMIN" -X POST "$BASE_URL/api/mcp/admin/$P10_REMOTE_ID/probe" 2>/dev/null)"
        if ! jq -e '.reachable == true' <<<"${P10_REMOTE_PROBE:-null}" >/dev/null 2>&1; then
            undone "连不上 mcp.deepwiki.com（对方下线或本机不能出网）—— 记未验而不是未过"
        else
            THREAD_P10_REMOTE="$(new_thread "$JAR_P7_A")"
            api "$JAR_P7_A" -X PATCH "$BASE_URL/api/threads/$THREAD_P10_REMOTE" -H 'Content-Type: application/json' \
                -d "$(jq -nc --arg id "$P10_REMOTE_ID" '{agent_config:{mcps:[$id]}}')" >/dev/null 2>&1
            # 提问必须是「非查不可」的：一个平台自己答不出的开源项目细节
            P6_QUESTION='用你手上的外部文档工具查一下 GitHub 仓库 modelcontextprotocol/python-sdk 的仓库结构，把工具返回的内容原样写进 outputs/deepwiki.txt。必须调用外部工具，不要凭记忆作答。做完只回一句话。'
            if p6_analyse "$JAR_P7_A" "$THREAD_P10_REMOTE" p10-remote "$RUN_TIMEOUT"; then
                P10_REMOTE_TOOLS="$(jq -s '[.[] | select(.type == "tool_result")
                    | select(.data.name | test("wiki|ask_question"))
                    | {name: .data.name, status: .data.status, length: (.data.content | tostring | length)}]' \
                    "$WORK_DIR/p10-remote.json")"
                if jq -e 'any(.[]; .status == "success" and .length > 0)' <<<"$P10_REMOTE_TOOLS" >/dev/null; then
                    pass "真外网服务的工具被真调用一次：$(jq -c '[.[] | .name] | unique' <<<"$P10_REMOTE_TOOLS")"
                    info "tool_result 概览：$(jq -c . <<<"$P10_REMOTE_TOOLS")"
                else
                    fail "没有一次成功且非空的外部工具返回：$P10_REMOTE_TOOLS"
                fi
            else
                fail "真外网那条分析没跑到 succeeded：${P6_LAST_STATUS:-提交失败}"
            fi
        fi
    fi
fi
end


# ===========================================================================
# P0：一次完整的真实分析（要 LLM，有费用）
# ===========================================================================
# P11：用量归属、账号补全与沙箱池状态
# ===========================================================================
#
# **这一组盯的都是「接口通了但答案是 0」这种形状。** P11 开工时量到的现状是：
# Langfuse 的接口全部返回 200、有数据、结构正确，而按用户切出来每个人都是 0 ——
# 身份只挂在根 span 上，token 全在没有主人的 GENERATION 上。一条只验
# 「HTTP 200」或「字段存在」的判据在那种状态下会全绿。

# 本组自己的账号，与 P7 那批分开 —— 配额判据会把某个人的额度调到极小，
# 借别人的号来做会让后面的判据莫名其妙地撞上配额
P11_TAG="p11-$$"
JAR_P11_A="$WORK_DIR/p11-a.jar"
JAR_P11_ADMIN="$WORK_DIR/p11-admin.jar"
P11_READY=0
P11_SETUP_NOTE=""
P11_USER_A=""

if P11_USER_A="$(open_session "$JAR_P11_A" teacher "$P11_TAG-a")" &&
    open_session "$JAR_P11_ADMIN" admin "$P11_TAG-admin" >/dev/null; then
    P11_READY=1
else
    P11_SETUP_NOTE="P11 的账号没开出来"
fi

# 向 Langfuse 直接查一个人的用量。**不经平台**：平台那条路正是要验的东西，
# 用它来验它自己等于什么都没验
p11_langfuse_generation_tokens() {
    local user_id="$1"
    in_api python -c "
import json, os, urllib.parse, urllib.request
from base64 import b64encode
from datetime import UTC, datetime, timedelta

base = os.environ.get('LANGFUSE_BASE_URL', '').rstrip('/')
public, secret = os.environ.get('LANGFUSE_PUBLIC_KEY', ''), os.environ.get('LANGFUSE_SECRET_KEY', '')
if not (base and public and secret):
    print('NOCONFIG')
    raise SystemExit(0)

query = {
    'view': 'observations',
    'metrics': [{'measure': 'totalTokens', 'aggregation': 'sum'}, {'measure': 'count', 'aggregation': 'count'}],
    'filters': [
        {'column': 'userId', 'operator': '=', 'value': '$user_id', 'type': 'string'},
        {'column': 'type', 'operator': '=', 'value': 'GENERATION', 'type': 'string'},
    ],
    'fromTimestamp': (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    'toTimestamp': datetime.now(UTC).isoformat(),
}
url = base + '/api/public/v2/metrics?' + urllib.parse.urlencode({'query': json.dumps(query)})
auth = b64encode(f'{public}:{secret}'.encode()).decode()
request = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read()).get('data', [])
except Exception as error:
    print(f'ERROR {error}')
    raise SystemExit(0)
row = rows[0] if rows else {}
print(f\"{int(row.get('sum_totalTokens') or 0)} {int(row.get('count_count') or 0)}\")
" 2>/dev/null | tr -d '\r'
}

# ------------------------------------------ P11① 身份真的落到了 GENERATION 上
begin "P11①" "一次真实分析之后，该用户名下的 GENERATION 有 token（不是 0）"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条要一次真实分析"
elif (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    P11_PROBE="$(p11_langfuse_generation_tokens "$P11_USER_A")"
    if [[ $P11_PROBE == NOCONFIG ]]; then
        undone "api 容器里没配 Langfuse，用量归属验不了"
    else
        THREAD_P11="$(new_thread "$JAR_P11_A")"
        # **提交响应里那个字段叫 id，不是 run_id。** 取错名字时 curl 照常收到 202、
        # jq 照常退 0，只是吐出 null —— 报出来的是「没提交上去」，而分析其实已经
        # 跑起来了，钱也花了。2026-08-16 实测被它骗过一轮，所以失败时连响应体一起打
        P11_SUBMIT="$(api "$JAR_P11_A" -X POST "$BASE_URL/api/threads/$THREAD_P11/runs" \
            -H 'Content-Type: application/json' \
            -d "$(jq -nc '{content:"用一句话说明什么是夏普比率，不要写代码、不要建文件。"}')")"
        RUN_P11="$(jq -r '.id // empty' <<<"${P11_SUBMIT:-null}")"
        if [[ -z $RUN_P11 ]]; then
            fail "P11 的分析没提交上去：${P11_SUBMIT:-（没有响应体）}"
        elif ! wait_status "$JAR_P11_A" "$RUN_P11" succeeded "$RUN_WINDOW"; then
            fail "P11 的分析没跑到 succeeded（当前 $(run_status "$JAR_P11_A" "$RUN_P11")）"
        else
            # Langfuse 的摄入是异步的，等它落库再查
            sleep 25
            read -r P11_TOKENS P11_COUNT <<<"$(p11_langfuse_generation_tokens "$P11_USER_A")"
            info "该用户名下 GENERATION：$P11_COUNT 条，合计 ${P11_TOKENS} token"
            # **三条缺一不可。** 只验「有 observation」的话，开工前那个状态
            # （只捞得到一条 CHAIN、token 为 0）也会绿
            if (( ${P11_COUNT:-0} <= 0 )); then
                fail "按 userId 一条 GENERATION 都捞不到 —— 身份还是没传到模型那一层"
            elif (( ${P11_TOKENS:-0} <= 0 )); then
                fail "GENERATION 捞得到但 token 是 0 —— 用量仍然归不到人头上"
            else
                pass "身份落到了 GENERATION 上：$P11_COUNT 条、${P11_TOKENS} token"
            fi
            # 平台自己那份账也要对得上（P11②）
            P11_RUNS_TOKENS="$(psql_query "SELECT COALESCE(SUM(tokens_uncached + tokens_output), 0)
                FROM runs WHERE id = '$RUN_P11';" | tr -d '[:space:]')"
        fi
    fi
fi
end

# ------------------------------------------ P11② 两份账目同量级
begin "P11②" "Langfuse 与 runs 表对同一次分析给出同量级的 token"

if [[ ${SKIP_LLM:-0} == 1 ]]; then
    undone "SKIP_LLM=1，这条依赖 P11① 那次真实分析"
elif [[ -z ${P11_TOKENS:-} || -z ${P11_RUNS_TOKENS:-} ]]; then
    undone "P11① 没跑成，没有可对账的数"
else
    # **验的是「两边都在记」与一个必然成立的不等式，不是数值接近。**
    #
    # 计划 §1.4 原本写的是「同量级」，2026-08-16 实测把它推翻了：同一次 run
    # 上 Langfuse 报 7412，runs 表报 145 —— 差 51 倍。原因是口径，不是缺陷：
    # runs 表记 `tokens_uncached + tokens_output`（**cache 命中一律不计**，
    # 见 quota/usage.py 开头那段），Langfuse 记的是 input 全量 + output，
    # 而长系统提示词的第二次调用几乎全是 cache 命中。
    #
    # 所以这里改验 `Langfuse >= runs 表`：这个不等式由两者的定义保证必然成立，
    # 一旦反过来就说明其中一边算错了。加上「两边都不是 0」，足以抓到
    # 「某一份账没在记」这个真正要防的故障
    info "Langfuse=${P11_TOKENS}  runs 表=${P11_RUNS_TOKENS}（口径不同，前者含 cache 命中）"
    if (( P11_RUNS_TOKENS <= 0 )); then
        fail "runs 表里这次 run 的 token 是 0 —— 配额闸门读的就是它"
    elif (( P11_TOKENS < P11_RUNS_TOKENS )); then
        fail "Langfuse 比 runs 表还少，而它多算了 cache 命中 —— 有一边算错了"
    else
        pass "两份账都在记，且大小关系与各自的口径相符"
    fi
fi
end

# ------------------------------------------ P11③ 平台的用量端点答得出这个人的用量
begin "P11③" "GET /api/usage/me 给出的是真数，且与 Langfuse 一致"

if (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    P11_MINE="$(api "$JAR_P11_A" "$BASE_URL/api/usage/me")"
    if ! jq -e '.available' <<<"${P11_MINE:-null}" >/dev/null 2>&1; then
        undone "api 侧没接 Langfuse（available=false），这条验不了"
    elif [[ ${SKIP_LLM:-0} == 1 ]]; then
        # 没跑过分析就没有可比的数，但端点本身通了
        pass "端点接上了账本（available=true）"
    else
        P11_MINE_TOKENS="$(jq -r '.tokens' <<<"$P11_MINE")"
        info "/api/usage/me 报 ${P11_MINE_TOKENS} token"
        if (( ${P11_MINE_TOKENS:-0} <= 0 )); then
            fail "端点报 0 —— 与 P11① 直接查 Langfuse 得到的 ${P11_TOKENS:-?} 对不上"
        else
            pass "端点报的是真数：${P11_MINE_TOKENS} token"
        fi
    fi
fi
end

# ------------------------------------------ P11④ 邮箱能当账号登录
begin "P11④" "同一个账号用用户名与邮箱各登一次，拿到同一个 user_id"

if (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    P11_MAIL_NAME="zuel-$P11_TAG-mail"
    P11_MAIL_ADDR="$P11_MAIL_NAME@verify.zuel.edu.cn"
    P11_MAIL_PASS="zuel-secret-$$"
    if ! make_user "$P11_MAIL_NAME" "$P11_MAIL_PASS" teacher; then
        fail "邮箱登录用的账号没造出来"
    else
        JAR_P11_BY_NAME="$WORK_DIR/p11-by-name.jar"
        JAR_P11_BY_MAIL="$WORK_DIR/p11-by-mail.jar"
        if ! login "$P11_MAIL_NAME" "$P11_MAIL_PASS" "$JAR_P11_BY_NAME"; then
            fail "用用户名登不进去"
        elif ! login "$P11_MAIL_ADDR" "$P11_MAIL_PASS" "$JAR_P11_BY_MAIL"; then
            fail "用邮箱登不进去 —— 第二把钥匙没生效"
        else
            P11_ID_BY_NAME="$(api "$JAR_P11_BY_NAME" "$BASE_URL/api/auth/me" | jq -r .id)"
            P11_ID_BY_MAIL="$(api "$JAR_P11_BY_MAIL" "$BASE_URL/api/auth/me" | jq -r .id)"
            if [[ -z $P11_ID_BY_MAIL || $P11_ID_BY_MAIL == null ]]; then
                fail "邮箱登进去了但拿不到身份"
            elif [[ $P11_ID_BY_NAME != "$P11_ID_BY_MAIL" ]]; then
                fail "两把钥匙开出了不同的人（$P11_ID_BY_NAME vs $P11_ID_BY_MAIL）"
            else
                pass "两种写法登的是同一个账号：$P11_ID_BY_MAIL"
            fi
        fi
    fi
fi
end

# ------------------------------------------ P11⑤ 配额改得动，且闸门真读它
begin "P11⑤" "后台把日配额调到极小之后，那个人提交分析被 QUOTA_EXCEEDED 挡下"

if (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    JAR_P11_Q="$WORK_DIR/p11-quota.jar"
    if ! P11_USER_Q="$(open_session "$JAR_P11_Q" teacher "$P11_TAG-q")"; then
        fail "配额判据的账号没开出来"
    else
        # **额度要设 0，不能设 1。** 闸门判的是「今天已经用掉的 >= 上限」，
        # 不是「这一次会不会超」—— 新账号已用 0，上限 1 时 `0 >= 1` 不成立，
        # 照样放行。那是设计如此（见 route/thread.py 的 _require_quota），
        # 不是漏洞。0 才是策略里写明的「一次都不许跑」那一档。
        # **第一版判据设的就是 1，于是这条红了一轮 —— 红的是判据不是产品。**
        P11_PATCH_CODE="$(code "$JAR_P11_ADMIN" -X PATCH "$BASE_URL/api/admin/users/$P11_USER_Q" \
            -H 'Content-Type: application/json' -d '{"quota_tokens_daily":0}')"
        P11_READBACK="$(api "$JAR_P11_ADMIN" "$BASE_URL/api/admin/users" |
            jq -r --arg id "$P11_USER_Q" '.[] | select(.id == $id) | .quota_tokens_daily')"
        if [[ $P11_PATCH_CODE != 200 ]]; then
            fail "改配额返回 $P11_PATCH_CODE"
        elif [[ $P11_READBACK != 0 ]]; then
            fail "配额没写进去（回读是 ${P11_READBACK:-空}）"
        else
            # **只验回读是代理指标。** 字段写进去了不等于闸门读的是它 ——
            # 必须一路验到提交被拒
            THREAD_P11_Q="$(new_thread "$JAR_P11_Q")"
            P11_Q_BODY="$(body "$JAR_P11_Q" -X POST "$BASE_URL/api/threads/$THREAD_P11_Q/runs" \
                -H 'Content-Type: application/json' -d '{"content":"随便算一下 1+1"}')"
            P11_Q_CODE="$(jq -r '.error.code // empty' <<<"${P11_Q_BODY:-null}")"
            info "配额 0 时提交返回的错误码：${P11_Q_CODE:-（没有错误，提交成功了）}"
            if [[ $P11_Q_CODE != QUOTA_EXCEEDED ]]; then
                fail "配额调到 0 之后仍然提交得上去 —— 那个字段没有被闸门读到"
            else
                # **还要证明这个 429 来自配额，不是来自别的什么。** 把配额撤回
                # 默认档（显式传 null），同一个账号同一条路径必须重新提交得上去 ——
                # 少了这一步，一个「无论如何都拒绝」的实现也能让上面那条绿
                code "$JAR_P11_ADMIN" -X PATCH "$BASE_URL/api/admin/users/$P11_USER_Q" \
                    -H 'Content-Type: application/json' -d '{"quota_tokens_daily":null}' >/dev/null
                P11_Q_AGAIN="$(body "$JAR_P11_Q" -X POST "$BASE_URL/api/threads/$THREAD_P11_Q/runs" \
                    -H 'Content-Type: application/json' -d '{"content":"随便算一下 1+1"}')"
                P11_Q_RUN="$(jq -r '.id // empty' <<<"${P11_Q_AGAIN:-null}")"
                # **收进来就立刻取消。** 这条判据验的是闸门放不放行，不是分析跑得对不对 ——
                # 让它跑完就是白花一次 DeepSeek 的钱，而这一条本该属于免费的那 42 条
                [[ -n $P11_Q_RUN ]] && api "$JAR_P11_Q" -X POST "$BASE_URL/api/runs/$P11_Q_RUN/cancel" >/dev/null 2>&1
                info "撤回配额后再提交：${P11_Q_RUN:+收下了 run $P11_Q_RUN（已取消）}${P11_Q_RUN:-$(jq -r '.error.code // "没有 run id"' <<<"${P11_Q_AGAIN:-null}")}"
                if [[ -n $P11_Q_RUN ]]; then
                    pass "配额闸门读的就是刚写进去那一列：设 0 挡下、撤回放行"
                else
                    fail "撤回配额之后仍然提交不上 —— 那个 429 未必来自配额"
                fi
            fi
        fi
    fi
fi
end

# ------------------------------------------ P11⑥ 沙箱池的数字来自 broker
begin "P11⑥" "占一个沙箱前后，/api/admin/system 的 in_use 差值为 1"

if (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    P11_SYS_BEFORE="$(api "$JAR_P11_ADMIN" "$BASE_URL/api/admin/system")"
    P11_CAP="$(jq -r '.capacity' <<<"${P11_SYS_BEFORE:-null}")"
    P11_IN_BEFORE="$(jq -r '.in_use' <<<"${P11_SYS_BEFORE:-null}")"
    if ! jq -e '.broker_reachable == true' <<<"${P11_SYS_BEFORE:-null}" >/dev/null 2>&1; then
        fail "api 说 broker 不可达 —— 这一页拿不到真数"
    elif (( ${P11_CAP:-0} <= 0 )); then
        fail "容量报 0，那不是一个真的池"
    else
        # 借一个沙箱：跑一次不花钱的文件工具就会让 broker 起容器
        THREAD_P11_S="$(new_thread "$JAR_P11_A")"
        api "$JAR_P11_A" -X POST "$BASE_URL/api/threads/$THREAD_P11_S/files/directory" \
            -H 'Content-Type: application/json' -d '{"path":"probe"}' >/dev/null 2>&1 || true
        in_broker python -c "
import httpx
httpx.post('http://127.0.0.1:8100/threads/$THREAD_P11_S/sandbox',
           json={'holder': 'p11-probe'}, timeout=120)" >/dev/null 2>&1 || true
        sleep 3
        P11_IN_AFTER="$(api "$JAR_P11_ADMIN" "$BASE_URL/api/admin/system" | jq -r '.in_use')"
        info "in_use：$P11_IN_BEFORE → $P11_IN_AFTER（容量 $P11_CAP）"
        if (( ${P11_IN_AFTER:-0} > ${P11_IN_BEFORE:-0} )); then
            pass "数字跟着真实占用动了，不是写死的"
        else
            undone "这一轮没能占上沙箱（$P11_IN_BEFORE → $P11_IN_AFTER），没触发到要测的场景"
        fi
    fi
fi
end

# ------------------------------------------ P11⑦ 场景与智能体在目录里分得开
begin "P11⑦" "广场只出现没挂子智能体的，挂了的只出现在场景库"

if (( ! P11_READY )); then
    fail "前置没就绪（$P11_SETUP_NOTE）"
else
    # 判据是「有没有挂子智能体」这个客观事实（P6-decision G2），
    # 因此直接问后端要两份列表，看有没有一条同时出现在该出现与不该出现的地方
    P11_AVAILABLE="$(api "$JAR_P11_A" "$BASE_URL/api/agents/available")"
    P11_CANDIDATES="$(api "$JAR_P11_A" "$BASE_URL/api/agents/subagent-candidates")"
    if [[ -z $P11_AVAILABLE || $P11_AVAILABLE == null ]]; then
        fail "取不到可用列表"
    else
        # 候选里但凡有一个自己挂着子智能体，「一层限制」与「场景不能当子智能体」
        # 就同时破了 —— 这条判据同时守着 P9③
        P11_BAD="$(jq '[.[] | select((.subagent_refs // []) | length > 0)] | length' <<<"${P11_CANDIDATES:-[]}")"
        info "候选 $(jq 'length' <<<"${P11_CANDIDATES:-[]}") 个，其中挂着子智能体的 $P11_BAD 个"
        if (( ${P11_BAD:-1} != 0 )); then
            fail "子智能体候选里混进了场景（$P11_BAD 个）"
        else
            pass "候选里全是没挂子智能体的，场景没混进来"
        fi
    fi
fi
end

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
    # 另外二十四条与它无关，没有理由陪着一起不跑
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
