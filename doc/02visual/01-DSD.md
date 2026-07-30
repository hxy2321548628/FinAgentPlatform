# FinAgentPlatform 设计风格文档（DSD）

> 版本：v1.0
> 日期：2026-06-06
> 项目：金融学院智能体平台

---

## 一、风格定位

**名称：Intelligence-Minimal（情报极简风）**

整体气质是"冷静、可靠的高技术感"：深海军蓝作为锚色，冷灰调底色，配合工程/终端美学的细节装饰。不追求视觉冲击，而是传递**分析深度、数据可信、系统专业**的品牌调性。面向需要做专业分析决策的用户。

核心关键词：**深海军蓝 · 冷灰底色 · 报告感排版 · 装饰克制 · 数据化视觉**

---

## 二、色彩系统

### 基础色板

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg`         | `#EDF0F5` | 页面背景，冷蓝灰色调，非纯白 |
| `--surface`    | `#FFFFFF` | 卡片、面板背景 |
| `--border`     | `#D4DCE8` | 分割线、输入框、卡片边框（带蓝色底调） |
| `--border-light` | `#E8EDF4` | 更浅的内部分割线 |
| `--text-primary`   | `#0D1829` | 主文字（近黑，含蓝色底调，比纯黑更冷静） |
| `--text-secondary` | `#5A6A7E` | 次级文字（蓝灰调，替代中性灰） |
| `--text-muted`     | `#8E9BB0` | 占位符、禁用、注释文字 |

### 品牌色与强调色

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--brand`       | `#0B2E5C` | 品牌深海军蓝，用于导航激活态、重要强调 |
| `--logo-red`    | `#A61B29` | 学校红，**仅用于 Logo**，不参与界面配色 |
| `--action`      | `#1749C4` | 主交互色：按钮、链接、选中态（比亮蓝更沉稳） |
| `--action-hover`| `#1239A6` | 按钮 hover 态 |
| `--action-light`| `#EAF0FC` | 轻量填充背景（选中卡片、标签 active 态） |
| `--action-border`| `#BBCEF5` | 选中态边框颜色 |

### 状态色

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--status-done`    | `#10B981` | 完成 / COMPLETE |
| `--status-active`  | `#1749C4` | 进行中 / IN PROGRESS |
| `--status-pending` | `#8E9BB0` | 待处理 / PENDING |
| `--status-warn`    | `#D97706` | 警告 / 注意（谨慎使用） |

### CSS 变量声明

```css
:root {
  --bg:            #EDF0F5;
  --surface:       #FFFFFF;
  --border:        #D4DCE8;
  --border-light:  #E8EDF4;
  --text-primary:  #0D1829;
  --text-secondary:#5A6A7E;
  --text-muted:    #8E9BB0;

  --brand:         #0B2E5C;
  --logo-red:      #A61B29;   /* 仅 Logo，见 §6 */
  --action:        #1749C4;
  --action-hover:  #1239A6;
  --action-light:  #EAF0FC;
  --action-border: #BBCEF5;

  --status-done:   #10B981;
  --status-active: #1749C4;
  --status-pending:#8E9BB0;
}
```

### 配色原则

- **75% 冷灰无色系 + 25% 深海军蓝调**
- `--action`（`#1749C4`）用于所有可交互元素，不要用在纯装饰上
- Hero 大标题可用 `--action` 大面积着色（这是全站蓝色最集中的位置）
- 严禁引入暖色系（红、橙、黄）作为主调，仅限警告状态
- **唯一例外**：Logo 使用学校红 `--logo-red`，作为机构标识独立存在。该色不得扩散到按钮、链接、图表或任何界面元素上——界面配色仍以深海军蓝为唯一品牌色
- 不使用渐变作为主视觉，仅用于细节装饰

---

## 三、排版系统

### 字体栈

```css
font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont,
             'PingFang SC', 'Noto Sans SC', '微软雅黑', sans-serif;
```

