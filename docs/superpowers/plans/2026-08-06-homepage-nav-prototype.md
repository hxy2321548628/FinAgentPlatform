# 首页与导航页实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成首页 + 三个导航页的 HTML 原型，并在此基础上用 Vite + React + TypeScript + Tailwind v4 生成可跑通的前端代码。

**Architecture:** 两阶段交付。第一阶段：更新 prototype/ 目录下的静态 HTML（共享 shared.css），快速验证布局与内容。第二阶段：在 web/ 目录下初始化 React 项目，按照 02frontend-selection.md 的技术选型实现四个页面组件，可通过 `pnpm dev` 本地运行。

**Tech Stack:** HTML/CSS（原型）· Vite 7 · React 19 · TypeScript 5 · Tailwind CSS v4 · React Router 7 · lucide-react · pnpm 11

---

## 文件结构

### 原型层（prototype/）
- 修改：`prototype/02-home.html` — 首页完整重写
- 新建：`prototype/04-scenarios.html` — 研究范式页
- 新建：`prototype/05-capabilities.html` — 技术底座页
- 新建：`prototype/06-data.html` — 数据要素页
- 修改：`prototype/shared.css` — 补充新增组件样式

### 前端工程层（web/）
- 新建：`web/` — Vite + React + TS 项目根
- 新建：`web/src/styles/theme.css` — DSD token 映射
- 新建：`web/src/components/Navbar.tsx` — 导航栏
- 新建：`web/src/components/Footer.tsx` — 页脚
- 新建：`web/src/components/DecoStamp.tsx` — 装饰时间戳
- 新建：`web/src/components/DashboardCard.tsx` — Agent 执行卡片
- 新建：`web/src/pages/Home.tsx` — 首页
- 新建：`web/src/pages/Scenarios.tsx` — 研究范式页
- 新建：`web/src/pages/Capabilities.tsx` — 技术底座页
- 新建：`web/src/pages/DataAssets.tsx` — 数据要素页
- 新建：`web/src/App.tsx` — 路由入口
- 新建：`web/src/main.tsx` — 应用挂载点

---

## Task 1：更新 shared.css，补充新增组件样式

**Files:**
- Modify: `prototype/shared.css`

- [ ] 在 shared.css 末尾追加以下新增样式：

