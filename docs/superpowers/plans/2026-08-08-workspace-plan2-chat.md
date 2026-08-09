# 工作台 Plan 2：分析对话页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现分析对话页（`/workspace/chat`）的完整静态 UI，包含三栏布局、所有消息类型、右侧产物面板三区。

**Architecture:** 分析对话页分解为 5 个独立组件，每个职责单一：`ChatLayout`（三栏框架 + 拖拽）、`ThreadSidebar`（左侧会话列表）、`MessageList`（所有消息类型渲染）、`ChatInput`（底部输入区）、`ArtifactPanel`（右侧产物面板三区）。所有数据为静态 mock，无真实 SSE 接入。

**Tech Stack:** React 18 + TypeScript · 内联 style + CSS 变量（DSD token）· useRef 实现拖拽调宽 · useState 管理 UI 状态

**前置条件：** Plan 1 已完成，`/workspace` 框架和路由已就绪。

---

## 文件结构

```
web/src/workspace/
├── pages/
│   └── Chat.tsx                    ← 新建：对话页入口，组合所有子组件
└── components/
    ├── ThreadSidebar.tsx            ← 新建：左侧 240px 会话列表
    ├── MessageList.tsx              ← 新建：消息流，含所有消息类型
    ├── ChatInput.tsx                ← 新建：底部输入区
    └── ArtifactPanel.tsx            ← 新建：右侧产物面板三区
web/src/workspace/
└── WorkspaceRouter.tsx              ← 修改：接入 Chat 组件
```

---

### Task 1：ThreadSidebar — 左侧会话列表

**Files:**
- Create: `web/src/workspace/components/ThreadSidebar.tsx`

- [ ] **Step 1: 创建 ThreadSidebar.tsx**

```tsx
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

type RunStatus = 'running' | 'done' | 'failed' | 'waiting'

interface Thread {
  id: string
  title: string
  time: string
  status: RunStatus
}

const MOCK_THREADS: Thread[] = [
  { id: '1', title: '新能源行业波动率分析', time: '进行中', status: 'running' },
  { id: '2', title: 'A 股收益归因分解', time: '昨天 14:32', status: 'done' },
  { id: '3', title: 'Fama-French 三因子复现', time: '2 天前', status: 'done' },
  { id: '4', title: '持仓集中度风险分析', time: '3 天前', status: 'failed' },
  { id: '5', title: '财报核查 · 格力电器', time: '4 天前', status: 'waiting' },
]

const STATUS_ICON: Record<RunStatus, string> = {
  running: '◉',
  done: '✓',
  failed: '✗',
  waiting: '⏸',
}

const STATUS_COLOR: Record<RunStatus, string> = {
  running: 'var(--action)',
  done: 'var(--status-done)',
  failed: '#DC2626',
  waiting: 'var(--status-warn)',
}

export function ThreadSidebar() {
  const navigate = useNavigate()
  const { threadId } = useParams()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [threads, setThreads] = useState(MOCK_THREADS)

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setThreads(prev => prev.filter(t => t.id !== id))
    if (threadId === id) navigate('/workspace/chat')
  }

  return (
    <div style={{
      width: 240, flexShrink: 0,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflow: 'hidden',
    }}>
      {/* 新建会话按钮 */}
      <div style={{ padding: '12px 12px 8px' }}>
        <button
          onClick={() => navigate('/workspace/chat')}
          style={{
            width: '100%', padding: '8px 0',
            background: 'var(--action)', color: '#fff',
            border: 'none', borderRadius: 7,
            fontSize: 13, fontWeight: 500,
            cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新建分析
        </button>
      </div>

      {/* 历史标题 */}
      <div style={{ padding: '4px 16px 8px', fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
        // HISTORY
      </div>

      {/* 会话列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {threads.map(thread => {
          const isActive = threadId === thread.id
          const isHovered = hoveredId === thread.id
          return (
            <div
              key={thread.id}
              onClick={() => navigate(`/workspace/chat/${thread.id}`)}
              onMouseEnter={() => setHoveredId(thread.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                padding: '10px 12px',
                borderRadius: 7,
                cursor: 'pointer',
                marginBottom: 2,
                position: 'relative',
                background: isActive ? 'var(--action-light)' : isHovered ? 'var(--bg)' : 'transparent',
                border: isActive ? '1px solid var(--action-border)' : '1px solid transparent',
                transition: 'background 0.15s',
              }}
            >
              <div style={{
                fontSize: 13, fontWeight: 500,
                color: isActive ? 'var(--action)' : 'var(--text-primary)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                marginBottom: 4, paddingRight: isHovered ? 20 : 0,
              }}>
                {thread.title}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                <span style={{ color: 'var(--text-muted)' }}>{thread.time}</span>
                <span style={{ color: STATUS_COLOR[thread.status], fontWeight: 600 }}>
                  {STATUS_ICON[thread.status]}
                </span>
              </div>
              {/* 删除按钮，hover 时出现 */}
              {isHovered && (
                <button
                  onClick={e => handleDelete(e, thread.id)}
                  style={{
                    position: 'absolute', top: '50%', right: 10,
                    transform: 'translateY(-50%)',
                    width: 20, height: 20, borderRadius: 4,
                    border: 'none', background: 'transparent',
                    color: 'var(--text-muted)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 12,
                  }}
                  title="删除会话"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                    <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                  </svg>
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm tsc --noEmit 2>&1 | head -10
```

