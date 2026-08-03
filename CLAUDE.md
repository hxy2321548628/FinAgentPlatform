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
├── app/            # Python 后端（uv 工程，虚拟环境在 app/.venv）
│   └── spike/      # P0 验证探针 + 结论 FINDINGS.md。一次性代码，回填完文档即可删
├── frontend/       # React 前端（未开始）
├── deploy/         # Docker Compose 与部署配置（未开始）
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
cd app && uv run python spike/probe1_api_surface.py
```

`.env` 在**仓库根**（不在 `app/`），业务代码一律走 `pydantic_settings.BaseSettings` 读取，不直接 `os.getenv`。

### 两个会浪费时间的坑

- **开发机的 `ALL_PROXY=socks://…` 会让 `ChatDeepSeek` 构造直接报错**（httpx 不认 socks 方案）。`api.deepseek.com` 实测可直连，剥掉该变量即可。内网服务器上没有这些变量，是纯开发机问题。

---

## 提交约定

- 直接提交到 `main`，不开分支。
- 消息格式 `Type(scope): 中文描述`，与现有历史一致（`Docs(design):` / `Feat(spike):`）。正文说清改了什么、为什么。
- 提交前 `make all` 全绿。`make hooks` 装上 pre-push hook 后 push 会自动跑（**新克隆的仓库要手动跑一次**，hook 配置不随 clone 走）。

---

## 交互约定

- **中文回复**：与我交流一律使用中文。
- **先问再写**：设计文档已经把大量取舍论证过了。若实现与文档冲突，先确认是文档过时还是理解有误，不要单方面改实现绕过。