```css
/* ══════════════════════════════════════
   VALUE CARDS（战略价值区三列卡片）
   ══════════════════════════════════════ */
.value-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 32px 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.value-card:hover {
  border-color: var(--action-border);
  box-shadow: 0 4px 16px rgba(23,73,196,0.08);
}
.value-card-icon {
  width: 44px; height: 44px;
  background: var(--action-light);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: var(--action);
  flex-shrink: 0;
}
.value-card-title {
  font-size: 18px; font-weight: 700; color: var(--text-primary);
}
.value-card-body {
  font-size: 14px; color: var(--text-secondary); line-height: 1.75;
}
.value-card-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 6px;
}
.value-card-list li {
  font-size: 13px; color: var(--text-muted);
  padding-left: 16px; position: relative;
}
.value-card-list li::before {
  content: '→';
  position: absolute; left: 0;
  color: var(--action); font-size: 11px;
}

/* ══════════════════════════════════════
   STRATEGIC BANNER（深色全宽战略横幅）
   ══════════════════════════════════════ */
.strategic-banner {
  background: var(--brand);
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  padding: 48px 80px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
.strategic-banner-text {
  font-size: 15px;
  color: rgba(255,255,255,0.75);
  line-height: 1.9;
  max-width: 860px;
  margin: 0 auto;
  font-family: 'Noto Sans SC', sans-serif;
}
.strategic-banner-text strong {
  color: #ffffff;
  font-weight: 600;
}

/* ══════════════════════════════════════
   ENTRY CARDS（快速入口三列）
   ══════════════════════════════════════ */
.entry-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px 24px;
  display: flex; flex-direction: column; gap: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
  cursor: pointer;
  text-decoration: none;
}
.entry-card:hover {
  border-color: var(--action-border);
  box-shadow: 0 4px 16px rgba(23,73,196,0.08);
}
.entry-card-title {
  font-size: 16px; font-weight: 600; color: var(--text-primary);
}
.entry-card-desc {
  font-size: 14px; color: var(--text-secondary); line-height: 1.7; flex: 1;
}
.entry-card-link {
  font-size: 13px; color: var(--action); font-weight: 500;
  display: flex; align-items: center; gap: 4px;
}

/* ══════════════════════════════════════
   SCENARIO SECTION（场景两栏布局）
   ══════════════════════════════════════ */
.scenario-section {
  max-width: 1300px; margin: 0 auto;
  padding: 80px 80px;
  display: flex; gap: 60px; align-items: flex-start;
  position: relative;
}
.scenario-section.reverse { flex-direction: row-reverse; }
.scenario-left { flex: 1; min-width: 0; }
.scenario-right { flex-shrink: 0; width: 420px; }
.scenario-context {
  font-size: 13px; color: var(--text-secondary); line-height: 1.8;
  padding: 16px 20px;
  background: var(--bg);
  border-left: 2px solid var(--action-border);
  border-radius: 0 6px 6px 0;
  margin-bottom: 28px;
}
.scenario-title {
  font-size: 24px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 12px;
}
.scenario-quote {
  font-size: 15px; color: var(--text-secondary);
  font-style: italic; line-height: 1.7;
  border-left: 2px solid var(--border);
  padding-left: 16px;
  margin-bottom: 20px;
}
.scenario-steps { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
.scenario-step {
  display: flex; align-items: flex-start; gap: 10px;
  font-size: 13px; color: var(--text-secondary);
}
.step-check { color: var(--status-done); flex-shrink: 0; font-weight: 600; }
.scenario-output {
  display: flex; flex-wrap: wrap; gap: 8px;
  font-size: 13px; color: var(--text-secondary);
  padding-top: 16px; border-top: 1px solid var(--border-light);
}
.output-item {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px; background: var(--bg);
  border: 1px solid var(--border); border-radius: 5px;
  font-size: 12px;
}

/* 终端执行卡片（场景右栏） */
.terminal-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 4px 8px rgba(11,46,92,0.06), 0 12px 40px rgba(11,46,92,0.10);
}
.terminal-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 14px;
  background: #F7F9FC;
  border-bottom: 1px solid var(--border-light);
}
.terminal-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--border); }
.terminal-title {
  font-size: 11px; color: var(--text-muted);
  margin-left: 6px; font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
}
.terminal-body {
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11.5px;
  line-height: 1.9;
  color: var(--text-secondary);
  background: var(--surface);
}
.tl-done { color: var(--status-done); }
.tl-running { color: var(--status-active); }
.tl-pending { color: var(--text-muted); }
.tl-indent { padding-left: 18px; color: var(--text-muted); font-size: 11px; }
.tl-divider { border: none; border-top: 1px solid var(--border-light); margin: 8px 0; }
.tl-summary { color: var(--status-done); font-weight: 500; }

/* ══════════════════════════════════════
   TECH STACK BLOCK（深色终端全宽区）
   ══════════════════════════════════════ */
.tech-block {
  background: var(--brand);
  padding: 60px 80px;
  position: relative; overflow: hidden;
}
.tech-block::before {
  content: '';
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}
.tech-inner { max-width: 1300px; margin: 0 auto; position: relative; }
.tech-pre {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  line-height: 1.9;
  color: rgba(255,255,255,0.75);
  white-space: pre;
}
.tech-pre .tc { color: rgba(255,255,255,0.35); }
.tech-pre .tk { color: #93C5FD; }
.tech-pre .tv { color: rgba(255,255,255,0.9); }
.tech-footer {
  margin-top: 24px;
  font-size: 13px;
  color: rgba(255,255,255,0.45);
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.05em;
}

/* ══════════════════════════════════════
   CAPABILITY CARDS（2×2 网格）
   ══════════════════════════════════════ */
.cap-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}
.cap-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px 24px;
  display: flex; flex-direction: column; gap: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.cap-card:hover {
  border-color: var(--action-border);
  box-shadow: 0 4px 16px rgba(23,73,196,0.08);
}
.cap-icon {
  width: 44px; height: 44px; border-radius: 10px;
  background: var(--action-light);
  display: flex; align-items: center; justify-content: center;
  color: var(--action);
}
.cap-title { font-size: 17px; font-weight: 600; color: var(--text-primary); }
.cap-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.7; flex: 1; }
.cap-note {
  font-size: 12px; color: var(--text-muted);
  padding-top: 10px; border-top: 1px solid var(--border-light);
  line-height: 1.6;
}
.cap-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.cap-tag {
  padding: 3px 8px; font-size: 10px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: 3px;
  font-family: 'JetBrains Mono', monospace;
}

/* ══════════════════════════════════════
   SECURITY SECTION
   ══════════════════════════════════════ */
.security-section {
  display: flex; gap: 60px; align-items: flex-start;
  max-width: 1300px; margin: 0 auto; padding: 80px;
}
.security-left { flex: 1; }
.security-right { flex: 1; display: flex; flex-direction: column; gap: 20px; }
.security-item {
  display: flex; gap: 14px; align-items: flex-start;
}
.security-check {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--action-light); color: var(--action);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-size: 13px; font-weight: 700;
  margin-top: 2px;
}
.security-item-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.security-item-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.65; }

/* ══════════════════════════════════════
   DATA PATH（双路径卡片）
   ══════════════════════════════════════ */
.data-paths {
  display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
  max-width: 1300px; margin: 0 auto; padding: 0 80px 80px;
}
.data-path-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 32px 28px;
  display: flex; flex-direction: column; gap: 20px;
}
.drop-zone {
  border: 1.5px dashed var(--border);
  border-radius: 8px; padding: 32px 20px;
  text-align: center; color: var(--text-muted);
  font-size: 13px; line-height: 1.8;
  background: var(--bg);
}
.drop-zone-formats {
  display: flex; justify-content: center; gap: 8px;
  margin-top: 12px;
}
.format-tag {
  padding: 3px 8px; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--action); background: var(--action-light);
  border: 1px solid var(--action-border); border-radius: 3px;
  font-family: 'JetBrains Mono', monospace;
}
.market-list { display: flex; flex-direction: column; gap: 10px; }
.market-item {
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; color: var(--text-secondary);
}
.market-icon {
  width: 28px; height: 28px; border-radius: 6px;
  background: var(--action-light); display: flex; align-items: center;
  justify-content: center; font-size: 14px; flex-shrink: 0;
}

/* ══════════════════════════════════════
   DATA LIFECYCLE（深色三栏时间线）
   ══════════════════════════════════════ */
.lifecycle-block {
  background: var(--brand); padding: 60px 80px;
  position: relative; overflow: hidden;
}
.lifecycle-block::before {
  content: '';
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}
.lifecycle-inner {
  max-width: 1300px; margin: 0 auto;
  display: grid; grid-template-columns: 1fr auto 1fr auto 1fr;
  gap: 0; align-items: start; position: relative;
}
.lifecycle-col { padding: 0 24px; }
.lifecycle-arrow {
  color: rgba(255,255,255,0.2);
  font-size: 24px; align-self: center; padding-top: 32px;
}
.lifecycle-col-title {
  font-size: 11px; font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase; letter-spacing: 0.25em;
  color: rgba(255,255,255,0.4); margin-bottom: 20px;
}
.lifecycle-items { display: flex; flex-direction: column; gap: 8px; }
.lifecycle-item {
  font-size: 13px; color: rgba(255,255,255,0.7);
  display: flex; align-items: center; gap: 8px;
}
.lifecycle-item::before { content: '·'; color: rgba(255,255,255,0.3); }

/* ══════════════════════════════════════
   PAGE HERO（导航子页 Hero）
   ══════════════════════════════════════ */
.page-hero {
  padding: 80px 80px 72px;
  max-width: 1300px; margin: 0 auto;
  position: relative;
}
.page-hero-label {
  font-size: 10px; font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase; letter-spacing: 0.3em;
  color: var(--text-muted); margin-bottom: 20px;
}
.page-hero-title {
  font-size: 40px; font-weight: 900; color: var(--text-primary);
  line-height: 1.2; margin-bottom: 20px;
}
.page-hero-desc {
  font-size: 16px; color: var(--text-secondary); line-height: 1.8;
  max-width: 640px;
}
.page-hero-data {
  margin-top: 24px;
  font-size: 11px; font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted); letter-spacing: 0.05em;
}

/* ══════════════════════════════════════
   SECTION WRAPPER
   ══════════════════════════════════════ */
.section-wrap {
  max-width: 1300px; margin: 0 auto; padding: 80px;
  position: relative;
}
.section-wrap-title {
  font-size: 32px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 12px;
}
.section-wrap-desc {
  font-size: 15px; color: var(--text-secondary); margin-bottom: 40px;
  max-width: 560px; line-height: 1.7;
}

/* ══════════════════════════════════════
   CTA SECTION
   ══════════════════════════════════════ */
.cta-section {
  text-align: center; padding: 80px;
  background: var(--surface);
  border-top: 1px solid var(--border);
}
.cta-title { font-size: 28px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.cta-desc { font-size: 15px; color: var(--text-secondary); margin-bottom: 32px; }
.cta-actions { display: flex; gap: 12px; justify-content: center; }

/* ══════════════════════════════════════
   FORMAT TABLE
   ══════════════════════════════════════ */
.format-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.format-table th {
  text-transform: uppercase; letter-spacing: 0.12em; font-size: 10px;
  color: var(--text-muted); padding: 10px 16px; text-align: left;
  border-bottom: 1px solid var(--border); font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}
.format-table td {
  padding: 12px 16px; border-bottom: 1px solid var(--border-light);
  color: var(--text-secondary);
}
.format-table tr:last-child td { border-bottom: none; }
.format-ext {
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  color: var(--action); font-weight: 500;
}
```

