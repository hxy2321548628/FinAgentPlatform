#!/usr/bin/env bash
#
# 四条破坏性测试：LLM 生成的代码失控时，宿主机不受影响。
#
#   sudo bash deploy/test/hostile.sh
#
# 需要 root：设 project quota 要 CAP_SYS_ADMIN。
#
# **验的是「宿主机没事」，不是「沙箱里的命令失败了」** —— 后者太容易蒙对：
# 命令因为任何理由报错都会让一个只看退出码的检查通过。因此每条都先记基线再跑，
# 跑完比对宿主机的可用内存、可用磁盘与进程数。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$REPO_ROOT/data/sandbox}"
SANDBOX_IMAGE="${SANDBOX_IMAGE:-zuel-sandbox:latest}"

DISK_QUOTA="${SANDBOX_DISK_QUOTA:-5g}"
TMP_SIZE="${SANDBOX_TMP_SIZE:-512m}"
PIDS_LIMIT="${SANDBOX_PIDS_LIMIT:-128}"

# 宿主机指标的容忍带。跑测试期间机器上还有别的东西在动，要求分毫不差只会得到假失败
MEMORY_TOLERANCE_MB=2048
DISK_TOLERANCE_MB=2048
PROCESS_TOLERANCE=100

log() { printf '\n\033[36m━━ %s\033[0m\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=1; }
info() { printf '     %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "需要 root：sudo bash $0" >&2; exit 1; }
command -v xfs_quota >/dev/null || { echo "缺 xfs_quota，先跑 deploy/setup-xfs.sh" >&2; exit 1; }
docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1 || { echo "缺镜像 $SANDBOX_IMAGE" >&2; exit 1; }

failed=0
CONTAINER=""
WORKSPACE=""

free_memory_mb() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }
free_disk_mb() { df -m --output=avail "$WORKSPACE_ROOT" | tail -1 | tr -d ' '; }
process_count() { ps -e --no-headers | wc -l; }

# 每条测试用一个自己的 workspace，全部登记下来一起清 —— 只留一个变量的话，
# start_sandbox 每次覆盖它，最后只有最后一条的目录被清掉，前面的连同几 GB 数据留在盘上
WORKSPACE_PREFIX=hostile

cleanup() {
    [[ -n $CONTAINER ]] && docker rm -f "$CONTAINER" >/dev/null 2>&1
    rm -rf "${WORKSPACE_ROOT:?}/$WORKSPACE_PREFIX"-*
    fstrim "$WORKSPACE_ROOT" >/dev/null 2>&1
    return 0
}
trap cleanup EXIT

# 起一个与平台完全同款的沙箱：加固参数照 app/sandbox/container.py 的 Hardening
start_sandbox() {
    local thread_id="$1"
    WORKSPACE="$WORKSPACE_ROOT/$WORKSPACE_PREFIX-$thread_id"
    rm -rf "$WORKSPACE"; mkdir -p "$WORKSPACE"
    # 本脚本以 root 跑，建出来的目录是 root 属主，而沙箱以调用者的 uid 跑 ——
    # 不改属主，容器里 dd 会得到 Permission denied，看起来像配额生效实际是没权限。
    # 平台自己跑时目录属主本就是平台用户，这是本脚本独有的问题
    chown "$SUDO_UID:$SUDO_GID" "$WORKSPACE"

    # 配额照 app/sandbox/quota.py 的派生方式算，保证测的是平台真正会用的那个 id
    local projid
    projid=$(python3 -c "import zlib,sys; print(zlib.crc32(sys.argv[1].encode()) % 0x7FFFFFFF + 1)" "$thread_id")
    xfs_quota -x -c "project -s -p $WORKSPACE $projid" "$WORKSPACE_ROOT" >/dev/null
    xfs_quota -x -c "limit -p bhard=$DISK_QUOTA $projid" "$WORKSPACE_ROOT" >/dev/null

    CONTAINER=$(docker run -d --rm --pull=never \
        --runtime=runsc --network=none --read-only \
        --tmpfs "/tmp:rw,noexec,nosuid,size=$TMP_SIZE" \
        --cap-drop=ALL --security-opt=no-new-privileges \
        --memory=2g --cpus=1 --pids-limit="$PIDS_LIMIT" \
        --user "$SUDO_UID:$SUDO_GID" \
        -v "$WORKSPACE:/workspace" -w /workspace -e HOME=/tmp \
        "$SANDBOX_IMAGE" sleep infinity)
}

sandbox_exec() { timeout 180 docker exec "$CONTAINER" bash -o pipefail -c "$1" 2>&1 | head -c 4000; }

log "记录宿主机基线"
BASE_MEMORY=$(free_memory_mb); BASE_DISK=$(free_disk_mb); BASE_PROCESS=$(process_count)
info "可用内存 ${BASE_MEMORY}MB ｜ ${WORKSPACE_ROOT} 可用 ${BASE_DISK}MB ｜ 进程数 ${BASE_PROCESS}"

# ------------------------------------------------------------------ ① 死循环
log "① 死循环：被 --cpus=1 限住，只烧掉自己那一份"
start_sandbox busyloop
docker exec -d "$CONTAINER" bash -c 'python -c "
while True: pass
"'
sleep 6
CPU=$(docker stats --no-stream --format '{{.CPUPerc}}' "$CONTAINER" | tr -d '%')
# docker stats 里 100% 就是一个核；宿主机 16 核跑满会是 1600%
if awk "BEGIN{exit !($CPU < 150)}"; then
    pass "CPU 占用 ${CPU}%（上限一个核）"
else
    fail "CPU 占用 ${CPU}%，超出了一个核"
fi
docker rm -f "$CONTAINER" >/dev/null; CONTAINER=""

# ------------------------------------------------------------------ ② fork 炸弹
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
NOW_PROCESS=$(process_count)
if (( NOW_PROCESS < BASE_PROCESS + PROCESS_TOLERANCE )); then
    pass "宿主机进程数 ${BASE_PROCESS} → ${NOW_PROCESS}，未被拖垮"
else
    fail "宿主机进程数 ${BASE_PROCESS} → ${NOW_PROCESS}，炸弹漏到宿主机了"
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1; CONTAINER=""

# ------------------------------------------------------------------ ③ 写满 workspace
log "③ 写满 /workspace：在 $DISK_QUOTA 处得到 ENOSPC，宿主机磁盘不见少"
start_sandbox disk
# dd 的四行输出里，「No space left on device」在**第一行**，后三行是统计。
# 这里不要再 tail —— 砍掉第一行就等于把唯一的判定依据丢了，配额明明生效也会判失败
OUT=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/workspace/fill bs=1M count=20000 2>&1')
WRITTEN_MB=$(( $(stat -c %s "$WORKSPACE/fill" 2>/dev/null || echo 0) / 1024 / 1024 ))
if grep -qi 'no space left' <<<"$OUT"; then
    pass "在 ${WRITTEN_MB}MB 处得到 ENOSPC（限额 $DISK_QUOTA）"
else
    fail "没在限额处停下：实写 ${WRITTEN_MB}MB ｜ $(tr '\n' ' ' <<<"$OUT")"
fi

# 验收标准③：配额对**文件工具写入**同样生效。文件工具是宿主侧直接写、不进容器的，
# 绕开了一切容器级限制 —— 这条能成立全靠 project quota 是对目录而非对容器生效
rm -f "$WORKSPACE/fill"
HOST_OUT=$(LC_ALL=C dd if=/dev/zero of="$WORKSPACE/host-written" bs=1M count=20000 2>&1)
if grep -qi 'no space left' <<<"$HOST_OUT"; then
    pass "宿主侧直接写（文件工具走的这条路）同样被挡住"
else
    fail "宿主侧直接写没被挡住 ｜ $(tr '\n' ' ' <<<"$HOST_OUT")"
fi
rm -f "$WORKSPACE/host-written"

# 验收标准④：容器销毁重建后配额仍在
docker rm -f "$CONTAINER" >/dev/null
# 重建时不能走 start_sandbox：它会清掉 workspace 并重设配额，那样验的就成了
# 「刚设的配额生效吗」，而不是「配额熬过了容器的销毁重建吗」
CONTAINER=$(docker run -d --rm --pull=never --runtime=runsc --network=none \
    --user "$SUDO_UID:$SUDO_GID" -v "$WORKSPACE:/workspace" -w /workspace \
    "$SANDBOX_IMAGE" sleep infinity)
AGAIN=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/workspace/again bs=1M count=20000 2>&1')
if grep -qi 'no space left' <<<"$AGAIN"; then
    pass "容器销毁重建后配额仍在"
else
    fail "重建后配额没了 ｜ $(tr '\n' ' ' <<<"$AGAIN")"
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1; CONTAINER=""

# 先把测试自己写下的 5GB 清掉再量。不清就是拿「测试留下的占用」去指控平台漏磁盘，
# 量出来的差值恰好等于配额本身
rm -rf "$WORKSPACE"
# loop 镜像是稀疏文件，XFS 里删了文件不会自动把洞还给宿主的 ext4。
# 开发机特有，服务器上是真实分区没这一步
fstrim "$WORKSPACE_ROOT" >/dev/null 2>&1 || true

NOW_DISK=$(free_disk_mb)
if (( NOW_DISK > BASE_DISK - DISK_TOLERANCE_MB )); then
    pass "宿主机可用磁盘 ${BASE_DISK}MB → ${NOW_DISK}MB，回到基线"
else
    fail "宿主机可用磁盘 ${BASE_DISK}MB → ${NOW_DISK}MB，掉得太多"
fi

# ------------------------------------------------------------------ ④ 写满 /tmp
log "④ 写满 /tmp：在 $TMP_SIZE 处得到 ENOSPC，宿主机内存不见少"
start_sandbox tmp
OUT=$(sandbox_exec 'LC_ALL=C dd if=/dev/zero of=/tmp/fill bs=1M count=4096 2>&1')
if grep -qi 'no space left' <<<"$OUT"; then
    pass "在 $TMP_SIZE 处得到 ENOSPC（tmpfs 吃的是宿主机内存）"
else
    fail "tmpfs 没在限额处停下 ｜ $(tr '\n' ' ' <<<"$OUT")"
fi
docker rm -f "$CONTAINER" >/dev/null; CONTAINER=""
sleep 3

NOW_MEMORY=$(free_memory_mb)
if (( NOW_MEMORY > BASE_MEMORY - MEMORY_TOLERANCE_MB )); then
    pass "宿主机可用内存 ${BASE_MEMORY}MB → ${NOW_MEMORY}MB，回到基线"
else
    fail "宿主机可用内存 ${BASE_MEMORY}MB → ${NOW_MEMORY}MB，掉得太多"
fi

log "结果"
if (( failed )); then
    printf '\033[31m破坏性测试未全过。\033[0m\n'
    exit 1
fi
printf '\033[32m四条破坏性测试全过：宿主机的内存、磁盘与进程数都回到了基线。\033[0m\n'
