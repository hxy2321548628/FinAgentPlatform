# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 前端

React 19 + TypeScript + Vite + Tailwind 4 + TanStack Query，包管理用 `pnpm`。总体架构与两端合跑的门禁见[仓库根 CLAUDE.md](../CLAUDE.md)。

## 命令

```bash
pnpm dev          # vite 开发服务器，把 /api 代理到 nginx（默认 127.0.0.1:80）
pnpm lint         # oxlint
pnpm typecheck    # tsc -b
pnpm test         # vitest run
pnpm coverage     # vitest + v8，白名单模块 80% 下限
pnpm test -- src/workspace/eventReducer.test.ts   # 跑单个文件
```

## 部署形态

**前端不是单独的容器**：`web/Dockerfile` 第一阶段 `pnpm build`，第二阶段把 `dist/` 烤进 nginx 镜像 —— compose 里那个 nginx 服务就是它，`/` 发静态文件，`/api/` 才转给 api。因此**改了前端代码要 `make rebuild`**，`restart` 拿到的还是旧产物。反代配置仍从 `docker/nginx.conf` 挂进去，改配置不必重建。

`pnpm dev` 那条路没变：vite 起在 5173，把 `/api` 代理给 nginx 的 80 —— 开发时看到的前端是 vite 的，不是镜像里的那份。

**深链接靠 nginx 的 `try_files` 兜底**，路由表里的每个路径都得刷新得起来；而 `X-Accel-Redirect` 的内部前缀是 `/__workspace/`，正是为了避开 `/workspace/*` 这个前端路由。

端到端走查另有一套：`pnpm exec playwright test`。它要六个服务起着、要真账号（由 `script/test/verify.sh` 造好后从环境变量传入 —— 平台没有公开的教师注册入口），因此**不进 `make all`**，进 `verify.sh`。换栈跑时用 `E2E_API_TARGET` 覆盖 vite 的代理目标。

## 路由三层（`src/App.tsx`）

| 层 | 路径 | 守卫 |
|---|---|---|
| 公开站点 | `/`、`/marketplace`、`/scenarios`、`/capabilities`、`/data`、`/login`、`/register` | 无 |
| 工作台 | `/workspace/*` → `workspace/WorkspaceRouter.tsx` | `AuthGuard` + `WorkspaceLayout` |
| 后台 | `/admin/{agents,skills,mcp}` | `ReviewerGuard` |
| 后台 | `/admin/{users,usage,system}` | `AdminGuard` |

后台拆成两块不是笔误：`reviewer` 只判「这份东西该不该让全平台用」，账号、配额与 MCP 运维仍归 `admin`。

## 事件层

前端最容易改坏的一段，四个文件一条链：

```
api/runEventTransport.ts   SSE 传输：fetch-event-source，1s→30s 指数退避
        ↓                  （退避必须自己给：库默认固定 1s，撞上 429 会每秒撞一次，
        ↓                    60 秒的滑动窗口再也清不空，闸门自己把自己锁死）
api/events.ts              事件名白名单与解析
        ↓
hooks/useRunEvents.ts      订阅 + 内存游标 + 终态判定 + 一次性 replay 补齐
        ↓
workspace/eventReducer.ts  折叠成 RunViewItem[]（reasoning / answer / tool / notice）
```

三条容易踩的：

- **游标只在同页内复用**（重连时放进 `Last-Event-ID`），整页刷新从头重放；
- **事件 id 是数字对**，比较要按 `{毫秒}-{序号}` 拆开比 —— 字典序会把 `10-0` 排在 `9-0` 前面；
- **429 一律不重试**（`queryClient.ts`）—— 重试等于给限流窗口续命，该让教师看见「操作太快了」并自己停手。

## 与后端的契约

- 事件名与信封照抄 `src/app/event/model.py`；八个 `ErrorCode` 照抄后端（`api/request.ts`）。
- run 事件的 `path` 是子智能体的嵌套路径，渲染分组按它走。
- 文件下载走 nginx 的 `X-Accel-Redirect`，**只有跑在 nginx 后面才拿得到字节** —— 直连 uvicorn 时浏览器只会收到空响应。
- 「我的智能体」三个页签由后端五个事实（版本 `draft`/`released` × 审核 `pending`/`approved`/`rejected`）合成，规则集中在 `workspace/agent.ts` —— 映错了没有报错，只有一通「我的东西不见了」的电话。

## 测试分层

- **vitest 只管 `src/**`**，`e2e/` 在 `vitest.config.ts` 里被显式排除 —— 混进来会让 `make all` 变成依赖一整套 compose 栈。
- 覆盖率的 80% 只卡在 `vitest.config.ts` 的**白名单**上（api 三件套、`useRunEvents`、workspace 四件套）。新增纯逻辑模块要自己加进去，否则不受门禁保护。
- playwright **单 worker、不重试**：走查会在多个账号之间切登录态，并行会互相顶掉 cookie；自动重试会把「第一次红、第二次绿」的偶发问题藏起来。

## 样式

Tailwind 4 走 `@tailwindcss/vite`，色板与暗色变量在 `src/styles/theme.css`（只认 `<html class="dark">` 这一个作用域），主题切换在 `components/ui/theme.ts`（`light`/`dark`/`system`，持久化在 `localStorage`）。设计基准是 `doc/02visual/01-DSD.md`。
