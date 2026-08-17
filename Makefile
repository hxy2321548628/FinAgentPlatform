# 本地质量门禁入口（.claude/python-constitution.md 第四条）。
#
# `make` 一条命令跑完 lint / 类型 / 测试，未全绿不得提交。
# 门禁目标只读不改文件，将来接 CI 时可原样复用；要自动改代码用 `make fix`。
#
# Python 工程在 src/，web 工程在 web/；recipe 先进各自目录，不在根目录复制配置。
# 两侧同一个形态：各自持有自己的依赖声明与工具配置，包根就是那个目录。

APP := src
WEB := web
UV  := uv run

COMPOSE := docker compose -f docker/compose.yml
# 跟着代码走的四个服务：三个应用入口共用 src/ 的镜像，nginx 烤着 web/ 的构建产物。
# 存储那两个不在里面，改代码时不必动它们
APP_SERVICE := api worker broker nginx

# workspace 根。.env 里没写就用仓库内的默认值（config.py 同一个默认）
SANDBOX_WORKSPACE_ROOT := $(shell sed -n 's/^SANDBOX_WORKSPACE_ROOT=//p' .env 2>/dev/null)
ifeq ($(SANDBOX_WORKSPACE_ROOT),)
SANDBOX_WORKSPACE_ROOT := $(CURDIR)/data/sandbox
endif

# **每次现查再 export**：loop 设备号每次挂载都可能变（实测 loop0 → loop28），
# 写进 .env 必然过期。broker 的 `devices:` 是**建容器那一刻**定死的，设备对不上时
# 它的 xfs_quota 每条命令只往 stderr 打一句然后退出 0 —— 配额一个都设不上，
# broker fail-closed，建会话一律 500，而症状完全不指向挂载。
#
# 只认 xfs：没挂 XFS 的机器本来就不设配额，此时留空让 compose 回落到 /dev/null，
# 不能把宿主根盘的设备节点映射进容器
export SANDBOX_QUOTA_DEVICE := $(shell findmnt -no SOURCE,FSTYPE --target "$(SANDBOX_WORKSPACE_ROOT)" 2>/dev/null | awk '$$2 == "xfs" { print $$1 }')

.DEFAULT_GOAL := all
.PHONY: all fix fmt lint type test cov sync sync-locked hooks clean help \
        deploy up down rebuild remount remount-apply logs ps sandbox-image

## all: 本地门禁 —— lint + 类型 + 测试（提交前必须全绿）
all: lint type test
	@echo "✅ 门禁通过"

## fix: 自动修复能修的 lint 问题并格式化（会改文件）
fix:
	@cd $(APP) && $(UV) ruff check --fix .
	@cd $(APP) && $(UV) ruff format .

## fmt: 只格式化（会改文件）
fmt:
	@cd $(APP) && $(UV) ruff format .

## lint: 检查格式与 lint 规则，不改文件
lint:
	@cd $(APP) && $(UV) ruff format --check .
	@cd $(APP) && $(UV) ruff check .
	@cd $(WEB) && pnpm lint

## type: 静态类型检查
type:
	@cd $(APP) && $(UV) mypy
	@cd $(WEB) && pnpm typecheck

## test: 跑测试
test:
	@cd $(APP) && $(UV) pytest; \
	status=$$?; \
	if [ $$status -eq 5 ]; then \
		echo "⚠️  未收集到任何测试。"; \
		echo "   技术章程第一条要求测试先行；写下第一个 *_test.py 后本目标即转为真实门禁。"; \
		exit 0; \
	fi; \
	exit $$status
	@cd $(WEB) && pnpm test

## cov: 跑测试并检查覆盖率下限（80%）
cov:
	@cd $(APP) && $(UV) pytest --cov=. --cov-report=term-missing
	@cd $(WEB) && pnpm coverage

## sync: 按两侧锁文件重建依赖
sync:
	@cd $(APP) && uv sync
	@cd $(WEB) && pnpm install

## sync-locked: 同上但禁止改动锁文件（CI 用；声明与锁文件不一致即失败）
sync-locked:
	@cd $(APP) && uv sync --locked
	@cd $(WEB) && pnpm install --frozen-lockfile

