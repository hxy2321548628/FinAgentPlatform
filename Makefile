# 本地质量门禁入口（.claude/python-constitution.md 第四条）。
#
# `make` 一条命令跑完 lint / 类型 / 测试，未全绿不得提交。
# 门禁目标只读不改文件，将来接 CI 时可原样复用；要自动改代码用 `make fix`。
#
# Python 工程在 app/，所有配置都在 app/pyproject.toml，因此 recipe 一律先 cd 进去。

APP := app
UV  := uv run

.DEFAULT_GOAL := all
.PHONY: all fix fmt lint type test cov sync clean help

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

## type: 静态类型检查
type:
	@cd $(APP) && $(UV) mypy

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

## cov: 跑测试并检查覆盖率下限（80%）
cov:
	@cd $(APP) && $(UV) pytest --cov=. --cov-report=term-missing

## sync: 按 uv.lock 重建虚拟环境
sync:
	@cd $(APP) && uv sync

## clean: 清理工具缓存与构建产物
clean:
	@find $(APP) -type d -name __pycache__ -not -path '*/.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(APP)/.ruff_cache $(APP)/.mypy_cache $(APP)/.pytest_cache $(APP)/.coverage
	@echo "✅ 已清理"

## help: 列出所有目标
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