- [ ] 保存文件，用浏览器打开现有 `prototype/02-home.html` 确认 CSS 无报错

---

## Task 2：重写 prototype/02-home.html（首页）

**Files:**
- Modify: `prototype/02-home.html`

- [ ] 完整替换 `02-home.html` 为以下内容：

（见代码实现步骤，内容在下方 Task 2 实现块中）

- [ ] 浏览器打开确认：Hero 标题两行、Dashboard 卡片右对齐、三列价值卡片、深色横幅、Ticker 滚动、三列入口、Footer 正常显示

---

## Task 3：新建 prototype/04-scenarios.html（研究范式）

**Files:**
- Create: `prototype/04-scenarios.html`

- [ ] 按规格创建三个场景页面（见实现块）
- [ ] 浏览器打开确认：Hero 居中、三个场景左右交错、终端卡片、CTA 区

---

## Task 4：新建 prototype/05-capabilities.html（技术底座）

**Files:**
- Create: `prototype/05-capabilities.html`

- [ ] 按规格创建技术底座页（见实现块）
- [ ] 确认：2×2 能力卡片、深色技术栈区、安全隔离两栏

---

## Task 5：新建 prototype/06-data.html（数据要素）

**Files:**
- Create: `prototype/06-data.html`

- [ ] 按规格创建数据要素页（见实现块）
- [ ] 确认：深色 Hero、生命周期区、双路径卡片、格式表格

