import { memo, useEffect, useMemo, useState } from 'react'
import type { InterruptAction } from '../../api/events'
import type { Decision } from '../../api/types'
import { errorMessage } from '../../api/request'
import { buildDecisions, createDecisionDrafts, DECISION_LABEL } from '../decisions'
import type { DecisionDraft } from '../decisions'
import type { RunViewItem } from '../eventReducer'
import { MarkdownAnswer } from './MarkdownAnswer'

interface MessageListProps {
  items: RunViewItem[]
  pendingActions?: InterruptAction[] | null
  onApprove?: (decisions: Decision[]) => Promise<void>
  /** 所属 thread，用于把答复里的 outputs/ 相对路径重写为下载 URL。 */
  threadId?: string
  /** 该 run 是否还在流式输出；流式期间最后一条走轻量渲染 + 光标。 */
  live?: boolean
}

type RenderEntry =
  | { kind: 'item'; item: RunViewItem; index: number }
  | { kind: 'subagent'; path: string[]; items: Array<{ item: RunViewItem; index: number }> }

const DECISION_TYPES = ['approve', 'reject', 'edit', 'respond'] as const

function jsonArgs(args: Record<string, unknown>): string {
  return JSON.stringify(args, null, 2)
}

function pathLabel(path: string[]): string {
  return path.length > 0 ? path.join(' / ') : 'FinAgent'
}

function samePath(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((part, index) => part === right[index])
}

function groupNestedItems(items: RunViewItem[]): RenderEntry[] {
  const entries: RenderEntry[] = []
  items.forEach((item, index) => {
    if (item.path.length === 0) {
      entries.push({ kind: 'item', item, index })
      return
    }
    const previous = entries.at(-1)
    if (previous?.kind === 'subagent' && samePath(previous.path, item.path)) {
      previous.items.push({ item, index })
      return
    }
    entries.push({ kind: 'subagent', path: item.path, items: [{ item, index }] })
  })
  return entries
}

function ToolView({ item, nested = false }: { item: Extract<RunViewItem, { kind: 'tool' }>; nested?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const color = item.status === 'error' ? '#DC2626' : item.status === 'running' ? 'var(--action)' : 'var(--status-done)'
  return <div style={{ marginLeft: nested ? 0 : 44, border: '1px solid var(--border-light)', borderRadius: 7, background: 'var(--surface)', overflow: 'hidden' }}>
    <button type="button" onClick={() => setExpanded(value => !value)} style={{ width: '100%', padding: '8px 12px', border: 'none', background: 'transparent', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontFamily: 'inherit', color: 'var(--text-secondary)' }}>
      <span style={{ color, fontWeight: 700 }}>{item.status === 'running' ? '◉' : item.status === 'success' ? '✓' : '✗'}</span>
      <strong>{item.name}</strong>
      <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>{nested ? '' : `${pathLabel(item.path)} · `}{expanded ? '收起' : '详情'}</span>
    </button>
    {expanded && <pre style={{ margin: 0, padding: '10px 12px', borderTop: '1px solid var(--border-light)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11, color: 'var(--text-secondary)', background: 'var(--bg)' }}>
      {jsonArgs(item.args)}{item.content === undefined ? '' : `\n\n${item.content}`}
    </pre>}
  </div>
}

const ItemView = memo(function ItemView({ item, index, nested = false, streaming = false, threadId }: { item: RunViewItem; index: number; nested?: boolean; streaming?: boolean; threadId?: string }) {
  if (item.kind === 'tool') return <ToolView key={`tool-${item.id}-${index}`} item={item} nested={nested} />
  if (item.kind === 'notice') return <div key={`notice-${index}`} style={{ marginLeft: nested ? 0 : 44, padding: '8px 12px', borderRadius: 6, background: item.tone === 'error' ? '#FEF2F2' : item.tone === 'warning' ? '#FFFBEB' : 'var(--action-light)', color: item.tone === 'error' ? '#DC2626' : item.tone === 'warning' ? '#92400E' : 'var(--action)', fontSize: 12 }}>{item.message}</div>
  if (item.kind === 'reasoning') {
    if (nested) return <div key={`reasoning-${index}`} style={{ padding: '8px 12px', borderLeft: '2px solid var(--action-border)', background: 'var(--action-light)', color: 'var(--text-secondary)', fontSize: 12 }}>
      <div style={{ color: 'var(--action)', marginBottom: 6 }}>分析思路</div>
      <MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} />
    </div>
    return <details key={`reasoning-${index}`} open style={{ marginLeft: 44, padding: '8px 12px', borderLeft: '2px solid var(--action-border)', background: 'var(--action-light)', color: 'var(--text-secondary)', fontSize: 12 }}>
      <summary style={{ cursor: 'pointer', color: 'var(--action)', marginBottom: 6 }}>{pathLabel(item.path)} · 分析思路</summary>
      <MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} />
    </details>
  }
  if (nested) return <div key={`answer-${index}`} style={{ padding: '10px 12px', border: '1px solid var(--border-light)', borderRadius: 7, background: 'var(--surface)', overflowWrap: 'anywhere', lineHeight: 1.7, fontSize: 13 }}><MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} /></div>
  return <div key={`answer-${index}`} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand)', color: '#fff', display: 'grid', placeItems: 'center', flexShrink: 0, fontWeight: 700 }}>F</div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5 }}>{pathLabel(item.path)}</div>
      <div style={{ padding: '14px 18px', border: '1px solid var(--border)', borderRadius: '2px 12px 12px 12px', background: 'var(--surface)', overflowWrap: 'anywhere', lineHeight: 1.75, fontSize: 14 }}>
        <MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} />
        {streaming && <span className="cursor" aria-hidden="true" />}
      </div>
    </div>
  </div>
})

