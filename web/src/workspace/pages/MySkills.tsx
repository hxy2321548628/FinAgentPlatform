import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { groupKeys, listMyGroups } from '../../api/groups'
import { errorMessage } from '../../api/request'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'
import {
  createSkill,
  deleteSkill,
  listMine,
  releaseVersion,
  setSharing,
  skillKeys,
  submitForReview,
  updateSkill,
  writeDraft,
} from '../../api/skills'
import type { MySkill, ReviewStatus, SkillVersion } from '../../api/types'

const SUBJECTS = ['公司金融', '量化投资', '资产管理', '风险管理', '学术科研', '会计审计', '其他']
const TABS = ['draft', 'reviewing', 'published'] as const
type SkillTab = (typeof TABS)[number]

const TAB_LABEL: Record<SkillTab, string> = {
  draft: '草稿',
  reviewing: '待审核',
  published: '已发布',
}

interface SkillState {
  tab: SkillTab
  draft: SkillVersion | null
  released: SkillVersion | null
  reviewStatus: ReviewStatus | null
  rejectedReason: string | null
}

function skillState(skill: MySkill): SkillState {
  const draft = skill.versions.find(one => one.status === 'draft') ?? null
  const released = [...skill.versions].reverse().find(one => one.status === 'released') ?? null
  const reviewStatus = released?.review_status ?? null
  return {
    tab: reviewStatus === 'pending' || reviewStatus === 'rejected' ? 'reviewing' : released ? 'published' : 'draft',
    draft,
    released,
    reviewStatus,
    rejectedReason: reviewStatus === 'rejected' ? (released?.review_reason ?? null) : null,
  }
}

function validationReasons(error: unknown): string[] {
  return error instanceof Error ? error.message.split('；').filter(Boolean) : ['上传失败，请稍后重试']
}

