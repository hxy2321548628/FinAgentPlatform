#!/usr/bin/env bash
# 从 origin/main 打包并在当前 Linux 主机安装；部署工具始终来自 CICD。
set -euo pipefail
[[ $EUID == 0 ]] || { echo '服务器部署请使用 root 执行'; exit 1; }
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$TOOLS/.." && pwd)"
TRIAL=false
PRELOAD=false
for arg in "$@"; do
    case "$arg" in
        --trial-xfs) TRIAL=true ;;
        --ecr) PRELOAD=true ;;
        *) echo '用法：deploy-main.sh [--trial-xfs] [--ecr]'; exit 2 ;;
    esac
done
command -v python3 >/dev/null || { echo '先安装 python3：apt-get install -y python3'; exit 1; }
# 只更新远程 main 引用，保留 CICD 当前工作目录。
git -C "$REPO" fetch origin main:refs/remotes/origin/main
stage="$(mktemp -d /tmp/finagent-main.XXXXXXXX)"
trap 'rm -rf "$stage"' EXIT
python3 "$TOOLS/package.py" --ref origin/main --result-file "$stage/result.json"
archive="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["archive"])' "$stage/result.json")"
version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$stage/result.json")"
tar -xzf "$archive" -C "$stage"
release="$stage/$version"
bash "$release/linux/bootstrap.sh"
if [[ $TRIAL == true ]]; then
    bash "$release/linux/setup-trial-xfs.sh"
fi
if [[ $PRELOAD == true ]]; then
    bash "$release/linux/preload-ecr.sh"
fi
bash "$release/linux/install.sh" "$release"