- **中文正文/标题**：PingFang SC / Noto Sans SC / 微软雅黑
- **英文标签/装饰**：`Inter` 或 `monospace`，用于大写字母标签
- **数据/代码场景**：`'JetBrains Mono', 'Fira Code', monospace`

### 字号层级

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| Hero Display | 48–60px | Black/900 | Hero 主标题（"标题文字示例"） |
| Page Title   | 28–36px | Bold/700  | 页面级标题（"登录系统"、"页面标题"） |
| Section Label| 11–12px | 500，letter-spacing: 0.22em | 英文大写区块标签（"SECTION LABEL"） |
| Card Title   | 16–18px | SemiBold/600 | 卡片、模块标题 |
| Body         | 14–15px | Regular/400  | 正文、描述文字 |
| Tag / Badge  | 10–11px | 500，letter-spacing: 0.12em | 标签、状态徽章 |
| Caption      | 11px    | Regular | 底部注释 |
| Decoration   | 11–12px | Regular，opacity: 0.12–0.16 | 旋转装饰时间戳 |

### 特殊排版技巧

**1. 终端光标效果**（用于 Hero 标题末尾）

```css
.cursor {
  display: inline-block;
  width: 3px;
  height: 0.85em;
  background: var(--action);
  vertical-align: text-bottom;
  margin-left: 4px;
  animation: blink 1.1s step-end infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
```

**2. 英文标签全大写 + 宽字距**

```css
text-transform: uppercase;
letter-spacing: 0.2em;
font-size: 11px;
color: var(--text-muted);
```

**3. 中英文混排节奏**：大中文标题 + 小英文副标题，形成明显的视觉对比层级

**4. 括号标注前缀**：章节标题使用 `【模块名称】`、`【分类名称】` 等括号，增加报告体系感

---

## 四、背景装饰系统

### 1. 网格底纹

```css
.page-bg {
  background-color: var(--bg);  /* #EDF0F5 */
  background-image:
    linear-gradient(rgba(11, 46, 92, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(11, 46, 92, 0.035) 1px, transparent 1px);
  background-size: 40px 40px;
}
```

蓝调网格线（`rgba(11, 46, 92, ...)` 使用品牌深蓝色）比纯黑网格更契合整体冷色调。

### 2. 斜向实时时间装饰文字

在页面各 Section 角落放置旋转的当前时间文字，增强"系统运行中"的氛围。

```css
.deco-stamp {
  position: absolute;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.2em;
  color: rgba(11, 46, 92, 0.12);   /* 品牌深蓝，极低透明度 */
  transform: rotate(-45deg);
  user-select: none;
  pointer-events: none;
  white-space: nowrap;
}
```

**内容格式**：`ANALYSIS · HH:MM`（使用当前实时时间，每分钟更新）

```javascript
// 初始化并每分钟自动更新所有装饰时间戳
function updateDecoStamps() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const text = `ANALYSIS · ${hh}:${mm}`;
  document.querySelectorAll('.deco-stamp').forEach(el => {
    el.textContent = text;
  });
}
updateDecoStamps();
setInterval(updateDecoStamps, 60 * 1000);
```

**定位规范**：
- 使用 `position: absolute`，配合各 Section 的 `position: relative`
- 每个 Section 最多放 2 个（左上角 + 右下角），避免视觉噪音

```css
.deco-stamp-tl { top: 60px;  left: 80px; }
.deco-stamp-br { bottom: 60px; right: 80px; }
```

---

## 五、导航栏（Navbar）

```
┌──────────────────────────────────────────────────────────────────┐
│  [≡ 品牌名]  [导航项一]  [导航项二]  [导航项三]  [导航项四]  [👤] │
└──────────────────────────────────────────────────────────────────┘
```

```css
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 54px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 40px;
  gap: 36px;
}

.nav-link {
  font-size: 14px;
  color: var(--text-secondary);
  text-decoration: none;
  padding: 5px 12px;
  border-radius: 6px;
  transition: color 0.2s, background 0.2s;
}
.nav-link:hover { color: var(--text-primary); }

/* 激活状态：深海军蓝药丸 */
.nav-link.active {
  background: var(--brand);   /* #0B2E5C */
  color: #FFFFFF;
  font-weight: 500;
}
```

