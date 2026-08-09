import { useState } from 'react'

type RunStatus = 'running' | 'done' | 'waiting' | 'queued'

interface WorkspaceFile {
  name: string
  size: string
  type: 'csv' | 'py' | 'png' | 'md' | 'other'
  isOutput?: boolean
  desc?: string  // 用户友好的文件说明
}

interface StepItem {
  status: 'done' | 'running' | 'pending' | 'failed'
  label: string   // 中文描述
  detail?: string
  time?: string
}

// ── Mock 数据（与 MessageList 的对话内容匹配）───────────────────
const MOCK_STATUS: RunStatus = 'done'
const MOCK_ELAPSED = '3m22s'
const MOCK_TOKENS = 31340
const MOCK_TOKEN_QUOTA = 120000

const MOCK_FILES: WorkspaceFile[] = [
  { name: 'portfolio_2026Q2.csv', size: '1.2 MB', type: 'csv', desc: '原始持仓数据' },
  { name: 'volatility_analysis.py', size: '2.1 KB', type: 'py', desc: '波动率分析脚本' },
  { name: 'rebalance_plan.py', size: '1.8 KB', type: 'py', desc: '减仓方案计算脚本' },
  // 分析产物
  { name: 'volatility_chart.png', size: '84 KB', type: 'png', isOutput: true, desc: '各行业年化波动率对比图' },
  { name: 'rebalance_plan.csv', size: '18 KB', type: 'csv', isOutput: true, desc: '减仓操作方案（可下载）' },
]

const MOCK_STEPS: StepItem[] = [
  { status: 'done', label: '读取持仓数据', detail: 'portfolio_2026Q2.csv · 4,831 行', time: '0.2s' },
  { status: 'done', label: '生成波动率分析脚本', time: '0.1s' },
  { status: 'failed', label: '执行分析', detail: '字段名错误，已自动修正', time: '0.4s' },
  { status: 'done', label: '修正代码后重新执行', detail: '处理完成，图表已生成', time: '3.8s' },
  { status: 'done', label: '读取持仓数据（减仓计算）', time: '0.1s' },
  { status: 'done', label: '生成减仓方案脚本', time: '0.1s' },
  { status: 'done', label: '计算减仓明细', detail: '科技行业 18.3% → 12%，减仓 1,505 万元', time: '1.2s' },
]

// ── 文件类型图标和颜色 ──────────────────────────────────────────
const FILE_CONFIG: Record<WorkspaceFile['type'], { icon: string; color: string; bg: string }> = {
  csv:   { icon: '📊', color: '#059669', bg: '#ECFDF5' },
  py:    { icon: '⌨️', color: '#2563EB', bg: '#EFF6FF' },
  png:   { icon: '🖼️', color: '#7C3AED', bg: '#F5F3FF' },
  md:    { icon: '📄', color: '#D97706', bg: '#FFFBEB' },
  other: { icon: '📁', color: '#6B7280', bg: '#F9FAFB' },
}

const STEP_TOOL_LABEL: Record<string, string> = {
  '读取持仓数据': '📂',
  '生成波动率分析脚本': '📝',
  '执行分析': '⚙️',
  '修正代码后重新执行': '🔄',
  '读取持仓数据（减仓计算）': '📂',
  '生成减仓方案脚本': '📝',
  '计算减仓明细': '⚙️',
}

// ── 子组件 ──────────────────────────────────────────────────────

function RunStatusBar({ status, elapsed, tokens, quota }: { status: RunStatus; elapsed: string; tokens: number; quota: number }) {
  const pct = Math.round(tokens / quota * 100)
  const cfg = {
    running: { color: 'var(--action)',       label: `分析中 · 已用时 ${elapsed}`,   dot: '◉' },
    done:    { color: 'var(--status-done)',  label: `分析完成 · 用时 ${elapsed}`,    dot: '✓' },
    waiting: { color: 'var(--status-warn)',  label: '等待您确认操作',               dot: '⏸' },
    queued:  { color: 'var(--text-muted)',   label: '排队中，请稍候',               dot: '○' },
  }[status]

  return (
    <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 18, color: cfg.color, lineHeight: 1 }}>{cfg.dot}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: cfg.color, flex: 1 }}>{cfg.label}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{ flex: 1, height: 5, background: 'var(--border-light)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: cfg.color, borderRadius: 3, transition: 'width 0.4s' }} />
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0, fontFamily: "'JetBrains Mono', monospace" }}>
          {(tokens / 1000).toFixed(0)}K / {(quota / 1000).toFixed(0)}K tokens
        </span>
      </div>
    </div>
  )
}

