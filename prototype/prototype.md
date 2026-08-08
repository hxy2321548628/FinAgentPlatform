# FinDeepResearch 原型图说明文档

> 版本：v1.0
> 日期：2026-06-06
> 原型文件目录：`prototype/`

---

## 一、页面总览

| 文件 | 页面 | 入口 |
|------|------|------|
| `01-login.html` | 登录 / 注册页 | 默认落地页，未登录时跳转 |
| `02-home.html` | 首页 | 登录成功后跳转；导航栏"首页"链接 |
| `03-research.html` | 研究页 | 首页"开始研究"按钮；导航栏"研究平台"链接 |
| `04-knowledge.html` | 知识库页 | 首页"上传知识库"按钮；导航栏"知识库"链接 |
| `05-settings.html` | 设置页 | 导航栏头像下拉菜单"设置"项 |
| `shared.css` | 公共样式 | 所有页面通过 `<link>` 引入 |

**导航路径示意：**

```
01-login → 02-home ←→ 03-research
                  ←→ 04-knowledge
                  ←→ 05-settings（头像菜单）
```

---

## 二、公共组件（shared.css）

所有页面共享以下组件，实现时统一封装为 React 组件。

### 2.1 顶部导航栏（Navbar）

**结构：**
- 左侧：Logo（图标 + 文字 `FinDeepResearch`），点击跳转首页
- 中间：导航链接区（首页 / 研究平台 / 知识库），当前页链接有 `active` 高亮
- 右侧：用户头像（首字母），点击弹出下拉菜单

**头像下拉菜单内容：**
- 用户名 + 邮箱（只读展示）
- 分隔线
- "设置"→ 跳转 `05-settings.html`
- 分隔线
- "退出登录"→ 跳转 `01-login.html`，清除 Token

**交互：** 点击头像切换菜单显示/隐藏；点击页面任意其他区域关闭菜单。

### 2.2 CSS 设计令牌

| 变量 | 用途 |
|------|------|
| `--brand` | 品牌主色（深蓝 `#0B2E5C`） |
| `--action` | 交互色（蓝 `#1749C4`） |
| `--action-hover` | 交互色 hover 态 |
| `--action-light` | 交互色浅底（按钮背景、Tag 背景） |
| `--action-border` | 交互色边框 |
| `--surface` | 卡片/面板背景（白） |
| `--bg` | 页面底色（浅灰） |
| `--border` | 常规边框 |
| `--border-light` | 浅边框（分隔线） |
| `--text-primary` | 主文字色 |
| `--text-secondary` | 次级文字色 |
| `--text-muted` | 弱文字色（辅助说明） |
| `--status-done` | 成功状态绿色 |
| `--status-warn` | 警告状态橙色 |
| `--status-pending` | 待处理状态灰色 |

### 2.3 通用按钮

| 类名 | 样式 | 用途 |
|------|------|------|
| `.btn-dark` | 深蓝实心，全宽 | 表单主操作（登录/注册） |
| `.btn-primary` | 蓝色实心，自适应宽度 | 卡片主操作 |
| `.btn-outline` | 无色边框 | 次要操作（取消/刷新） |
| `.btn-danger` | 红色实心 | 危险操作（删除/注销） |
| `.icon-btn` | 图标按钮（28×28） | 表格行操作 |
| `.icon-btn.delete` | 图标按钮，hover 变红 | 删除操作 |

### 2.4 状态徽标

| 类名 | 颜色 | 文字 |
|------|------|------|
| `.status-complete` | 绿色 | `● Complete` |
| `.status-in-progress` | 蓝色 | `◉ In Progress` |
| `.status-pending` | 灰色 | `○ Pending` |
| `.badge-done` | 绿色 | `● 已完成` |
| `.badge-processing` | 蓝色 | `◉ 处理中` |

### 2.5 装饰元素

- `.grid-bg`：格子背景纹理，用于首页 Hero、登录页、知识库页、设置页
- `.deco-stamp`：左上/右下角的时间装饰文字（`ANALYSIS · HH:MM`），每分钟通过 `setInterval` 自动更新
- `.status-badge`：绿色运行状态指示点 + 文字

---

## 三、页面详细说明

### 3.1 登录 / 注册页（01-login.html）

**布局：** 居中双列卡片（宽 900px）

#### 左侧品牌区（固定宽 380px，深蓝背景）

