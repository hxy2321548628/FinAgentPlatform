#!/usr/bin/env bash
#
# 孤儿 workspace 目录的清理：磁盘上有，库里查无此人。
#
#   bash script/reap-orphan-workspace.sh              # 只报告，不删（默认）
#   bash script/reap-orphan-workspace.sh --delete     # 真删
#
# **与 workspace-report.sh 不是一回事**：那个体检的是「占用在往哪儿走」，管的是
# 有主的会话，而架构 §6.5 明确本期不回收它们 —— 删掉教师就再也拉不回来。
# 这里删的是**没有任何会话指向的目录**：前端列不出来、教师点不开、broker 也不会再碰。
# 它们的来源是测试与验收脚本（那些直接建 workspace，不走建会话的接口），
# 以及销毁失败留下的残骸（见 api/route/thread.py 里 204 那段说明）。
#
# **判据是「库里没有」而不是「目录是空的」**：空目录里也可能是一个刚建好还没写东西的
# 真会话，而有内容的孤儿反倒是测试留下的大头。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="${SANDBOX_WORKSPACE_ROOT:-$REPO_ROOT/data/sandbox}"
COMPOSE_FILE="$REPO_ROOT/docker/compose.yml"

# 目录至少这么老才考虑删。**建会话是「表先于目录」**，理论上目录在表就在，
# 但那两步之间有一个瞬间；这道年龄线让正在创建中的会话不会被误判成孤儿
MIN_AGE_HOUR="${MIN_AGE_HOUR:-24}"

DELETE=""
[[ ${1:-} == "--delete" ]] && DELETE=1

log() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -d $WORKSPACE_ROOT ]] || die "workspace 根不存在：$WORKSPACE_ROOT"

DB_USER="$(sed -n 's/^POSTGRES_USER=//p' "$REPO_ROOT/.env")"
DB_NAME="$(sed -n 's/^POSTGRES_DB=//p' "$REPO_ROOT/.env")"
[[ -n $DB_USER && -n $DB_NAME ]] || die "从 .env 里读不到 POSTGRES_USER / POSTGRES_DB"

# **查库失败必须中止，不能当成「库里没有」** —— 那会把所有目录都判成孤儿，
# 一次误删就是全部教师的数据。软删的会话也算「有主」：它的目录本就该在删会话时
# 一并销毁了，这里还查得到说明销毁失败，那是要人去看的故障，不是垃圾
log "查库里的会话清单"
KNOWN="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "SELECT replace(id::text,'-','') FROM threads;" 2>/dev/null)" \
    || die "查库失败。栈起着吗（make ps）？查不到就不能删 —— 那会把所有目录都当成孤儿"
[[ -n $KNOWN ]] || die "库里一个会话都没有，不像是正常状态。人工确认后再跑"

KNOWN_COUNT="$(printf '%s\n' "$KNOWN" | grep -c . || true)"
log "库里 $KNOWN_COUNT 个会话"

ORPHAN_LIST="$(mktemp)"
trap 'rm -f "$ORPHAN_LIST"' EXIT

# 只看第一层目录，且够老
find "$WORKSPACE_ROOT" -mindepth 1 -maxdepth 1 -type d -mmin "+$(( MIN_AGE_HOUR * 60 ))" -printf '%f\n' |
    grep -vxF -f <(printf '%s\n' "$KNOWN") > "$ORPHAN_LIST" || true

ORPHAN_COUNT="$(grep -c . "$ORPHAN_LIST" || true)"
if (( ORPHAN_COUNT == 0 )); then
    printf '\033[32m   ✅ 没有孤儿目录\033[0m\n'
    exit 0
fi

# 用字节精算再换算，不用 `du -sm` 逐个相加 —— 那个按块向上取整，
# 上千个几 KB 的空目录会被摊成上千 MB，报出来的「释放空间」差一个量级
SIZE_MB="$(cd "$WORKSPACE_ROOT" && du -sc --block-size=1 $(tr '\n' ' ' < "$ORPHAN_LIST") 2>/dev/null |
    tail -1 | awk '{printf "%.0f", $1/1048576}')"
printf '   孤儿目录 \033[33m%s\033[0m 个，合计 \033[33m%s MB\033[0m（超过 %s 小时未改动）\n' \
    "$ORPHAN_COUNT" "$SIZE_MB" "$MIN_AGE_HOUR"

if [[ -z $DELETE ]]; then
    printf '\n   前 10 个：\n'
    head -10 "$ORPHAN_LIST" | sed 's/^/     /'
    printf '\n\033[36m   这是预演。确认无误后加 --delete 真删\033[0m\n'
    exit 0
fi

log "删除 $ORPHAN_COUNT 个孤儿目录"
FAILED=0
while IFS= read -r name; do
    # 名字来自 find 的第一层结果，不含斜杠；仍然显式拼根目录，不让相对路径有机会跑出去
    rm -rf -- "$WORKSPACE_ROOT/$name" || FAILED=$(( FAILED + 1 ))
done < "$ORPHAN_LIST"

if (( FAILED > 0 )); then
    printf '\033[33m   ⚠️  有 %s 个没删掉，多半是属主不对（沙箱以宿主 uid 跑，不该出现）\033[0m\n' "$FAILED"
    exit 1
fi
printf '\033[32m   ✅ 已删 %s 个目录，释放 %s MB\033[0m\n' "$ORPHAN_COUNT" "$SIZE_MB"
