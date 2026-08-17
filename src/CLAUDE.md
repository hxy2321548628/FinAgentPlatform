# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 后端

Python 3.13 + FastAPI + SQLModel/Alembic + LangGraph/DeepAgents，包管理用 `uv`。总体架构与门禁命令见[仓库根 CLAUDE.md](../CLAUDE.md)。

## 包根

**本目录就是包根**，一切从这里起算：

- 领域代码在 `app` 包里 —— `from app.run.executor import ...`，**不带 `src.` 前缀**；
- `config.py` / `log.py` / `cursor.py` 与 `app/` 平级，裸导入 —— `from config import Settings`；
- 工具一律在这里跑（`cd src && uv run …`，`make` 已经代劳），镜像里 `src/` 的内容平铺进 `/app`，模块路径与本地一字不差；
- 镜像定义就是本目录的 `Dockerfile`，**构建上下文也是本目录** —— api / worker / broker 三个入口共用它，差别只在 compose 给的 command。

**改动模块路径时，字符串形式的那些一起改**：logger 名（`logging.getLogger(__name__)` 的断言值，如 `"app.api.route.auth"`）、`monkeypatch.setattr("app.agent.factory.create_deep_agent", …)`、以及 `container_test.py` 里塞进子进程 `-c` 的那一行。它们躲得过 import 检查，只会在跑测试时才现形。

## 进程

三个常驻进程，同一份代码、同一个镜像，差别只在入口：

| 进程 | 入口 | 说明 |
|---|---|---|
| api | `app.api.app:app` | 网关。不碰 Docker、不碰 workspace、不驱动智能体；唯一的模型调用是给会话起标题 |
| worker | `python -m app.worker.main` | 不是 HTTP 服务，不开端口。进程内并发驱动多个 run，副本数解决的是「挂了怎么办」而非吞吐 |
| broker | `app.broker.app:app` | **唯一持有 `docker.sock` 与宿主机 workspace 目录**，只在内部网络上开端口 |

三个 cron 形态的一次性任务，跑一次即退出、随时可重跑：`app.store.retention`（保留期清理）、`app.run.approval`（审批超时清扫）、`app.run.reaper`（孤儿 run 收割 —— 库里还活着、队列里已经没有它了）。

## 包边界

包名即职责。最容易搞混的六组：

| 这个 | 不是那个 |
|---|---|
| `agent/` **装配层**：把一次 run 的配置拼成可执行的图 | `preset/` **目录层**：谁写了什么、共享给谁、审没审过 |
| 根 `log.py` 进程日志（JSON 行，给运维排障） | `run/log.py` 事件日志（Redis Stream，给教师看进度） |
| `run/submitter.py` 提交那一半（api 进程） | `run/executor.py` 执行那一半（worker 进程） |
| `threads` 表是「会话存不存在」的权威 | workspace 目录是它的副产品，越权过滤长在表上 |
| `store/` 只管连接的建立、体检、关闭 | 表结构在 `migration/`，业务读写在各模块的 repository |
| 根 `config.py` 平台 Settings | `agent/config.py` 一次 run 内生效的配置与快照 |

`agent/factory.py` 是执行器与 LangGraph 之间的**唯一接触面**；`event/mapper.py` 是 DeepAgents 流与平台事件之间的**唯一防腐层**。换编排框架时改这两处就够。

## 关键不变量

- **目录引用在提交那一刻解析并冻结**。agent 引用冻结版本与提示词，skill 引用冻结版本与名称；执行侧只读快照，不再解析引用。解析不出来一律硬失败 —— 静默回退默认提示词跑得完、不报错，唯一症状是回答变味。
- **事件 id 形如 `{毫秒}-{同毫秒内序号}`**，由事件日志追加时分配（对齐 Redis Stream ID），前端的 `Last-Event-ID` 认的就是它。映射层不自己发号。
- **ack 写在 `finally` 里**：正常结束与业务失败都 ack；只有 `kill -9` 才留 pending 给别的 worker `XAUTOCLAIM`。跑着的 worker 定期 `touch` 把 idle 归零，认领阈值因此可以很短。至少一次投递，重复执行是定义不是 bug。
- **不做自动重试**，失败时只在 `run.failed` 里给出 `retryable`，重不重试由人决定。
- **checkpoint 那几张表由 LangGraph 自己 `setup()` 建**，不进 Alembic，一个字都不要改。
- **列表一律游标分页**（`cursor.py`），不用 offset —— 会话按 `updated_at DESC` 排，翻页途中被顶到首页会静默漏条目。解析不了的游标要明确拒绝，不能当成「从头开始」。
- **认证挂在路由器上**，不逐个端点挂（`api/app.py`）；`api/security.py` 只答「你是谁」，「能不能看这一条」落在 repository 的过滤条件上。
- **三道闸**在 `quota/`：频率限流（Redis 滑动窗口，先数再记）、token 日配额（**按未命中部分算，`cache_read` 不计入**）、并发 run 上限。档位在 `quota/policy.py`，每个常量旁边写了它是怎么外推来的。
- **映射层遇到不认识的 chunk 记警告后跳过，不抛异常** —— 不该因为框架多吐一种形状就掀掉一次跑了半小时的分析。
- **事件同步双写**：Redis Stream（热，有 MAXLEN 与 TTL）+ `run_events` 表（历史）。异步追赶会在裁剪与归档之间留一个不报错的空白窗口。

## 数据

- **Postgres**：`runs` / `run_events` / `users` / `threads` / `groups` / `agents` / `agent_versions` / `reviews` / `skills` / `mcp_servers` 等，结构由 `migration/version/` 的 15 个脚本管。新增表走 `alembic revision`，**不 `create_all`** —— 两条路都能建表时它们迟早分叉。
- **Redis**：任务队列（Stream + consumer group）、事件日志（一个 run 一条流）、登录态（Redis 重启 = 全员重新登录，这是选它的代价）、限流计数、MCP 熔断计数。

## 测试

- 文件名 `{module}_test.py`，函数名 `test_<场景>_<预期>`，`asyncio_mode = "auto"`，覆盖率下限 80%。
- **不用替身顶掉要验的东西**。`test/conftest.py` 那一组要**真** Postgres 与**真** Redis，服务没起时整包 skip（不静默通过）；`test/api/conftest.py` 里假的只有**沙箱池**与**模型**，api ↔ broker 之间走真 HTTP（ASGI 传输）、队列的投递与消费也没被绕过。
- 沙箱用例需要 `zuel-sandbox:latest`，缺镜像会静默跳过 —— 根目录 `make sandbox-image`。
- 跑单个文件或用例：`uv run pytest test/run/executor_test.py -k <名字>`。

## 门禁

`ruff`（含 D/ANN/N 全开）+ `mypy --strict` + `pytest`，配置全在 `pyproject.toml`，入口是仓库根的 `make`。不用 `# noqa` / `# type: ignore` 掩盖问题，除非就地注释说明理由。加依赖用 `uv add`，不用 `uv pip install`。