- Logo + 品牌名
- 标语文案："行业深度研究 / 智能分析引擎"
- 三项数据统计：`20+ INDUSTRIES` / `5min AVG REPORT` / `99% UPTIME SLA`
- 右下角旋转装饰文字（`ANALYSIS · HH:MM`）

#### 右侧表单区

**Tab 切换：** "登录" / "注册" 两个 Tab，默认显示"登录"。

**登录面板字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| 邮箱地址 | `email` | placeholder: `your@company.com` |
| 密码 | `password` | - |
| 记住我 | `checkbox` | 默认勾选 |
| 忘记密码 | 链接 | 仅展示，暂无功能 |
| 登录按钮 | 全宽深蓝按钮 | 点击跳转首页 |

**注册面板字段：**

| 字段 | 类型 | 校验 |
|------|------|------|
| 用户名 | `text` | 必填 |
| 邮箱地址 | `email` | 必填，唯一 |
| 密码 | `password` | 至少 8 位 |
| 确认密码 | `password` | 与密码一致 |

**Tab 切换时：** 标题/副标题同步切换（"欢迎回来" ↔ "创建账户"）。

---

### 3.2 首页（02-home.html）

**整体结构（从上到下）：** Navbar → Hero 区 → Ticker 行业滚动条 → 行业分析模块卡片区 → 核心能力区 → Footer

#### Hero 区（左右两栏）

**左栏（max-width 560px）：**
- 绿色运行状态徽标
- 大标题（56px，两行：深色 + 蓝色）+ 打字机光标动画
- 副标题描述文字
- 两个 CTA 按钮：
  - "开始研究"（蓝色实心）→ 跳转 `03-research.html`
  - "上传知识库"（描边）→ 跳转 `04-knowledge.html`

**右栏 Dashboard 卡片（宽 460px）：**
- 仿终端标题栏（三个圆点 + `agent_executor · task_0x2F4A`）
- 任务标题 + 任务 ID 标签
- 四行任务状态表格（数据采集 Complete / 行业分析 In Progress / 竞争格局 Pending / 报告生成 Pending）
- 进度条（45%，持续脉冲动画）
- Agent 日志区（Mono 字体，三行模拟日志）

> **注意：** Dashboard 卡片为静态展示，无交互，纯视觉渲染运行感。

#### Ticker 行业滚动条

- 20+ 行业领域无缝循环滚动（CSS 动画 `ticker-scroll`，35s 线性）
- 行业列表：新能源、半导体、消费电子、人工智能、生物医疗、金融科技、云计算、自动驾驶……

#### 行业分析模块区

- 标题：`【行业分析】研究模块`
- 四个标签按钮（行业概览 / 竞争格局 / 技术路径 / 投资机会）：**仅视觉高亮，无内容切换功能**
- 4 列卡片网格：

| 卡片 | 图标标签 | 标题 | 关键词 Tag |
|------|---------|------|-----------|
| 市场规模测算 | MARKET SIZE | 市场规模测算 | TAM / CAGR / Forecast |
| 竞争格局分析 | COMPETITION | 竞争格局分析 | Porter / Moat / Share |
| 产业链图谱 | SUPPLY CHAIN | 产业链图谱 | Upstream / Value / Risk |
| 政策环境分析 | POLICY | 政策环境分析 | Regulation / Catalyst / ESG |

卡片 hover 时边框变蓝色、有阴影；点击无跳转。

#### 核心能力区（3 列）

| 标题 | 说明 |
|------|------|
| 端到端行研自动化 | LangGraph 驱动多智能体工作流 |
| 私有知识库融合 | PDF/Word/TXT 向量化，与公开数据融合 |
| 全链路可观测 | LangFuse 追踪每步推理与工具调用 |

---

### 3.3 研究页（03-research.html）

**整体布局：** 固定高度 `100vh`，`overflow: hidden`，三栏水平布局。

```
┌──────────┬──────────────────────────┬──┬───────────────┐
│          │                          │  │               │
│  左侧    │     主对话区              │  │  右侧面板      │
│  历史    │     (flex: 1)            │  │  (380px,      │
│  记录    │                          │  │  可拖拽)      │
│ (240px)  │                          │  │               │
│          ├──────────────────────────┤  │               │
│          │     底部输入区            │  │               │
└──────────┴──────────────────────────┴──┴───────────────┘
                                       ↑
                                  4px 拖拽分隔条
```

