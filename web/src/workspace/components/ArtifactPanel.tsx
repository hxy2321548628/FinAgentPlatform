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

const FILE_ICON: Record<WorkspaceFile['type'], string> = { csv: '📄', py: '📄', png: '🖼', md: '📝', other: '📄' }

function RunStatusBar({ status, elapsed, tokens, quota }: { status: RunStatus; elapsed: string; tokens: number; quota: number }) {
  const pct = Math.round(tokens / quota * 100)
  const color = status === 'running' ? 'var(--action)' : status === 'done' ? 'var(--status-done)' : status === 'waiting' ? 'var(--status-warn)' : 'var(--text-muted)'
  const icon = status === 'running' ? '◉' : status === 'done' ? '✓' : status === 'waiting' ? '⏸' : '📋'
  const label = status === 'running' ? `运行中  ${elapsed}` : status === 'done' ? `完成 · 用时 ${elapsed} · 消耗 ${tokens.toLocaleString()} tokens` : status === 'waiting' ? '等待确认' : '排队中'
  return (
    <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>{icon} {label}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>{(tokens / 1000).toFixed(0)}K / {(quota / 1000).toFixed(0)}K</span>
      </div>
      <div style={{ height: 3, background: 'var(--border-light)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2 }} />
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
        <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{file.name}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>{file.size}</span>
        {canPreview && <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', padding: 0 }}>↗</button>}
        <button style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', padding: 0 }}>↓</button>
      </div>
      {isExpanded && (
        <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, padding: '8px 10px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 4 }}>
          <div style={{ color: 'var(--text-muted)' }}># {file.name} 预览</div>
          <div>import pandas as pd</div>
          <div>import numpy as np</div>
          <div style={{ color: 'var(--text-muted)' }}># ... 联调时替换为真实文件内容</div>
        </div>
      )}
    </div>
  )
}

function WorkspaceTree({ files }: { files: WorkspaceFile[] }) {
  const [previewFile, setPreviewFile] = useState<string | null>(null)
  const outputFiles = files.filter(f => f.isOutput)
  const rootFiles = files.filter(f => !f.isOutput)
  return (
    <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 10 }}>// 分析产物</div>
      {outputFiles.filter(f => f.type === 'png').map(f => (
        <div key={f.name} style={{ marginBottom: 10 }}>
          <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 120, padding: 12, color: 'var(--text-muted)', fontSize: 12 }}>
            🖼 {f.name} <span style={{ marginLeft: 6, fontSize: 11 }}>({f.size})</span>
          </div>
          <div style={{ marginTop: 6, textAlign: 'right' as const }}>
            <button style={{ fontSize: 12, color: 'var(--action)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>↓ 下载图片</button>
          </div>
        </div>
      ))}
      <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 4 }}>
        {[...rootFiles, ...outputFiles.filter(f => f.type !== 'png')].map(f => (
          <FileRow key={f.name} file={f} isExpanded={previewFile === f.name} onToggle={() => setPreviewFile(p => p === f.name ? null : f.name)} />
        ))}
      </div>
    </div>
  )
}

function StepsLog({ steps }: { steps: StepItem[] }) {
  const [collapsed, setCollapsed] = useState(false)
  const allDone = steps.every(s => s.status === 'done')
  return (
    <div style={{ padding: '14px 16px', flex: 1 }}>
      <button onClick={() => setCollapsed(s => !s)} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', padding: 0, marginBottom: collapsed ? 0 : 10 }}>
        <span>// STEPS</span>
        <span>{collapsed ? `▾ 展开查看（共 ${steps.length} 步）` : '▲ 收起'}</span>
      </button>
      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 4 }}>
          {steps.map((step, i) => {
            const icon = step.status === 'done' ? '✓' : step.status === 'pending' ? '○' : '◉'
            const color = step.status === 'done' ? 'var(--status-done)' : step.status === 'pending' ? 'var(--text-muted)' : 'var(--action)'
            return (
              <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)' }}>
                  <span style={{ color, fontWeight: 700, width: 10 }}>{icon}</span>
                  <span style={{ color: 'var(--action)', minWidth: 90 }}>{step.name}</span>
                  <span style={{ color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{step.arg}</span>
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
              <span style={{ color: 'var(--action)' }}>◉</span><span>执行中...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ArtifactPanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, height: '100%', overflow: 'hidden', background: 'var(--surface)' }}>
      <RunStatusBar status={MOCK_STATUS} elapsed={MOCK_ELAPSED} tokens={MOCK_TOKENS} quota={MOCK_TOKEN_QUOTA} />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <WorkspaceTree files={MOCK_FILES} />
        <StepsLog steps={MOCK_STEPS} />
      </div>
    </div>
  )
}