---

## Task 6：初始化 web/ 前端工程

**Files:**
- Create: `web/` 目录及工程文件

- [ ] 在 `FinAgentPlatform/` 目录下执行：
```bash
cd web
pnpm create vite . --template react-ts
pnpm install
pnpm add react-router-dom@7 lucide-react
pnpm add -D tailwindcss @tailwindcss/vite
```

- [ ] 确认 `pnpm dev` 能启动，浏览器访问 `http://localhost:5173` 看到默认页

---

## Task 7：配置 Tailwind v4 + DSD Token

**Files:**
- Modify: `web/vite.config.ts`
- Create: `web/src/styles/theme.css`
- Modify: `web/src/main.tsx`

- [ ] `vite.config.ts` 添加 Tailwind 插件：
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

- [ ] 创建 `web/src/styles/theme.css`：
```css
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

:root {
  --bg:            #EDF0F5;
  --surface:       #FFFFFF;
  --border:        #D4DCE8;
  --border-light:  #E8EDF4;
  --text-primary:  #0D1829;
  --text-secondary:#5A6A7E;
  --text-muted:    #8E9BB0;
  --brand:         #0B2E5C;
  --logo-red:      #A61B29;
  --action:        #1749C4;
  --action-hover:  #1239A6;
  --action-light:  #EAF0FC;
  --action-border: #BBCEF5;
  --status-done:   #10B981;
  --status-active: #1749C4;
  --status-pending:#8E9BB0;
  --status-warn:   #D97706;
}

.dark { /* TODO */ }

@theme inline {
  --color-bg:             var(--bg);
  --color-surface:        var(--surface);
  --color-border:         var(--border);
  --color-border-light:   var(--border-light);
  --color-text-primary:   var(--text-primary);
  --color-text-secondary: var(--text-secondary);
  --color-text-muted:     var(--text-muted);
  --color-brand:          var(--brand);
  --color-action:         var(--action);
  --color-action-hover:   var(--action-hover);
  --color-action-light:   var(--action-light);
  --color-action-border:  var(--action-border);
  --color-status-done:    var(--status-done);
  --color-status-active:  var(--status-active);
  --color-status-pending: var(--status-pending);
  --color-status-warn:    var(--status-warn);
  --radius-input: 6px;
  --radius-btn:   8px;
  --radius-card:  10px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
@keyframes ticker-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

body {
  font-family: 'Noto Sans SC', 'PingFang SC', '微软雅黑', sans-serif;
  background-color: var(--bg);
  color: var(--text-primary);
}
```