function SubagentGroup({ path, items, threadId, lastIndex, live }: Extract<RenderEntry, { kind: 'subagent' }> & { threadId?: string; lastIndex: number; live: boolean }) {
  const name = path[path.length - 1]
  return <details data-subagent={name} style={{ marginLeft: 44, border: '1px solid var(--action-border)', borderRadius: 8, background: 'var(--action-light)', overflow: 'hidden' }}>
    <summary style={{ padding: '10px 12px', cursor: 'pointer', color: 'var(--action)', fontSize: 13 }}>
      <strong>{name}</strong><span style={{ marginLeft: 8, color: 'var(--text-muted)', fontSize: 11 }}>{items.length} 条过程</span>
    </summary>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '0 12px 12px' }}>
      {items.map(one => <ItemView key={`${one.item.kind}-${one.index}`} item={one.item} index={one.index} nested threadId={threadId} streaming={live && one.index === lastIndex} />)}
    </div>
  </details>
}

function ApprovalBatch({ actions, onApprove }: { actions: InterruptAction[]; onApprove: (decisions: Decision[]) => Promise<void> }) {
  const signature = useMemo(() => actions.map(action => `${action.index}:${action.tool_name}:${jsonArgs(action.args)}`).join('|'), [actions])
  const [drafts, setDrafts] = useState<Record<number, DecisionDraft>>({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setDrafts(createDecisionDrafts(actions))
    setFormError('')
  }, [actions, signature])

  const patchDraft = (index: number, change: Partial<DecisionDraft>) => {
    setDrafts(current => ({
      ...current,
      [index]: { ...(current[index] ?? { type: null, message: '', args: '{}' }), ...change },
    }))
    setFormError('')
  }

  const submit = async () => {
    try {
      setSubmitting(true)
      await onApprove(buildDecisions(actions, drafts))
    } catch (error) {
      setFormError(errorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return <div style={{ marginLeft: 44, padding: 16, border: '1px solid #FDE68A', borderLeft: '4px solid var(--status-warn)', borderRadius: '0 8px 8px 8px', background: '#FFFBEB' }}>
    <div style={{ fontSize: 14, fontWeight: 700, color: '#92400E', marginBottom: 6 }}>智能体请求执行 {actions.length} 个敏感操作</div>
    <div style={{ fontSize: 12, color: '#92400E', marginBottom: 12 }}>请逐项选择决策，所有操作将一次性提交。</div>
    {actions.map(action => {
      const draft = drafts[action.index] ?? { type: null, message: '', args: jsonArgs(action.args) }
      return <fieldset key={action.index} style={{ border: '1px solid #FDE68A', borderRadius: 7, margin: '0 0 10px', padding: 12 }}>
        <legend style={{ padding: '0 6px', color: '#92400E', fontSize: 12, fontWeight: 600 }}>#{action.index + 1} {action.tool_name}</legend>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: 'rgba(146,64,14,0.06)', padding: 9, borderRadius: 5, color: '#92400E', fontSize: 11 }}>{jsonArgs(action.args)}</pre>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {DECISION_TYPES.filter(type => action.allowed_decisions.includes(type)).map(type => <button key={type} type="button" onClick={() => patchDraft(action.index, { type })} style={{ padding: '6px 11px', border: draft.type === type ? '1px solid var(--action)' : '1px solid #FDE68A', borderRadius: 5, background: draft.type === type ? 'var(--action)' : '#fff', color: draft.type === type ? '#fff' : '#92400E', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>{DECISION_LABEL[type]}</button>)}
        </div>
        {(draft.type === 'reject' || draft.type === 'respond') && <textarea value={draft.message} onChange={event => patchDraft(action.index, { message: event.target.value })} placeholder="必填：说明理由或告诉智能体如何调整" style={{ width: '100%', minHeight: 64, boxSizing: 'border-box', marginTop: 9, padding: 8, border: '1px solid #FDE68A', borderRadius: 5, font: 'inherit', fontSize: 12 }} />}
        {draft.type === 'edit' && <textarea value={draft.args} onChange={event => patchDraft(action.index, { args: event.target.value })} aria-label={`修改${action.tool_name}参数`} style={{ width: '100%', minHeight: 90, boxSizing: 'border-box', marginTop: 9, padding: 8, border: '1px solid #FDE68A', borderRadius: 5, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }} />}
      </fieldset>
    })}
    {formError && <div role="alert" style={{ color: '#DC2626', fontSize: 12, marginBottom: 8 }}>{formError}</div>}
    <button type="button" disabled={submitting} onClick={() => void submit()} style={{ padding: '8px 18px', border: 'none', borderRadius: 6, background: 'var(--action)', color: '#fff', cursor: submitting ? 'default' : 'pointer', fontWeight: 600, fontFamily: 'inherit' }}>{submitting ? '正在提交…' : '提交全部决策'}</button>
  </div>
}

export function MessageList({ items, pendingActions, onApprove, threadId, live = false }: MessageListProps) {
  const entries = groupNestedItems(items)
  // 流式态：只有列表最后一条（token/reasoning 增量都合并进最后一项）在「动」，
  // 其余项渲染结果不变 —— 用 identity 判断，避免逐 token 重渲染已定稿消息。
  const lastIndex = items.length - 1
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }} aria-live="polite">
    {entries.map((entry, index) => entry.kind === 'subagent'
      ? <SubagentGroup key={`subagent-${entry.path.join('/')}-${index}`} {...entry} threadId={threadId} lastIndex={lastIndex} live={live} />
      : <ItemView key={`item-${entry.index}`} item={entry.item} index={entry.index} threadId={threadId} streaming={live && entry.index === lastIndex} />)}
    {pendingActions && pendingActions.length > 0 && onApprove && <ApprovalBatch actions={pendingActions} onApprove={onApprove} />}
  </div>
}