function FileSection({ files }: { files: WorkspaceFile[] }) {
  const [previewFile, setPreviewFile] = useState<string | null>(null)
  const outputs = files.filter(f => f.isOutput)
  const inputs = files.filter(f => !f.isOutput)

  return (
    <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>分析产物</div>

      {/* 图片产物全宽展示 */}
      {outputs.filter(f => f.type === 'png').map(f => (
        <div key={f.name} style={{ marginBottom: 12 }}>
          <div style={{ background: 'var(--bg)', border: '1px dashed var(--border)', borderRadius: 8, height: 140, display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
            <span style={{ fontSize: 28 }}>🖼️</span>
            <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{f.desc}</span>
            <span style={{ fontSize: 11 }}>{f.name} · {f.size}</span>
          </div>
          <button style={{ width: '100%', marginTop: 6, padding: '6px 0', background: 'var(--action-light)', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit' }}>
            ↓ 下载图表
          </button>
        </div>
      ))}

      {/* CSV/其他产物 */}
      {outputs.filter(f => f.type !== 'png').map(f => {
        const fc = FILE_CONFIG[f.type]
        return (
          <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: fc.bg, borderRadius: 7, border: `1px solid ${fc.color}22`, marginBottom: 8 }}>
            <span style={{ fontSize: 16, flexShrink: 0 }}>{fc.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{f.desc}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>{f.name} · {f.size}</div>
            </div>
            <button style={{ padding: '4px 10px', background: 'var(--surface)', color: fc.color, border: `1px solid ${fc.color}44`, borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }}>
              ↓ 下载
            </button>
          </div>
        )
      })}

      {/* 输入文件（折叠区） */}
      {inputs.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer', listStyle: 'none', display: 'flex', alignItems: 'center', gap: 4, userSelect: 'none' }}>
            <span>▶</span> 上传的文件（{inputs.length} 个）
          </summary>
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column' as const, gap: 4 }}>
            {inputs.map(f => {
              const fc = FILE_CONFIG[f.type]
              const isExpanded = previewFile === f.name
              return (
                <div key={f.name}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0' }}>
                    <span style={{ fontSize: 13 }}>{fc.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{f.name}</div>
                      {f.desc && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{f.desc} · {f.size}</div>}
                    </div>
                    {(f.type === 'py' || f.type === 'csv') && (
                      <button onClick={() => setPreviewFile(p => p === f.name ? null : f.name)} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', padding: 0, flexShrink: 0 }}>
                        {isExpanded ? '收起' : '预览'}
                      </button>
                    )}
                  </div>
                  {isExpanded && (
                    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, padding: '8px 10px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 4 }}>
                      <div style={{ color: 'var(--text-muted)' }}># {f.name}</div>
                      <div>import pandas as pd</div>
                      <div style={{ color: 'var(--text-muted)' }}># ... 联调时替换为真实内容</div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </details>
      )}
    </div>
  )
}

function StepsSection({ steps }: { steps: StepItem[] }) {
  const [collapsed, setCollapsed] = useState(true)
  const allDone = steps.every(s => s.status === 'done' || s.status === 'failed')

  return (
    <div style={{ padding: '14px 16px' }}>
      <button
        onClick={() => setCollapsed(s => !s)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', padding: 0, marginBottom: collapsed ? 0 : 12 }}
      >
        <span>执行步骤</span>
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>
          {collapsed ? `▾ 展开（共 ${steps.length} 步）` : '▲ 收起'}
        </span>
      </button>

      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 0 }}>
          {steps.map((step, i) => {
            const isFailed = step.status === 'failed'
            const isRunning = step.status === 'running'
            const isDone = step.status === 'done'
            const statusColor = isFailed ? '#DC2626' : isRunning ? 'var(--action)' : isDone ? 'var(--status-done)' : 'var(--text-muted)'
            const statusIcon = isFailed ? '✗' : isRunning ? '◉' : isDone ? '✓' : '○'
            const icon = STEP_TOOL_LABEL[step.label] ?? '🔧'

            return (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', paddingBottom: 10, position: 'relative' as const }}>
                {/* 竖线连接 */}
                {i < steps.length - 1 && (
                  <div style={{ position: 'absolute' as const, left: 11, top: 22, width: 1, height: 'calc(100% - 12px)', background: 'var(--border-light)' }} />
                )}
                {/* 状态点 */}
                <div style={{ width: 22, height: 22, borderRadius: '50%', border: `2px solid ${statusColor}`, background: isDone ? statusColor : isFailed ? statusColor : 'var(--surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, zIndex: 1 }}>
                  <span style={{ fontSize: 10, color: (isDone || isFailed) ? '#fff' : statusColor, fontWeight: 700, lineHeight: 1 }}>{statusIcon}</span>
                </div>
                {/* 内容 */}
                <div style={{ flex: 1, paddingTop: 2 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 12 }}>{icon}</span>
                    <span style={{ fontSize: 13, color: isFailed ? '#DC2626' : 'var(--text-primary)', fontWeight: 500 }}>{step.label}</span>
                    {step.time && <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto', flexShrink: 0 }}>{step.time}</span>}
                  </div>
                  {step.detail && (
                    <div style={{ fontSize: 12, color: isFailed ? '#DC2626' : 'var(--text-muted)', marginTop: 2, paddingLeft: 18 }}>{step.detail}</div>
                  )}
                </div>
              </div>
            )
          })}
          {!allDone && (
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ width: 22, height: 22, borderRadius: '50%', border: '2px solid var(--action)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: 8, color: 'var(--action)', animation: 'thinking-bounce 1.2s ease-in-out infinite' }}>◉</span>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>执行中...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ArtifactPanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, height: '100%', overflow: 'hidden', background: 'var(--surface)', borderLeft: '1px solid var(--border)' }}>
      <RunStatusBar status={MOCK_STATUS} elapsed={MOCK_ELAPSED} tokens={MOCK_TOKENS} quota={MOCK_TOKEN_QUOTA} />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <FileSection files={MOCK_FILES} />
        <StepsSection steps={MOCK_STEPS} />
      </div>
    </div>
  )
}