---

## 六、Logo 规范

**学院塔形图标 + 粗体品牌文字**

图标取自中南财经政法大学金融学院院徽，使用学校红 `--logo-red`（`#A61B29`）。这是本设计系统中唯一的暖色，作为机构标识独立存在——它标示平台的归属，不参与界面配色（见 §2 配色原则的例外条款）。

资产文件：`doc/02visual/logo.svg`，`viewBox="12 3 24 34"`，**竖版**，宽高比约 5:7。

```html
<a class="logo" href="/">
  <svg class="logo-icon" viewBox="12 3 24 34" fill="currentColor" aria-hidden="true">
    <path d="…" /><path d="…" />   <!-- 路径见 logo.svg -->
  </svg>
  <span class="logo-text">FinAgentPlatform</span>
</a>
```

```css
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.logo-icon {
  height: 24px;             /* 54px navbar 内的推荐高度 */
  width: auto;              /* 竖版，宽度按比例约 17px */
  color: var(--logo-red);
  display: block;
  flex-shrink: 0;
}

.logo-text {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
```

**SVG 必须使用 `fill="currentColor"`**，颜色一律通过 CSS `color` 控制。深色背景反白时只需覆盖 `color: #fff`，不要维护多份 SVG 文件。

### 使用规则

| 场景 | 图标高度 | 颜色 |
|---|---|---|
| Navbar | 24px | `--logo-red` |
| 登录页 / 页面级标识 | 40–48px | `--logo-red` |
| 深色背景反白 | 同上 | `#FFFFFF` |
| 页脚 | 22px | `rgba(255,255,255,0.6)` |

最小安全距离 = Logo 高度 × 1。

**禁止**：改变图标颜色（含改为交互蓝或警告色）、拉伸变形、旋转、添加投影或描边、改变图标与文字的相对比例。

---

## 七、Hero 区布局

Hero 采用**左文右图**两栏布局，右侧是模拟系统 Dashboard 的浮动卡片（展示分析任务进度）。

```
┌─────────────────────────────────────────────────────────┐
│ [Navbar]                                                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [● 状态徽章]                                            │
│                                                          │
│  标题文字示例              ┌────────────────────────┐   │
│  副标题文字示例            │ ● ● ●  系统分析进度     │   │
│  占位文字_                 │ ───────────────────── │   │
│                            │ 任务项一   COMPLETE    │   │
│  描述文字段落              │ 任务项二   IN PROGRESS  │   │
│                            │ 任务项三   PENDING      │   │
│  [主按钮]  [描边按钮]      └────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 状态徽章

```html
<div class="status-badge">
  <span class="dot"></span>
  智能体系统运行中 · 状态提示占位
</div>
```

```css
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px;
  border: 1px solid var(--border);
  border-radius: 100px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--surface);
}
.status-badge .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-done);   /* 绿色，表示系统在线 */
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}
```

### Hero 标题排版

```css
.hero-title-dark { color: var(--text-primary); font-size: 56px; font-weight: 900; line-height: 1.15; }
.hero-title-blue { color: var(--action);       font-size: 56px; font-weight: 900; line-height: 1.15; }
```

### Hero 主按钮（深蓝填充）

```css
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 48px;
  padding: 0 28px;
  background: var(--action);     /* #1749C4 */
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, transform 0.1s;
}
.btn-primary:hover  { background: var(--action-hover); }
.btn-primary:active { transform: scale(0.97); }
```

### Hero 描边次级按钮

```css
.btn-outline {
  height: 48px;
  padding: 0 24px;
  background: transparent;
  color: var(--text-primary);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.btn-outline:hover {
  border-color: var(--action-border);
  background: var(--action-light);
  color: var(--action);
}
```

---

## 八、模拟 Dashboard 卡片（Hero 右侧）

右侧浮动卡片展示智能体分析任务的实时进度，增强"系统正在工作"的视觉叙事。

```css
.dashboard-card {
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border);
  box-shadow:
    0 4px 8px rgba(11, 46, 92, 0.06),
    0 12px 40px rgba(11, 46, 92, 0.10);
  overflow: hidden;
  width: 480px;
}