# ---- Docker 部署 ----
#
# 这一段把 CLAUDE.md 里那几条「忘了就要查半天」的前置条件固化成命令：
# docker/.env 链接、现查的 quota 设备、重挂之后必须动的两个容器。

# compose 的 ${...} 插值只读 compose.yml 同目录的 .env，而这个项目的 .env 在仓库根 ——
# 两边从来不是同一份文件。缺了链接的话，**任何一条 compose 子命令都在解析阶段就失败**
# （连 stop 与 ps 都算）。链接被 gitignore 忽略，不随 clone 走
docker/.env:
	@ln -sf ../.env docker/.env
	@echo "✅ 已建 docker/.env → ../.env"

## deploy: 新机器一键部署（gVisor / XFS / 沙箱镜像缺什么补什么，起栈后自检）
#
# 机器改造那三步是一次性的，日常改代码用 rebuild。脚本反过来转调下面的 up，
# compose 的调用方式因此只有这一份
deploy:
	@bash script/deploy.sh

## up: 起全套六个服务（nginx + api + worker×2 + broker + postgres + redis）
up: docker/.env
	@$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory ps

## down: 停掉全套服务。数据目录是宿主机 bind mount，不会被删
down:
	@$(COMPOSE) down

## rebuild: 改过 src/ 或 web/ 代码后重建并重启这四个容器
rebuild: docker/.env
	@$(COMPOSE) up -d --build --force-recreate $(APP_SERVICE)
	@$(MAKE) --no-print-directory ps

## remount: 重启机器后的恢复序列 —— 重挂 XFS，再让 broker / nginx 重新解析挂载
#
# 分成两个目标是必须的：设备号在 Makefile 解析时就算好了，而它要等 setup-xfs.sh
# 跑完才有新值 —— 只有子 make 会重新解析一遍 Makefile
remount:
	@sudo bash script/setup-xfs.sh
	@$(MAKE) --no-print-directory remount-apply

# broker 必须 force-recreate 而非 restart：bind mount 靠 restart 能重新解析，但
# `devices:` 那一项是建容器那一刻定死的。nginx 只绑卷不要设备，restart 足够 ——
# **漏掉它的症状在下载上**：字节走 X-Accel-Redirect 由 nginx 直发，它绑着旧目录时
# api 照常回 200 而浏览器收 404。旧沙箱容器同样绑着旧目录，清掉让 broker 按需重建
remount-apply: docker/.env
	@$(COMPOSE) up -d --no-deps --force-recreate broker
	@$(COMPOSE) restart nginx
	@docker ps -q --filter 'name=zuel-sandbox' | xargs -r docker rm -f
	@$(MAKE) --no-print-directory ps

## logs: 跟随日志（make logs S=worker 只看一个服务）
logs: docker/.env
	@$(COMPOSE) logs -f --tail=100 $(S)

## ps: 服务状态，并核对 broker 里的 quota 设备与宿主机现值是否一致
ps: docker/.env
	@$(COMPOSE) ps
	@echo "宿主机 quota 设备：$(or $(SANDBOX_QUOTA_DEVICE),（未挂 XFS，不设配额）)"
	@echo "broker 映射设备：  $$($(COMPOSE) ps -q broker | xargs -r docker inspect --format '{{range .HostConfig.Devices}}{{.PathOnHost}}{{end}}')"

## sandbox-image: 构建沙箱镜像（新克隆的仓库要跑一次，否则沙箱测试静默跳过）
sandbox-image:
	@docker build -f docker/sandbox.Dockerfile -t zuel-sandbox:latest docker

## hooks: 启用仓库内的 git hooks（新克隆的仓库需手动跑一次）
hooks:
	@git config core.hooksPath .githooks
	@echo "✅ 已启用 .githooks/：push 前自动跑 make all"

## clean: 清理工具缓存与构建产物
clean:
	@find $(APP) -type d -name __pycache__ -not -path '*/.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(APP)/.ruff_cache $(APP)/.mypy_cache $(APP)/.pytest_cache $(APP)/.coverage
	@rm -rf $(WEB)/coverage
	@echo "✅ 已清理"

## help: 列出所有目标
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
