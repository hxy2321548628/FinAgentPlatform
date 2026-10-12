#!/usr/bin/env bash
# 仅在确认数据库结构兼容时执行代码回滚。
set -euo pipefail
[[ $EUID == 0 && ${1:-} == --schema-compatible ]] || { echo '用法：bash rollback.sh --schema-compatible（先确认迁移向后兼容）'; exit 1; }
previous="$(readlink -f /opt/finagent/previous)"
[[ $previous == /opt/finagent/releases/* && -f $previous/release.json ]] || { echo '没有可用的上一版本'; exit 1; }
systemctl stop FinAgentPlatform.service
ln -sfn "$previous" /opt/finagent/current
systemctl start FinAgentPlatform.service
