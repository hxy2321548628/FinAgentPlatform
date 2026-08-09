# 工作台 Plan 3：场景库 + 智能体广场 + 我的数据 + 我的智能体 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现工作台的四个内容页面：场景库、智能体广场（含发布表单）、我的数据、我的智能体，并接入路由。

**Architecture:** 四个独立页面组件，均为静态 mock 数据。每个页面自包含数据和状态，通过 WorkspaceRouter 挂载。所有页面共用 DSD token + 内联 style，风格与 Overview 页一致。

**Tech Stack:** React 18 + TypeScript · 内联 style + CSS 变量 · useNavigate 跳转

---

## 文件结构

```
web/src/workspace/pages/
├── AgentScenarios.tsx     ← 新建：场景库
├── AgentPlaza.tsx         ← 新建：智能体广场 + 发布表单（同文件两个导出）
├── MyData.tsx             ← 新建：我的数据
└── MyAgents.tsx           ← 新建：我的智能体
web/src/workspace/
└── WorkspaceRouter.tsx    ← 修改：接入四个页面
```

---

### Task 1：AgentScenarios（场景库）+ AgentPlaza（智能体广场 + 发布）

**Files:**
- Create: `web/src/workspace/pages/AgentScenarios.tsx`
- Create: `web/src/workspace/pages/AgentPlaza.tsx`

- [ ] **Step 1: 创建 AgentScenarios.tsx**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Scenario {
  id: string
  name: string
  subject: string
  subjectTag: string
  desc: string
  tags: string[]
  steps: number
  author: string
  uses: number
}

const SUBJECTS = ['全部', '金融学', '会计学', '经济学', '管理科学']

const MOCK_SCENARIOS: Scenario[] = [
  {
    id: 'risk',
    name: '企业风险分析',
    subject: '金融学',
    subjectTag: '金融学 · 产业研究',
    desc: '上传财报 CSV，识别偿债/盈利/运营风险信号，输出带证据链的风险报告草稿。',
    tags: ['财务分析', '风险识别', '报告生成'],
    steps: 5,
    author: '金融学院',
    uses: 127,
  },
  {
    id: 'replicate',
    name: '论文量化复现',
    subject: '金融学',
    subjectTag: '金融学 / 经济学 · 学术研究',
    desc: '上传数据集，复现回归模型，验证论文中的 alpha 显著性，输出复现报告。',
    tags: ['计量方法', '回归分析', '复现验证'],
    steps: 4,
    author: '金融学院',
    uses: 89,
  },
  {
    id: 'survey',
    name: '课题数据分析',
    subject: '管理科学',
    subjectTag: '全学科 · 科研支持',
    desc: '上传问卷或面板数据，进行描述统计、假设检验与可视化，输出分析结论。',
    tags: ['描述统计', '假设检验', '可视化'],
    steps: 4,
    author: '金融学院',
    uses: 203,
  },
  {
    id: 'factor',
    name: '量化因子研究',
    subject: '金融学',
    subjectTag: '金融学 · 量化投资',
    desc: '上传股票行情数据，构建因子序列，检验 alpha 显著性，生成因子收益图表。',
    tags: ['因子模型', 'Fama-French', 'alpha 检验'],
    steps: 5,
    author: '金融学院',
    uses: 64,
  },
]

