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
interface HitlMessage {
  type: 'hitl'; tool: string; args: string
  resolved?: boolean; onApprove?: () => void; onReject?: () => void
}
interface ThinkingMessage { type: 'thinking' }

type Message = UserMessage | ReasoningMessage | ToolMessage | AgentMessage | HitlMessage | ThinkingMessage

const TOOL_LABEL: Record<string, { label: string; icon: string }> = {
  read_file:  { label: '读取数据文件', icon: '📂' },
  write_file: { label: '生成分析代码', icon: '📝' },
  execute:    { label: '执行计算',     icon: '⚙️' },
  edit_file:  { label: '修正代码',     icon: '✏️' },
  delete:     { label: '删除文件',     icon: '🗑' },
  ls:         { label: '查看目录',     icon: '📁' },
  glob:       { label: '搜索文件',     icon: '🔍' },
  grep:       { label: '搜索内容',     icon: '🔎' },
}

function getToolInfo(name: string, arg: string) {
  const info = TOOL_LABEL[name] ?? { label: name, icon: '🔧' }
  let desc = arg
  if (name === 'execute' && arg.startsWith('python ')) desc = `运行 ${arg.replace('python ', '')}`
  else if (name === 'write_file' && arg.endsWith('.py')) desc = `保存为 ${arg}`
  else if (name === 'read_file') desc = `加载 ${arg}`
  else if (name === 'edit_file') desc = `修正 ${arg}`
  else if (name === 'ls') desc = arg || '/workspace'
  return { ...info, desc }
}

