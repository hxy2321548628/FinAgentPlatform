# FinAgentPlatform 设计风格文档（DSD）

> 版本：v1.1
> 日期：2026-06-06（v1.1 增补于 2026-08-16）
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
| `--logo-green`    | `#A61B29` | 学校绿，**仅用于 Logo**，不参与界面配色 |
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
  --logo-green:      #A61B29;   /* 仅 Logo，见 §6 */
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

图标取自中南财经政法大学金融学院院徽，使用 `--logo-green`（`#A61B29`）。这是本设计系统中唯一的暖色，作为机构标识独立存在——它标示平台的归属，不参与界面配色（见 §2 配色原则的例外条款）。

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
  color: var(--logo-green);
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
| Navbar | 24px | `--logo-green` |
| 登录页 / 页面级标识 | 40–48px | `--logo-green` |
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

## 第二章 工作台组件规范

> v1.1 增补（2026-08-16）。第一章只覆盖营销页与登录页 —— 选型文档 §6 曾把
> 「扩写工作台规范」列为工作台开工前的第一步，这一步迟到了一整个 P6-P11。
> 本章补上它，作为 P0-2/P0-3 无障碍改造与 P1 组件层重构的唯一规格来源。
> 已实现的部分（答复渲染层，见 [04-answer-rendering-plan](./04-answer-rendering-plan.md)）
> 以「✅ 已落地」标注；其余是待实现的规格。
>
> v1.2 增补（2026-08-16）：对话页十条使用反馈的改造口径 —— 助手头像改 Logo、
> 思考块默认收起单行流式、会话三点菜单、输入区/配置弹窗重设计（标签页 +
> 固定尺寸 + 选项分页）、工作台侧栏视觉刷新、欢迎页懒创建、配置会话级持久化、
> 会话搜索与历史轮次视口自动回放，分别落在 §2.1/§2.3/§2.5/§2.7。

### 2.1 布局与三层导航

```
┌────────┬─────────┬──────────────────────────────┬──────────┐
│ Workspace│ Thread  │  主区                        │ 文件面板  │
│ 侧栏     │ 侧栏    │  header 54px                │ 380px    │
│ 220px    │ 240px   │  消息流（可滚动，padding 0 28px）│ （可收起） │
│ 深色      │ 浅色    │  输入区（贴底，随滚动不覆盖消息）  │          │
└────────┴─────────┴──────────────────────────────┴──────────┘
```

- Workspace 侧栏：深色 `--ws-sidebar-bg`，宽 220px，导航项 13px。**导航项
  圆角药丸式**（border-radius 8、左右 8px 留白），激活态 `--ws-sidebar-accent`
  底白字；hover `--ws-sidebar-hover`（激活态不叠加 hover）。**导航分组带小标题**
  （概览 / 分析 / 资源 / 系统，10px 字距拉开）；用户区为 Radix DropdownMenu
  （返回首页 / 退出登录），退出失败在用户区下方行内 `role="alert"`。
  （2026-08-16 视觉刷新：以药丸高亮替代旧「3px 左沿」方案。）
- Thread 侧栏：浅色 `--surface`，宽 240px；「＋ 新建分析」按钮贴顶 ——
  **它只导航到 `/workspace/chat` 欢迎页，不建会话**（幂等）；下方是会话搜索框
  （300ms 防抖、服务端 `q` 标题模糊匹配）；行内操作收敛进「⋮」菜单
  （重命名 / 删除），悬停、聚焦或菜单打开时可见，触屏设备常显。
- 主区 header：高 54px，左为会话标题（截断省略），右侧操作按钮。
- 文件面板：宽 380px，可整体收起/展开（header 按钮），收起后主区消息流占满。
- **欢迎页（无会话态）**：主区居中显示 Logo + 标题「开始一次新的分析」+ 一句
  说明，输入区直接可用；**第一次发送才创建会话**（提交成功后再跳转到新会话，
  失败留在欢迎页保住草稿），不产生空会话。
- **响应式边界（P2）**：≥1280px 完整三栏；≥1024px 收起文件面板、两栏；
  <1024px 暂不承诺（见审查文档 §4.10）。

### 2.2 色彩补充：错误与警告 token 化

第一章只给了状态四色，错误/警告在组件里一直硬编码 `#DC2626` 族。补齐：

```css
:root {
  --danger:       #DC2626;   /* 错误文字、危险按钮 */
  --danger-bg:    #FEF2F2;   /* 错误底色 */
  --danger-border:#FECACA;
  --warn:         #92400E;   /* 警告文字 */
  --warn-bg:      #FFFBEB;
  --warn-border:  #FDE68A;
  --success:      #166534;   /* 成功文字（注册成功等） */
  --success-bg:   #F0FDF4;
  --success-border:#BBF7D0;
  --code-surface: #F0F3F8;   /* 代码块底（--code-bg 别名，见 2.6） */
}
```

