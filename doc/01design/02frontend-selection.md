# 前端技术选型

> 状态：已确认
> 日期：2026-07-30
> 上游依据：[总体架构设计](../doc/01design/01architecture.md) · [设计风格文档 DSD](../doc/02visual/01-DSD.md)

---

## 1. 由上游文档决定、无需再议的前提

| 前提 | 来源 |
|---|---|
| 框架为 React | 架构文档 §1 |
| 事件流走 SSE，非 WebSocket | 架构文档 §7.2 |
| 控制通道走 REST（提交/取消/审批/查历史） | 架构文档 §3 |
| 事件流可断线重放，携带 `Last-Event-ID` | 架构文档 §3 |
| 视觉体系为自研 Intelligence-Minimal，非第三方设计语言 | DSD 全文 |
| 内网部署，静态资源由 compose 内已有 nginx 托管 | 架构文档 §9 |

---

## 2. 选型总表

| 层 | 选择 | 版本 |
|---|---|---|
| 应用形态 | Vite SPA，打包为静态 dist | Vite 7 |
| 语言 | TypeScript | 5.x |
| 包管理 | pnpm | 11.x（本机已就绪） |
| 路由 | React Router（declarative mode） | 7.x |
| 样式引擎 | Tailwind CSS + `@theme` token | v4 |
| 组件行为层 | Radix UI Primitives | latest |
| 组件代码来源 | shadcn/ui（复制改造，不作依赖） | — |
| 服务端状态 | TanStack Query | v5 |
| 客户端状态 | Zustand | v5 |
| 表格 | TanStack Table（headless） | v8 |
| SSE 客户端 | `@microsoft/fetch-event-source` | — |
| Markdown | react-markdown + remark-gfm + rehype-katex | — |
| 代码高亮 | Shiki | — |
| 图标 | lucide-react（`strokeWidth={1.5}`） | — |
| 事件校验 | Zod | v4 |
| 图表库 | **不引入** | — |

---

## 3. 关键决策与理由

### 3.1 Vite SPA，不用 Next.js

登录后全部是私有动态数据，无 SEO 需求；后端是 FastAPI，Next 的 RSC 与 Server Actions 用不上。选 Next 等于在内网 compose 里多运维一个 Node 进程、多分发一个镜像，换不到对应收益。产物是纯静态 dist，交给架构文档 §9 里已有的 nginx 直接托管。

### 3.2 不用 Ant Design（或任何成品组件库）

DSD 已经把色彩（`--action: #1749C4`）、圆角（6/8/10px 三档）、字距（大写标签 `0.22em`）、动效时长（150/200/400ms）逐条定死。成品组件库自带一整套设计语言，改造成 Intelligence-Minimal 需要大规模 token 覆盖与样式对抗，且每次库升级都可能破坏覆盖结果。**有自研设计系统时引入组件库，是在跟自己的设计系统对着干。**

改为「Tailwind 管样式 + Radix 管行为」：Radix 只提供无样式的交互与无障碍能力（Dialog 焦点陷阱、Dropdown 键盘导航、Tooltip 定位），外观 100% 由 DSD token 决定。shadcn/ui 按需复制代码进仓库再替换成 DSD token —— 它本来就是这个用法，不是当依赖装。

### 3.3 SSE 客户端不能用原生 `EventSource`

平台是多租户带鉴权的，而原生 `EventSource` 不支持自定义请求头，无法携带 Authorization。改用 `@microsoft/fetch-event-source`，基于 fetch 实现，可带 header、可 POST、可自定义重连退避。

代价是 `Last-Event-ID` 的维护由浏览器转到应用侧：需要自己记录最后一条事件 id，重连时放进请求头，对接架构文档 §3 的 per-run Redis Stream 重放机制。这部分要封成一个 `useRunStream` hook 统一处理，不散落在组件里。

### 3.4 对话 UI 自研，不用 assistant-ui

DeepAgents 的事件类型相当特殊：子 agent 嵌套、todo 列表、虚拟文件系统、HITL `interrupt()` 审批。把这些映射到成品库的 runtime 协议，成本未必低于直接消费自己的 SSE 事件，且遇到边界情况改不动。自研消息渲染层，用 Zod 校验事件 payload 保证类型安全。

### 3.5 不引入图表库

沙箱内 matplotlib 出图 → MinIO → 前端拿签名 URL 渲染 `<img>`。前端零图表依赖。若后续需要可交互图表，再单独引入 ECharts 并约定图表 schema，不影响现有结构。

---

## 4. DSD 落地方式

### 4.1 token 映射（Tailwind v4）

DSD §2 的 `:root` 变量块原样保留，Tailwind 通过 `@theme inline` 引用而非复制。这样切换主题时只需覆盖 `:root` 变量，所有 utility class 无需改动。

```css
/* src/styles/theme.css */
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

:root {
  /* 直接来自 DSD §2，浅色为唯一实现值 */
  --bg:            #EDF0F5;
  --surface:       #FFFFFF;
  --border:        #D4DCE8;
  --border-light:  #E8EDF4;
  --text-primary:  #0D1829;
  --text-secondary:#5A6A7E;
  --text-muted:    #8E9BB0;
  --brand:         #0B2E5C;
  --action:        #1749C4;
  --action-hover:  #1239A6;
  --action-light:  #EAF0FC;
  --action-border: #BBCEF5;
  --status-done:   #10B981;
  --status-active: #1749C4;
  --status-pending:#8E9BB0;
  --status-warn:   #D97706;
}

/* 暗色仅预留作用域，暂不填色值，见 §4.2 */
.dark { /* TODO */ }

@theme inline {
  --color-bg:            var(--bg);
  --color-surface:       var(--surface);
  --color-border:        var(--border);
  --color-brand:         var(--brand);
  --color-action:        var(--action);
  --color-action-light:  var(--action-light);
  --color-action-border: var(--action-border);
  --color-status-done:   var(--status-done);
  /* ...其余同理 */

  --radius-input: 6px;   /* DSD：输入框、登录按钮 */
  --radius-btn:   8px;   /* DSD：Hero 按钮 */
  --radius-card:  10px;  /* DSD：卡片、Dashboard */
}
```