- [ ] `web/src/main.tsx` 导入主题：
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles/theme.css'
import App from './App.tsx'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

---

## Task 8：实现公共组件

**Files:**
- Create: `web/src/components/Navbar.tsx`
- Create: `web/src/components/Footer.tsx`
- Create: `web/src/components/DecoStamp.tsx`
- Create: `web/src/components/DashboardCard.tsx`

- [ ] 创建 `web/src/components/DecoStamp.tsx`：
```tsx
import { useEffect, useState } from 'react'

export function DecoStamp({ className = '' }: { className?: string }) {
  const [text, setText] = useState('')
  useEffect(() => {
    const update = () => {
      const now = new Date()
      const hh = String(now.getHours()).padStart(2, '0')
      const mm = String(now.getMinutes()).padStart(2, '0')
      setText(`ANALYSIS · ${hh}:${mm}`)
    }
    update()
    const id = setInterval(update, 60000)
    return () => clearInterval(id)
  }, [])
  return (
    <span
      className={className}
      style={{
        position: 'absolute',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: '0.2em',
        color: 'rgba(11,46,92,0.12)',
        transform: 'rotate(-45deg)',
        userSelect: 'none',
        pointerEvents: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {text}
    </span>
  )
}
```

- [ ] 创建 `web/src/components/DashboardCard.tsx`：
```tsx
export function DashboardCard() {
  return (
    <div style={{
      background: 'var(--surface)', borderRadius: 10,
      border: '1px solid var(--border)',
      boxShadow: '0 4px 8px rgba(11,46,92,0.06), 0 12px 40px rgba(11,46,92,0.10)',
      overflow: 'hidden', width: 460, flexShrink: 0,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '10px 14px', background: '#F7F9FC',
        borderBottom: '1px solid var(--border-light)',
      }}>
        {[0,1,2].map(i => (
          <div key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border)' }} />
        ))}
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6, fontFamily: 'monospace', letterSpacing: '0.04em' }}>
          agent_executor · run_0x8B3F
        </span>
      </div>
      <div style={{ padding: 18, fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, lineHeight: 1.9, color: 'var(--text-secondary)' }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 8 }}>任务：持仓 CSV 年化波动率分析</div>
        <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', marginBottom: 8 }} />
        {[
          { status: 'done', icon: '✓', name: 'read_file', arg: 'portfolio.csv', time: '0.1s' },
          { status: 'done', icon: '✓', name: 'write_file', arg: 'volatility.py', time: '0.1s' },
          { status: 'run',  icon: '◉', name: 'execute',   arg: 'python volatility.py', time: '' },
          { status: 'pend', icon: '○', name: 'write_file', arg: 'outputs/vol_chart.png', time: '' },
        ].map((s, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
            <span style={{ color: s.status === 'done' ? 'var(--status-done)' : s.status === 'run' ? 'var(--action)' : 'var(--text-muted)', minWidth: 12 }}>{s.icon}</span>
            <span style={{ minWidth: 72, color: s.status === 'pend' ? 'var(--text-muted)' : undefined }}>{s.name}</span>
            <span style={{ color: 'var(--text-muted)', flex: 1 }}>{s.arg}</span>
            {s.time && <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{s.time}</span>}
          </div>
        ))}
        {['└─ Computing sector volatility...', '└─ Annualizing: 252 trading days'].map((l, i) => (
          <div key={i} style={{ paddingLeft: 20, color: 'var(--text-muted)', fontSize: 11 }}>{l}</div>
        ))}
        <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', margin: '8px 0' }} />
        <div style={{ color: 'var(--status-active)', fontWeight: 500 }}>◉ 执行中 · 已用时 3.2s</div>
      </div>
    </div>
  )
}
```