**硬性约束**：组件不得再出现上述十六进制字面量；暗色模式靠覆盖这组变量成立。
（✅ 已落地 2026-08-16：19 个文件 111 处替换；AdminUsers 的 ROLE_STYLE 角色徽章
是语义色，有意保留字面量。）

### 2.2.1 暗色色板（2026-08-16 增补）

选型文档 §4.2 原决策「只预留结构不实现」。P1 把状态色 token 化、组件 class 化、
Shiki 变量主题全部落地后，暗色的前置条件已经满足 —— 成本从「重构组件」降为
「补一套变量」。**决策变更：本期实现**，规则：

- 只覆盖 `:root` 变量，组件零改动；作用域 `<html class="dark">`；
- 背景 `#10141D` / 表面 `#1A2030`，`--text-muted` 提亮至 `#8490A8`
  （实测对比度 bg 5.7:1 / surface 5.1:1，全系 ≥ 4.5:1）；
- Shiki token 色随 `--shiki-*` 变量一起换，代码块零改动；
- 主题三态：浅色 / 深色 / 跟随系统，持久化 localStorage（`finagent-theme`）；
  **切换入口在公共站顶栏（Navbar）**，对所有访问者（含未登录）开放；设置页留
  同一入口，两处靠 `theme.ts` 的订阅机制同步。
- **已知债务**：沙箱产出的 matplotlib PNG 是浅底图，暗色下预览区保持浅底
  （内容区豁免），暗色图表需要沙箱侧统一 matplotlib 样式（后端改动，另立）。

### 2.3 消息流组件

| 组件 | 规格 |
|---|---|
| 用户气泡 | 右对齐，`--brand` 底白字，圆角 `12px 12px 2px 12px`，max-width 620px；**下方不再显示「本轮配置」**（冗余信息，配置在配置弹窗可见，历史快照在 run 数据里） |
| 助手消息 | 左对齐，32px 圆角方块头像（`--brand` 底、白色平台 Logo，Logo 组件一份复用）+ 白色气泡，圆角 `2px 12px 12px 12px` |
| 思考块 | `<details>` **默认收起**；标题行 `[状态点]「{来源} · 分析思路」+ 单行流式预览 + 折叠箭头`，流式中的思考 token 以单行省略方式实时内联在标题行（仿 DSH Web），点击展开完整 Markdown；流式结束后自动回到收起态 |
| 工具调用块 | 全宽可折叠按钮：状态符（◉ 运行 / ✓ 成功 / ✗ 失败）+ 工具名 + 详情；展开后 mono 展示参数与结果 |
| 子智能体组 | `<details>` 卡片，标题为子智能体名 + 「N 条过程」，内部条目嵌套渲染 |
| 审批卡片 | 琥珀系（`--warn-*`），`fieldset/legend` 按操作分条，决策按钮四选一 |
| 流式光标 | 流式态末条答复尾部 `.cursor`（3px 宽、`--action` 底、`blink 1.1s step-end`），`aria-hidden`；✅ 已落地 |
| 历史轮次回放 | **滚进视口自动回放**（IntersectionObserver，rootMargin 上下各 600px，粘住不回退），不再要求逐条点击「查看本轮回答与过程」；运行中的轮次始终回放；IO 不可用时退化立即回放，按钮保留为异常兜底 |

消息流容器挂 `aria-live="polite"`（✅ 已落地）；定稿消息不因其他消息流式而重渲染。

### 2.4 状态与反馈

| 反馈 | 规格 |
|---|---|
| 加载中 | 列表与卡片用骨架屏（Skeleton：灰底 shimmer 1.4s，`prefers-reduced-motion` 下静态）✅ 已落地；非列表场景仍可用「正在加载…」文字 |
| 空状态 | 居中文字 + 行动指引（如「还没有分析对话」），不渲染残缺 UI |
| 错误 | 行内 `role="alert"`，`--danger` 色，含下一步动作（如「请重试」） |
| 成功/失败通知 | Toast：右上角、3s 自动消失、三态（success/error/default）、可手动关闭、`aria-live` 由 Radix 语义承载 ✅ 已落地（`components/ui/Toast.tsx`，Radix Toast） |
| 危险操作 | 一律自定义确认弹窗（2.8），**禁止 `window.confirm`**；文案明确「不可撤销」（后端无恢复端点，不做假撤销）✅ 已落地 |

### 2.5 输入区

- 组合框（composer）：`--surface` 底、1px `--border`、圆角 14、聚焦时
  `--action-border` 描边 + 轻微阴影；无边框 `<textarea>` 随内容自动长高
  （min 48px / max 180px），14px 字号，placeholder「输入分析需求…（Enter 发送，
  Shift+Enter 换行）」；底部一行：左「本轮配置」胶囊（配置摘要 + 折叠箭头，
  打开配置弹窗）、右提示文案与发送按钮。
- 发送按钮：36×36px 圆角 9、`--action` 底、`aria-label="发送"`；运行中替换为
  同尺寸停止按钮（`--danger` 底、`aria-label="停止分析"`）。
