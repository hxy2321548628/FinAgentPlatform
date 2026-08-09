import { useState } from 'react'

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
interface HitlMessage { type: 'hitl'; tool: string; args: string; resolved?: boolean; onApprove?: () => void; onReject?: () => void }
interface ThinkingMessage { type: 'thinking' }

type Message = UserMessage | ReasoningMessage | ToolMessage | AgentMessage | HitlMessage | ThinkingMessage

// 将技术性工具名映射为用户友好的中文描述
const TOOL_LABEL: Record<string, { label: string; icon: string }> = {
  read_file:   { label: '读取数据文件',   icon: '📂' },
  write_file:  { label: '生成分析代码',   icon: '📝' },
  execute:     { label: '执行计算',       icon: '⚙️' },
  edit_file:   { label: '修改代码',       icon: '✏️' },
  delete:      { label: '删除文件',       icon: '🗑' },
  ls:          { label: '查看目录',       icon: '📁' },
  glob:        { label: '搜索文件',       icon: '🔍' },
  grep:        { label: '搜索内容',       icon: '🔎' },
}

function getToolInfo(name: string, arg: string) {
  const info = TOOL_LABEL[name] ?? { label: name, icon: '🔧' }
  // 为部分工具生成更友好的参数描述
  let desc = arg
  if (name === 'execute' && arg.startsWith('python ')) {
    desc = `运行 ${arg.replace('python ', '')}`
  } else if (name === 'write_file' && arg.endsWith('.py')) {
    desc = `保存为 ${arg}`
  } else if (name === 'read_file') {
    desc = `加载 ${arg}`
  }
  return { ...info, desc }
}

const MOCK_MESSAGES: Message[] = [
  {
    type: 'user',
    text: '请分析 portfolio.csv 中各行业持仓的年化波动率，并生成对比图表。',
    attachments: [{ name: 'portfolio.csv' }],
  },
  {
    type: 'reasoning',
    text: '用户上传了持仓数据文件，需要计算各行业的年化波动率。\n\n分析思路：\n1. 读取持仓数据，了解字段结构和行业分类方式\n2. 按行业分组，提取各行业的历史价格序列\n3. 计算日收益率，再乘以 √252 得到年化波动率\n4. 生成各行业波动率对比条形图，存至 outputs/ 目录供用户下载',
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
    output: ['处理 4,831 条持仓记录', '按行业分组完成，共 8 个行业', '图表已保存至 outputs/industry_volatility.png'],
  },
  {
    type: 'agent',
    markdown: `已完成各行业年化波动率分析，结果如下：

| 行业 | 年化波动率 | 持仓样本数 |
|------|-----------|--------|
| 科技 | 31.2% | 892 |
| 能源 | 24.1% | 1,203 |
| 金融 | 18.3% | 2,847 |
| 消费 | 15.7% | 1,781 |

图表已生成，可在右侧面板下载。

**主要发现：** 科技行业波动率最高（31.2%），金融行业最低（18.3%）。建议适当降低科技行业配置比例，以控制组合整体风险敞口。`,
  },
  {
    type: 'hitl',
    tool: 'delete',
    args: '/workspace/raw_backup.csv',
    resolved: false,
  },
]

const AGENT_LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const AGENT_LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

function AgentAvatar() {
  return (
    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg viewBox="12 3 24 34" fill="#fff" style={{ height: 18, width: 'auto' }}>
        <path d={AGENT_LOGO_PATH_1} /><path d={AGENT_LOGO_PATH_2} />
      </svg>
    </div>
  )
}

