# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 中南财经政法大学金融学院智能体平台

教师用自然语言提问，智能体在隔离沙箱里写 Python、执行、返回结论与图表。内网单机部署。

面向用户的文字（docstring、注释、错误消息、前端文案）一律中文。

## 规范

- **python技术章程** → @.claude/python-constitution.md
- **代码风格指南** → @.claude/python-style.md

## 目录

| 路径 | 内容 |
|---|---|
| `src/` | 后端 Python 工程（见 [src/CLAUDE.md](src/CLAUDE.md)） |
| `web/` | 前端 React 工程（见 [web/CLAUDE.md](web/CLAUDE.md)） |
| `deploy/` | compose、Dockerfile、nginx、宿主机脚本、回归验收脚本 |
| `doc/01design/` | 九份设计文档 + 16 条 ADR |
| `doc/03plan/` | P0–P11 分期计划与验收记录（[索引](doc/03plan/CLAUDE.md)） |
| `data/` | postgres / redis / sandbox 三个宿主机 bind mount |

## 架构

六个容器（`deploy/compose.yml`）。**沙箱容器不在其中** —— 由 broker 在运行时按会话动态创建与销毁。

```
nginx ──> api ──XADD──> Redis Stream ──XREADGROUP──> worker ×2
                                                        │
                          broker <──── HTTP ────────────┘
                            │ docker.sock
                            └── 沙箱容器（gVisor / 无网 / XFS 配额）
```

一次分析的链路：

1. `POST /api/runs` —— api 把目录引用解析成快照写进 `runs`，再投一条任务消息；
2. worker 领任务 → 向 broker 申请沙箱 → 驱动 DeepAgents 图 → 把框架的流翻译成平台事件，写进 Redis Stream 并同步归档到 Postgres；
3. 前端订阅 `GET /api/runs/{id}/events`（SSE），断线靠 `Last-Event-ID` 补齐；
4. 命中人工审批时 run 挂起 —— 既不占队列消息也不占沙箱；教师决策后作为**新任务**重投，从 checkpoint 接着走。

三条不可越的边界，改动前先读对应 ADR：

- **api 与 worker 都不挂 `docker.sock`、不挂 workspace 目录**，一切沙箱与文件操作走 broker 的 HTTP（ADR-0004）；
- **沙箱 `--runtime=runsc --network=none`**，2g 内存 / 1 CPU / 128 pids / 5g XFS 配额（ADR-0002、ADR-0015）；
- **数据库迁移只由 api 容器跑** —— worker 有两个副本，各自 upgrade 会撞同一把 DDL 锁。

## 命令

门禁入口是根 `Makefile`，两端一起跑，不要绕过它单独调工具：

```bash
make            # = lint + type + test，提交前必须全绿
make fix        # 自动修 lint 并格式化（会改文件）
make cov        # 覆盖率，两端下限都是 80%
make hooks      # 新克隆的仓库跑一次，启用 pre-push 门禁
```

部署：

```bash
make up / down / rebuild / ps
make logs S=worker
make remount        # 重启机器后：重挂 XFS，并让 broker 与 nginx 重新解析挂载
make sandbox-image  # 新克隆的仓库跑一次，否则沙箱测试静默跳过
```

几条「忘了就要查半天」的前置条件已经固化进 Makefile，不必再手工记：`deploy/.env → ../.env` 的链接（缺了它**任何** compose 子命令在解析阶段就失败，连 `ps` 都算）、每次现查的 `SANDBOX_QUOTA_DEVICE`（loop 设备号每次挂载都可能变）、重挂之后必须 force-recreate 的 broker 与必须 restart 的 nginx。

真实验收要六个服务起着，与 `make all` 是两回事：

```bash
bash deploy/test/verify.sh                             # 61 条判据全跑，要 sudo、有 LLM 费用
SKIP_LLM=1 SKIP_HOSTILE=1 bash deploy/test/verify.sh   # 免费的 42 条，约 30 分钟
```

**判据没触发到要测的场景时记「未验」，不记通过** —— 这条规矩比判据本身更重要。

## 包根

**两个子工程各自自洽**：`src/` 与 `web/` 各持有自己的依赖声明与工具配置，包根就是那个目录。因此后端的模块路径是 `app.api.app`、`config`、`log`、`cursor` —— **不带 `src.` 前缀**，`src/` 只是目录名，不是包。所有工具都在 `src/` 里跑（`make` 已经代劳），compose 的三个入口与镜像里的路径与本地完全一致。
