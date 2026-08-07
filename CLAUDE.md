# 金融学院智能体平台

面向金融学院教师的多用户智能体平台。教师用自然语言提出分析问题，智能体自行编写 Python、在隔离沙箱中执行、返回结果与图表 —— 教师不需要会写代码。

这决定了两个贯穿全局的性质：**任务是长的**（几分钟到几十分钟，不能用请求-响应承载），**要执行不可信代码**（LLM 生成，沙箱隔离不是可选项）。

---

## Standards Files

- **python技术章程** → @.claude/python-constitution.md
- **代码风格指南** → @.claude/python-style.md
- **文档指南** → @.claude/document.md

---

## 项目结构

```
zuel-platform/
├── app/            # Python 后端（uv 工程，虚拟环境在 app/.venv）。三个入口：api.app:app、broker.app:app、worker.main
├── frontend/       # React 前端（未开始）
├── deploy/         # 部署配置：compose.yml（nginx+api+broker+postgres+redis）、两个 Dockerfile、nginx.conf、环境搭建与验收脚本
├── doc/            # 设计文档，见上方文档地图
├── .claude/        # 技术章程与风格指南
├── .github/        # CI（gate workflow：干净环境里复跑 make all）
├── .githooks/      # pre-push 门禁 hook，需 `make hooks` 启用
├── .env            # 凭据，不入库；模板见 .env.example
└── Makefile        # 质量门禁入口，见下
```

---

## 开发

Python 3.13 + uv。虚拟环境在 `app/.venv`，**不在仓库根**：

```bash
cd app && uv sync                      # 装依赖
cd app && uv run pytest                # 跑脚本一律走 uv run；门禁入口仍是仓库根的 make

# 沙箱镜像。**新克隆的仓库要跑一次**，否则沙箱测试会静默跳过而门禁照样绿
docker build -f deploy/sandbox.Dockerfile -t zuel-sandbox:latest .

# Postgres 与 Redis。跑门禁前要起着，否则落库与事件流的用例会 skip（同上，门禁照样绿）
docker compose -f deploy/compose.yml up -d postgres redis
cd app && uv run alembic upgrade head    # 建 runs 等业务表。测试会自己跑一次，手工部署要跑

# 环境（gVisor + XFS prjquota）。新机器要跑一次，脚本可重跑
sudo bash deploy/setup-gvisor.sh && sudo bash deploy/setup-xfs.sh && sudo bash deploy/verify-env.sh

# 起服务。**三个进程**：broker 持有 docker.sock；worker 驱动智能体；api 只投递任务与转 SSE。
# cwd 必须在 app/ —— 模块路径是 api.app，从仓库根起会 ModuleNotFoundError
cd app && uv run uvicorn broker.app:app --port 8100   # 先起它，另两个依赖它
cd app && uv run uvicorn api.app:app --reload         # 另开一个终端
cd app && uv run python -m worker.main                # 再开一个。不起它的话 run 会一直停在 queued
```

整套跑起来（nginx + api + broker）用 Compose：

```bash
export SANDBOX_USER="$(id -u):$(id -g)" SANDBOX_WORKSPACE_ROOT="$(pwd)/data/sandbox"
docker compose -f deploy/compose.yml up -d --build

# P1 验收六条的总入口，转调下面两个脚本。操作步骤见 doc/04acceptance-guide/P1/
bash deploy/test/p1.sh                             # 六条全跑（要 sudo，有 LLM 费用）
SKIP_HOSTILE=1 SKIP_LLM=1 bash deploy/test/p1.sh   # 只跑免费的四条，约 3 分钟

bash deploy/test/acceptance.sh    # P0 验收四条（真实 LLM 调用，有费用）
sudo bash deploy/test/hostile.sh  # 四条破坏性测试

# P2 验收六条。②③⑥ 免费自验，①④ 要 LLM，⑤ 转调 p1.sh
bash deploy/test/p2.sh                             # 六条全跑（有 LLM 费用）
SKIP_LLM=1 SKIP_P1=1 bash deploy/test/p2.sh        # 只跑免费的三条，约 1 分钟

# P3 验收七条。②③④⑤⑥ 免费自验，① 要 LLM，⑦ 转调 p2.sh
bash deploy/test/p3.sh                             # 七条全跑（有 LLM 费用）
SKIP_LLM=1 SKIP_P2=1 bash deploy/test/p3.sh        # 只跑免费的五条，约 3 分钟
```

**两个 cron 任务**（都可重跑，删/改的都是「早于某个时点」的东西）：

```bash
cd app && uv run python -m store.retention   # 事件与 checkpoint 的保留期清理
cd app && uv run python -m run.approval      # 挂超过 24 小时的待审批转 cancelled
```

`.env` 在**仓库根**（不在 `app/`），业务代码一律走 `pydantic_settings.BaseSettings` 读取，不直接 `os.getenv`。

**首个管理员**由 `.env` 的 `ADMIN_NAME` / `ADMIN_PASSWORD` 在**空库时**建一次，之后再启动都不看它 —— 否则改过口令的账号会被一次重启改回去。**Redis 重启会把所有人踢下线**：session 存在那里，这不是故障，是选它的代价。

沙箱 workspace 的宿主目录由 `SANDBOX_WORKSPACE_ROOT` 决定，默认落在仓库内的 `data/sandbox/`（已 gitignore）。compose 部署时**容器内外必须是同一个路径** —— broker 把它交给宿主机的 Docker 守护进程，那是在宿主机上解析的。

### 两个会浪费时间的坑

- **开发机的 `ALL_PROXY=socks://…` 会让 `ChatDeepSeek` 构造直接报错**（httpx 不认 socks 方案）。`api.deepseek.com` 实测可直连，剥掉该变量即可。内网服务器上没有这些变量，是纯开发机问题。
- **没有 `zuel-sandbox:latest` 镜像时，沙箱测试会 skip 而不是失败**，`make all` 依旧显示通过。要验沙箱就得先构建镜像，见上方命令。Postgres / Redis 没起时同理。
- **平台自己的 Postgres 在宿主机上听 5433，不是 5432**。装了系统 Postgres 的机器上 5432 已被占用，而「连错了库」这种故障不报错。这个端口在 `deploy/compose.yml` 里**写死不走插值** —— compose 的插值只认 shell 里 `export` 过的值，而 `.env` 在仓库根，两边不是同一份。
- **直接跑 uvicorn 时不要设 `SANDBOX_USER`**：留空即取当前进程的 uid:gid，正好对。只有 compose 部署才必须显式给 —— broker 在容器里是 root，不给的话它建出来的 workspace 目录沙箱写不进去，而**症状不指向权限**：`execute` 全部成功，agent 只是「选择」把图存到别处，最后产物一个都没有。

---

## 提交约定

- 消息格式 `Type(scope): 中文描述`，与现有历史一致（`Docs(design):` / `Feat(spike):`）。正文说清改了什么、为什么。
- 提交前 `make all` 全绿。`make hooks` 装上 pre-push hook 后 push 会自动跑（**新克隆的仓库要手动跑一次**，hook 配置不随 clone 走）。

---

## 交互约定

- **中文回复**：与我交流一律使用中文。
- **先问再写**：设计文档已经把大量取舍论证过了。若实现与文档冲突，先确认是文档过时还是理解有误，不要单方面改实现绕过。