function UserBubble({ msg }: { msg: UserMessage }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ maxWidth: 560 }}>
        <div style={{ background: 'var(--brand)', color: '#fff', padding: '12px 16px', borderRadius: '12px 12px 2px 12px', fontSize: 14, lineHeight: 1.65 }}>
          {msg.text}
          {msg.attachments?.map(a => (
            <div key={a.name} style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)', borderRadius: 5, fontSize: 12 }}>
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
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AgentAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>FinAgent</div>
        <div style={{ borderLeft: '2px solid var(--action-border)', borderRadius: '0 6px 6px 0', background: 'var(--action-light)', overflow: 'hidden' }}>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{ width: '100%', padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, color: 'var(--action)', textAlign: 'left' as const }}
          >
            <span style={{ fontSize: 10 }}>{expanded ? '▼' : '▶'}</span>
            <span style={{ fontWeight: 500 }}>分析思路</span>
            {msg.done && <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>已完成</span>}
          </button>
          {expanded && (
            <div style={{ padding: '8px 14px 12px', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75, whiteSpace: 'pre-wrap' as const, borderTop: '1px solid var(--action-border)' }}>
              {msg.text}
              {!msg.done && <span style={{ display: 'inline-block', width: 2, height: '1em', background: 'var(--action)', verticalAlign: 'text-bottom', marginLeft: 2, animation: 'blink 1.1s step-end infinite' }} />}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ToolRow({ msg }: { msg: ToolMessage }) {
  const [showOutput, setShowOutput] = useState(false)
  const { label, icon, desc } = getToolInfo(msg.name, msg.arg)
  const statusColor = msg.status === 'done' ? 'var(--status-done)' : msg.status === 'failed' ? '#DC2626' : 'var(--action)'
  const statusIcon = msg.status === 'done' ? '✓' : msg.status === 'failed' ? '✗' : '◉'

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      {/* 左侧竖线连接占位 */}
      <div style={{ width: 32, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
        <div style={{ width: 1, height: '100%', background: 'var(--border-light)', minHeight: 28, margin: '0 auto' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '5px 12px', background: 'var(--bg)', borderRadius: 6, border: '1px solid var(--border-light)' }}>
        <span style={{ fontSize: 14, flexShrink: 0 }}>{icon}</span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>{label}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, maxWidth: 200 }}>{desc}</span>
        {msg.time && <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0, fontFamily: "'JetBrains Mono', monospace" }}>{msg.time}</span>}
        <span style={{ color: statusColor, fontWeight: 700, fontSize: 13, flexShrink: 0 }}>{statusIcon}</span>
        {msg.output && (
          <button onClick={() => setShowOutput(s => !s)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', flexShrink: 0 }}>
            {showOutput ? '收起' : '详情'}
          </button>
        )}
      </div>
      {showOutput && msg.output && (
        <div style={{ gridColumn: '2', paddingLeft: 44, paddingTop: 4 }}>
          {/* 下方输出独占行，通过flex布局处理 */}
        </div>
      )}
    </div>
  )
}

// 单独渲染工具输出（避免嵌套布局问题）
function ToolOutputRow({ output }: { output: string[] }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ width: 32, flexShrink: 0 }} />
      <div style={{ flex: 1, paddingLeft: 12, paddingBottom: 4 }}>
        {output.map((line, i) => (
          <div key={i} style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 8, lineHeight: 1.7 }}>
            <span style={{ opacity: 0.5, flexShrink: 0 }}>└</span>
            <span>{line}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function AgentBubble({ msg }: { msg: AgentMessage }) {
  const renderMarkdown = (text: string) => {
    const lines = text.split('\n')
    const elements: React.ReactNode[] = []
    let tableLines: string[] = []
    let inTable = false

    const flushTable = () => {
      if (tableLines.length < 2) { tableLines = []; inTable = false; return }
      const rows = tableLines.map(l => l.split('|').filter((_, i, a) => i > 0 && i < a.length - 1).map(c => c.trim()))
      elements.push(
        <table key={`table-${elements.length}`} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, margin: '10px 0' }}>
          <thead>
            <tr>{rows[0].map((cell, i) => <th key={i} style={{ background: 'var(--bg)', padding: '8px 14px', textAlign: 'left' as const, border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>{cell}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(2).map((row, ri) => (
              <tr key={ri}>{row.map((cell, ci) => <td key={ci} style={{ padding: '8px 14px', border: '1px solid var(--border-light)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{cell}</td>)}</tr>
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
      const rendered = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**')) return <strong key={j} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
        if (part.startsWith('`') && part.endsWith('`')) return <code key={j} style={{ background: 'var(--bg)', padding: '1px 6px', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{part.slice(1, -1)}</code>
        return part
      })
      elements.push(<p key={i} style={{ margin: '4px 0', lineHeight: 1.8, color: 'var(--text-primary)' }}>{rendered}</p>)
    })
    if (inTable) flushTable()
    return elements
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AgentAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>FinAgent</div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '2px 12px 12px 12px', padding: '16px 20px', fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.75, boxShadow: '0 1px 4px rgba(11,46,92,0.05)' }}>
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

  // 工具名转为中文
  const toolInfo = getToolInfo(msg.tool, msg.args)

  if (resolved) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <div style={{ width: 32, flexShrink: 0 }} />
        <div style={{ fontSize: 13, color: 'var(--status-done)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          已确认操作
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AgentAvatar />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>FinAgent · 需要您确认</div>
        <div style={{ borderLeft: '4px solid var(--status-warn)', background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '0 8px 8px 8px', padding: '16px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 16 }}>{toolInfo.icon}</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#92400E' }}>智能体即将执行：{toolInfo.label}</span>
          </div>
          <div style={{ fontSize: 13, color: '#92400E', background: 'rgba(146,64,14,0.06)', borderRadius: 5, padding: '8px 12px', marginBottom: 16, fontFamily: "'JetBrains Mono', monospace" }}>
            {msg.args}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' as const }}>
            <button onClick={() => { msg.onApprove?.(); setResolved(true) }} style={{ padding: '7px 18px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>允许执行</button>
            <button onClick={() => { msg.onReject?.(); setResolved(true) }} style={{ padding: '7px 18px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 6, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
            <button onClick={() => setShowReply(s => !s)} style={{ padding: '7px 18px', background: 'transparent', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 6, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>回复智能体</button>
          </div>
          {showReply && (
            <div style={{ marginTop: 12 }}>
              <textarea
                value={replyText}
                onChange={e => setReplyText(e.target.value)}
                placeholder="告诉智能体你的想法，它会据此调整下一步操作..."
                style={{ width: '100%', minHeight: 72, padding: '8px 12px', border: '1px solid #FDE68A', borderRadius: 6, fontFamily: 'inherit', fontSize: 13, resize: 'vertical' as const, background: '#fff', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)' }}
              />
              <div style={{ marginTop: 8, textAlign: 'right' as const }}>
                <button onClick={() => { if (replyText.trim()) setResolved(true) }} style={{ padding: '6px 18px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>发送</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AgentAvatar />
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>FinAgent</div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '2px 12px 12px 12px', padding: '14px 18px', display: 'flex', gap: 4, alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--action)', animation: 'thinking-bounce 1.2s ease-in-out infinite', animationDelay: `${i * 0.2}s` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

interface MessageListProps {
  messages?: Message[]
}

export function MessageList({ messages = MOCK_MESSAGES }: MessageListProps) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      {messages.map((msg, i) => {
        if (msg.type === 'tool') {
          return (
            <div key={`${msg.type}-${i}`} style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              <ToolRow msg={msg} />
              {msg.output && (
                <ToolOutputRow output={msg.output} />
              )}
            </div>
          )
        }
        switch (msg.type) {
          case 'user':      return <UserBubble key={`${msg.type}-${i}`} msg={msg} />
          case 'reasoning': return <ReasoningBlock key={`${msg.type}-${i}`} msg={msg} />
          case 'agent':     return <AgentBubble key={`${msg.type}-${i}`} msg={msg} />
          case 'hitl':      return <HitlCard key={`${msg.type}-${i}`} msg={msg} />
          case 'thinking':  return <ThinkingBubble key={`${msg.type}-${i}`} />
          default:          return null
        }
      })}
    </div>
  )
}