#### 3.3.1 左侧历史记录栏（固定宽 240px）

- 顶部"新建研究"按钮（蓝色实心，全宽）
- `// HISTORY` 标题
- 历史记录列表：每项显示标题 + 日期，当前活跃项高亮（蓝色背景）
- 每项右侧有删除图标，hover 时显示

**新建研究：** 点击后清空主对话区，显示欢迎消息。

#### 3.3.2 主对话区

**消息气泡类型：**

| 类名 | 位置 | 样式 |
|------|------|------|
| `.msg-user` | 右对齐 | 蓝色背景气泡 |
| `.msg-agent` | 左对齐 | 白色卡片，含 Agent 头像（三横线 Logo） |

**用户消息气泡：** 支持显示附件标签（文件名 + 回形针图标）。

**Agent 消息气泡内容类型：**
1. **工具调用步骤**（`.tool-step`）：Mono 字体，显示工具名 + 参数 + 返回摘要
2. **Markdown 报告内容**（`.report-content`）：支持 H2/H3/p/table 渲染
3. **思考中动画**（`.thinking`）：三个跳动圆点

#### 3.3.3 底部输入区

| 元素 | 行为 |
|------|------|
| 多行文本框 | `Enter` 发送，`Shift+Enter` 换行 |
| 附件按钮 | 触发隐藏的 `<input type="file">`，支持 `.pdf/.docx/.txt/.png/.jpg` |
| 暂停研究按钮 | 默认隐藏，发送中显示；点击后切换为"继续研究" |
| 继续研究按钮 | 暂停后显示；点击恢复执行 |
| 发送按钮（圆形蓝色） | 点击发送消息 |
| `Enter 发送` 提示 | 输入框右下角灰色文字 |

> **Token 用量展示：** 原型中未渲染，实现时需在输入框下方添加 `TokenUsage` 组件（参见 PRD）。

#### 3.3.4 右侧面板拖拽调宽

- 分隔条（`.panel-resize-handle`）宽 4px，位于面板左侧
- 监听 `mousedown` → `document.mousemove` → `mouseup` 事件序列
- 宽度范围：200px ~ 700px，默认 380px
- 分隔条 hover / 拖拽中变为蓝色（`var(--action)`）

#### 3.3.5 右侧面板四个 Tab

**Tab 列表：** 搜索结果 / 知识图谱 / 图表 / 过程报告

---

**Tab ① 搜索结果**

分为两个子区块：`// WEB SEARCH` 和 `// KNOWLEDGE BASE`

每条搜索结果卡片（`.search-result`）：
- 来源标签：`网络`（蓝色）或 `知识库`（绿色）
- 标题（粗体，13px）
- 摘要（2 行截断）
- 来源域名 或 相似度分数

---

**Tab ② 知识图谱**

- `// KNOWLEDGE GRAPH` 标签
- CSS 模拟节点图（原型为静态布局）：中心节点（深蓝实心）+ 四个周边节点（浅蓝描边）
- 实体关系列表：`实体A → 关系 → 实体B`（文字形式）

> 实现时替换为 ECharts Graph 组件，接收 `graph_update` WebSocket 消息增量更新。

---

**Tab ③ 图表**

- `// VISUALIZATIONS` 标签
- 柱状图占位（CSS 模拟）：中国新能源汽车年销量（2019-2024）
- 市占率图例（色块 + 文字）

> 实现时替换为 ECharts 动态渲染，接收 `chart_data` WebSocket 消息。

---

**Tab ④ 过程报告**

- 顶部下载操作栏：`下载 Markdown` + `下载 PDF` 两个按钮（带下载图标）
- 完整 Markdown 报告（连续单一文档，非折叠卡片）：
  - `H2`：主章节标题，带底部分隔线
  - `H3`：小节标题
  - 正文段落、**加粗**关键词
  - 数据表格（含表头、行数据）
- 报告元信息：生成时间 + 引用来源数量（Mono 字体，灰色）

---

### 3.4 知识库页（04-knowledge.html）

**整体结构（从上到下）：** Navbar → 页面标题区 → 统计卡片行 → 文档列表卡片

#### 页面标题区

- 左侧：`// KNOWLEDGE BASE` 标签 + 标题 + 描述文字
- 右侧操作区：`刷新` 按钮 + `上传文档` 蓝色按钮