/* macOS 风格窗口标题栏 */
.window-titlebar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  background: #F7F9FC;
  border-bottom: 1px solid var(--border-light);
}
.window-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--border);   /* 统一灰色，不用红黄绿 */
}
.window-title {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
  letter-spacing: 0.05em;
  font-family: monospace;
}
```

### Dashboard 数据表格

```css
.data-table { width: 100%; font-size: 12px; border-collapse: collapse; }

.data-table th {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 10px;
  color: var(--text-muted);
  padding: 8px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  font-weight: 500;
}
.data-table td {
  padding: 9px 16px;
  border-bottom: 1px solid #F5F7FA;
  color: var(--text-secondary);
}
/* 行ID：品牌蓝 */
.data-table .row-id    { color: var(--action); font-weight: 500; font-family: monospace; }
/* 状态文字 */
.status-complete       { color: var(--status-done);    font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; }
.status-in-progress    { color: var(--status-active);  font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; }
.status-pending        { color: var(--status-pending); text-transform: uppercase; letter-spacing: 0.08em; }
```

---

## 九、能力领域 Ticker 条

分隔 Section 的全宽横向滚动条，展示平台覆盖的能力领域。

```
SECTION LABEL
领域一  |  领域二  |  领域三  |  领域四  |  领域五  |  领域六  |  ...  →（无限滚动）
```

```css
.ticker-wrap {
  width: 100%;
  background: var(--surface);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 20px 0;
  overflow: hidden;
}
.ticker-label {
  text-align: center;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.28em;
  color: var(--text-muted);
  margin-bottom: 14px;
}
.ticker-track {
  display: flex;
  animation: ticker-scroll 35s linear infinite;
  width: max-content;
}
.ticker-item {
  padding: 0 32px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  border-right: 1px solid var(--border);
  white-space: nowrap;
}
@keyframes ticker-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }   /* 内容复制两份实现无缝循环 */
}
```

---

## 十、功能模块卡片

### Section 标题区

```html
<div class="section-header">
  <h2>【模块名称】功能模块</h2>
  <p class="section-desc">描述文字...</p>
  <div class="tab-group">
    <button class="tab active">标签页一</button>
    <button class="tab">标签页二</button>
    <button class="tab">标签页三</button>
    <button class="tab">标签页四</button>
  </div>