**硬性约束：任何组件不得出现硬编码颜色值。** 全部走 token，否则暗色模式的预留会失效。

### 4.2 暗色模式：只预留结构，不实现

DSD 未定义暗色色值，现在配等于设计工作前置。当前做法是保证「所有颜色经由 CSS 变量」这一条纪律，并预留 `.dark` 作用域。将来要做时只需补一套色值，不需要重构组件。

两处需要额外留意，它们是最容易漏掉的暗色债务：
- **Shiki 代码高亮主题** —— 初始化时就配成双主题（`themes: { light, dark }`），一次到位，后补要重新处理所有代码块
- **沙箱产出的图表图片** —— matplotlib 出的是浅底 PNG，暗色下会刺眼。将来若做暗色，需要在沙箱侧统一 matplotlib 样式，属于后端改动，提前记在这里

### 4.3 装饰系统分层

| 装饰 | 落地页 / 登录页 | 对话工作台 |
|---|---|---|
| 蓝调网格底纹（DSD §4.1） | 保留 | 保留 |
| 光标闪烁 `.cursor`（DSD §3） | 保留 | **保留，用作流式输出光标** |
| 旋转实时时间戳（DSD §4.2） | 保留 | 去掉 |
| Ticker 无限滚动条（DSD §9） | 保留 | 去掉 |

工作台去掉后两者的原因：35s 无限循环动画加每分钟触发的 `setInterval`，在教师长时间停留的界面上既分散注意力也无谓耗电。落地页是短暂停留，观感收益大于成本。

`.cursor` 是 DSD 里唯一能直接复用到工作台的动效资产 —— 它原本是 Hero 标题的终端光标，语义上正好对应 LLM 流式输出。

### 4.4 字体自托管

内网服务器访问不到 Google Fonts CDN，构建期就要处理：

- **Inter**、**JetBrains Mono**：子集化为 woff2 打包进 dist，本地 `@font-face` 声明。二者只用于英文标签、等宽数据与代码，子集后体积很小
- **中文**：不自托管。Noto Sans SC 全量数 MB，内网带宽不值得。走 DSD §3 字体栈里的 `PingFang SC` / `微软雅黑` 系统字体兜底

### 4.5 品牌标识

- **英文品牌名 `FinAgentPlatform`** —— 用于 Logo 文字、footer、页面 `<title>`
- **中文项目名「金融学院智能体平台」** —— 用于正文表述与文档

Logo 采用「学院塔形图标 + FinAgentPlatform 文字」的组合（DSD §6）。图标资产为 `doc/02visual/logo.svg`，取自学院院徽，色值 `--logo-red: #A61B29`。

**这是整套设计系统里唯一的暖色**，仅用于标示机构归属，不得扩散到界面任何元素。界面配色仍以深海军蓝 `--brand` 为唯一品牌色。

前端集成时 SVG 必须写成 `fill="currentColor"`，颜色由 CSS `color` 控制——深色背景反白只需覆盖 `color`，不要维护第二份 SVG 文件。

---

## 5. 目录结构

```
src/
├─ styles/theme.css          # DSD token 映射，全站唯一颜色来源
├─ lib/
│  ├─ sse.ts                 # fetch-event-source 封装 + Last-Event-ID 维护
│  ├─ events.ts              # Zod schema，SSE 事件类型定义
│  └─ api.ts                 # REST 客户端
├─ components/ui/            # shadcn 改造后的基础件（Button/Dialog/Table…）
├─ features/
│  ├─ chat/                  # 消息流、工具调用块、审批卡片、输入区
│  └─ admin/                 # 用户、配额、run 历史（RBAC 定义后展开）
├─ hooks/useRunStream.ts     # 订阅 run 事件流，含断线重放
└─ routes/
```

---

## 6. 下一步

1. **扩写 DSD 第二章「工作台组件规范」**（已确认采用此路径，先文档后实现）
   需覆盖：消息气泡（用户/assistant 区分）、会话侧边栏、`execute` 的命令与 stdout/stderr 折叠块、`write_file` 的代码块（[智能体设计 §6](./03agent-design.md) 要求代码先写成 `.py` 再执行，因此代码渲染挂在 `write_file` 而非执行工具上）、todo 与子 agent 嵌套展示、HITL 审批卡片、Toast / Modal / Dropdown / Tooltip、代码高亮配色主题。
   这些 DSD 现有章节完全没有覆盖 —— 它写的是落地页与登录页。
2. 规范评审通过后初始化工程，先落 §4.1 的 token 层
3. 按架构文档 §11 的 P0 目标接通 SSE 流式输出

---

## 7. 待确认

| 项 | 说明 |
|---|---|
| **DSD 内的示例文案** | 视觉文件搬运自其他项目，品牌标识与业务文案均已清理：界面示例文案统一替换为占位符（`标题文字示例`、`导航项一`、`领域一`、`标签一` 等），规范正文改为本平台口径。待 RBAC 与功能模块确定后，按实际导航项与模块名填入真实文案 |
| **响应式范围** | DSD 全篇为固定 px（navbar `padding: 0 40px`、Dashboard 卡片 `width: 480px`），未定义任何断点。若教师需要用平板或手机查看报告，须先补断点规范；若仅限桌面浏览器，可跳过 |
