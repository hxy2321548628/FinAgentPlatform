#!/usr/bin/env bash
# 参数是解压后的版本目录；先校验和构建，再停机激活。
set -euo pipefail
[[ $EUID == 0 ]] || { echo '请以 root 执行'; exit 1; }
RELEASE="$(realpath "${1:?用法：bash install.sh /root/解压后的版本目录}")"
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$RELEASE/release.json")"
[[ $VERSION =~ ^[0-9]{8}T[0-9]{12}Z$ ]] || { echo '非法版本号'; exit 1; }
python3 - "$RELEASE" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
for name, expected in json.loads((root / 'manifest.json').read_text()).items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SystemExit(f'非法或缺失文件：{name}')
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise SystemExit(f'文件校验失败：{name}')
print('发布内容 SHA256 校验通过')
PY
ENV=/etc/finagent/platform.env
if [[ ! -f $ENV ]]; then
    install -d -m 700 /etc/finagent
    cp "$RELEASE/app/.env.example" "$ENV"
    python3 - "$ENV" <<'PY'
import pwd, secrets, sys
from pathlib import Path
p = Path(sys.argv[1]); user = pwd.getpwnam('finagent')
values = {'POSTGRES_DATA_DIR':'/var/lib/finagent/postgres',
          'REDIS_DATA_DIR':'/var/lib/finagent/redis',
          'SKILL_ROOT':'/var/lib/finagent/skill',
          'SANDBOX_WORKSPACE_ROOT':'/var/lib/finagent/sandbox',
          'SANDBOX_USER':f'{user.pw_uid}:{user.pw_gid}',
          'POSTGRES_PASSWORD':secrets.token_urlsafe(32),
          'MCP_CREDENTIALS':'{}', 'SANDBOX_QUOTA_DEVICE':''}
p.write_text('\n'.join(key+'='+values[key] if (key:=line.partition('=')[0]) in values
                       else line for line in p.read_text().splitlines())+'\n')
PY
    chmod 600 "$ENV"
    echo "已生成 $ENV；请填写 DEEPSEEK_API_KEY、ADMIN_PASSWORD，再重跑安装命令。"
    exit 1
fi
python3 - "$ENV" <<'PY'
import sys
from pathlib import Path
values = dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines()
              if '=' in line and not line.lstrip().startswith('#'))
for key in ('DEEPSEEK_API_KEY','ADMIN_PASSWORD','POSTGRES_PASSWORD'):
    value = values.get(key,'').strip().strip('\"\'')
    if not value or 'xxxxxxxx' in value or value in ('change-me-before-deploy','zuel'):
        raise SystemExit(f'请配置真实的 {key}')
if values.get('SANDBOX_WORKSPACE_ROOT') != '/var/lib/finagent/sandbox':
    raise SystemExit('本工作流固定 workspace 为 /var/lib/finagent/sandbox；请保持配置与挂载一致')
PY
findmnt -no FSTYPE --target /var/lib/finagent/sandbox | grep -qx xfs
xfs_quota -x -c state /var/lib/finagent/sandbox | grep -A3 -i 'project quota state' | grep -qi 'Enforcement: ON'
chown finagent:finagent /var/lib/finagent/sandbox
TARGET="/opt/finagent/releases/$VERSION"
mkdir -p /opt/finagent/releases
if [[ -e $TARGET ]]; then
    cmp "$RELEASE/manifest.json" "$TARGET/manifest.json" || { echo 'release content mismatch'; exit 1; }
else
    cp -a "$RELEASE" "$TARGET"
fi
ln -sfn "$ENV" "$TARGET/app/.env"
ln -sfn "$ENV" "$TARGET/app/docker/.env"
export SANDBOX_QUOTA_DEVICE
SANDBOX_QUOTA_DEVICE="$(findmnt -no SOURCE --target /var/lib/finagent/sandbox)"
compose() { docker compose --project-name finagent-platform --env-file "$ENV" -f "$TARGET/app/docker/compose.yml" -f "$TARGET/app/docker/release.yml" "$@"; }
if [[ -f $TARGET/images.tar ]]; then
    docker load -i "$TARGET/images.tar"
else
    compose build
    compose pull --policy missing postgres redis
    sandbox="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sandbox_image"])' "$TARGET/release.json")"
    docker build -t "$sandbox" -f "$TARGET/app/docker/sandbox.Dockerfile" "$TARGET/app"
fi
compose config --quiet
# 迁移前必须保存数据库；不输出数据库密码。
if [[ -L /opt/finagent/current && $(readlink -f /opt/finagent/current) != "$TARGET" ]]; then
    previous="$(readlink -f /opt/finagent/current)"
    systemctl stop FinAgentPlatform.service
    oldapp="$previous/app"
    docker compose --project-name finagent-platform --env-file "$ENV" -f "$oldapp/docker/compose.yml" -f "$oldapp/docker/release.yml" up -d --no-build --pull never postgres
    backup="/var/backups/finagent/pre-$VERSION.sql"
    umask 077
    docker compose --project-name finagent-platform --env-file "$ENV" -f "$oldapp/docker/compose.yml" -f "$oldapp/docker/release.yml" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$backup"
    [[ -s $backup ]] || { echo '数据库备份失败，保持旧版本'; exit 1; }
    ln -sfn "$previous" /opt/finagent/previous
fi
ln -sfn "$TARGET" /opt/finagent/current
install -m 644 "$TARGET/linux/FinAgentPlatform.service" /etc/systemd/system/FinAgentPlatform.service
systemctl daemon-reload
systemctl enable FinAgentPlatform.service
if ! systemctl start FinAgentPlatform.service; then
    echo '新版本启动失败。查看 journalctl 和容器日志；数据库可能已迁移，禁止自动回滚数据库。' >&2
    exit 1
fi
echo "安装成功：$VERSION；使用 systemctl start|stop|restart FinAgentPlatform.service"
