#!/usr/bin/env bash
#
# 验证 P1 步骤零：gVisor 与 XFS project quota 都真的能用。
#
# 这两条是步骤一二验证标准成立的前提 —— 环境没补齐时，加固参数写得再对也验不出来。
#
#   sudo bash deploy/verify-env.sh
#
# 需要 root：xfs_quota -x 只对 root 开放。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOUNT_POINT="${SANDBOX_WORKSPACE_ROOT:-$REPO_ROOT/data/sandbox}"
SANDBOX_IMAGE="${SANDBOX_IMAGE:-zuel-sandbox:latest}"

# 只在验证期间借用的 project id，取一个业务侧 crc32 派生不会撞上的值
TEST_PROJID=4294967000
TEST_QUOTA_MB=8
TEST_WRITE_MB=16

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }
pass() { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m  ❌ %s\033[0m\n' "$*"; failed=1; }

[[ $EUID -eq 0 ]] || { printf '需要 root：sudo bash %s\n' "$0" >&2; exit 1; }
failed=0

log "① gVisor 下跑通 import pandas"
if ! docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' | tr ' ' '\n' | grep -qx runsc; then
    fail "Docker 未注册 runsc 运行时，先跑 deploy/setup-gvisor.sh"
elif ! docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1; then
    fail "沙箱镜像不存在：$SANDBOX_IMAGE，先 docker build -f deploy/sandbox.Dockerfile -t $SANDBOX_IMAGE ."
else
    # 验的是 runsc 的 syscall 覆盖够不够真实分析场景用 —— hello world 跑通不算数，
    # pandas 导入会摸到 mmap / futex / 一堆文件系统调用
    if output="$(docker run --rm --runtime=runsc --pull=never "$SANDBOX_IMAGE" \
        python -c 'import pandas, matplotlib; print(pandas.__version__)' 2>&1)"; then
        pass "runsc + pandas $output"
    else
        fail "runsc 下起容器或 import 失败：$output"
    fi
fi

log "② XFS project quota 在 ${TEST_QUOTA_MB}MB 处触发 ENOSPC"
if ! mountpoint -q "$MOUNT_POINT"; then
    fail "$MOUNT_POINT 未挂载，先跑 deploy/setup-xfs.sh"
elif [[ $(findmnt -no FSTYPE "$MOUNT_POINT") != xfs ]]; then
    fail "$MOUNT_POINT 不是 XFS"
else
    probe="$MOUNT_POINT/.quota-probe"
    rm -rf "$probe" && mkdir -p "$probe"
    xfs_quota -x -c "project -s -p $probe $TEST_PROJID" "$MOUNT_POINT" >/dev/null
    xfs_quota -x -c "limit -p bhard=${TEST_QUOTA_MB}m $TEST_PROJID" "$MOUNT_POINT" >/dev/null

    # 强制 C locale：下面按英文原文匹配 ENOSPC，中文环境下 dd 的报错会被翻译掉
    dd_output="$(LC_ALL=C dd if=/dev/zero of="$probe/fill" bs=1M count=$TEST_WRITE_MB 2>&1)"
    written_mb=$(( $(stat -c %s "$probe/fill" 2>/dev/null || echo 0) / 1024 / 1024 ))

    if grep -qi 'no space left' <<<"$dd_output" && (( written_mb <= TEST_QUOTA_MB )); then
        pass "写到 ${written_mb}MB 即 ENOSPC（限额 ${TEST_QUOTA_MB}MB）"
    else
        fail "未在限额处失败：实写 ${written_mb}MB，dd 输出：$(tr '\n' ' ' <<<"$dd_output")"
    fi

    # 探针留着会一直占着 projid 与目录，下次重跑读到的就不是干净状态
    rm -rf "$probe"
    xfs_quota -x -c "limit -p bhard=0 $TEST_PROJID" "$MOUNT_POINT" >/dev/null
fi

if (( failed )); then
    printf '\n\033[31m步骤零未通过。\033[0m\n'
    exit 1
fi
printf '\n\033[32m步骤零通过：gVisor 与 XFS project quota 均可用。\033[0m\n'