export function MySkills() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<SkillTab>('published')
  const [editingId, setEditingId] = useState<string | null | undefined>(undefined)
  const [sharingId, setSharingId] = useState<string | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)

  const mine = useQuery({ queryKey: skillKeys.mine(), queryFn: listMine })
  const skills = (mine.data ?? []).filter(one => !one.is_deleted)
  const refresh = () => queryClient.invalidateQueries({ queryKey: skillKeys.all })
  const release = useMutation({ mutationFn: releaseVersion, onSuccess: refresh })
  const remove = useMutation({ mutationFn: deleteSkill, onSuccess: refresh })

  const shown = skills.filter(one => skillState(one).tab === tab)
  const editingSkill = editingId ? skills.find(one => one.id === editingId) ?? null : null
  const sharingSkill = skills.find(one => one.id === sharingId) ?? null
  const reviewingSkill = skills.find(one => one.id === reviewingId) ?? null

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 28 }}>
        <div>
          <div style={eyebrowStyle}>// MY SKILLS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的 Skills</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>上传后先形成草稿；发布版本后可组内共享，提审通过后进入平台目录</p>
        </div>
        <button type="button" onClick={() => setEditingId(null)} style={primaryButton}>+ 创建 Skill</button>
      </div>

      {mine.isPending && <div style={{ color: 'var(--text-muted)' }}>正在加载…</div>}
      {mine.isError && <div role="alert" style={errorStyle}>{errorMessage(mine.error)}</div>}

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(one => (
          <button type="button" key={one} onClick={() => setTab(one)} style={{ ...tabStyle, borderBottomColor: tab === one ? 'var(--action)' : 'transparent', color: tab === one ? 'var(--action)' : 'var(--text-muted)' }}>
            {TAB_LABEL[one]}
            <span style={countStyle}>{skills.filter(skill => skillState(skill).tab === one).length}</span>
          </button>
        ))}
      </div>

      {(release.isError || remove.isError) && <div role="alert" style={{ ...errorStyle, marginBottom: 16 }}>{errorMessage(release.error ?? remove.error)}</div>}

      {!mine.isPending && shown.length === 0 ? (
        <div style={emptyStyle}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 10 }}>该状态下还没有 Skill</div>
          <button type="button" onClick={() => setEditingId(null)} style={primaryButton}>+ 创建 Skill</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {shown.map(skill => {
            const state = skillState(skill)
            const description = state.draft?.description ?? state.released?.description ?? ''
            return (
              <div key={skill.id} data-testid="my-skill-row" style={rowStyle}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{skill.name}</span>
                    {skill.in_catalog && <span style={badgeStyle}>平台目录</span>}
                    {skill.visibility === 'group' && skill.group_ids.length > 0 && <span style={badgeStyle}>组内共享 · {skill.group_ids.length} 个组</span>}
                    {!skill.in_catalog && skill.visibility === 'private' && <span style={badgeStyle}>私有</span>}
                    {state.reviewStatus === 'pending' && <span style={warningBadgeStyle}>待审核</span>}
                    {state.reviewStatus === 'rejected' && <span style={rejectedBadgeStyle}>已拒绝</span>}
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{skill.call_count} 次调用</span>
                  </div>
                  {state.rejectedReason && <div role="alert" style={reasonStyle}><strong>审核未通过：</strong>{state.rejectedReason}</div>}
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 5 }}>{description}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {skill.subject || '未分类'}
                    {state.released ? ` · 已发布 v${state.released.version}` : ' · 还没发布过版本'}
                    {state.draft ? ` · 草稿 v${state.draft.version} 未发布` : ''}
                    {(state.draft ?? state.released) && ` · ${(state.draft ?? state.released)?.file_count} 个文件 · ${formatBytes((state.draft ?? state.released)?.total_bytes ?? 0)}`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button type="button" onClick={() => setEditingId(skill.id)} style={ghostButton}>上传新草稿</button>
                  {state.draft && <button type="button" onClick={() => release.mutate(skill.id)} disabled={release.isPending} style={outlineButton}>发布 v{state.draft.version}</button>}
                  {state.released && <button type="button" onClick={() => setSharingId(skill.id)} style={outlineButton}>共享设置</button>}
                  {state.released && state.reviewStatus !== 'pending' && <button type="button" onClick={() => setReviewingId(skill.id)} style={outlineButton}>{state.reviewStatus === 'rejected' ? '改后重新提审' : '提交审核'}</button>}
                  <button type="button" onClick={() => remove.mutate(skill.id)} style={{ ...ghostButton, color: '#DC2626', borderColor: '#FECACA' }}>删除</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {editingId !== undefined && <UploadDialog skill={editingSkill} onClose={() => setEditingId(undefined)} onDone={() => { setEditingId(undefined); setTab('draft'); void refresh() }} />}
      {sharingSkill && <SharingDialog skill={sharingSkill} onClose={() => setSharingId(null)} onDone={() => { setSharingId(null); void refresh() }} />}
      {reviewingSkill && <ReviewDialog skill={reviewingSkill} onClose={() => setReviewingId(null)} onDone={() => { setReviewingId(null); setTab('reviewing'); void refresh() }} />}
    </div>
  )
}

function UploadDialog({ skill, onClose, onDone }: { skill: MySkill | null; onClose: () => void; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [subject, setSubject] = useState(skill?.subject || SUBJECTS[0])
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('请选择 Skill 文件')
      if (!skill) return createSkill(file, subject)
      if (subject !== skill.subject) await updateSkill(skill.id, subject)
      return writeDraft(skill.id, file)
    },
    onSuccess: onDone,
  })

  return (
    <Dialog title={skill ? `上传「${skill.name}」的新草稿` : '上传 Skill'} onClose={onClose} width={500}>
      <p style={hintStyle}>支持整个 Skill 目录的 ZIP，或单个包含 frontmatter 的 Markdown 文件。名称与描述由服务端从 SKILL.md 读取。</p>
      <label style={labelStyle}>学科</label>
      <select value={subject} onChange={event => setSubject(event.target.value)} style={{ ...inputStyle, marginBottom: 14 }}>
        {SUBJECTS.map(one => <option key={one} value={one}>{one}</option>)}
      </select>
      <input
        ref={fileRef}
        aria-label="Skill 文件"
        type="file"
        accept=".zip,application/zip,.md,text/markdown,text/plain"
        style={{ display: 'none' }}
        onChange={event => setFile(event.target.files?.[0] ?? null)}
      />
      <button type="button" onClick={() => fileRef.current?.click()} style={fileButtonStyle}>
        <span style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{file?.name ?? '选择 ZIP 或 Markdown 文件'}</span>
        <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)' }}>解压后不超过 5 MB；允许 Markdown、文本、HTML、Python 与结构化数据附件</span>
      </button>
      <div style={noticeStyle}>平台会校验路径穿越、符号链接、总大小、文件数量、压缩比、扩展名、单文件大小，以及 Skill 名称与目录名。</div>
      {upload.isError && <ul role="alert" style={{ ...errorStyle, margin: '0 0 14px', paddingLeft: 30 }}>{validationReasons(upload.error).map(reason => <li key={reason}>{reason}</li>)}</ul>}
      <DialogActions onClose={onClose} onSubmit={() => upload.mutate()} pending={upload.isPending} disabled={!file} label={skill ? '更新文件' : '上传并创建'} />
    </Dialog>
  )
}