</div>
```

```css
.tab-group { display: flex; gap: 4px; }
.tab {
  padding: 7px 16px;
  font-size: 13px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.tab:hover  { background: var(--action-light); color: var(--action); }
.tab.active { background: var(--brand); color: #FFFFFF; font-weight: 500; }
```

### 卡片网格

```css
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
```

### 单张功能模块卡片

```css
.research-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.research-card:hover {
  border-color: var(--action-border);
  box-shadow: 0 4px 16px rgba(23, 73, 196, 0.08);
}
.research-card.active {
  border-color: var(--action);
  border-width: 1.5px;
  box-shadow: 0 4px 20px rgba(23, 73, 196, 0.12);
  background: #FAFCFF;
}
```

### 卡片内部结构

```
┌──────────────────────────────┐
│                              │
│        [stroke icon]         │  ← 细线风格 SVG 图标，居中，颜色 #BBCEF5
│      ICON LABEL CAPS         │  ← 10px 大写标签
│                              │
│  分析维度                     │  ← 小灰字（次级分类）
│  模块标题                     │  ← 粗体 16px
│  描述文字...                  │  ← 灰色 13px
│                              │
│  [TAG1] [TAG2] [TAG3]        │  ← 底部标签行
└──────────────────────────────┘
```

```css
.card-icon-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0 16px;
  gap: 8px;
}
.card-icon {
  width: 36px;
  height: 36px;
  color: var(--action-border);   /* #BBCEF5 浅蓝描边 */
  stroke-width: 1.5;
}
.card-icon-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

.card-dimension { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.card-title     { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.card-desc      { font-size: 13px; color: var(--text-secondary); line-height: 1.65; flex: 1; }

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}
.card-tag {
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 3px;
}
/* 激活卡片标签变蓝 */
.research-card.active .card-tag {
  color: var(--action);
  border-color: var(--action-border);
  background: var(--action-light);
}
```

---

## 十一、通用卡片与容器

```css
.card {
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border);
  box-shadow: 0 1px 4px rgba(11,46,92,0.05), 0 4px 16px rgba(11,46,92,0.06);
  padding: 32px;
}
```

---

## 十二、表单组件（登录页）

### 输入框

```css
.input {
  width: 100%;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 12px;
  font-size: 14px;
  color: var(--text-primary);
  background: #F7F9FC;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input::placeholder { color: var(--text-muted); }
.input:focus {
  border-color: var(--action);
  background: var(--surface);
  box-shadow: 0 0 0 3px rgba(23, 73, 196, 0.1);
}
```

### 字段标签

```css
.field-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 8px;
}
```

### 主按钮（深海军蓝 CTA，登录场景）

```css
.btn-dark {
  width: 100%;
  height: 44px;
  background: var(--brand);    /* #0B2E5C */
  color: #ffffff;
  border: none;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.03em;
  transition: background 0.15s, transform 0.1s;
}
.btn-dark:hover  { background: #0E3870; }
.btn-dark:active { transform: scale(0.98); }
```

---

## 十三、动效规范

| 场景 | 属性 | 时长 | 缓动 |
|------|------|------|------|
| 按钮 hover | background, color | 150ms | ease |
| 输入框 focus | border-color, box-shadow | 200ms | ease |
| 卡片 hover | border-color, box-shadow | 200ms | ease |
| 卡片入场 | opacity + translateY(16px→0) | 400ms | ease-out |
| 终端光标 | opacity 0↔1 | 1.1s | step-end, infinite |
| Ticker 滚动 | translateX | 35s | linear, infinite |
| 时间戳更新 | — | 每 60s 触发 JS 更新 | — |

**原则**：装饰性动画慢而优雅，交互反馈快而精准。不做弹跳、旋转等夸张动效。

---

## 十四、页面整体结构

```
┌──────────────────────────────────────────────────────┐
│  Navbar（sticky，毛玻璃背景，深海军蓝激活态）          │
├──────────────────────────────────────────────────────┤
│  Hero Section                                        │
│  ├── 左：状态徽章 + 大字标题（黑+蓝）+ CTA 按钮组    │
│  └── 右：分析进度 Dashboard 模拟卡片                  │
│  背景：蓝调网格纹 + 斜向实时时间装饰文字              │
├──────────────────────────────────────────────────────┤
│  Ticker 条（全宽，SECTION LABEL 领域名无限滚动）      │
├──────────────────────────────────────────────────────┤
│  功能模块 Section                                    │
│  ├── Section 标题 + 描述 + Tab 切换                  │
│  └── 4 列卡片网格（图标 + 维度 + 标题 + 标签）        │
│  背景：斜向实时时间装饰文字                           │
├──────────────────────────────────────────────────────┤
│  更多 Section...                                     │
└──────────────────────────────────────────────────────┘
```

---

## 十五、核心设计原则

1. **留白即设计**：大量空白让核心内容"呼吸"，padding 充足，不拥挤
2. **装饰不干扰**：背景装饰 opacity < 0.16，永远不抢夺视线
3. **深海军蓝定调**：用 `#0B2E5C` 传递可靠、权威、专业的学术机构气质
4. **冷色系贯通**：所有灰色带蓝色底调（`#5A6A7E`、`#8E9BB0`），而非中性灰
5. **终端美学点缀**：等宽字体、全大写标签、网格底纹、实时时间戳、光标闪烁
6. **数据即设计**：用数据表格、状态徽章、进度指标来传递分析系统的专业感
7. **排版建立层次**：字号跨度大（11px~56px），层级清晰，无需依赖颜色区分

---

*最后更新：2026-06-02*
