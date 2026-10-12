#!/usr/bin/env bash
# Docker 与 gVisor 宿主机初始化；可能重启 Docker，应在维护窗口执行。
set -euo pipefail
[[ $EUID == 0 ]] || { echo '请以 root 执行'; exit 1; }
apt-get update
apt-get install -y ca-certificates curl xfsprogs python3
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    [[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo '此初始化脚本仅支持 Ubuntu 24.04'; exit 1; }
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/finagent-docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version
systemctl enable --now docker
if ! docker info --format '{{json .Runtimes}}' | grep -q '"runsc"'; then
    bash "$(dirname "$0")/../app/script/setup-gvisor.sh"
fi
id finagent >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin finagent
mkdir -p /etc/finagent /opt/finagent/releases /var/lib/finagent/{postgres,redis,skill,sandbox} /var/backups/finagent
chmod 700 /etc/finagent /var/backups/finagent
chown finagent:finagent /var/lib/finagent/skill
printf '基础软件准备完成。下一步配置 XFS 挂载和 /etc/finagent/platform.env。\n'
