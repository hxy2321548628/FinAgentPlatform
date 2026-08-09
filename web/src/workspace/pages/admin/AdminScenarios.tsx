import { useState } from 'react'

interface ScenarioApplication {
  id: string
  agentName: string
  agentAuthor: string
  scenarioName: string  // 申请时填写的场景展示名
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

const thStyle: React.CSSProperties = {
  padding: '10px 16px', textAlign: 'left', fontSize: 11,
  color: 'var(--text-muted)', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.08em',
  borderBottom: '1px solid var(--border)', background: 'var(--bg)',
}

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
    setApplications(prev => prev.filter(a => a.id !== app.id))
  }

  const handleReject = (id: string) => {
    setApplications(prev => prev.filter(a => a.id !== id))
  }

  const handleUnpublish = (id: string) => {
    setScenarios(prev => prev.filter(s => s.id !== id))
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// SCENARIO MANAGEMENT</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>场景库管理</h1>
      </div>

      {/* 上架申请队列 */}
      {applications.length > 0 && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--action-border)', borderRadius: 10, marginBottom: 24, overflow: 'hidden' }}>
          <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--action-light)' }}>
            <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--action)', fontWeight: 700 }}>
              // 上架申请
            </div>
            <span style={{ padding: '2px 10px', background: 'var(--action)', color: '#fff', borderRadius: 20, fontSize: 12, fontWeight: 700 }}>{applications.length} 个待处理</span>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>{['场景名称', '来源 Agent', '申请人', '学科', '申请时间', '操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {applications.map((app, i) => (
                <tr key={app.id} style={{ borderBottom: i < applications.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{app.scenarioName}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--action)', fontSize: 12 }}>{app.agentName}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{app.agentAuthor}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{app.subject}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>{app.submittedAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => handleApprove(app)} style={{ padding: '5px 12px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>通过</button>
                      <button onClick={() => handleReject(app.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 已发布场景列表 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)' }}>// 已发布场景</div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>共 {scenarios.length} 个</span>
      </div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        {scenarios.length === 0 ? (
          <div style={{ padding: '48px 20px', textAlign: 'center' as const, color: 'var(--text-muted)', fontSize: 13 }}>暂无已发布场景</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>{['场景名称', '来源 Agent', '创建者', '学科', '使用次数', '发布时间', '操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {scenarios.map((s, i) => (
                <tr key={s.id} style={{ borderBottom: i < scenarios.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{s.name}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--action)', fontSize: 12 }}>{s.agentName}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{s.agentAuthor}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{s.subject}</td>
                  <td style={{ padding: '12px 16px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--text-secondary)' }}>{s.uses}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{s.publishedAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <button onClick={() => handleUnpublish(s.id)} style={{ padding: '4px 10px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>下架</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
