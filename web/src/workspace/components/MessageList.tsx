import { memo, useEffect, useMemo, useState } from 'react'
import type { InterruptAction } from '../../api/events'
import type { Decision } from '../../api/types'
import { errorMessage } from '../../api/request'
import { buildDecisions, createDecisionDrafts, DECISION_LABEL, isQuestion, questionText } from '../decisions'
import type { DecisionDraft } from '../decisions'
import type { RunViewItem } from '../eventReducer'
import { MarkdownAnswer } from './MarkdownAnswer'
import { Logo } from '../../components/Logo'

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

/**
 * 一次中断里既可能有审批也可能有提问，标题得说清楚在等什么。
 *
 * 全是提问时说「在问你」，全是操作时说「要执行」，混着时两个数都报 ——
 * 一律说「敏感操作」会让教师以为智能体要动他的文件。
 */
function batchTitle(total: number, questions: number): string {
  if (questions === 0) return `智能体请求执行 ${total} 个敏感操作`
  if (questions === total) return `智能体在问你 ${total} 个问题`
  return `智能体在问你 ${questions} 个问题，另有 ${total - questions} 个敏感操作待确认`
}

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
  const color = item.status === 'error' ? 'var(--danger)' : item.status === 'running' ? 'var(--action)' : 'var(--status-done)'
  // `data-tool` 是给走查用的：按可见文字找工具名会连教师问题里提到的那个词一起命中，
  // 而那种红指向的是「卡片没收编掉」这个完全不相干的结论
  return <div data-tool={item.name} style={{ marginLeft: nested ? 0 : 44, border: '1px solid var(--border-light)', borderRadius: 7, background: 'var(--surface)', overflow: 'hidden' }}>
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

/**
 * 分析思路块：默认收起，标题行单行流式展示思考进度（与 DSH Web 一致），
 * 点击展开完整 Markdown。流式结束后自动回到收起态。
 */
function ReasoningBlock({ item, nested, streaming, threadId }: { item: Extract<RunViewItem, { kind: 'reasoning' }>; nested?: boolean; streaming?: boolean; threadId?: string }) {
  const label = nested ? '分析思路' : `${pathLabel(item.path)} · 分析思路`
  return <details className="reasoning" style={{ marginLeft: nested ? 0 : 44, borderLeft: '2px solid var(--action-border)', background: 'var(--action-light)', color: 'var(--text-secondary)', fontSize: 12 }}>
    <summary className="reasoning-summary">
      <span className={`reasoning-dot${streaming ? ' streaming' : ''}`} aria-hidden="true" />
      <span className="reasoning-label" style={{ color: 'var(--action)' }}>{label}</span>
      {streaming && <span className="reasoning-preview" aria-hidden="true">{item.text}</span>}
      <svg className="reasoning-caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--text-muted)', flexShrink: 0 }}><polyline points="18 15 12 9 6 15"/></svg>
    </summary>
    <div className="reasoning-body">
      <MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} />
    </div>
  </details>
}

