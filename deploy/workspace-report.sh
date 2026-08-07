#!/usr/bin/env bash
#
# workspace 占用体检：磁盘水位 + 异常大的会话。
#
#   bash deploy/workspace-report.sh                    # 看一眼
#   WARN_PERCENT=70 bash deploy/workspace-report.sh    # 收紧阈值
#
# 超过水位时**退出码为 1**，方便挂到 cron 上让它自己叫：
#
#   0 7 * * * cd /path/to/zuel-platform && bash deploy/workspace-report.sh || mail -s ...
#
# **本期不回收 workspace**（决策见架构 §6.5）：实测典型会话只有几百 KB，
# 而删掉就再也拉不回来 —— 归档删除要等 MinIO 到位（P2）。在那之前，
# 唯一该做的是知道占用在往哪儿走，以及是哪几个会话在推着它走。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$REPO_ROOT/data/sandbox}"

# 超过这个百分比就判定要处理。留足余量：真到 90% 时沙箱已经在写失败了
WARN_PERCENT="${WARN_PERCENT:-80}"
# 单个会话超过这个 MB 数就点名。每会话配额 5GB，到 1GB 就该看看它在干什么
LARGE_MB="${LARGE_MB:-1024}"
# 列出最大的几个
TOP_N="${TOP_N:-10}"

[[ -d $WORKSPACE_ROOT ]] || { echo "workspace 根不存在：$WORKSPACE_ROOT" >&2; exit 1; }

printf '\033[36m━━ workspace 占用体检  %s\033[0m\n' "$(date '+%Y-%m-%d %H:%M')"
printf '   根目录 %s\n\n' "$WORKSPACE_ROOT"

df -h --output=source,size,used,avail,pcent "$WORKSPACE_ROOT" | sed 's/^/   /'
USED_PERCENT=$(df --output=pcent "$WORKSPACE_ROOT" | tail -1 | tr -dc '0-9')
THREAD_COUNT=$(find "$WORKSPACE_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)
printf '\n   会话目录 %s 个\n' "$THREAD_COUNT"

if (( THREAD_COUNT > 0 )); then
    printf '\n   最大的 %s 个（大小 ｜ 最后修改 ｜ 会话）：\n' "$TOP_N"
    # -d1 只算每个会话一行，别把 outputs/ 也铺开
    du -m -d1 "$WORKSPACE_ROOT" 2>/dev/null | grep -v "^[0-9]*	${WORKSPACE_ROOT}$" |
        sort -rn | head -n "$TOP_N" |
        while IFS=$'\t' read -r size path; do
            printf '     %6s MB  %s  %s\n' "$size" "$(date -r "$path" '+%m-%d %H:%M')" "$(basename "$path")"
        done

    LARGE=$(du -m -d1 "$WORKSPACE_ROOT" 2>/dev/null | grep -v "^[0-9]*	${WORKSPACE_ROOT}$" |
        awk -v limit="$LARGE_MB" '$1 >= limit' | wc -l)
    if (( LARGE > 0 )); then
        printf '\n\033[33m   ⚠️  有 %s 个会话超过 %s MB —— 墙是被这类会话推着走的，不是被数量推的\033[0m\n' \
            "$LARGE" "$LARGE_MB"
    fi
fi

printf '\n'
if (( USED_PERCENT >= WARN_PERCENT )); then
    printf '\033[31m   ❌ 已用 %s%%，超过 %s%% 阈值。本期没有回收机制，处置只有三条：\033[0m\n' \
        "$USED_PERCENT" "$WARN_PERCENT"
    printf '      1. 上面点名的大会话，确认无用后手工删 \n'
    printf '      2. 扩容承载 workspace 的分区\n'
    printf '      3. 若这已成常态，说明 MinIO 归档（P2）该提前排\n'
    exit 1
fi
printf '\033[32m   ✅ 已用 %s%%，低于 %s%% 阈值\033[0m\n' "$USED_PERCENT" "$WARN_PERCENT"
