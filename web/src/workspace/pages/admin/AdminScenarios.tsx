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

interface ScenarioApplication {
  id: string
  agentName: string
  agentAuthor: string
  scenarioName: string
  subject: string
  submittedAt: string
}

interface PublishedScenario {
  id: string
  name: string
  subject: string
  agentName: string
  agentAuthor: string
  uses: number
  publishedAt: string
}

const MOCK_APPLICATIONS: ScenarioApplication[] = [
  { id: 'a1', agentName: '企业财务异常检测', agentAuthor: '张老师', scenarioName: '企业风险快速评估', subject: '金融学', submittedAt: '2026-08-09 10:15' },
  { id: 'a2', agentName: '计量方法识别', agentAuthor: '赵老师', scenarioName: '论文方法论审查', subject: '经济学', submittedAt: '2026-08-09 14:32' },
]

const MOCK_PUBLISHED: PublishedScenario[] = [
  { id: 's1', name: '企业风险分析', subject: '金融学', agentName: '企业财务异常检测', agentAuthor: '张老师', uses: 127, publishedAt: '2026-07-20' },
  { id: 's2', name: '论文量化复现', subject: '金融学', agentName: '计量方法识别', agentAuthor: '赵老师', uses: 89, publishedAt: '2026-07-25' },
  { id: 's3', name: '课题数据分析', subject: '管理科学', agentName: '（平台内置）', agentAuthor: '金融学院', uses: 203, publishedAt: '2026-07-01' },
  { id: 's4', name: '量化因子研究', subject: '金融学', agentName: '（平台内置）', agentAuthor: '金融学院', uses: 64, publishedAt: '2026-07-01' },
]

export function AdminScenarios() {
  const [applications, setApplications] = useState(MOCK_APPLICATIONS)
  const [scenarios, setScenarios] = useState(MOCK_PUBLISHED)

  const handleApprove = (app: ScenarioApplication) => {
    setScenarios(prev => [{
      id: `s${Date.now()}`,
      name: app.scenarioName,
      subject: app.subject,
      agentName: app.agentName,
      agentAuthor: app.agentAuthor,
      uses: 0,
      publishedAt: new Date().toISOString().split('T')[0],
    }, ...prev])
    setApplications(prev => prev.filter(item => item.id !== app.id))
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// SCENARIO MANAGEMENT" title="场景管理" pendingCount={applications.length} />

      <AdminTableSection title="待审核场景">
        {applications.length === 0 ? (
          <div style={emptyStyle}>暂无待审核场景</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['场景名称', '来源 Agent', '申请人', '学科', '申请时间', '操作'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
            <tbody>
              {applications.map((application, index) => (
                <tr key={application.id} style={{ borderBottom: index < applications.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={nameCellStyle}>{application.scenarioName}</td>
                  <td style={{ ...cellStyle, color: 'var(--action)', fontSize: 12 }}>{application.agentName}</td>
                  <td style={cellStyle}>{application.agentAuthor}</td>
                  <td style={cellStyle}><span style={tagStyle}>{application.subject}</span></td>
                  <td style={monoCellStyle}>{application.submittedAt}</td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button type="button" onClick={() => handleApprove(application)} style={approveButtonStyle}>通过</button>
                      <button type="button" onClick={() => setApplications(prev => prev.filter(item => item.id !== application.id))} style={rejectButtonStyle}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AdminTableSection>

      <AdminTableSection title="已发布场景">
        {scenarios.length === 0 ? (
          <div style={emptyStyle}>暂无已发布场景</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['场景名称', '来源 Agent', '创建者', '学科', '使用次数', '发布时间', '操作'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
            <tbody>
              {scenarios.map((scenario, index) => (
                <tr key={scenario.id} style={{ borderBottom: index < scenarios.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={nameCellStyle}>{scenario.name}</td>
                  <td style={{ ...cellStyle, color: 'var(--action)', fontSize: 12 }}>{scenario.agentName}</td>
                  <td style={cellStyle}>{scenario.agentAuthor}</td>
                  <td style={cellStyle}><span style={tagStyle}>{scenario.subject}</span></td>
                  <td style={monoCellStyle}>{scenario.uses}</td>
                  <td style={monoCellStyle}>{scenario.publishedAt}</td>
                  <td style={cellStyle}>
                    <button type="button" onClick={() => setScenarios(prev => prev.filter(item => item.id !== scenario.id))} style={secondaryButtonStyle}>下架</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AdminTableSection>
    </div>
  )
}