// ── Mock 对话数据（覆盖所有消息类型与场景）────────────────────────
const MOCK_MESSAGES: Message[] = [

  // ── 第一轮：用户上传文件，先探索数据结构 ─────────────────────────
  {
    type: 'user',
    text: '我上传了 portfolio_2026Q2.csv，里面是公司最新持仓数据。先帮我看看数据结构，了解一下有哪些字段和行业分类。',
    attachments: [{ name: 'portfolio_2026Q2.csv' }],
  },
  // 工具：查看目录（ls）
  { type: 'tool', status: 'done', name: 'ls', arg: '/workspace', time: '0.1s' },
  // 工具：读取文件（含输出详情）
  {
    type: 'tool', status: 'done', name: 'read_file', arg: 'portfolio_2026Q2.csv', time: '0.2s',
    output: ['共 4,831 行数据', '字段：股票代码 / 行业 / 持仓市值(万元) / 持仓比例 / 买入日期 / 当前价格', '行业分类：金融 · 科技 · 消费 · 能源 · 医疗 · 工业 · 材料 · 公用事业（共 8 个）'],
  },
  // Agent 回答（纯文字，无表格）
  {
    type: 'agent',
    markdown: `数据结构清晰，可以直接开始分析。

**基本信息：**
- 持仓股票 **312 只**，覆盖 8 个行业
- 最大单笔持仓：科技行业某只股票，占比 **4.2%**
- 数据时间范围：2026-01-02 至 2026-06-30（共 6 个月）

**各行业持仓比例概览：**
科技 18.3% · 金融 22.1% · 消费 15.7% · 能源 12.4% · 医疗 11.2% · 其他 20.3%

数据质量良好，未发现缺失值。请告诉我下一步想做什么分析。`,
  },

  // ── 第二轮：计算年化波动率，遇到错误并自动修复 ────────────────────
  {
    type: 'user',
    text: '帮我计算各行业的年化波动率，用条形图对比展示，并给出风险评估结论。',
  },
  // 分析思路（完成后折叠）
  {
    type: 'reasoning',
    text: '需要按行业分组，从持仓数据中提取各行业的历史价格序列。\n\n计算步骤：\n1. 按行业分组，提取每只股票的日收益率序列\n2. 计算组合层面的行业日收益率（按持仓比例加权）\n3. 对日波动率乘以 √252 得到年化波动率\n4. 用 matplotlib 生成横向条形图，按波动率从高到低排列\n5. 结合波动率阈值给出风险评级（高/中/低）',
    done: true,
  },
  // 工具：写代码
  { type: 'tool', status: 'done', name: 'write_file', arg: 'volatility_analysis.py', time: '0.1s' },
  // 工具：执行失败（关键场景：错误恢复）
  {
    type: 'tool', status: 'failed', name: 'execute', arg: 'python volatility_analysis.py', time: '0.4s',
    output: ['KeyError: "date"', '数据中日期字段名为 "buy_date"，代码使用了错误的字段名，已定位到第 23 行'],
  },
  // 工具：修正代码
  { type: 'tool', status: 'done', name: 'edit_file', arg: 'volatility_analysis.py', time: '0.1s' },
  // 工具：重新执行（成功）
  {
    type: 'tool', status: 'done', name: 'execute', arg: 'python volatility_analysis.py', time: '3.8s',
    output: ['正在处理 4,831 条持仓记录...', '按 8 个行业分组，加权计算日收益率...', '年化波动率计算完成', '图表已保存至 outputs/volatility_chart.png'],
  },
  // Agent 回答（含表格 + 结论）
  {
    type: 'agent',
    markdown: `各行业年化波动率计算完成，图表已生成。

| 行业 | 年化波动率 | 风险等级 | 持仓占比 |
|------|-----------|---------|--------|
| 科技 | 31.2% | 🔴 高 | 18.3% |
| 能源 | 24.1% | 🟡 中 | 12.4% |
| 材料 | 22.8% | 🟡 中 | 5.1% |
| 医疗 | 19.6% | 🟡 中 | 11.2% |
| 工业 | 17.3% | 🟢 低 | 8.8% |
| 消费 | 15.7% | 🟢 低 | 15.7% |
| 金融 | 14.2% | 🟢 低 | 22.1% |
| 公用事业 | 10.9% | 🟢 低 | 6.4% |

**风险评估结论：** 科技行业波动率（31.2%）显著高于组合均值（18.9%），是当前最主要的风险来源。能源和材料次之。整体来看，金融和公用事业起到了较好的压舱作用。`,
  },

  // ── 第三轮：HITL 审批确认（已处理） ────────────────────────────
  {
    type: 'hitl',
    tool: 'delete',
    args: '/workspace/raw_price_cache.csv',
    resolved: true,
  },

  // ── 第四轮：追问，纯文字回答（无工具调用）────────────────────────
  {
    type: 'user',
    text: '科技行业波动率这么高，是个别股票拉高的还是整体都高？有没有什么风险控制建议？',
  },
  {
    type: 'agent',
    markdown: `科技行业高波动率是**结构性问题而非个别股票**导致的。

从持仓数据来看：
- 科技行业 57 只股票中，有 **43 只**年化波动率超过 25%
- 其中 11 只超过 40%，集中在半导体设备和 AI 算力方向
- 持仓最重的前 5 只科技股，单只波动率均在 28%-35% 之间

**风险控制建议：**

**① 降低集中度** — 科技行业当前占比 18.3%，建议压缩至 12%-14%，降低整体组合波动

**② 内部结构调整** — 在科技持仓内部，将高波动（超过 30%）标的替换为波动相对温和的软件或互联网板块

**③ 动态止损线** — 对单只波动率超过 35% 的持仓设置 12% 的动态止损线，控制尾部风险

**④ 对冲工具** — 如有条件，可用科技 ETF 期权对冲极端波动，成本约为持仓市值的 0.8-1.2%/季度

如需进一步分析具体要卖出哪些标的，请直接告诉我目标配置比例。`,
  },

  // ── 第五轮：要求出具体操作方案，含代码块的回答 ───────────────────
  {
    type: 'user',
    text: '好，按你的建议把科技行业从 18.3% 降到 12%，帮我算出需要减仓的具体股票和金额。',
  },
  {
    type: 'reasoning',
    text: '需要重新读取持仓数据，按科技行业的持仓市值排序，计算需要减仓的总金额（18.3% - 12% = 6.3% 的仓位），然后从高波动率的标的开始优先减仓，同时保持行业内分散度。',
    done: true,
  },
  { type: 'tool', status: 'done', name: 'read_file', arg: 'portfolio_2026Q2.csv', time: '0.1s' },
  {
    type: 'tool', status: 'done', name: 'write_file', arg: 'rebalance_plan.py', time: '0.1s' },
  {
    type: 'tool', status: 'done', name: 'execute', arg: 'python rebalance_plan.py', time: '1.2s',
    output: ['科技行业当前总市值：4,382 万元', '目标市值：2,877 万元（12%）', '需减仓：1,505 万元', '优先减仓列表已生成（按波动率降序排列）'],
  },
  {
    type: 'agent',
    markdown: `根据目标配置，需减仓科技行业 **1,505 万元**（从 18.3% → 12.0%）。

建议优先减仓以下标的（按波动率从高到低）：

| 股票 | 当前持仓(万) | 建议减仓(万) | 波动率 | 减后占比 |
|------|------------|------------|--------|---------|
| 某半导体A | 312 | 312 | 42.1% | 0%（清仓）|
| 某AI算力B | 286 | 200 | 38.6% | 0.8% |
| 某设备C | 248 | 180 | 35.2% | 0.7% |
| 某芯片D | 201 | 150 | 31.8% | 0.5% |
| 某软件E | 178 | 120 | 28.4% | 0.6% |
| 其他（共14只）| — | 543 | <28% | 按比例减 |

操作完成后，科技行业持仓将从 **57 只** 调整为 **52 只**，预计年化波动率从 31.2% 降至约 **23.8%**。

减仓方案已写入 \`outputs/rebalance_plan.csv\`，可在右侧面板下载。`,
  },

  // ── 第六轮：用户问代码问题，agent 还在思考中 ─────────────────────
  {
    type: 'user',
    text: '顺便问一下，如果我想自己用 Python 计算夏普比率，代码大概怎么写？无风险利率用 2.5%。',
  },
  { type: 'thinking' },
]

// ── 样式常量 ──────────────────────────────────────────────────────
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