function SharingDialog({ skill, onClose, onDone }: { skill: MySkill; onClose: () => void; onDone: () => void }) {
  const groups = useQuery({ queryKey: groupKeys.mine(), queryFn: listMyGroups })
  const [shared, setShared] = useState(skill.visibility === 'group')
  const [selected, setSelected] = useState(skill.group_ids)
  const save = useMutation({ mutationFn: () => setSharing(skill.id, shared ? 'group' : 'private', shared ? selected : []), onSuccess: onDone })
  return (
    <Dialog title={`共享「${skill.name}」`} onClose={onClose}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 14 }}><input type="checkbox" checked={shared} onChange={event => setShared(event.target.checked)} />共享给我的课题组</label>
      {groups.isPending && <div style={hintStyle}>正在加载课题组…</div>}
      {groups.isError && <div role="alert" style={errorStyle}>{errorMessage(groups.error)}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        {(groups.data ?? []).map(group => <label key={group.id} style={{ display: 'flex', gap: 8, fontSize: 13, opacity: shared ? 1 : 0.5 }}><input type="checkbox" disabled={!shared} checked={selected.includes(group.id)} onChange={event => setSelected(current => event.target.checked ? [...current, group.id] : current.filter(one => one !== group.id))} />{group.name}</label>)}
      </div>
      {save.isError && <div role="alert" style={errorStyle}>{errorMessage(save.error)}</div>}
      <DialogActions onClose={onClose} onSubmit={() => save.mutate()} pending={save.isPending} disabled={shared && selected.length === 0} label="保存共享设置" />
    </Dialog>
  )
}

function ReviewDialog({ skill, onClose, onDone }: { skill: MySkill; onClose: () => void; onDone: () => void }) {
  const [confirmed, setConfirmed] = useState(false)
  const state = skillState(skill)
  const submit = useMutation({ mutationFn: () => submitForReview(skill.id, confirmed), onSuccess: onDone })
  return (
    <Dialog title={`提交「${skill.name}」审核`} onClose={onClose}>
      <p style={hintStyle}>提交当前已发布的 <strong>v{state.released?.version}</strong>。通过后这一版进入平台目录；以后发布新版本需重新提审。</p>
      <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} style={{ marginTop: 3 }} />我确认该 Skill 的内容合规，并对它产生的分析结果负责。</label>
      {submit.isError && <div role="alert" style={errorStyle}>{errorMessage(submit.error)}</div>}
      <DialogActions onClose={onClose} onSubmit={() => submit.mutate()} pending={submit.isPending} disabled={!confirmed} label="提交审核" />
    </Dialog>
  )
}

function Dialog({ title, onClose, width = 460, children }: { title: string; onClose: () => void; width?: number; children: React.ReactNode }) {
  return (
    <DialogPrimitive.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay dialog-overlay-strong" onClick={onClose} />
        <DialogPrimitive.Content className="dialog-content" aria-describedby={undefined} style={{ width: Math.min(width, 640) }}>
          <DialogPrimitive.Title className="dialog-title" style={{ paddingBottom: 14, borderBottom: '1px solid var(--border)', marginBottom: 0 }}>{title}</DialogPrimitive.Title>
          <div style={{ paddingTop: 18 }}>{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function DialogActions({ onClose, onSubmit, pending, disabled = false, label }: { onClose: () => void; onSubmit: () => void; pending: boolean; disabled?: boolean; label: string }) {
  return <div className="dialog-actions"><Button variant="secondary" size="md" onClick={onClose}>取消</Button><Button variant="primary" size="md" onClick={onSubmit} disabled={pending || disabled}>{pending ? '正在提交…' : label}</Button></div>
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

const eyebrowStyle: React.CSSProperties = { fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }
const primaryButton: React.CSSProperties = { padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }
const ghostButton: React.CSSProperties = { padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }
const outlineButton: React.CSSProperties = { ...ghostButton, color: 'var(--action)', borderColor: 'var(--action-border)' }
const tabStyle: React.CSSProperties = { padding: '10px 20px', fontSize: 13, fontWeight: 500, background: 'none', border: 'none', borderBottom: '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit' }
const countStyle: React.CSSProperties = { marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }
const emptyStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' }
const rowStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }
const badgeStyle: React.CSSProperties = { padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' }
const warningBadgeStyle: React.CSSProperties = { ...badgeStyle, background: '#FFFBEB', color: '#92400E', borderColor: '#FDE68A' }
const rejectedBadgeStyle: React.CSSProperties = { ...badgeStyle, background: '#FEF2F2', color: '#DC2626', borderColor: '#FECACA' }
const reasonStyle: React.CSSProperties = { fontSize: 12, color: '#DC2626', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 6, padding: '7px 12px', margin: '4px 0' }
const errorStyle: React.CSSProperties = { color: '#DC2626', fontSize: 13 }
const hintStyle: React.CSSProperties = { fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 14 }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }
const fileButtonStyle: React.CSSProperties = { width: '100%', padding: '24px 18px', marginBottom: 14, border: '1px dashed var(--action-border)', borderRadius: 9, background: 'var(--action-light)', color: 'var(--action)', cursor: 'pointer', fontFamily: 'inherit' }
const noticeStyle: React.CSSProperties = { padding: '10px 12px', marginBottom: 16, borderRadius: 7, background: 'var(--bg)', color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.65 }