- [ ] 创建 `web/src/components/Navbar.tsx`：
```tsx
import { useState } from 'react'
import { NavLink } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/', label: '首页' },
  { to: '/scenarios', label: '研究范式' },
  { to: '/capabilities', label: '技术底座' },
  { to: '/data', label: '数据要素' },
]

export function Navbar() {
  const [open, setOpen] = useState(false)
  return (
    <nav style={{
      height: 56, flexShrink: 0,
      background: 'rgba(255,255,255,0.96)', backdropFilter: 'blur(10px)',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center',
      padding: '0 40px', gap: 4, position: 'sticky', top: 0, zIndex: 100,
    }}>
      <NavLink to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', marginRight: 20 }}>
        <svg style={{ height: 24, width: 'auto', color: 'var(--logo-red)' }} viewBox="12 3 24 34" fill="currentColor">
          <path d="M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z"/>
          <path d="M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z"/>
        </svg>
        <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
          FinAgentPlatform
        </span>
      </NavLink>
      <div style={{ display: 'flex', gap: 4, flex: 1 }}>
        {NAV_LINKS.map(({ to, label }) => (
          <NavLink key={to} to={to} end={to === '/'}
            style={({ isActive }) => ({
              fontSize: 13, textDecoration: 'none', padding: '5px 12px', borderRadius: 6,
              transition: 'all 0.2s',
              background: isActive ? 'var(--brand)' : 'transparent',
              color: isActive ? '#fff' : 'var(--text-secondary)',
              fontWeight: isActive ? 500 : 400,
            })}>
            {label}
          </NavLink>
        ))}
      </div>
      <div style={{ marginLeft: 'auto', position: 'relative' }}>
        <div onClick={() => setOpen(o => !o)} style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'var(--action-light)', border: '1px solid var(--action-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--action)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
        }}>张</div>
        {open && (
          <>
            <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 199 }} />
            <div style={{
              position: 'absolute', top: 'calc(100% + 8px)', right: 0,
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 10, boxShadow: '0 8px 24px rgba(11,46,92,0.12)',
              padding: 6, minWidth: 176, zIndex: 200,
            }}>
              <div style={{ padding: '8px 12px 10px' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>张老师</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>zhang@fin.edu.cn</div>
              </div>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <a href="/workspace" style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 600 }}>进入工作台 →</a>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <a href="#" style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-secondary)', textDecoration: 'none' }}>设置</a>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <a href="/login" style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: '#DC2626', textDecoration: 'none' }}>退出登录</a>
            </div>
          </>
        )}
      </div>
    </nav>
  )
}
```