export function AgentScenarios() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')

  const filtered = activeSubject === '全部'
    ? MOCK_SCENARIOS
    : MOCK_SCENARIOS.filter(s => s.subject === activeSubject || activeSubject === '全学科')

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>
          // SCENARIOS
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>场景库</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>选择分析场景，一键启动预配置的智能体分析流程</p>
      </div>

      {/* 学科筛选 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' as const }}>
        {SUBJECTS.map(s => (
          <button
            key={s}
            onClick={() => setActiveSubject(s)}
            style={{
              padding: '6px 16px', borderRadius: 20,
              border: '1px solid ' + (activeSubject === s ? 'var(--action)' : 'var(--border)'),
              background: activeSubject === s ? 'var(--action)' : 'var(--surface)',
              color: activeSubject === s ? '#fff' : 'var(--text-secondary)',
              fontSize: 13, fontWeight: activeSubject === s ? 600 : 400,
              cursor: 'pointer', fontFamily: 'inherit',
              transition: 'all 0.15s',
            }}
          >{s}</button>
        ))}
      </div>

      {/* 卡片网格 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {filtered.map(scenario => (
          <ScenarioCard key={scenario.id} scenario={scenario} onStart={() => navigate('/workspace/chat')} />
        ))}
      </div>
    </div>
  )
}

function ScenarioCard({ scenario, onStart }: { scenario: Scenario; onStart: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--surface)',
        border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'),
        borderRadius: 10, padding: '24px',
        display: 'flex', flexDirection: 'column' as const, gap: 12,
        cursor: 'default',
        boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
    >
      <div>
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{scenario.name}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{scenario.subjectTag}</div>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, flex: 1 }}>{scenario.desc}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
        {scenario.tags.map(tag => (
          <span key={tag} style={{ padding: '2px 8px', fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 3 }}>{tag}</span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, borderTop: '1px solid var(--border-light)', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>📊 {scenario.steps} 步分析 · 👤 {scenario.author}</span>
        <span>▶ {scenario.uses} 次</span>
      </div>
      <button
        onClick={onStart}
        style={{
          width: '100%', padding: '9px 0',
          background: 'var(--action)', color: '#fff',
          border: 'none', borderRadius: 7,
          fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          transition: 'background 0.15s',
        }}
      >开始分析 →</button>
    </div>
  )
}
```

- [ ] **Step 2: 创建 AgentPlaza.tsx（智能体广场 + 发布表单，两个导出）**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Agent {
  id: string
  name: string
  author: string
  subject: string
  desc: string
  dataNeeded: string
  calls: number
  rating: number
  version: string
  status: 'published'
}

const SUBJECTS_FILTER = ['全部', '金融', '会计', '经济', '管理']

const MOCK_AGENTS: Agent[] = [
  { id: '1', name: '企业财务异常检测', author: '张老师', subject: '金融', desc: '对报表关键科目进行稽核式比率检查，识别异常项并输出清单。', dataNeeded: '财报 Excel / CSV', calls: 96, rating: 4.8, version: 'v1.2', status: 'published' },
  { id: '2', name: '计量方法识别', author: '赵老师', subject: '经济', desc: '识别论文使用的识别策略与计量方法（DID/RDD/IV），提取模型设定与稳健性检验清单。', dataNeeded: '论文 PDF', calls: 64, rating: 4.7, version: 'v1.1', status: 'published' },
  { id: '3', name: '公告语义分析', author: '平台 · 公共', subject: '金融', desc: '对上市公司公告进行语义分析，识别经营/治理/前瞻三类风险信号。', dataNeeded: '公告文本 / PDF', calls: 88, rating: 4.6, version: 'v1.0', status: 'published' },
  { id: '4', name: '申请书结构解析', author: '孙老师', subject: '管理', desc: '解析国家自然科学基金申请书的章节结构、立项依据与研究方案组织方式。', dataNeeded: '申请书 PDF', calls: 38, rating: 4.5, version: 'v1.0', status: 'published' },
  { id: '5', name: '创新点分析', author: '张老师', subject: '金融', desc: '对比目标文本与领域近期文献，分析创新点的表述方式与支撑证据是否充分。', dataNeeded: '论文 PDF', calls: 29, rating: 4.4, version: 'v1.0', status: 'published' },
  { id: '6', name: '财务报表核查', author: '陈老师', subject: '会计', desc: '按表关键科目衔接与勾稽关系做动态检查，输出异常项清单。', dataNeeded: '财报 CSV / Excel', calls: 61, rating: 4.6, version: 'v1.0', status: 'published' },
]

// ── 智能体广场主页 ──────────────────────────────────────
export function AgentPlaza() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const [sortBy, setSortBy] = useState<'calls' | 'rating'>('calls')

  const filtered = MOCK_AGENTS
    .filter(a => activeSubject === '全部' || a.subject === activeSubject)
    .sort((a, b) => b[sortBy] - a[sortBy])

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>
            // AGENT PLAZA
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>智能体广场</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>浏览并使用其他老师发布的分析智能体</p>
        </div>
        <button
          onClick={() => navigate('/workspace/agents/new')}
          style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }}
        >+ 发布我的智能体</button>
      </div>

      {/* 筛选 + 排序 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap' as const, gap: 10 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {SUBJECTS_FILTER.map(s => (
            <button key={s} onClick={() => setActiveSubject(s)} style={{ padding: '5px 14px', borderRadius: 20, border: '1px solid ' + (activeSubject === s ? 'var(--action)' : 'var(--border)'), background: activeSubject === s ? 'var(--action)' : 'var(--surface)', color: activeSubject === s ? '#fff' : 'var(--text-secondary)', fontSize: 12, fontWeight: activeSubject === s ? 600 : 400, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>{s}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>排序：</span>
          {(['calls', 'rating'] as const).map(s => (
            <button key={s} onClick={() => setSortBy(s)} style={{ padding: '5px 12px', borderRadius: 6, border: '1px solid ' + (sortBy === s ? 'var(--action-border)' : 'var(--border)'), background: sortBy === s ? 'var(--action-light)' : 'var(--surface)', color: sortBy === s ? 'var(--action)' : 'var(--text-secondary)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
              {s === 'calls' ? '调用次数' : '评分'}
            </button>
          ))}
        </div>
      </div>

      {/* 卡片网格 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {filtered.map(agent => (
          <AgentCard key={agent.id} agent={agent} onUse={() => navigate('/workspace/chat')} />
        ))}
      </div>
    </div>
  )
}

function AgentCard({ agent, onUse }: { agent: Agent; onUse: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: 'var(--surface)', border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'), borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column' as const, gap: 10, boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>📊 {agent.name}</div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginLeft: 8 }}>{agent.version}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.author} · {agent.subject}</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, flex: 1 }}>{agent.desc}</p>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0', borderTop: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)' }}>
        需要：{agent.dataNeeded}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>▶ {agent.calls} 次调用</span>
        <span>⭐ {agent.rating}</span>
      </div>
      <button onClick={onUse} style={{ width: '100%', padding: '8px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
        使用此 Agent
      </button>
    </div>
  )
}

// ── 发布智能体表单 ──────────────────────────────────────
const SUBJECT_OPTIONS = ['金融学', '会计学', '经济学', '管理科学', '其他']

export function PublishAgent() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('金融学')
  const [desc, setDesc] = useState('')
  const [dataNeeded, setDataNeeded] = useState('')
  const [prompt, setPrompt] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !desc.trim() || !prompt.trim()) return
    setSubmitted(true)
    setTimeout(() => navigate('/workspace/my-agents'), 1500)
  }

  if (submitted) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ textAlign: 'center' as const }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>已提交审核</div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>跳转至「我的智能体」...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// PUBLISH AGENT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>发布智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>将你的分析方法封装成可复用的智能体，提交审核后发布到广场</p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* 基本信息 */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20 }}>基本信息</div>
            <FormField label="智能体名称" required>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="如：企业财务异常检测" style={inputStyle} />
            </FormField>
            <FormField label="所属学科">
              <select value={subject} onChange={e => setSubject(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {SUBJECT_OPTIONS.map(s => <option key={s}>{s}</option>)}
              </select>
            </FormField>
            <FormField label="功能描述" required hint="广场展示用，200 字以内">
              <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="简要描述这个智能体能做什么、适用于什么场景" style={{ ...inputStyle, minHeight: 80, resize: 'vertical' as const }} maxLength={200} />
            </FormField>
            <FormField label="所需数据" hint="告知使用者需要上传什么格式的文件">
              <input value={dataNeeded} onChange={e => setDataNeeded(e.target.value)} placeholder="如：财报 CSV / Excel，上市公司 A 股数据" style={inputStyle} />
            </FormField>
          </div>

          {/* 方法论配置 */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>方法论配置</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>这段文字将作为 AI 的「工作说明」，决定智能体的分析角度和输出格式</div>
            <FormField label="系统提示词" required>
              <textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={'你是一位专业的财务分析师...\n\n请按以下步骤完成分析：\n1. 读取数据，了解结构\n2. 计算关键财务指标...'} style={{ ...inputStyle, minHeight: 200, resize: 'vertical' as const, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.7 }} />
            </FormField>
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" onClick={() => navigate('/workspace/agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
            <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>提交审核</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function FormField({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
        {label}{required && <span style={{ color: '#DC2626', marginLeft: 3 }}>*</span>}
      </label>
      {hint && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>{hint}</div>}
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px',
  border: '1px solid var(--border)', borderRadius: 7,
  fontSize: 13, color: 'var(--text-primary)',
  background: '#F7F9FC', outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
  transition: 'border-color 0.15s',
}
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm tsc --noEmit 2>&1 | head -15
```

Expected: 无相关报错。

- [ ] **Step 4: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/pages/AgentScenarios.tsx web/src/workspace/pages/AgentPlaza.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): add scenarios and agent plaza pages"
```

---

### Task 2：MyData（我的数据）+ MyAgents（我的智能体）+ 路由接入

**Files:**
- Create: `web/src/workspace/pages/MyData.tsx`
- Create: `web/src/workspace/pages/MyAgents.tsx`
- Modify: `web/src/workspace/WorkspaceRouter.tsx`

- [ ] **Step 1: 创建 MyData.tsx**

```tsx
import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

interface DataFile {
  id: string
  name: string
  size: string
  uploadTime: string
  type: 'csv' | 'xlsx' | 'pdf' | 'txt'
}

const FILE_TYPE_STYLE: Record<DataFile['type'], { bg: string; color: string }> = {
  csv:  { bg: '#ECFDF5', color: '#059669' },
  xlsx: { bg: '#EFF6FF', color: '#2563EB' },
  pdf:  { bg: '#FEF2F2', color: '#DC2626' },
  txt:  { bg: '#F9FAFB', color: '#6B7280' },
}

const MOCK_FILES: DataFile[] = [
  { id: '1', name: 'portfolio_2026Q2.csv', size: '1.2 MB', uploadTime: '2026-08-06', type: 'csv' },
  { id: '2', name: 'fund_nav_history.xlsx', size: '4.8 MB', uploadTime: '2026-07-28', type: 'xlsx' },
  { id: '3', name: 'macro_indicators.csv', size: '0.9 MB', uploadTime: '2026-07-20', type: 'csv' },
  { id: '4', name: 'annual_report_2025.pdf', size: '12.3 MB', uploadTime: '2026-07-15', type: 'pdf' },
]

export function MyData() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState(MOCK_FILES)
  const [dragOver, setDragOver] = useState(false)

  const handleDelete = (id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id))
  }

  const handleAnalyze = (file: DataFile) => {
    navigate(`/workspace/chat?file=${encodeURIComponent(file.name)}`)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// MY DATA</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的数据</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理上传的数据文件，点击「分析」直接进入对话</p>
        </div>
        <div>
          <input ref={fileInputRef} type="file" multiple accept=".csv,.xlsx,.xls,.pdf,.txt" style={{ display: 'none' }} />
          <button
            onClick={() => fileInputRef.current?.click()}
            style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >↑ 上传文件</button>
        </div>
      </div>

      {/* 拖拽上传区 */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false) }}
        style={{
          border: '1.5px dashed ' + (dragOver ? 'var(--action)' : 'var(--border)'),
          borderRadius: 10, padding: '28px',
          textAlign: 'center' as const,
          background: dragOver ? 'var(--action-light)' : 'var(--surface)',
          marginBottom: 20, cursor: 'pointer',
          transition: 'border-color 0.2s, background 0.2s',
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <div style={{ fontSize: 24, marginBottom: 8 }}>📁</div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>拖拽文件到此处，或点击上传</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>支持 CSV · XLSX · PDF · TXT，单文件最大 50 MB</div>
      </div>

      {/* 文件列表 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        {/* 表头 */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 100px 120px 160px', gap: 0, padding: '10px 20px', borderBottom: '1px solid var(--border)', background: 'var(--bg)' }}>
          {['文件名', '大小', '上传时间', '操作'].map(h => (
            <div key={h} style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em' }}>{h}</div>
          ))}
        </div>
        {files.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' as const, color: 'var(--text-muted)', fontSize: 13 }}>暂无文件，请上传数据文件</div>
        ) : (
          files.map((file, i) => {
            const typeStyle = FILE_TYPE_STYLE[file.type]
            return (
              <div key={file.id} style={{ display: 'grid', gridTemplateColumns: '2fr 100px 120px 160px', gap: 0, padding: '14px 20px', borderBottom: i < files.length - 1 ? '1px solid var(--border-light)' : 'none', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 700, background: typeStyle.bg, color: typeStyle.color, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const }}>{file.type}</span>
                  <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{file.name}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{file.size}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{file.uploadTime}</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => handleAnalyze(file)} style={{ padding: '5px 12px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>分析</button>
                  <button style={{ padding: '5px 12px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>下载</button>
                  <button onClick={() => handleDelete(file.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>删除</button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 MyAgents.tsx**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

type AgentStatus = 'draft' | 'reviewing' | 'published'

interface MyAgent {
  id: string
  name: string
  subject: string
  status: AgentStatus
  calls?: number
  rating?: number
  publishedAt?: string
  submittedAt?: string
}

const STATUS_LABEL: Record<AgentStatus, string> = { draft: '草稿', reviewing: '审核中', published: '已发布' }
const STATUS_COLOR: Record<AgentStatus, { bg: string; color: string }> = {
  draft:     { bg: 'var(--bg)', color: 'var(--text-muted)' },
  reviewing: { bg: '#FFFBEB', color: 'var(--status-warn)' },
  published: { bg: '#ECFDF5', color: 'var(--status-done)' },
}

const MOCK_MY_AGENTS: MyAgent[] = [
  { id: '1', name: '企业财务异常检测', subject: '金融学', status: 'published', calls: 96, rating: 4.8, publishedAt: '2026-07-20' },
  { id: '2', name: '创新点对比分析', subject: '金融学', status: 'reviewing', submittedAt: '2026-08-07 14:22' },
  { id: '3', name: '股价动量因子筛选', subject: '金融学', status: 'draft' },
]

const TABS: AgentStatus[] = ['draft', 'reviewing', 'published']

export function MyAgents() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<AgentStatus>('published')
  const [agents, setAgents] = useState(MOCK_MY_AGENTS)

  const filtered = agents.filter(a => a.status === activeTab)

  const handleOffline = (id: string) => {
    setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'draft' } : a))
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// MY AGENTS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理你创建和发布的分析智能体</p>
        </div>
        <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建智能体</button>
      </div>

      {/* Tab 切换 */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px', fontSize: 13, fontWeight: 500,
              background: 'none', border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--action)' : '2px solid transparent',
              marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit',
              color: activeTab === tab ? 'var(--action)' : 'var(--text-muted)',
              transition: 'color 0.15s',
            }}
          >
            {STATUS_LABEL[tab]}
            <span style={{ marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }}>
              {agents.filter(a => a.status === tab).length}
            </span>
          </button>
        ))}
      </div>

      {/* Agent 列表 */}
      {filtered.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' as const }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✨</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
            {activeTab === 'draft' ? '没有草稿' : activeTab === 'reviewing' ? '没有待审核的智能体' : '还没有发布的智能体'}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
            {activeTab === 'published' ? '创建并发布你的第一个智能体，与其他用户共享分析方法' : ''}
          </div>
          {activeTab !== 'reviewing' && (
            <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建智能体</button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 10 }}>
          {filtered.map(agent => {
            const statusStyle = STATUS_COLOR[agent.status]
            return (
              <div key={agent.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</span>
                    <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: statusStyle.bg, color: statusStyle.color }}>{STATUS_LABEL[agent.status]}</span>
                    {agent.calls !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.calls} 次调用</span>}
                    {agent.rating !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>⭐ {agent.rating}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {agent.subject}
                    {agent.publishedAt && ` · ${agent.publishedAt} 发布`}
                    {agent.submittedAt && ` · ${agent.submittedAt} 提交`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  {agent.status === 'draft' && (
                    <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '6px 14px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                  )}
                  {agent.status === 'published' && (
                    <>
                      <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      <button onClick={() => handleOffline(agent.id)} style={{ padding: '6px 14px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>下线</button>
                    </>
                  )}
                  {agent.status === 'reviewing' && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: '6px 0' }}>等待审核</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 修改 WorkspaceRouter.tsx 接入四个页面**

先 Read `WorkspaceRouter.tsx`，然后：

1. 在文件顶部 import 区追加：
```tsx
import { AgentScenarios } from './pages/AgentScenarios'
import { AgentPlaza, PublishAgent } from './pages/AgentPlaza'
import { MyData } from './pages/MyData'
import { MyAgents } from './pages/MyAgents'
```

2. 将以下四组占位路由逐一替换：
```tsx
// 将：
<Route path="scenarios" element={placeholder('场景库（Plan 3 实现）')} />
// 替换为：
<Route path="scenarios" element={<AgentScenarios />} />

// 将：
<Route path="agents" element={placeholder('智能体广场（Plan 3 实现）')} />
<Route path="agents/new" element={placeholder('发布智能体（Plan 3 实现）')} />
// 替换为：
<Route path="agents" element={<AgentPlaza />} />
<Route path="agents/new" element={<PublishAgent />} />

// 将：
<Route path="data" element={placeholder('我的数据（Plan 3 实现）')} />
// 替换为：
<Route path="data" element={<MyData />} />

// 将：
<Route path="my-agents" element={placeholder('我的智能体（Plan 3 实现）')} />
// 替换为：
<Route path="my-agents" element={<MyAgents />} />
```

- [ ] **Step 4: 构建验证**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm build 2>&1 | tail -5
```

Expected: `✓ built in X.XXs`，无错误。

- [ ] **Step 5: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/pages/MyData.tsx web/src/workspace/pages/MyAgents.tsx web/src/workspace/WorkspaceRouter.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): add my-data, my-agents pages and wire up all plan3 routes"
```

---

## 自查

**Spec 覆盖：**
- [x] §4 场景库：学科筛选 + 4 张预置场景卡片 + 开始分析跳转
- [x] §5.1 智能体广场：发布按钮 + 学科筛选 + 排序
- [x] §5.2 Agent 卡片：名/作者/描述/所需数据/调用次数/评分/使用按钮
- [x] §5.3 发布表单：基本信息 + 系统提示词 + 提交审核 → 跳转我的智能体
- [x] §6 我的数据：上传区 + 文件列表 + 分析/下载/删除操作
- [x] §7 我的智能体：草稿/审核中/已发布 三 Tab + 下线操作