const ItemView = memo(function ItemView({ item, index, nested = false, streaming = false, threadId }: { item: RunViewItem; index: number; nested?: boolean; streaming?: boolean; threadId?: string }) {
  if (item.kind === 'tool') return <ToolView key={`tool-${item.id}-${index}`} item={item} nested={nested} />
  if (item.kind === 'notice') return <div key={`notice-${index}`} style={{ marginLeft: nested ? 0 : 44, padding: '8px 12px', borderRadius: 6, background: item.tone === 'error' ? 'var(--danger-bg)' : item.tone === 'warning' ? 'var(--warn-bg)' : 'var(--action-light)', color: item.tone === 'error' ? 'var(--danger)' : item.tone === 'warning' ? 'var(--warn)' : 'var(--action)', fontSize: 12 }}>{item.message}</div>
  if (item.kind === 'reasoning') return <ReasoningBlock key={`reasoning-${index}`} item={item} nested={nested} streaming={streaming} threadId={threadId} />
  if (nested) return <div key={`answer-${index}`} style={{ padding: '10px 12px', border: '1px solid var(--border-light)', borderRadius: 7, background: 'var(--surface)', overflowWrap: 'anywhere', lineHeight: 1.7, fontSize: 13 }}><MarkdownAnswer text={item.text} threadId={threadId} streaming={streaming} /></div>
  return <div key={`answer-${index}`} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand)', display: 'grid', placeItems: 'center', flexShrink: 0 }}><Logo height={18} color="#fff" /></div>
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

  const questions = actions.filter(isQuestion).length
  return <div style={{ marginLeft: 44, padding: 16, border: '1px solid #FDE68A', borderLeft: '4px solid var(--status-warn)', borderRadius: '0 8px 8px 8px', background: 'var(--warn-bg)' }}>
    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--warn)', marginBottom: 6 }}>{batchTitle(actions.length, questions)}</div>
    <div style={{ fontSize: 12, color: 'var(--warn)', marginBottom: 12 }}>请逐项处理，所有内容将一次性提交。</div>
    {actions.map(action => {
      const draft = drafts[action.index] ?? { type: null, message: '', args: jsonArgs(action.args) }
      const asking = isQuestion(action)
      // `data-interrupt` 与工具卡片的 `data-tool` 同一个用途：走查要钉到这张卡片上，
      // 而问题原文同时还出现在教师自己的提问气泡、清单条目和思考过程里
      return <fieldset key={action.index} data-interrupt={action.tool_name} style={{ border: '1px solid #FDE68A', borderRadius: 7, margin: '0 0 10px', padding: 12 }}>
        <legend style={{ padding: '0 6px', color: 'var(--warn)', fontSize: 12, fontWeight: 600 }}>#{action.index + 1} {asking ? '智能体的提问' : action.tool_name}</legend>
        {asking
          // 提问显示问题原文，不显示参数 JSON —— 教师要读的是那句话，不是一个调用
          ? <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', padding: '2px 0 10px', color: 'var(--warn)', fontSize: 13, lineHeight: 1.7 }}>{questionText(action)}</div>
          : <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: 'rgba(146,64,14,0.06)', padding: 9, borderRadius: 5, color: 'var(--warn)', fontSize: 11 }}>{jsonArgs(action.args)}</pre>}
        {/* 只有一种决策时按钮已经替教师选好了，再摆一排单选按钮纯属多一步 */}
        {action.allowed_decisions.length > 1 && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {DECISION_TYPES.filter(type => action.allowed_decisions.includes(type)).map(type => <button key={type} type="button" onClick={() => patchDraft(action.index, { type })} style={{ padding: '6px 11px', border: draft.type === type ? '1px solid var(--action)' : '1px solid #FDE68A', borderRadius: 5, background: draft.type === type ? 'var(--action)' : '#fff', color: draft.type === type ? '#fff' : 'var(--warn)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>{DECISION_LABEL[type]}</button>)}
        </div>}
        {(draft.type === 'reject' || draft.type === 'respond') && <textarea value={draft.message} onChange={event => patchDraft(action.index, { message: event.target.value })} aria-label={asking ? `回答第 ${action.index + 1} 个问题` : undefined} placeholder={asking ? '必填：把你的口径告诉它，它会带着这句话接着跑' : '必填：说明理由或告诉智能体如何调整'} style={{ width: '100%', minHeight: 64, boxSizing: 'border-box', marginTop: 9, padding: 8, border: '1px solid #FDE68A', borderRadius: 5, font: 'inherit', fontSize: 12 }} />}
        {draft.type === 'edit' && <textarea value={draft.args} onChange={event => patchDraft(action.index, { args: event.target.value })} aria-label={`修改${action.tool_name}参数`} style={{ width: '100%', minHeight: 90, boxSizing: 'border-box', marginTop: 9, padding: 8, border: '1px solid #FDE68A', borderRadius: 5, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }} />}
      </fieldset>
    })}
    {formError && <div role="alert" style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 8 }}>{formError}</div>}
    <button type="button" disabled={submitting} onClick={() => void submit()} style={{ padding: '8px 18px', border: 'none', borderRadius: 6, background: 'var(--action)', color: '#fff', cursor: submitting ? 'default' : 'pointer', fontWeight: 600, fontFamily: 'inherit' }}>{submitting ? '正在提交…' : questions === actions.length ? '提交回答' : '提交全部决策'}</button>
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
