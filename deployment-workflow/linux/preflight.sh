#!/usr/bin/env bash
# 只读检查，不安装软件、不修改磁盘、不输出凭据。
set -u
printf '\n=== 系统与磁盘 ===\n'
uname -a
free -h
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
findmnt -t xfs -o TARGET,SOURCE,OPTIONS
printf '\n=== Docker / gVisor ===\n'
command -v docker >/dev/null && docker version
command -v docker >/dev/null && docker compose version
command -v docker >/dev/null && docker info --format '{{json .Runtimes}}'
command -v runsc >/dev/null && runsc --version
printf '\n=== 常用端口 ===\n'
ss -lnt | awk 'NR==1 || /:(80|443|5433|6379|8100) /'
printf '\n=== 出网检查（HTTP 状态；401/403 也说明能建立连接）===\n'
for url in https://registry-1.docker.io/v2/ https://ghcr.io/v2/ https://pypi.org/simple/ https://registry.npmjs.org/ https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc.sha512 https://api.deepseek.com; do
    printf '%s ' "$url"
    curl -I -sS --connect-timeout 5 --max-time 10 -o /dev/null -w '%{http_code}\n' "$url" || true
done
