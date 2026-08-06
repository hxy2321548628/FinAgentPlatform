#!/usr/bin/env bash
#
# 把 workspace 根目录挂到一个带 prjquota 的 XFS 文件系统上。
#
# ADR-0015 的 5GB / thread 配额靠 XFS project quota 实现，而 project quota 只在
# 挂载时带 prjquota 才可用。开发机的根分区是 ext4，因此这里用 loop 设备造一个
# XFS 镜像顶上。**服务器上不要用本脚本** —— 那里应该是真实分区加挂载选项，
# loop 与真实分区的配额语义一致但 IO 路径不同（P1 计划 §3 已登记为残留风险）。
#
#   sudo bash deploy/setup-xfs.sh
#
# 可重跑：镜像已存在则不重造（不会丢数据），已挂载则跳过挂载。
# 重启后文件系统不会自动挂回来，再跑一次本脚本即可。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOUNT_POINT="${SANDBOX_WORKSPACE_ROOT:-$REPO_ROOT/data/sandbox}"
IMAGE_PATH="${XFS_IMAGE_PATH:-$REPO_ROOT/data/sandbox.xfs.img}"
# 单 thread 配额 5GB，加上破坏性测试要真写满一次，容量取 30G 才有余量
IMAGE_SIZE="${XFS_IMAGE_SIZE:-30G}"

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "需要 root：sudo bash $0"
[[ -n ${SUDO_UID:-} && -n ${SUDO_GID:-} ]] || die "请用 sudo 执行，脚本要把挂载点属主还给你"

if ! command -v mkfs.xfs >/dev/null 2>&1; then
    log "安装 xfsprogs"
    apt-get update -qq
    apt-get install -y -qq xfsprogs
fi

if ! grep -qw xfs /proc/filesystems; then
    log "加载 xfs 内核模块"
    modprobe xfs || die "内核不支持 xfs，无法继续"
fi

if [[ -f $IMAGE_PATH ]]; then
    log "镜像已存在，保留现有数据：$IMAGE_PATH"
else
    log "创建 $IMAGE_SIZE 稀疏镜像：$IMAGE_PATH"
    mkdir -p "$(dirname "$IMAGE_PATH")"
    # 这层目录（默认是仓库内的 data/）还会放别的运行时数据，留成 root 属主的话
    # 平台进程往里写第二个东西时才会发现权限不对
    chown "$SUDO_UID:$SUDO_GID" "$(dirname "$IMAGE_PATH")"
    # 稀疏分配：镜像声明 30G 但只按实际写入占用宿主磁盘
    truncate -s "$IMAGE_SIZE" "$IMAGE_PATH"
    mkfs.xfs -q "$IMAGE_PATH"
fi

mkdir -p "$MOUNT_POINT"

if mountpoint -q "$MOUNT_POINT"; then
    log "已挂载，跳过：$MOUNT_POINT"
else
    log "挂载到 $MOUNT_POINT"
    mount -o loop,prjquota "$IMAGE_PATH" "$MOUNT_POINT"
    # 挂载后属主是 root，而平台进程以普通用户跑，不改属主就一个 workspace 都建不出来
    chown "$SUDO_UID:$SUDO_GID" "$MOUNT_POINT"
fi

log "放行 xfs_quota 的免密调用"
# 平台进程以普通用户跑，而 xfs_quota 要 CAP_SYS_ADMIN —— 不放行的话，
# 每建一个会话都会卡在配额那一步。**只放行这一个命令**，不是给整个 sudo。
# 生产上 broker 容器内以 root 跑，不需要这条规则。
SUDOERS_FILE=/etc/sudoers.d/zuel-xfs-quota
QUOTA_BIN="$(command -v xfs_quota)"
printf '%s ALL=(root) NOPASSWD: %s\n' "$(id -un "$SUDO_UID")" "$QUOTA_BIN" > "$SUDOERS_FILE.tmp"
chmod 0440 "$SUDOERS_FILE.tmp"
# 先校验再就位：sudoers 写坏会让整台机器的 sudo 全部失效
if visudo -cqf "$SUDOERS_FILE.tmp"; then
    mv "$SUDOERS_FILE.tmp" "$SUDOERS_FILE"
else
    rm -f "$SUDOERS_FILE.tmp"
    die "生成的 sudoers 规则语法不合法，已丢弃"
fi

log "验证 project quota 已启用"
findmnt -no FSTYPE "$MOUNT_POINT" | grep -qx xfs || die "$MOUNT_POINT 不是 XFS"
xfs_quota -x -c state "$MOUNT_POINT" | grep -A2 -i 'project quota state' | grep -qi 'Enforcement: ON' \
    || die "project quota 未启用，检查挂载选项是否带 prjquota"

log "完成。$MOUNT_POINT 已是 XFS + prjquota，且已放行免密 xfs_quota"
log "平台以普通用户跑时，.env 里需设 SANDBOX_QUOTA_COMMAND='sudo xfs_quota'"
log "重启后需再跑一次本脚本；要开机自动挂载，往 /etc/fstab 加："
printf '    %s %s xfs loop,prjquota 0 0\n' "$IMAGE_PATH" "$MOUNT_POINT"
