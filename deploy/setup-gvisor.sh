#!/usr/bin/env bash
#
# 安装 gVisor（runsc）并注册为 Docker 运行时。
#
# 沙箱靠 runsc 拦住容器逃逸（ADR-0002）。开发机与目标服务器都要跑一次；
# 不装则 --runtime=runsc 直接起不来，加固清单里最重要的一条落空。
#
#   sudo bash deploy/setup-gvisor.sh
#
# 可重跑：已装且版本一致时跳过下载，daemon.json 重复注册也不会写坏。

set -euo pipefail

# gVisor 官方发布源。内网机器装不上时把这三个文件带进来放同目录即可
GVISOR_BASE_URL="${GVISOR_BASE_URL:-https://storage.googleapis.com/gvisor/releases/release/latest}"
INSTALL_DIR=/usr/local/bin
DOCKER_CONFIG=/etc/docker/daemon.json

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "需要 root：sudo bash $0"

arch="$(uname -m)"
[[ $arch == x86_64 || $arch == aarch64 ]] || die "gVisor 不支持该架构：$arch"

if command -v runsc >/dev/null 2>&1; then
    log "runsc 已存在，跳过下载：$(runsc --version | head -1)"
else
    log "下载 runsc（$arch）"
    workdir="$(mktemp -d)"
    # 无论成功失败都清掉临时目录，否则反复重跑会在 /tmp 里堆积几十 MB 的二进制
    trap 'rm -rf "$workdir"' EXIT

    for name in runsc containerd-shim-runsc-v1; do
        curl -fsSL -o "$workdir/$name" "$GVISOR_BASE_URL/$arch/$name"
        curl -fsSL -o "$workdir/$name.sha512" "$GVISOR_BASE_URL/$arch/$name.sha512"
    done

    # 校验和必须验：这两个二进制以 root 身份跑，且是沙箱隔离的根基
    (cd "$workdir" && sha512sum -c runsc.sha512 containerd-shim-runsc-v1.sha512)

    install -m 0755 "$workdir/runsc" "$workdir/containerd-shim-runsc-v1" "$INSTALL_DIR/"
    log "已安装到 $INSTALL_DIR"
fi

log "注册为 Docker 运行时"
# 本机 daemon.json 里已有 registry-mirrors 与 nvidia 运行时，
# runsc install 是就地合并而非覆盖，但先备份一份才敢让它动这个文件
if [[ -f $DOCKER_CONFIG ]]; then
    cp -a "$DOCKER_CONFIG" "$DOCKER_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
fi
runsc install

log "重启 Docker 使运行时生效"
systemctl restart docker

log "验证"
docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' | tr ' ' '\n' | grep -qx runsc \
    || die "Docker 未认到 runsc 运行时，检查 $DOCKER_CONFIG"

log "完成。运行时清单：$(docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}')"