#### 统计卡片行（4 列）

| 指标 | 示例值 | 单位 |
|------|--------|------|
| DOCUMENTS | 8 | 份 |
| CHUNKS | 1,247 | 段 |
| TOTAL SIZE | 84 | MB |
| LAST QUERY | 09:32 | 今日检索次数 |

#### 文档列表卡片

**表格列：** 文档名称（含文件图标 + 大小）/ 上传时间 / 文件大小 / 切片数 / 状态 / 操作

**文件图标色：**

| 类型 | 背景色 | 文字色 |
|------|--------|--------|
| PDF | 浅红 | 红色 |
| DOC/DOCX | 浅蓝 | 蓝色 |
| TXT | 浅绿 | 绿色 |

**操作列（每行）：**
- 查看图标按钮 → 弹出切片预览抽屉（处理中状态时禁用，透明度 0.4）
- 删除图标按钮 → 弹出删除确认对话框

**分页：** `显示 1-5 / 共 8 条`，上一页/数字/下一页按钮

#### 上传文档弹窗（Modal）

- 拖拽区（`.drop-zone`）：
  - 拖拽 hover 时边框变蓝、背景变浅蓝
  - 支持文件类型标签：`PDF` / `DOCX` / `TXT`
  - 限制说明：单文件最大 50MB
- `<input type="file" multiple>` 隐藏输入
- 底部按钮：`取消`（描边）+ `开始上传`（蓝色实心）

#### 切片预览抽屉（Drawer）

- 从右侧滑入（`translateX` 动画，0.25s ease）
- 标题：`{文件名} · 切片预览`
- 元信息：切片总数 / `chunk_size=512` / `overlap=64`
- 每个切片（`.chunk-item`）：
  - `CHUNK-001` 蓝色标签 + 页码（灰色）
  - 切片文本内容（13px，行高 1.7）

#### 删除确认对话框

- 红色警告图标
- 标题：`确认删除文档？`
- 说明：删除将永久清除文档及向量数据，不可恢复
- 按钮：`取消` + `确认删除`（红色）

---

### 3.5 设置页（05-settings.html）

**整体布局：** 左侧导航（200px 固定，sticky）+ 右侧内容区（flex: 1）

#### 左侧导航菜单

三个菜单项（点击切换右侧内容区）：

| 菜单项 | 对应 section ID |
|--------|----------------|
| 模型配置 | `section-model` |
| 通知 | `section-notify` |
| 账号 | `section-account` |

激活项左侧蓝色竖线 + 蓝色文字 + 浅蓝背景。

---

#### Section ① 模型配置

**本月用量卡片**（顶部固定，不随 Toggle 滚动）：

- 标题：`本月用量` + 统计周期
- 右上角 **FAST / DEEP / EMBED 三档 Toggle**
- 四格用量统计：SESSIONS / INPUT / OUTPUT / COST
- 两条进度条：Input Tokens 月度消耗 / 估算费用

**Toggle 切换逻辑：**

| Toggle | 用量数据 | 下方配置卡片 |
|--------|----------|-------------|
| FAST | 快速模型数据 | 显示 `model-card-fast` |
| DEEP | 思考模型数据 | 显示 `model-card-deep` |
| EMBED | 嵌入模型数据 | 显示 `model-card-embed` |

**快速回复模型配置卡片（FAST）：**

| 字段 | 类型 | 只读 | 示例值 |
|------|------|------|--------|
| 模型名称 | text | 否 | `gpt-4o-mini` |
| 提供商 | text | 否 | `OpenAI` |
| API Key | password | 否 | `sk-••••••Ax1m`，含显示/隐藏切换 |
| API Base URL | text | 否 | `https://api.openai.com/v1` |
| Input 单价 | number | **是** | `0.001 元/1K` |
| Output 单价 | number | **是** | `0.002 元/1K` |
| 本月估算费用 | 展示区 | - | `¥1.2` |

卡片底部：`测试连接` 按钮（点击 800ms 后显示"✓ 连接成功"）+ `保存` 按钮（保存后 2.5s 显示"已保存"提示）

**深度思考模型配置卡片（DEEP）：** 结构与 FAST 相同，示例值：`deepseek-r1` / DeepSeek / `0.004/0.016 元/1K`

**向量嵌入模型配置卡片（EMBED）：**

