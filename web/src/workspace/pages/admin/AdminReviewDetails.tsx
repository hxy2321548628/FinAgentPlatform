import { listReviewSkillFiles, readReviewSkillFile } from '../../../api/reviews'
import type { AdminMcpServer, ReviewItem } from '../../../api/types'
import { McpCapabilityDrawer, SkillVersionDrawer } from '../../components/CapabilityDetails'
import { AdminDetailDialog } from './AdminUi'

// oxlint-disable-next-line react/only-export-components -- 审核状态文案需与列表和详情共用。
export function reviewStatusLabel(item: ReviewItem): string {
  if (item.status === 'pending') return '待审核'
  if (item.status === 'rejected') return '已拒绝'
  return item.catalog_enabled ? '已上架' : '已下架'
}

// oxlint-disable-next-line react/only-export-components -- 状态色与同一份状态文案必须保持一致。
export function reviewStatusClass(item: ReviewItem): string {
  if (item.status === 'pending') return 'pending'
  if (item.status === 'rejected') return 'rejected'
  return item.catalog_enabled ? 'approved' : 'disabled'
}

export function AgentReviewDetailDialog({ item, onClose }: { item: ReviewItem | null; onClose: () => void }) {
  if (!item) return null
  const scenario = (item.subagent_refs?.length ?? 0) > 0
  return (
    <AdminDetailDialog
      open
      title={item.agent_name ?? `未命名${scenario ? '场景' : '智能体'}`}
      eyebrow={`${scenario ? 'SCENARIO' : 'AGENT'} · V${item.version}`}
      description={item.description || '未填写说明'}
      onClose={onClose}
    >
      <ReviewMeta item={item} kind={scenario ? '场景' : '智能体'} />
      {item.catalog_disabled_reason && <div className="admin-inline-notice danger">下架原因：{item.catalog_disabled_reason}</div>}
      <DetailSection title="系统提示词">
        <pre className="admin-detail-code">{item.system_prompt || '未填写系统提示词'}</pre>
      </DetailSection>
      <ReferenceSection title="Skills" items={(item.skill_refs ?? []).map(one => `${one.name} · v${one.version}`)} />
      <ReferenceSection title="MCP" items={(item.mcp_refs ?? []).map(one => one.name)} />
      <ReferenceSection title="子智能体" items={(item.subagent_refs ?? []).map(one => `${one.name} · v${one.version}`)} />
    </AdminDetailDialog>
  )
}

export function SkillReviewDetailDialog({ item, onClose }: { item: ReviewItem | null; onClose: () => void }) {
  if (!item) return null
  return (
    <SkillVersionDrawer
      title={item.skill_name ?? '未命名 Skill'}
      subtitle={`${item.owner_name} · ${item.subject || '未分类'} · v${item.version}`}
      description={item.description || '未填写说明'}
      fileCount={item.file_count ?? 0}
      totalBytes={item.total_bytes ?? 0}
      cacheKey={['review-skill-detail', item.id]}
      loadFiles={() => listReviewSkillFiles(item.id)}
      loadFile={path => readReviewSkillFile(item.id, path)}
      context={(
        <>
          <ReviewMeta item={item} kind="Skill" />
          {item.catalog_disabled_reason && <div className="admin-inline-notice danger">下架原因：{item.catalog_disabled_reason}</div>}
        </>
      )}
      onClose={onClose}
    />
  )
}

export function McpDetailDialog({ item, onClose }: { item: AdminMcpServer | null; onClose: () => void }) {
  if (!item) return null
  return (
    <McpCapabilityDrawer
      item={item}
      context={(
        <>
          <div className="admin-detail-grid">
            <DetailField label="申请人" value={item.submitter_name || '—'} />
            <DetailField label="目录状态" value={mcpStatusLabel(item)} />
            <DetailField label="连续失败" value={`${item.failure_count} 次`} />
            <DetailField label="申请时间" value={new Date(item.created_at).toLocaleString('zh-CN')} />
          </div>
          {item.disabled_reason && <div className="admin-inline-notice danger">状态说明：{item.disabled_reason}</div>}
        </>
      )}
      onClose={onClose}
    />
  )
}

function ReviewMeta({ item, kind }: { item: ReviewItem; kind: string }) {
  return (
    <div className="admin-detail-grid">
      <DetailField label="内容类型" value={kind} />
      <DetailField label="提交方" value={item.owner_name} />
      <DetailField label="所属学科" value={item.subject || '未分类'} />
      <DetailField label="目录状态" value={reviewStatusLabel(item)} />
    </div>
  )
}

function DetailField({ label, value }: { label: string; value: string }) {
  return <div className="admin-detail-field"><span>{label}</span><strong>{value}</strong></div>
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="admin-detail-section"><h3 className="admin-detail-section-title">{title}</h3>{children}</section>
}

function ReferenceSection({ title, items }: { title: string; items: string[] }) {
  return (
    <DetailSection title={`${title}（${items.length}）`}>
      {items.length === 0 ? <div className="admin-reference-empty">未选择</div> : <div className="admin-reference-list">{items.map(item => <span key={item} className="admin-reference-chip">{item}</span>)}</div>}
    </DetailSection>
  )
}

function mcpStatusLabel(item: AdminMcpServer): string {
  if (item.status === 'pending') return '待审核'
  if (item.status === 'rejected') return '已拒绝'
  if (item.status === 'enabled') return '已上架'
  return item.disabled_reason?.includes('连续失败') ? '已自动下架' : '已下架'
}
