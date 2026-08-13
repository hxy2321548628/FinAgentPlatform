import { useState } from 'react'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import {
  approveButtonStyle,
  cellStyle,
  emptyStyle,
  monoCellStyle,
  nameCellStyle,
  pageStyle,
  rejectButtonStyle,
  secondaryButtonStyle,
  tableStyle,
  tagStyle,
  thStyle,
} from './AdminStyles'

type CapabilityKind = 'skill' | 'mcp'

interface CapabilityRecord {
  id: string
  name: string
  owner: string
  category: string
  summary: string
  specification?: string
  submittedAt?: string
  publishedAt?: string
  calls?: number
}

const PENDING: Record<CapabilityKind, CapabilityRecord[]> = {
  skill: [
    { id: 'skill-p1', name: '回归结果稳健性检查', owner: '赵老师', category: '科研分析', summary: '按预设清单检查回归模型的稳健性与诊断结果。', submittedAt: '2026-08-10 09:40' },
    { id: 'skill-p2', name: '行业数据字段标准化', owner: '张老师', category: '数据处理', summary: '统一不同来源的行业、公司与指标字段命名。', submittedAt: '2026-08-11 15:18' },
  ],
  mcp: [
    { id: 'mcp-p1', name: '校内数据库查询', owner: '实验中心', category: '业务系统', summary: '为获批场景提供校内研究数据库的只读查询能力。', specification: 'Tools 3 · Resources 2 · Prompts 0', submittedAt: '2026-08-11 10:25' },
  ],
}

const PUBLISHED: Record<CapabilityKind, CapabilityRecord[]> = {
  skill: [
    { id: 'skill-s1', name: '数据清洗', owner: '平台能力目录', category: '数据处理', summary: '识别缺失值、异常值与重复记录，并生成清洗记录。', publishedAt: '2026-07-01', calls: 186 },
    { id: 'skill-s2', name: '财务指标计算', owner: '金融学院', category: '金融分析', summary: '计算偿债、盈利、运营与成长能力指标。', publishedAt: '2026-07-15', calls: 128 },
  ],
  mcp: [
    { id: 'mcp-s1', name: '财报检索服务', owner: '金融学院', category: '金融数据', summary: '检索上市公司定期报告并返回文档与元数据。', specification: 'Tools 2 · Resources 1 · Prompts 1', publishedAt: '2026-07-08', calls: 95 },
    { id: 'mcp-s2', name: '论文检索服务', owner: '图书馆', category: '学术资源', summary: '按主题、作者与年份检索学术论文元数据。', specification: 'Tools 2 · Resources 2 · Prompts 0', publishedAt: '2026-07-18', calls: 73 },
  ],
}

const CONFIG = {
  skill: { eyebrow: '// SKILL MANAGEMENT', title: 'Skill 管理', pendingTitle: '待审核 Skills', publishedTitle: '已上架 Skills', specLabel: undefined },
  mcp: { eyebrow: '// MCP MANAGEMENT', title: 'MCP 管理', pendingTitle: '待审核 MCP Servers', publishedTitle: '已放行 MCP Servers', specLabel: '协议能力' },
} as const

export function AdminSkills() {
  return <AdminCapabilityManagement kind="skill" />
}

export function AdminMcp() {
  return <AdminCapabilityManagement kind="mcp" />
}

function AdminCapabilityManagement({ kind }: { kind: CapabilityKind }) {
  const config = CONFIG[kind]
  const [pending, setPending] = useState(PENDING[kind])
  const [published, setPublished] = useState(PUBLISHED[kind])

  const approve = (record: CapabilityRecord) => {
    setPending(current => current.filter(item => item.id !== record.id))
    setPublished(current => [{ ...record, publishedAt: '刚刚', calls: 0 }, ...current])
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow={config.eyebrow} title={config.title} pendingCount={pending.length} />

      <CapabilityTable
        title={config.pendingTitle}
        records={pending}
        specLabel={config.specLabel}
        action={record => (
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={() => approve(record)} style={approveButtonStyle}>通过</button>
            <button type="button" onClick={() => setPending(current => current.filter(item => item.id !== record.id))} style={rejectButtonStyle}>拒绝</button>
          </div>
        )}
      />

      <CapabilityTable
        title={config.publishedTitle}
        records={published}
        specLabel={config.specLabel}
        published
        action={record => <button type="button" onClick={() => setPublished(current => current.filter(item => item.id !== record.id))} style={secondaryButtonStyle}>下架</button>}
      />
    </div>
  )
}

interface CapabilityTableProps {
  title: string
  records: CapabilityRecord[]
  specLabel?: string
  published?: boolean
  action: (record: CapabilityRecord) => React.ReactNode
}

function CapabilityTable({ title, records, specLabel, published = false, action }: CapabilityTableProps) {
  const headers = ['名称', '提交方', '分类']
  if (specLabel) headers.push(specLabel)
  headers.push(published ? '上架时间' : '提交时间', published ? '调用量' : '说明', '操作')

  return (
    <AdminTableSection title={title}>
      {records.length === 0 ? (
        <div style={emptyStyle}>暂无记录</div>
      ) : (
        <table style={tableStyle}>
          <thead><tr>{headers.map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
          <tbody>
            {records.map((record, index) => (
              <tr key={record.id} style={{ borderBottom: index < records.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                <td style={nameCellStyle}><div>{record.name}</div><div style={{ marginTop: 3, color: 'var(--text-muted)', fontSize: 11, fontWeight: 400 }}>{record.summary}</div></td>
                <td style={cellStyle}>{record.owner}</td>
                <td style={cellStyle}><span style={tagStyle}>{record.category}</span></td>
                {specLabel && <td style={monoCellStyle}>{record.specification}</td>}
                <td style={monoCellStyle}>{published ? record.publishedAt : record.submittedAt}</td>
                <td style={cellStyle}>{published ? `${record.calls ?? 0} 次` : '内容与安全检查'}</td>
                <td style={cellStyle}>{action(record)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </AdminTableSection>
  )
}