- [ ] 创建 `web/src/components/Footer.tsx`：
```tsx
import { NavLink } from 'react-router-dom'

export function Footer() {
  return (
    <footer style={{
      padding: '32px 40px', background: 'var(--bg)',
      borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <NavLink to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
        <svg style={{ height: 20, color: 'var(--brand)' }} viewBox="12 3 24 34" fill="currentColor">
          <path d="M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z"/>
          <path d="M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z"/>
        </svg>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>FinAgentPlatform</span>
      </NavLink>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>© 2026 金融学院智能体平台</span>
      <div style={{ display: 'flex', gap: 24 }}>
        {[['研究范式','/scenarios'],['技术底座','/capabilities'],['数据要素','/data']].map(([label, to]) => (
          <NavLink key={to} to={to} style={{ fontSize: 13, color: 'var(--text-secondary)', textDecoration: 'none' }}>{label}</NavLink>
        ))}
      </div>
    </footer>
  )
}
```

---

## Task 9：实现 App.tsx 路由

**Files:**
- Modify: `web/src/App.tsx`

- [ ] 替换 `App.tsx`：
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import { Footer } from './components/Footer'
import { Home } from './pages/Home'
import { Scenarios } from './pages/Scenarios'
import { Capabilities } from './pages/Capabilities'
import { DataAssets } from './pages/DataAssets'

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Navbar />
        <main style={{ flex: 1 }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/scenarios" element={<Scenarios />} />
            <Route path="/capabilities" element={<Capabilities />} />
            <Route path="/data" element={<DataAssets />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
```

---

## Task 10：实现四个页面组件

**Files:**
- Create: `web/src/pages/Home.tsx`
- Create: `web/src/pages/Scenarios.tsx`
- Create: `web/src/pages/Capabilities.tsx`
- Create: `web/src/pages/DataAssets.tsx`

（各页面详细代码在实现阶段生成，结构完全对应规格文档中每个页面的各 section）

- [ ] 实现 `Home.tsx` — Hero + 战略价值区 + Ticker + 快速入口
- [ ] 实现 `Scenarios.tsx` — Hero + 三个场景（交错布局）+ CTA
- [ ] 实现 `Capabilities.tsx` — Hero + 2×2 能力卡片 + 深色技术栈 + 安全区
- [ ] 实现 `DataAssets.tsx` — Hero + 深色生命周期区 + 双路径卡片 + 格式表 + CTA
- [ ] `pnpm dev` 验证四个路由均可访问，视觉与 HTML 原型一致

---

## 自查清单

- [ ] 所有颜色使用 CSS 变量，无硬编码色值
- [ ] 英文标签全大写 + letter-spacing
- [ ] deco-stamp 在每个 section 角落出现
- [ ] Ticker 仅首页存在
- [ ] Logo 使用 `fill="currentColor"` 通过 color 控制颜色
- [ ] 导航 active 状态正确
- [ ] 四个页面路由均可访问
- [ ] `pnpm dev` 无 TS/lint 错误