| 字段 | 类型 | 只读 | 示例值 |
|------|------|------|--------|
| 模型名称 | text | **是** | `bge-m3` |
| 向量维度 | text | **是** | `1024` |
| API Key | password | 否 | 含显示/隐藏切换 |
| API Base URL | text | 否 | `https://api.siliconflow.cn/v1` |

---

#### Section ② 通知

**飞书机器人通知卡片：**

- 配置状态提示（绿色）：`Webhook 已配置，上次推送成功：…`
- Webhook URL 输入框（Mono 字体）
- 推送内容复选框组：
  - [x] 报告标题与摘要（前 500 字）
  - [x] 报告访问链接
  - [ ] Token 用量与费用
- 底部：`发送测试消息` 按钮 + `保存` 按钮

---

#### Section ③ 账号

**账号信息卡片：**
- 头像（首字母圆形，蓝色背景） + 用户名 + 邮箱
- 用户名 / 邮箱输入框（可编辑）
- 底部：注册时间 + `保存` 按钮

**修改密码卡片：**
- 当前密码 / 新密码 / 确认新密码 三个 password 输入框
- 底部：`更新密码` 按钮

**危险操作区（红色边框）：**
- 标题：`危险操作`（红色）
- 操作：`注销账号`，说明文字 + 红色按钮

---

## 四、关键交互索引

| 交互 | 页面 | 实现方式 |
|------|------|----------|
| Tab 登录/注册切换 | 01-login | `display:block/none` 切换面板 |
| 导航栏头像下拉 | 所有页 | `classList.toggle('open')`，点击外部关闭 |
| 研究页右侧面板拖拽调宽 | 03-research | `mousedown/mousemove/mouseup`，限制 200-700px |
| 右侧面板 Tab 切换 | 03-research | `display:block/none` 切换 panel-content |
| 发送消息 | 03-research | 创建 `.msg-user` DOM 节点，`Enter` 触发 |
| 新建研究 | 03-research | 清空 `#chatMessages`，注入欢迎消息 |
| 上传文档 Modal | 04-knowledge | `classList.add/remove('show')`，遮罩点击关闭 |
| 切片预览 Drawer | 04-knowledge | 从右侧滑入，`translateX` 过渡 |
| 删除确认 Dialog | 04-knowledge | `classList.add/remove('show')` |
| FAST/DEEP/EMBED Toggle | 05-settings | 切换用量数据 + 显示对应模型配置卡片 |
| 左侧导航切换 Section | 05-settings | `classList.add/remove('active')` |
| 测试连接 | 05-settings | 800ms 延迟后显示结果文字 |
| 保存配置 | 05-settings | 2500ms 显示"已保存"提示后自动消失 |
| API Key 显示/隐藏 | 05-settings | `input.type` 在 `password`/`text` 间切换 |
| 装饰时间戳更新 | 登录/首页 | `setInterval` 每 60s 更新 `.deco-stamp` 文字 |

---

## 五、实现注意事项

1. **Ant Design 使用边界**：`Form`/`Modal`/`Upload`/`Tooltip` 等功能性组件可用；`Layout`/`Tabs`/`Sider` 等结构性布局组件**不用**，按原型 CSS 手写。

2. **研究页布局**：三栏用 flexbox 实现（`display:flex; height:100vh; overflow:hidden`），不用 Grid，便于拖拽调宽。

3. **右侧面板宽度**：`flex-shrink: 0`，通过 `style.width` 动态设置，初始 380px。

4. **WebSocket 消息渲染**：按 `type` 字段分发：
   - `token` → 追加到当前 Agent 气泡尾部（流式）
   - `tool_call/tool_result` → 在气泡内渲染 `.tool-step` 折叠块
   - `search_result/kb_result` → 推入右侧"搜索结果" Tab
   - `graph_update` → 更新 ECharts Graph
   - `chart_data` → 追加 ECharts 图表到"图表" Tab
   - `final_report` → 在"过程报告" Tab 渲染完整 Markdown
   - `token_usage` → 更新底部输入区 `TokenUsage` 组件

5. **Markdown 渲染**：使用 `react-markdown` + `remark-gfm`，需覆盖 `.report-content` 样式以匹配原型中的表格/标题样式。

6. **装饰时间戳**：前端实现时可用 `useEffect` + `setInterval` 每分钟更新，或直接渲染静态文字（非功能性 UI）。