// ── 消息组件 ──────────────────────────────────────────────────────

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
  const isFailed = msg.status === 'failed'
  const statusColor = isFailed ? '#DC2626' : msg.status === 'running' ? 'var(--action)' : 'var(--status-done)'
  const statusIcon = isFailed ? '✗' : msg.status === 'running' ? '◉' : '✓'

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ width: 32, display: 'flex', justifyContent: 'center', flexShrink: 0, paddingTop: 6 }}>
        <div style={{ width: 1, background: isFailed ? '#FECACA' : 'var(--border-light)', minHeight: 24, margin: '0 auto' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '6px 12px',
          background: isFailed ? '#FEF2F2' : 'var(--bg)',
          borderRadius: 6,
          border: `1px solid ${isFailed ? '#FECACA' : 'var(--border-light)'}`,
        }}>
          <span style={{ fontSize: 14, flexShrink: 0 }}>{icon}</span>
          <span style={{ fontSize: 13, color: isFailed ? '#DC2626' : 'var(--text-secondary)', flex: 1 }}>{label}</span>
          <span style={{ fontSize: 12, color: isFailed ? '#DC2626' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, maxWidth: 200 }}>{desc}</span>
          {msg.time && <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0, fontFamily: "'JetBrains Mono', monospace" }}>{msg.time}</span>}
          <span style={{ color: statusColor, fontWeight: 700, fontSize: 13, flexShrink: 0 }}>{statusIcon}</span>
          {msg.output && (
            <button
              onClick={() => setShowOutput(s => !s)}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', flexShrink: 0, padding: '0 2px' }}
            >
              {showOutput ? '收起' : '详情'}
            </button>
          )}
        </div>
        {/* 输出详情（受 showOutput 控制，修复之前的 bug）*/}
        {showOutput && msg.output && (
          <div style={{ paddingLeft: 12, paddingTop: 4, paddingBottom: 4 }}>
            {msg.output.map((line, i) => (
              <div key={i} style={{ fontSize: 12, color: isFailed ? '#DC2626' : 'var(--text-muted)', display: 'flex', gap: 8, lineHeight: 1.7 }}>
                <span style={{ opacity: 0.5, flexShrink: 0 }}>└</span>
                <span>{line}</span>
              </div>
            ))}
          </div>
        )}
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

      // 处理有序列表
      if (/^\d+\.\s/.test(line)) {
        const content = line.replace(/^\d+\.\s/, '')
        const rendered = renderInline(content)
        elements.push(
          <div key={i} style={{ margin: '3px 0', paddingLeft: 16, fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.75, display: 'flex', gap: 8 }}>
            <span style={{ color: 'var(--text-muted)', flexShrink: 0, fontWeight: 600 }}>{line.match(/^\d+/)![0]}.</span>
            <span>{rendered}</span>
          </div>
        )
        return
      }

      // 处理无序列表
      if (line.startsWith('- ')) {
        const content = line.slice(2)
        const rendered = renderInline(content)
        elements.push(
          <div key={i} style={{ margin: '3px 0', paddingLeft: 16, fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.75, display: 'flex', gap: 8 }}>
            <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>·</span>
            <span>{rendered}</span>
          </div>
        )
        return
      }

      // 处理 **标题** 行（独立行的加粗视为小标题）
      if (line.startsWith('**') && line.endsWith('**') && line.length > 4) {
        elements.push(
          <div key={i} style={{ margin: '12px 0 4px', fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
            {line.slice(2, -2)}
          </div>
        )
        return
      }

      elements.push(<p key={i} style={{ margin: '4px 0', lineHeight: 1.8, color: 'var(--text-primary)', fontSize: 14 }}>{renderInline(line)}</p>)
    })
    if (inTable) flushTable()
    return elements
  }

  const renderInline = (text: string): React.ReactNode[] =>
    text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, j) => {
      if (part.startsWith('**') && part.endsWith('**')) return <strong key={j} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
      if (part.startsWith('`') && part.endsWith('`')) return <code key={j} style={{ background: 'var(--bg)', padding: '1px 6px', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--action)' }}>{part.slice(1, -1)}</code>
      return part
    })

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
  const toolInfo = getToolInfo(msg.tool, msg.args)

  if (resolved) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <div style={{ width: 32, flexShrink: 0 }} />
        <div style={{ fontSize: 13, color: 'var(--status-done)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          已允许执行：{toolInfo.label}（{msg.args}）
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

interface MessageListProps { messages?: Message[] }

export function MessageList({ messages = MOCK_MESSAGES }: MessageListProps) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      {messages.map((msg, i) => {
        switch (msg.type) {
          case 'user':      return <UserBubble key={`${msg.type}-${i}`} msg={msg} />
          case 'reasoning': return <ReasoningBlock key={`${msg.type}-${i}`} msg={msg} />
          case 'tool':      return <ToolRow key={`${msg.type}-${i}`} msg={msg} />
          case 'agent':     return <AgentBubble key={`${msg.type}-${i}`} msg={msg} />
          case 'hitl':      return <HitlCard key={`${msg.type}-${i}`} msg={msg} />
          case 'thinking':  return <ThinkingBubble key={`${msg.type}-${i}`} />
          default:          return null
        }
      })}
    </div>
  )
}
