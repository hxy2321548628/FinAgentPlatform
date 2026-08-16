import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  agentKeys,
  deleteAgent,
  listMine,
  releaseVersion,
  setSharing,
  submitForReview,
} from '../../api/agents'
import { groupKeys, listMyGroups } from '../../api/groups'
import { isScenario } from '../agent'
import { errorMessage } from '../../api/request'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'
import type { MyAgent } from '../../api/types'
import { AGENT_TABS, AGENT_TAB_EMPTY, AGENT_TAB_LABEL, agentState, visibilityBadges, type AgentTab } from '../agent'

/**
 * 「我的智能体」：三个页签、拒绝理由、发布、共享、提审。
 *
 * **软删掉的不在这里显示。** 行还留在库里（run 快照指着它），但作者已经删过一次，
 * 再列出来只会让「我删掉的东西怎么还在」变成一通电话。
 */
export function MyAgents() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<AgentTab>('published')
  const [sharingId, setSharingId] = useState<string | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)

  const mine = useQuery({ queryKey: agentKeys.mine(), queryFn: listMine })
  // **这一页只管智能体，挂了子智能体的归「我的场景」** —— 同一批数据两个入口
  // 各看一半，判据是 P6-decision G2 那条客观事实
  const agents = (mine.data ?? []).filter(one => {
    if (one.is_deleted) return false
    const latest = one.versions.at(-1)
    return latest === undefined || !isScenario(latest)
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: agentKeys.all })

  const release = useMutation({ mutationFn: releaseVersion, onSuccess: refresh })
  const remove = useMutation({ mutationFn: deleteAgent, onSuccess: refresh })

  const counted = (which: AgentTab) => agents.filter(one => agentState(one).tab === which).length
  const shown = agents.filter(one => agentState(one).tab === tab)
  const sharingAgent = agents.find(one => one.id === sharingId) ?? null
  const reviewingAgent = agents.find(one => one.id === reviewingId) ?? null

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div className="page-eyebrow">// MY AGENTS</div>
          <h1 className="page-title">我的智能体</h1>
          <p className="page-desc">发布一版之后组内才看得见；进广场要审核通过</p>
        </div>
        <button onClick={() => navigate('/workspace/my-agents/create')} style={primaryButton}>+ 创建智能体</button>
      </div>

      {mine.isPending && <div style={{ color: 'var(--text-muted)' }}>正在加载…</div>}
      {mine.isError && <div role="alert" style={{ color: '#DC2626' }}>{errorMessage(mine.error)}</div>}

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {AGENT_TABS.map(one => (
          <button key={one} onClick={() => setTab(one)} style={{
            padding: '10px 20px', fontSize: 13, fontWeight: 500, background: 'none', border: 'none',
            borderBottom: tab === one ? '2px solid var(--action)' : '2px solid transparent', marginBottom: -1,
            cursor: 'pointer', fontFamily: 'inherit', color: tab === one ? 'var(--action)' : 'var(--text-muted)',
          }}>
            {AGENT_TAB_LABEL[one]}
            <span style={{ marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }}>{counted(one)}</span>
          </button>
        ))}
      </div>

      {(release.isError || remove.isError) && (
        <div role="alert" style={{ marginBottom: 16, color: '#DC2626', fontSize: 13 }}>{errorMessage(release.error ?? remove.error)}</div>
      )}

      {!mine.isPending && shown.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>{AGENT_TAB_EMPTY[tab]}</div>
          <button onClick={() => navigate('/workspace/my-agents/create')} style={{ ...primaryButton, marginTop: 8 }}>+ 创建智能体</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {shown.map(agent => {
            const state = agentState(agent)
            return (
              <div key={agent.id} data-testid="my-agent-row" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</span>
                    {visibilityBadges(agent).map(badge => (
                      <span key={badge} style={{ padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: 'var(--action-light)', color: 'var(--action)', border: '1px solid var(--action-border)' }}>{badge}</span>
                    ))}
                    {state.reviewStatus === 'pending' && <span style={badgeStyle('#FFFBEB', 'var(--status-warn)', '#FDE68A')}>待审核</span>}
                    {state.reviewStatus === 'rejected' && <span style={badgeStyle('#FEF2F2', '#DC2626', '#FECACA')}>已拒绝</span>}
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.call_count} 次调用</span>
                  </div>
                  {state.rejectedReason && (
                    <div role="alert" style={{ fontSize: 12, color: '#DC2626', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 6, padding: '7px 12px', margin: '4px 0' }}>
                      <span style={{ fontWeight: 600 }}>审核未通过：</span>{state.rejectedReason}
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {agent.subject || '未分类'}
                    {state.released ? ` · 已发布 v${state.released.version}` : ' · 还没发布过版本'}
                    {state.draft ? ` · 草稿 v${state.draft.version} 未发布` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button onClick={() => navigate(`/workspace/my-agents/${agent.id}/edit`)} style={ghostButton}>编辑</button>
                  {state.draft && <button onClick={() => release.mutate(agent.id)} disabled={release.isPending} style={outlineButton}>发布 v{state.draft.version}</button>}
                  {state.released && <button onClick={() => setSharingId(agent.id)} style={outlineButton}>共享设置</button>}
                  {state.released && state.reviewStatus !== 'pending' && (
                    <button onClick={() => setReviewingId(agent.id)} style={outlineButton}>
                      {state.reviewStatus === 'rejected' ? '改后重新提审' : '提交审核'}
                    </button>
                  )}
                  <button onClick={() => remove.mutate(agent.id)} style={{ ...ghostButton, color: '#DC2626', borderColor: '#FECACA' }}>删除</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {sharingAgent && <SharingDialog agent={sharingAgent} onClose={() => setSharingId(null)} onDone={() => { setSharingId(null); void refresh() }} />}
      {reviewingAgent && <ReviewDialog agent={reviewingAgent} onClose={() => setReviewingId(null)} onDone={() => { setReviewingId(null); setTab('reviewing'); void refresh() }} />}
    </div>
  )
}

/**
 * 共享设置：可见性那一档 + 共享给哪些组。
 *
 * **只列出自己在里面的组** —— 后端也校验，填别人的组一律 422。前端这一层的职责
 * 是让那种请求根本发不出去。
 */
function SharingDialog({ agent, onClose, onDone }: { agent: MyAgent; onClose: () => void; onDone: () => void }) {
  const groups = useQuery({ queryKey: groupKeys.mine(), queryFn: listMyGroups })
  const [selected, setSelected] = useState<string[]>(agent.group_ids)
  const [shared, setShared] = useState(agent.visibility === 'group')
  const save = useMutation({
    mutationFn: () => setSharing(agent.id, shared ? 'group' : 'private', shared ? selected : []),
    onSuccess: onDone,
  })

  return (
    <Dialog title={`共享「${agent.name}」`} onClose={onClose}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 14 }}>
        <input type="checkbox" checked={shared} onChange={event => setShared(event.target.checked)} />
        共享给我的课题组
      </label>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        取消勾选即改回私有，组员下一次刷新就看不到它了；他们会话里存着的引用会在下次提问时报错，而不是悄悄换成默认提示词。
      </p>
      {groups.isPending && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>正在加载课题组…</div>}
      {groups.isError && <div role="alert" style={{ color: '#DC2626', fontSize: 13 }}>{errorMessage(groups.error)}</div>}
      {(groups.data ?? []).length === 0 && !groups.isPending && (
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>你还不属于任何课题组，先加入一个才能共享。</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        {(groups.data ?? []).map(group => (
          <label key={group.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, opacity: shared ? 1 : 0.5 }}>
            <input
              type="checkbox"
              disabled={!shared}
              checked={selected.includes(group.id)}
              onChange={event => setSelected(current => event.target.checked ? [...current, group.id] : current.filter(one => one !== group.id))}
            />
            {group.name}
          </label>
        ))}
      </div>
      {save.isError && <div role="alert" style={{ color: '#DC2626', fontSize: 13, marginBottom: 10 }}>{errorMessage(save.error)}</div>}
      <DialogActions onClose={onClose} onSubmit={() => save.mutate()} pending={save.isPending} label="保存共享设置" />
    </Dialog>
  )
}

/** 提审：**责任确认没勾就发不出去**，后端也拦一道。 */
function ReviewDialog({ agent, onClose, onDone }: { agent: MyAgent; onClose: () => void; onDone: () => void }) {
  const [confirmed, setConfirmed] = useState(false)
  const state = agentState(agent)
  const submit = useMutation({ mutationFn: () => submitForReview(agent.id, confirmed), onSuccess: onDone })

  return (
    <Dialog title={`提交「${agent.name}」审核`} onClose={onClose}>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 14 }}>
        提交的是当前已发布的 <strong>v{state.released?.version}</strong>。审核通过之后这一版出现在广场上；
        之后每改一版都要重新提审 —— 没审过的新版本不会自动上广场。
      </p>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        被拒不影响组内使用：审核管的是别人能不能看见，不是你能不能用。
      </p>
      <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
        <input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} style={{ marginTop: 3 }} />
        我确认这段提示词的内容合规，并对它产生的分析结果负责。
      </label>
      {submit.isError && <div role="alert" style={{ color: '#DC2626', fontSize: 13, marginBottom: 10 }}>{errorMessage(submit.error)}</div>}
      <DialogActions onClose={onClose} onSubmit={() => submit.mutate()} pending={submit.isPending} disabled={!confirmed} label="提交审核" />
    </Dialog>
  )
}

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <DialogPrimitive.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay dialog-overlay-strong" onClick={onClose} />
        <DialogPrimitive.Content className="dialog-content" aria-describedby={undefined} style={{ width: 460 }}>
          <DialogPrimitive.Title className="dialog-title" style={{ paddingBottom: 14, borderBottom: '1px solid var(--border)', marginBottom: 0 }}>{title}</DialogPrimitive.Title>
          <div style={{ paddingTop: 18 }}>{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function DialogActions({ onClose, onSubmit, pending, disabled = false, label }: { onClose: () => void; onSubmit: () => void; pending: boolean; disabled?: boolean; label: string }) {
  return (
    <div className="dialog-actions">
      <Button variant="secondary" size="md" onClick={onClose}>取消</Button>
      <Button variant="primary" size="md" onClick={onSubmit} disabled={pending || disabled}>{pending ? '正在提交…' : label}</Button>
    </div>
  )
}

function badgeStyle(background: string, color: string, border: string): React.CSSProperties {
  return { padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background, color, border: `1px solid ${border}` }
}

const primaryButton: React.CSSProperties = {
  padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7,
  fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
}

const ghostButton: React.CSSProperties = {
  padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)',
  border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
}

const outlineButton: React.CSSProperties = {
  padding: '6px 14px', background: 'transparent', color: 'var(--action)',
  border: '1px solid var(--action-border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
}
