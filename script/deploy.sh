#!/usr/bin/env bash
#
# 一键部署：新机器从零到六个服务起着。
#
#   bash script/deploy.sh                    # 缺什么补什么，补完起栈
#   SKIP_HOST_SETUP=1 bash script/deploy.sh  # 只重建镜像与容器（机器改造做过了）
#
# **幂等可重跑**：每一步先看它是不是已经成立，成立就跳过。三步机器改造
# （gVisor、XFS、沙箱镜像）是一次性的，日常改代码用 `make rebuild` 就够。
#
# **起容器那一段不在这里重写一遍，转调 `make up`** —— compose 文件的位置、
# `docker/.env` 的链接、每次现查的配额设备号，都只在 Makefile 里定义一处。
# 抄成第二份的话，两边迟早分叉，而分叉的症状是「照文档跑却起不来」。
#
# **要 sudo**：装 gVisor 与挂 XFS 都要 root，脚本只在真需要那两步时才提权。
# 全程不碰 `data/` 里已有的数据：Postgres 与 Redis 的目录是 bind mount，重跑不会动它们。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX_IMAGE="${SANDBOX_IMAGE:-zuel-sandbox:latest}"
# 起栈之后自检要等它 —— 六个服务里 api 要先跑完迁移，冷启动几秒到几十秒不等
READY_SECOND="${READY_SECOND:-90}"

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }
skip() { printf '    \033[90m已成立，跳过：%s\033[0m\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "别用 root 跑整个脚本：容器与镜像会归 root，agent 写出的文件宿主侧读不了。需要提权的两步脚本自己会调 sudo"

# ---------------------------------------------------------------- 前置
#
# **凭据缺了不能往下走**：compose 会拿着空的 API key 把六个服务全起起来，
# 而症状要等到第一次提问才现形（模型 401），完全不指向部署
[[ -f $REPO_ROOT/.env ]] || die "缺 $REPO_ROOT/.env：先 cp .env.example .env，再填 DEEPSEEK_API_KEY 等凭据"
command -v docker >/dev/null || die "没装 docker"
docker compose version >/dev/null 2>&1 || die "docker compose 插件不可用"
docker info >/dev/null 2>&1 || die "连不上 Docker 守护进程：当前用户要在 docker 组里（newgrp docker 后重试）"

# workspace 根。与 Makefile / config.py 同一个默认值
WORKSPACE_ROOT="$(sed -n 's/^SANDBOX_WORKSPACE_ROOT=//p' "$REPO_ROOT/.env")"
[[ -n $WORKSPACE_ROOT ]] || WORKSPACE_ROOT="$REPO_ROOT/data/sandbox"

# ---------------------------------------------------------------- ① gVisor
#
# 沙箱靠 runsc 拦住容器逃逸（ADR-0002）。**不装的话 broker 建会话一律失败**，
# 而不是「安全性弱一点」—— 加固参数写死在容器创建参数里，起不来就是起不来
log "① gVisor（runsc）"
if docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' | tr ' ' '\n' | grep -qx runsc; then
    skip "Docker 已注册 runsc 运行时"
elif [[ -n ${SKIP_HOST_SETUP:-} ]]; then
    die "runsc 没注册，而 SKIP_HOST_SETUP 说不做机器改造 —— 去掉那个开关再跑一次"
else
    sudo bash "$REPO_ROOT/script/setup-gvisor.sh"
fi

# ---------------------------------------------------------------- ② XFS
#
# 5GB/会话的配额靠 XFS project quota，而它只在挂载时带 prjquota 才可用。
# **没挂 XFS 不是致命的**（broker 会退化成不设配额），但一个跑飞的分析就能写满盘
log "② workspace 挂在带 prjquota 的 XFS 上（$WORKSPACE_ROOT）"
if [[ $(findmnt -no FSTYPE --target "$WORKSPACE_ROOT" 2>/dev/null) == xfs ]]; then
    skip "已经是 XFS"
elif [[ -n ${SKIP_HOST_SETUP:-} ]]; then
    printf '    \033[33m警告：没挂 XFS，本轮不设磁盘配额\033[0m\n'
else
    sudo bash "$REPO_ROOT/script/setup-xfs.sh"
fi

# ---------------------------------------------------------------- ③ 沙箱镜像
#
# **它不在 compose 里**：沙箱容器由 broker 在运行时按会话创建，镜像得先躺在本机上。
# 缺了它 broker 建会话就失败，而沙箱那组测试是静默跳过的 —— 门禁全绿也说明不了什么
log "③ 沙箱镜像 $SANDBOX_IMAGE"
if docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1; then
    skip "镜像已存在（要更新预装的库就 make sandbox-image）"
else
    make -C "$REPO_ROOT" sandbox-image
fi

# ---------------------------------------------------------------- ④ 起栈
log "④ 构建并起六个服务"
make -C "$REPO_ROOT" up

# ---------------------------------------------------------------- ⑤ 自检
#
# **不能只看 `docker compose ps`**：容器 Up 着而 api 在迁移里卡住、nginx 镜像里
# 没烤进前端，两种都照样显示 Up。这里要的是「浏览器打得开、api 应答」这两件事本身。
log "⑤ 自检"
PORT="$(sed -n 's/^HTTP_PORT=//p' "$REPO_ROOT/.env")"
BASE_URL="http://127.0.0.1:${PORT:-80}"

deadline=$(( SECONDS + READY_SECOND ))
until [[ $(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/auth/me") =~ ^(200|401)$ ]]; do
    (( SECONDS < deadline )) || die "$READY_SECOND 秒内 api 没应答：make logs S=api"
    sleep 3
done
printf '    \033[32m✅\033[0m api 应答（%s/api）\n' "$BASE_URL"

# 前端是烤在 nginx 镜像里的，因此首页必须是 SPA 那份 html 而不是 api 的 JSON。
# **认 index.html 里的挂载点**，只看 200 的话 api 的 404 页也能糊弄过去
if curl -fsS "$BASE_URL/" | grep -q '<div id="root">'; then
    printf '    \033[32m✅\033[0m 前端首页发得出来（%s/）\n' "$BASE_URL"
else
    die "首页不是前端的 index.html —— nginx 镜像里没烤进 dist，重建：make rebuild"
fi

# 深链接刷新走的是 try_files 兜底，缺了它教师按一次 F5 就是 404
[[ $(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/workspace/thread/deploy-probe") == 200 ]] \
    && printf '    \033[32m✅\033[0m 工作台深链接刷新不 404\n' \
    || die "深链接返回的不是 200 —— nginx.conf 的 try_files 兜底没生效"

log "部署完成：浏览器打开 $BASE_URL"
printf '  日常改代码：make rebuild      看日志：make logs S=worker\n'
printf '  重启机器后：make remount      真实验收：bash script/test/verify.sh\n'