Expected: 无 ThreadSidebar 相关报错。

- [ ] **Step 3: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/components/ThreadSidebar.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(chat): add ThreadSidebar component"
```

---

### Task 2：MessageList — 所有消息类型渲染

**Files:**
- Create: `web/src/workspace/components/MessageList.tsx`

- [ ] **Step 1: 创建 MessageList.tsx**

```tsx
import { useState } from 'react'

// ── 消息类型定义 ────────────────────────────────────────
type MessageType = 'user' | 'reasoning' | 'tool' | 'agent' | 'hitl' | 'thinking'

interface Attachment { name: string }

interface UserMessage { type: 'user'; text: string; attachments?: Attachment[] }

interface ReasoningMessage { type: 'reasoning'; text: string; done: boolean }

interface ToolMessage {
  type: 'tool'
  status: 'done' | 'running' | 'failed'
  name: string
  arg: string
  time?: string
  output?: string[]
}

interface AgentMessage { type: 'agent'; markdown: string }

interface HitlMessage {
  type: 'hitl'
  tool: string
  args: string
  resolved?: boolean
}

interface ThinkingMessage { type: 'thinking' }

type Message = UserMessage | ReasoningMessage | ToolMessage | AgentMessage | HitlMessage | ThinkingMessage

// ── Mock 对话数据 ──────────────────────────────────────
const MOCK_MESSAGES: Message[] = [
  {
    type: 'user',
    text: '请分析 portfolio.csv 中各行业持仓的年化波动率，并生成对比图表。',
    attachments: [{ name: 'portfolio.csv' }],
  },
  {
    type: 'reasoning',
    text: '用户上传了持仓数据文件，需要计算各行业的年化波动率。\n\n步骤：\n1. 读取 CSV 文件了解数据结构\n2. 按行业分组提取价格序列\n3. 计算日收益率的标准差 × √252 = 年化波动率\n4. 用 matplotlib 生成条形图并保存至 outputs/',
    done: true,
  },
  { type: 'tool', status: 'done', name: 'read_file', arg: 'portfolio.csv', time: '0.1s' },
  { type: 'tool', status: 'done', name: 'write_file', arg: 'volatility_analysis.py', time: '0.1s' },
  {
    type: 'tool',
    status: 'done',
    name: 'execute',
    arg: 'python volatility_analysis.py',
    time: '3.2s',
    output: ['Computing sector volatility...', 'Processing 4,831 rows...', 'Chart saved to outputs/industry_volatility.png'],
  },
  {
    type: 'agent',
    markdown: `已完成年化波动率分析，结果如下：

| 行业 | 年化波动率 | 样本数 |
|------|-----------|--------|
| 金融 | 18.3% | 2,847 |
| 能源 | 24.1% | 1,203 |
| 消费 | 15.7% | 1,781 |
| 科技 | 31.2% | 892 |

图表已生成并保存至 \`outputs/industry_volatility.png\`。

**主要发现：** 科技行业波动率最高（31.2%），金融行业最低（18.3%）。建议适当降低科技行业配置比例以控制组合整体风险。`,
  },
  {
    type: 'hitl',
    tool: 'delete',
    args: '/workspace/raw_backup.csv',
    resolved: false,
  },
]

