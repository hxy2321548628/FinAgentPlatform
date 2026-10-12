#!/usr/bin/env bash
set -euo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../app" && pwd)"
ENV=/etc/finagent/platform.env
[[ -f $ENV ]] || { echo "缺少 $ENV" >&2; exit 1; }
# .env 由 Compose/Python 解析，绝不作为 shell 脚本 source。
getenv() { python3 - "$ENV" "$1" <<'PY'
import sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
    key, sep, value = line.partition('=')
    if sep and key.strip() == sys.argv[2]:
        print(value.strip().strip('\"\''))
        break
PY
}
WORKSPACE="$(getenv SANDBOX_WORKSPACE_ROOT)"
if [[ ${1:-} != stop ]]; then
    [[ $(findmnt -no FSTYPE --target "$WORKSPACE") == xfs ]] || { echo 'workspace 必须是 XFS' >&2; exit 1; }
    xfs_quota -x -c state "$WORKSPACE" | grep -A3 -i 'project quota state' | grep -qi 'Enforcement: ON' || { echo '必须启用 XFS project quota' >&2; exit 1; }
    docker info --format '{{json .Runtimes}}' | grep -q '"runsc"' || { echo '缺少 runsc runtime' >&2; exit 1; }
fi
export SANDBOX_QUOTA_DEVICE
SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target "$WORKSPACE")"
[[ -b $SANDBOX_QUOTA_DEVICE ]] || { echo 'workspace 块设备不可用；先恢复挂载' >&2; exit 1; }
compose() { docker compose --project-name finagent-platform --env-file "$ENV" -f "$APP/docker/compose.yml" -f "$APP/docker/release.yml" "$@"; }
case ${1:-status} in
    start)
        memory="$(getenv SANDBOX_MEMORY_TOTAL)"
        [[ -n $memory ]] || memory="$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo) * 1024 * 6 / 10 ))"
        parent="$(getenv SANDBOX_CGROUP_PARENT)"
        systemctl set-property "${parent:-zuel-sandbox.slice}" MemoryMax="$memory"
        sandbox="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sandbox_image"])' "$APP/../release.json")"
        docker image inspect "$sandbox" >/dev/null
        compose up -d --no-build --pull never --force-recreate
        port="$(getenv HTTP_PORT)"
        url="http://127.0.0.1:${port:-80}"
        ready=false
        for ((i=0; i<90; i++)); do
            code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url/api/auth/me" || true)"
            if [[ $code == 200 || $code == 401 ]]; then ready=true; break; fi
            sleep 3
        done
        [[ $ready == true ]] || { compose ps; echo 'API 就绪检查失败，请查看容器日志' >&2; exit 1; }
        curl -fsS "$url/" | grep -q '<div id="root">' || { echo '前端首页检查失败' >&2; exit 1; }
        compose ps
        ;;
    stop) compose stop ;;
    status) compose ps ;;
    logs) shift; compose logs --tail 100 -f "$@" ;;
    *) echo '用法：control.sh start|stop|status|logs [服务名]' >&2; exit 2 ;;
esac