- 欢迎页时输入区随主区居中（max-width 720px、无顶部边框），可直接输入。
- **配置持久化**：配置以会话为粒度存 `thread.agent_config`（PATCH
  `/threads/{id}`）。「完成」与发送时都会把当前配置写回会话默认（继承模式且
  无追加时不写）；重新打开会话自动回填表单。欢迎页懒创建时随首次发送一并写入。
  会话默认稳定即 system prompt 稳定，直接影响 kv cache 命中率。

### 2.6 答复渲染规范（✅ 已落地，2026-08-16）

详见 [对话答复渲染层实现方案](./04-answer-rendering-plan.md)，规格摘要：

| 项 | 规格 |
|---|---|
| 结构 | GFM（标题/列表/表格/任务列表/删除线）；标题 15-20px，正文 14px/1.75 |
| 代码块 | Shiki 按需高亮（python/json/bash/markdown/sql/r/latex/yaml），`--code-surface` 底、圆角 8、右上角语言角标；未高亮降级 `data-unhighlighted` |
| 代码配色 | **CSS 变量主题**：token 颜色全部是 `--shiki-*`（定义于 theme.css），暗色模式只改变量 |
| 公式 | **仅块级 `$$`**（KaTeX，字体本地打包）；行内 `$` 关闭 —— 金融语境中 `$` 是金额 |
| 图片 | 文内图片：相对路径仅 `outputs/` 白名单 → raw URL；外链 lazy + no-referrer；白名单外降级为文件名文本 |
| 产物区 | run 终态后，`outputs/` 且 `modified_at ≥ started_at` 的文件：PNG 缩略图（点击新标签开原图）、其余下载卡；>6 个折叠 |
| 安全 | 不渲染原始 HTML；链接协议白名单；外链 `rel="noopener noreferrer"` |

### 2.7 弹窗（Dialog）规范

- 遮罩 `rgba(11,46,92,0.25)`（浅底）/ `rgba(13,24,41,0.35)`（深底）；面板
  `--surface`、圆角 10-12、阴影 `0 16px 45px rgba(11,46,92,0.2)`；
- 行为：打开即焦点入面板、Tab 焦点圈在面板内、Esc 关闭、点击遮罩关闭、
  `overscroll-behavior: contain`；
- 语义：`role="dialog" aria-modal="true"`；确认类用 `role="alertdialog"`。
- **配置弹窗（本轮智能体配置）**：`min(560px, 100vw-32) × min(560px,
  100vh-48)` 固定尺寸（换页签不跳动），四段布局：标题头 / 标签条 / 滚动主体 /
  底部操作条（场景名称 + 保存场景 + 完成）。**标签页**：智能体 / Skill /
  子智能体 / MCP，每页只装一类配置，页签带已选数量徽标（`role="tablist"`，
  左右方向键切换）。挂载页的选项列表**固定高度内部滚动 + 分页加载**（每页 12
  个，「加载更多（还剩 N 个）」；列表 >6 项时带筛选框）。校验失败时自动跳到
  出错页签并展示 `role="alert"`。
- **✅ 已落地（2026-08-16）**：Radix Dialog/AlertDialog（`theme.css` 的
  `.dialog-*` class 承载 DSD 视觉）；ConfirmDialog 与 ChatInput 配置弹窗已迁移，
  其余存量弹窗（MySkills / PublishDialog 的手写 modal）按此规格在后续迁移。

### 2.8 无障碍与交互基线（P0-2 改造口径）

| 规则 | 说明 |
|---|---|
| 焦点可见 | 全局 `:focus-visible` 2px ring（`--action` 系），**禁止 `outline: none` 无替代** |
| 导航语义 | 可跳转元素一律 `<Link>`/`<a>`/`<button>`，**禁止 `div onClick` 导航** |
| 图标按钮 | 一律 `aria-label`；`title` 不替代 |
| 触控目标 | 交互元素 ≥ 40×40px（视觉可更小、命中区放大）；行内小图标按钮例外 ≥ 28×28px 且与邻近元素间距 ≥ 8px |
| 对比度 | 文字 ≥ 4.5:1；`--text-muted` 已加深至 `#5D6D82`（白底 5.3:1 / 灰底 4.6:1，实测）；内容性说明文字 ≥12px，10-11px 仅限装饰性标签 |
| 动效降级 | `prefers-reduced-motion: reduce` 下关闭 ticker/blink/thinking-bounce（✅ 已落地） |
| 页面元数据 | `lang="zh-CN"`、`<meta name="description">`、`theme-color` 随 `--bg` |
| 跳转链接 | 主内容前提供 skip link |
| 危险操作 | 确认弹窗 + 明确不可撤销文案（见 2.4） |

### 2.9 编号与命名

- 组件文件放 `src/workspace/components/`；营销页组件在 `src/components/`；
- 样式入口唯一：`src/styles/theme.css`；组件内不写十六进制颜色字面量；
- 图标统一走 `lucide-react`（`strokeWidth=1.5`），内联 SVG 仅限 LOGO 与一次性装饰。

---

*最后更新：2026-08-16*