// ── 子组件 ────────────────────────────────────────────

const AGENT_LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const AGENT_LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

function UserBubble({ msg }: { msg: UserMessage }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ maxWidth: 560 }}>
        <div style={{
          background: 'var(--brand)', color: '#fff',
          padding: '12px 16px',
          borderRadius: '12px 12px 2px 12px',
          fontSize: 14, lineHeight: 1.65,
        }}>
          {msg.text}
          {msg.attachments?.map(a => (
            <div key={a.name} style={{
              marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 5,
              padding: '4px 10px',
              background: 'rgba(255,255,255,0.15)',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 5, fontSize: 12,
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
              </svg>
              {a.name}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ReasoningBlock({ msg }: { msg: ReasoningMessage }) {
  const [expanded, setExpanded] = useState(!msg.done)
  return (
    <div style={{
      borderLeft: '2px solid var(--border)', borderRadius: 6,
      background: 'var(--bg)', overflow: 'hidden',
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', padding: '8px 14px',
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'inherit', fontSize: 12, color: 'var(--text-muted)',
          textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 10 }}>{expanded ? '▼' : '▶'}</span>
        思考过程
        {msg.done && <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>已完成</span>}
      </button>
      {expanded && (
        <div style={{
          padding: '8px 14px 12px',
          fontSize: 13, color: 'var(--text-muted)',
          lineHeight: 1.7, whiteSpace: 'pre-wrap',
          borderTop: '1px solid var(--border-light)',
        }}>
          {msg.text}
          {!msg.done && <span style={{ display: 'inline-block', width: 2, height: '1em', background: 'var(--action)', verticalAlign: 'text-bottom', marginLeft: 2, animation: 'blink 1.1s step-end infinite' }} />}
        </div>
      )}
    </div>
  )
}

function ToolRow({ msg }: { msg: ToolMessage }) {
  const [showOutput, setShowOutput] = useState(false)
  const iconColor = msg.status === 'done' ? 'var(--status-done)' : msg.status === 'failed' ? '#DC2626' : 'var(--action)'
  const icon = msg.status === 'done' ? '✓' : msg.status === 'failed' ? '✗' : '◉'
  return (
    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, background: 'var(--bg)', borderRadius: 5, padding: '6px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ color: iconColor, fontWeight: 700, width: 12 }}>{icon}</span>
        <span style={{ color: 'var(--action)', minWidth: 120 }}>{msg.name}</span>
        <span style={{ color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{msg.arg}</span>
        {msg.time && <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', flexShrink: 0 }}>{msg.time}</span>}
        {msg.output && (
          <button onClick={() => setShowOutput(s => !s)} style={{ marginLeft: 8, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
            {showOutput ? '▼' : '▶'}
          </button>
        )}
      </div>
      {showOutput && msg.output && (
        <div style={{ paddingLeft: 22, marginTop: 4, color: 'var(--text-secondary)', fontSize: 11, lineHeight: 1.7 }}>
          {msg.output.map((line, i) => (
            <div key={i} style={{ display: 'flex', gap: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>└─</span>
              <span>{line}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AgentBubble({ msg }: { msg: AgentMessage }) {
  // 简单 Markdown 渲染：粗体、行内代码、表格、段落
  const renderMarkdown = (text: string) => {
    const lines = text.split('\n')
    const elements: React.ReactNode[] = []
    let tableLines: string[] = []
    let inTable = false

    const flushTable = () => {
      if (tableLines.length < 2) { tableLines = []; inTable = false; return }
      const rows = tableLines.map(l => l.split('|').filter((_, i, a) => i > 0 && i < a.length - 1).map(c => c.trim()))
      elements.push(
        <table key={`table-${elements.length}`} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, margin: '8px 0' }}>
          <thead>
            <tr>{rows[0].map((cell, i) => <th key={i} style={{ background: 'var(--bg)', padding: '6px 12px', textAlign: 'left', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>{cell}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(2).map((row, ri) => (
              <tr key={ri}>{row.map((cell, ci) => <td key={ci} style={{ padding: '6px 12px', border: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      )
      tableLines = []; inTable = false
    }

    lines.forEach((line, i) => {
      if (line.startsWith('|')) { tableLines.push(line); inTable = true; return }
      if (inTable) flushTable()

      if (!line.trim()) { elements.push(<div key={i} style={{ height: 8 }} />); return }

      // 处理粗体和行内代码
      const rendered = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**')) return <strong key={j}>{part.slice(2, -2)}</strong>
        if (part.startsWith('`') && part.endsWith('`')) return <code key={j} style={{ background: 'var(--bg)', padding: '1px 5px', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{part.slice(1, -1)}</code>
        return part
      })
      elements.push(<p key={i} style={{ margin: '4px 0', lineHeight: 1.75 }}>{rendered}</p>)
    })
    if (inTable) flushTable()
    return elements
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      {/* Agent 头像 */}
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: 'var(--brand)', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <svg viewBox="12 3 24 34" fill="#fff" style={{ height: 18, width: 'auto' }}>
          <path d={AGENT_LOGO_PATH_1} /><path d={AGENT_LOGO_PATH_2} />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
          FinAgent
        </div>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: '2px 12px 12px 12px',
          padding: '14px 18px',
          fontSize: 14, color: 'var(--text-primary)',
        }}>
          {renderMarkdown(msg.markdown)}
        </div>
      </div>
    </div>
  )
}

function HitlCard({ msg }: { msg: HitlMessage }) {
  const [showReply, setShowReply] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [resolved, setResolved] = useState(msg.resolved ?? false)

  if (resolved) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", padding: '6px 0' }}>
        ✓ 已处理审批请求
      </div>
    )
  }

  return (
    <div style={{
      borderLeft: '4px solid var(--status-warn)',
      background: '#FFFBEB',
      border: '1px solid #FDE68A',
      borderRadius: 8, padding: '16px 20px',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#92400E', marginBottom: 12 }}>⏸ 等待您的确认</div>
      <div style={{ fontSize: 13, color: '#92400E', marginBottom: 4 }}>agent 即将执行：</div>
      <div style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
        background: 'rgba(0,0,0,0.05)', borderRadius: 5,
        padding: '8px 12px', marginBottom: 16, color: '#7C2D12',
      }}>
        {msg.tool}  {msg.args}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' as const, marginBottom: showReply ? 12 : 0 }}>
        <button
          onClick={() => setResolved(true)}
          style={{ padding: '7px 16px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
        >✓ 批准</button>
        <button
          onClick={() => setResolved(true)}
          style={{ padding: '7px 16px', background: '#DC2626', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
        >✗ 拒绝</button>
        <button
          onClick={() => setShowReply(s => !s)}
          style={{ padding: '7px 16px', background: 'transparent', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 6, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
        >💬 直接回复</button>
      </div>
      {showReply && (
        <div style={{ marginTop: 10 }}>
          <textarea
            value={replyText}
            onChange={e => setReplyText(e.target.value)}
            placeholder="输入回复内容，agent 将以此作为工具结果..."
            style={{
              width: '100%', minHeight: 72, padding: '8px 12px',
              border: '1px solid #FDE68A', borderRadius: 6,
              fontFamily: 'inherit', fontSize: 13, resize: 'vertical',
              background: '#fff', outline: 'none', boxSizing: 'border-box' as const,
            }}
          />
          <div style={{ marginTop: 8, textAlign: 'right' }}>
            <button
              onClick={() => { if (replyText.trim()) setResolved(true) }}
              style={{ padding: '6px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
            >发送</button>
          </div>
        </div>
      )}
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg viewBox="12 3 24 34" fill="#fff" style={{ height: 18, width: 'auto' }}>
          <path d={AGENT_LOGO_PATH_1} /><path d={AGENT_LOGO_PATH_2} />
        </svg>
      </div>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: '2px 12px 12px 12px',
        padding: '14px 18px',
        display: 'flex', gap: 4, alignItems: 'center',
      }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--action)',
            animation: 'thinking-bounce 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
      </div>
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────

interface MessageListProps {
  messages?: Message[]
}

export function MessageList({ messages = MOCK_MESSAGES }: MessageListProps) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {messages.map((msg, i) => {
        switch (msg.type) {
          case 'user': return <UserBubble key={i} msg={msg} />
          case 'reasoning': return <ReasoningBlock key={i} msg={msg} />
          case 'tool': return <ToolRow key={i} msg={msg} />
          case 'agent': return <AgentBubble key={i} msg={msg} />
          case 'hitl': return <HitlCard key={i} msg={msg} />
          case 'thinking': return <ThinkingBubble key={i} />
          default: return null
        }
      })}
    </div>
  )
}
```

- [ ] **Step 2: 在 theme.css 末尾追加 thinking 动画**

在 `web/src/styles/theme.css` 末尾追加（如果还没有的话）：

```css
@keyframes thinking-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40%           { transform: scale(1);   opacity: 1; }
}
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm tsc --noEmit 2>&1 | head -15
```

Expected: 无 MessageList 相关报错。

- [ ] **Step 4: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/components/MessageList.tsx web/src/styles/theme.css && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(chat): add MessageList with all message types"
```

---

### Task 3：ChatInput + ArtifactPanel

**Files:**
- Create: `web/src/workspace/components/ChatInput.tsx`
- Create: `web/src/workspace/components/ArtifactPanel.tsx`

- [ ] **Step 1: 创建 ChatInput.tsx**

```tsx
import { useState, useRef } from 'react'

interface ChatInputProps {
  isRunning?: boolean
  onSend?: (text: string, files: string[]) => void
  onStop?: () => void
}

export function ChatInput({ isRunning = false, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')
  const [attachments, setAttachments] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    if (!text.trim() && attachments.length === 0) return
    onSend?.(text, attachments)
    setText('')
    setAttachments([])
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []).map(f => f.name)
    setAttachments(prev => [...prev, ...files])
    e.target.value = ''
  }

  return (
    <div style={{ padding: '12px 24px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg)', flexShrink: 0 }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 10, padding: '12px 16px',
        boxShadow: '0 2px 8px rgba(11,46,92,0.06)',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入分析需求，或描述你想做的事情...（Enter 发送，Shift+Enter 换行）"
          style={{
            width: '100%', minHeight: 52, maxHeight: 160,
            border: 'none', outline: 'none',
            fontSize: 14, color: 'var(--text-primary)',
            background: 'transparent', resize: 'none',
            fontFamily: 'inherit', lineHeight: 1.65,
            boxSizing: 'border-box',
          }}
        />

        {/* 附件标签 */}
        {attachments.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {attachments.map(name => (
              <div key={name} style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '3px 10px',
                background: 'var(--action-light)', border: '1px solid var(--action-border)',
                borderRadius: 5, fontSize: 12, color: 'var(--action)',
              }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                </svg>
                {name}
                <button
                  onClick={() => setAttachments(prev => prev.filter(n => n !== name))}
                  style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', padding: 0, fontSize: 12, lineHeight: 1 }}
                >×</button>
              </div>
            ))}
          </div>
        )}

        {/* 底部工具栏 */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginTop: 8, paddingTop: 8,
          borderTop: '1px solid var(--border-light)',
        }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".csv,.xlsx,.xls,.pdf,.txt"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '5px 10px', border: '1px solid var(--border)',
                borderRadius: 5, background: 'transparent',
                fontSize: 12, color: 'var(--text-secondary)',
                cursor: 'pointer', fontFamily: 'inherit',
                transition: 'border-color 0.2s, color 0.2s',
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
              </svg>
              附件
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Enter 发送</span>
            {isRunning ? (
              <button
                onClick={onStop}
                style={{
                  width: 36, height: 36, borderRadius: 7,
                  background: '#DC2626', border: 'none',
                  color: '#fff', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.2s',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16"/></svg>
              </button>
            ) : (
              <button
                onClick={handleSend}
                style={{
                  width: 36, height: 36, borderRadius: 7,
                  background: 'var(--action)', border: 'none',
                  color: '#fff', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.2s',
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 ArtifactPanel.tsx**

```tsx
import { useState } from 'react'

type RunStatus = 'running' | 'done' | 'waiting' | 'queued'

interface WorkspaceFile {
  name: string
  size: string
  type: 'csv' | 'py' | 'png' | 'md' | 'other'
  isOutput?: boolean
}

interface StepItem {
  status: 'done' | 'running' | 'pending'
  name: string
  arg: string
  time?: string
  output?: string[]
}

// ── Mock 数据 ────────────────────────────────────────
const MOCK_STATUS: RunStatus = 'done'
const MOCK_ELAPSED = '3m22s'
const MOCK_TOKENS = 31340
const MOCK_TOKEN_QUOTA = 120000

const MOCK_FILES: WorkspaceFile[] = [
  { name: 'portfolio.csv', size: '1.2 MB', type: 'csv' },
  { name: 'volatility_analysis.py', size: '2.1 KB', type: 'py' },
  { name: 'industry_volatility.png', size: '84 KB', type: 'png', isOutput: true },
]

const MOCK_STEPS: StepItem[] = [
  { status: 'done', name: 'read_file', arg: 'portfolio.csv', time: '0.1s' },
  { status: 'done', name: 'write_file', arg: 'volatility_analysis.py', time: '0.1s' },
  { status: 'done', name: 'execute', arg: 'python volatility_analysis.py', time: '3.2s', output: ['Computing sector volatility...', 'Chart saved to outputs/industry_volatility.png'] },
]

const FILE_ICON: Record<WorkspaceFile['type'], string> = {
  csv: '📄', py: '📄', png: '🖼', md: '📝', other: '📄',
}

// ── 状态栏 ───────────────────────────────────────────
function RunStatusBar({ status, elapsed, tokens, quota }: { status: RunStatus; elapsed: string; tokens: number; quota: number }) {
  const pct = Math.round(tokens / quota * 100)
  const color = status === 'running' ? 'var(--action)' : status === 'done' ? 'var(--status-done)' : status === 'waiting' ? 'var(--status-warn)' : 'var(--text-muted)'
  const icon = status === 'running' ? '◉' : status === 'done' ? '✓' : status === 'waiting' ? '⏸' : '📋'
  const label = status === 'running' ? `运行中  ${elapsed}` : status === 'done' ? `完成 · 用时 ${elapsed} · 消耗 ${tokens.toLocaleString()} tokens` : status === 'waiting' ? '等待确认' : '排队中'

  return (
    <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>
          {icon} {label}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
          {(tokens / 1000).toFixed(0)}K / {(quota / 1000).toFixed(0)}K
        </span>
      </div>
      <div style={{ height: 3, background: 'var(--border-light)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2, transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

// ── 文件树 ───────────────────────────────────────────
function WorkspaceTree({ files }: { files: WorkspaceFile[] }) {
  const [previewFile, setPreviewFile] = useState<string | null>(null)
  const outputFiles = files.filter(f => f.isOutput)
  const rootFiles = files.filter(f => !f.isOutput)

  return (
    <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 10 }}>
        // WORKSPACE
      </div>

      {/* 图片产物：全宽展示 */}
      {outputFiles.filter(f => f.type === 'png').map(f => (
        <div key={f.name} style={{ marginBottom: 10 }}>
          <div style={{
            background: 'var(--bg)', border: '1px solid var(--border)',
            borderRadius: 8, overflow: 'hidden',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            minHeight: 120, padding: 12,
            color: 'var(--text-muted)', fontSize: 12,
          }}>
            🖼 {f.name}
            <span style={{ marginLeft: 6, fontSize: 11 }}>({f.size})</span>
          </div>
          <div style={{ marginTop: 6, textAlign: 'right' }}>
            <button style={{ fontSize: 12, color: 'var(--action)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>↓ 下载图片</button>
          </div>
        </div>
      ))}

      {/* 文件列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rootFiles.map(f => (
          <FileRow key={f.name} file={f} isExpanded={previewFile === f.name} onToggle={() => setPreviewFile(p => p === f.name ? null : f.name)} />
        ))}
        {outputFiles.filter(f => f.type !== 'png').map(f => (
          <FileRow key={f.name} file={f} isExpanded={previewFile === f.name} onToggle={() => setPreviewFile(p => p === f.name ? null : f.name)} />
        ))}
      </div>
    </div>
  )
}

function FileRow({ file, isExpanded, onToggle }: { file: WorkspaceFile; isExpanded: boolean; onToggle: () => void }) {
  const canPreview = file.type === 'py' || file.type === 'md' || file.type === 'csv'
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0' }}>
        <span style={{ fontSize: 13 }}>{FILE_ICON[file.type]}</span>
        <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>{file.size}</span>
        {canPreview && (
          <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', padding: 0 }}>↗</button>
        )}
        <button style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', padding: 0 }}>↓</button>
      </div>
      {isExpanded && (
        <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, padding: '8px 10px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 4 }}>
          {/* 原型阶段展示占位内容 */}
          <div style={{ color: 'var(--text-muted)' }}># {file.name} 预览</div>
          <div>import pandas as pd</div>
          <div>import numpy as np</div>
          <div>import matplotlib.pyplot as plt</div>
          <div style={{ color: 'var(--text-muted)' }}># ... 联调时替换为真实文件内容</div>
        </div>
      )}
    </div>
  )
}

// ── 步骤日志 ─────────────────────────────────────────
function StepsLog({ steps }: { steps: StepItem[] }) {
  const [collapsed, setCollapsed] = useState(false)
  const allDone = steps.every(s => s.status === 'done')

  return (
    <div style={{ padding: '14px 16px', flex: 1 }}>
      <button
        onClick={() => setCollapsed(s => !s)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
          textTransform: 'uppercase', letterSpacing: '0.2em',
          color: 'var(--text-muted)', padding: 0, marginBottom: collapsed ? 0 : 10,
        }}
      >
        <span>// STEPS</span>
        <span>{collapsed ? `▾ 展开查看（共 ${steps.length} 步）` : '▲ 收起'}</span>
      </button>

      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {steps.map((step, i) => {
            const icon = step.status === 'done' ? '✓' : step.status === 'failed' ? '✗' : '◉'
            const color = step.status === 'done' ? 'var(--status-done)' : step.status === 'failed' ? '#DC2626' : 'var(--action)'
            return (
              <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)' }}>
                  <span style={{ color, fontWeight: 700, width: 10 }}>{icon}</span>
                  <span style={{ color: 'var(--action)', minWidth: 90 }}>{step.name}</span>
                  <span style={{ color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{step.arg}</span>
                  {step.time && <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{step.time}</span>}
                </div>
                {step.output?.map((line, li) => (
                  <div key={li} style={{ paddingLeft: 18, color: 'var(--text-muted)', fontSize: 10, display: 'flex', gap: 6 }}>
                    <span>└─</span><span>{line}</span>
                  </div>
                ))}
              </div>
            )
          })}
          {!allDone && (
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
              <span style={{ color: 'var(--action)' }}>◉</span>
              <span>执行中...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────
export function ArtifactPanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: 'var(--surface)' }}>
      <RunStatusBar status={MOCK_STATUS} elapsed={MOCK_ELAPSED} tokens={MOCK_TOKENS} quota={MOCK_TOKEN_QUOTA} />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <WorkspaceTree files={MOCK_FILES} />
        <StepsLog steps={MOCK_STEPS} />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm tsc --noEmit 2>&1 | head -15
```

Expected: 无相关报错。

- [ ] **Step 4: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/components/ChatInput.tsx web/src/workspace/components/ArtifactPanel.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(chat): add ChatInput and ArtifactPanel components"
```

---

### Task 4：Chat.tsx — 三栏布局组合 + 拖拽 + WorkspaceRouter 接入

**Files:**
- Create: `web/src/workspace/pages/Chat.tsx`
- Modify: `web/src/workspace/WorkspaceRouter.tsx`

- [ ] **Step 1: 创建 Chat.tsx**

```tsx
import { useRef, useState, useCallback } from 'react'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ChatInput } from '../components/ChatInput'
import { ArtifactPanel } from '../components/ArtifactPanel'

const MIN_PANEL_WIDTH = 200
const MAX_PANEL_WIDTH = 700
const DEFAULT_PANEL_WIDTH = 380

export function Chat() {
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [isRunning] = useState(false)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(DEFAULT_PANEL_WIDTH)

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = panelWidth

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - ev.clientX
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth.current + delta))
      setPanelWidth(newWidth)
    }
    const onMouseUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [panelWidth])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* 左侧会话列表 */}
      <ThreadSidebar />

      {/* 主对话区 */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        backgroundColor: 'var(--bg)',
        backgroundImage: 'linear-gradient(rgba(11,46,92,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(11,46,92,0.025) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}>
        <MessageList />
        <ChatInput isRunning={isRunning} />
      </div>

      {/* 拖拽分隔条 */}
      <div
        onMouseDown={onResizeStart}
        style={{
          width: 4, flexShrink: 0, cursor: 'col-resize',
          background: 'var(--border-light)',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--action)'}
        onMouseLeave={e => { if (!dragging.current) (e.currentTarget as HTMLElement).style.background = 'var(--border-light)' }}
      />

      {/* 右侧产物面板 */}
      <div style={{
        width: panelWidth, flexShrink: 0,
        borderLeft: 'none',
      }}>
        <ArtifactPanel />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 修改 WorkspaceRouter.tsx 接入 Chat 组件**

先 Read `WorkspaceRouter.tsx`，然后：

1. 在文件顶部 import 区追加：`import { Chat } from './pages/Chat'`
2. 将：
   ```tsx
   <Route path="chat" element={placeholder('分析对话（Plan 2 实现）')} />
   <Route path="chat/:threadId" element={placeholder('分析对话（Plan 2 实现）')} />
   ```
   替换为：
   ```tsx
   <Route path="chat" element={<Chat />} />
   <Route path="chat/:threadId" element={<Chat />} />
   ```

- [ ] **Step 3: 构建验证**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm build 2>&1 | tail -5
```

Expected: `✓ built in X.XXs`，无错误。

- [ ] **Step 4: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/pages/Chat.tsx web/src/workspace/WorkspaceRouter.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(chat): assemble Chat page with resizable three-column layout"
```

---

## 自查清单

**Spec 覆盖检查：**
- [x] §3.1 三栏布局（ThreadSidebar 240px + MessageList flex:1 + ArtifactPanel 380px 可拖拽）
- [x] §3.2 左侧会话列表（新建按钮 + HISTORY 标题 + 状态徽标 4 种 + hover 删除）
- [x] §3.3 消息类型 ① 用户气泡（右对齐深蓝 + 附件标签）
- [x] §3.3 消息类型 ② Reasoning 折叠块（展开/折叠 toggle + 完成后折叠）
- [x] §3.3 消息类型 ③ 工具调用单行（Mono + 状态图标 + 可展开 output）
- [x] §3.3 消息类型 ④ Agent 正式回复（白卡片 + Markdown 渲染含表格）
- [x] §3.3 消息类型 ⑤ HITL 审批卡（批准/拒绝/直接回复 + 输入框展开）
- [x] §3.3 消息类型 ⑥ 思考动画（三点跳动）
- [x] §3.4 底部输入区（多行 + Enter 发送 + 附件 + 停止按钮）
- [x] §3.5 右侧面板区一 Run 状态栏（4 种状态 + token 进度条）
- [x] §3.5 右侧面板区二 文件树（图片全宽展示 + 代码预览 + 下载）
- [x] §3.5 右侧面板区三 Steps 日志（展开/折叠 + 输出行）

**无 placeholder — 所有步骤含完整代码。**
