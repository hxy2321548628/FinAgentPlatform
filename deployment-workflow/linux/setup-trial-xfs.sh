#!/usr/bin/env bash
# 仅供试运行：在现有文件系统创建 30 GiB XFS 文件，不改分区。
set -euo pipefail
IMAGE=/var/lib/finagent/sandbox.xfs.img
WORKSPACE=/var/lib/finagent/sandbox
SIZE=$((30 * 1024 * 1024 * 1024))
RESERVE=$((10 * 1024 * 1024 * 1024))
die() { echo "错误：$*" >&2; exit 1; }
[[ $EUID == 0 ]] || die '请使用 root 执行'
command -v mkfs.xfs >/dev/null || die '缺少 xfsprogs，请先执行 bootstrap.sh'
id finagent >/dev/null 2>&1 || die '缺少 finagent 用户，请先执行 bootstrap.sh'
mkdir -p "$WORKSPACE"
[[ ! -L $IMAGE && ! -L $WORKSPACE ]] || die '目标不能是符号链接'
if mountpoint -q "$WORKSPACE"; then
    [[ $(findmnt -no FSTYPE --target "$WORKSPACE") == xfs ]] || die '目录已有非 XFS 挂载'
    [[ $(findmnt -no SOURCE --target "$WORKSPACE") == /dev/loop* ]] || die '已有其他挂载，请由运维确认'
    device="$(findmnt -no SOURCE --target "$WORKSPACE")"
    [[ $(losetup -no BACK-FILE "$device") == "$IMAGE" ]] || die '已有其他镜像挂载'
else
    [[ -z $(find "$WORKSPACE" -mindepth 1 -maxdepth 1 -print -quit) ]] || die 'workspace 非空，拒绝覆盖挂载已有数据'
    if [[ -e $IMAGE ]]; then
        [[ -f $IMAGE && $(blkid -p -s TYPE -o value "$IMAGE") == xfs ]] || die '现有镜像不是 XFS，不自动重新格式化'
    else
        available="$(df -B1 --output=avail /var/lib/finagent | tail -1 | tr -d ' ')"
        (( available >= SIZE + RESERVE )) || die '至少需要 40 GiB 可用空间（30 GiB 镜像 + 10 GiB 余量）'
        # 预分配实际空间，避免稀疏文件后续写入挤满根分区。
        (umask 077; set -o noclobber; : > "$IMAGE")
        fallocate -l "$SIZE" "$IMAGE"
        mkfs.xfs "$IMAGE"
    fi
fi
entry="$IMAGE $WORKSPACE xfs loop,prjquota 0 0"
existing="$(awk -v target="$WORKSPACE" '$1 !~ /^#/ && $2 == target {print}' /etc/fstab)"
if [[ -n $existing ]]; then
    [[ $existing == "$entry" ]] || die 'fstab 已有不同配置，请先检查，不自动覆盖'
else
    cp -a /etc/fstab "/etc/fstab.finagent.$(date +%Y%m%d%H%M%S).bak"
    printf '\n%s\n' "$entry" >> /etc/fstab
fi
systemctl daemon-reload
mountpoint -q "$WORKSPACE" || mount "$WORKSPACE"
xfs_quota -x -c state "$WORKSPACE" | grep -A3 -i 'project quota state' | grep -qi 'Enforcement: ON' || die 'project quota 没有启用'
chown finagent:finagent "$WORKSPACE"
findmnt -no SOURCE,FSTYPE,OPTIONS --target "$WORKSPACE"
xfs_quota -x -c state "$WORKSPACE"
echo '试运行 workspace 已就绪，30 GiB 空间已预留；可以继续 install.sh。'
