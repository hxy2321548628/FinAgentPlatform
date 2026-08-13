import { useRef, useState } from 'react'
import { PublishDialog } from '../components/PublishDialog'

type SkillStatus = 'created' | 'reviewing' | 'published'

interface MySkill {
  id: string
  name: string
  category: string
  description: string
  details: string
  archiveName?: string
  status: SkillStatus
  calls?: number
  submittedAt?: string
  publishedAt?: string
}

const STATUS_LABEL: Record<SkillStatus, string> = {
  created: '已创建',
  reviewing: '待审核',
  published: '已发布',
}

const STATUS_STYLE: Record<SkillStatus, { bg: string; color: string }> = {
  created: { bg: '#EFF6FF', color: '#2563EB' },
  reviewing: { bg: '#FFFBEB', color: 'var(--status-warn)' },
  published: { bg: '#ECFDF5', color: 'var(--status-done)' },
}

const MOCK_SKILLS: MySkill[] = [
  { id: '1', name: '财务比率证据链', category: '金融分析', description: '计算关键财务比率，并保留公式、输入科目与结果证据。', details: '输入财务报表 CSV 或 XLSX，输出指标表与口径说明。', status: 'published', calls: 76, publishedAt: '2026-07-28' },
  { id: '2', name: '回归结果稳健性检查', category: '科研分析', description: '按预设清单检查回归模型的稳健性与诊断结果。', details: '输入回归数据和模型结果，输出诊断清单。', status: 'reviewing', submittedAt: '2026-08-10 09:40' },
  { id: '3', name: '行业数据字段标准化', category: '数据处理', description: '将不同来源的行业与公司字段统一为标准命名。', details: '输入 CSV 或 XLSX，输出标准化数据及字段映射。', status: 'created' },
]

const TABS: SkillStatus[] = ['created', 'reviewing', 'published']
const EMPTY_FORM = { name: '', category: '', description: '', details: '', archiveName: '' }

export function MySkills() {
  const [activeTab, setActiveTab] = useState<SkillStatus>('created')
  const [skills, setSkills] = useState(MOCK_SKILLS)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [showEditor, setShowEditor] = useState(false)
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const archiveRef = useRef<HTMLInputElement>(null)

  const filtered = skills.filter(skill => skill.status === activeTab)
  const formReady = Boolean(form.archiveName.trim())

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowEditor(true)
  }

  const openEdit = (skill: MySkill) => {
    setEditingId(skill.id)
    setForm({ name: skill.name, category: skill.category, description: skill.description, details: skill.details, archiveName: skill.archiveName ?? `${skill.name}.zip` })
    setShowEditor(true)
  }

  const saveSkill = (event: React.FormEvent) => {
    event.preventDefault()
    if (!formReady) return
    if (editingId) {
      setSkills(current => current.map(skill => skill.id === editingId ? { ...skill, ...form } : skill))
    } else {
      const fallbackName = form.archiveName.replace(/\.zip$/i, '')
      setSkills(current => [{ id: String(Date.now()), name: form.name.trim() || fallbackName, category: form.category.trim() || '未分类', description: form.description.trim() || '从 ZIP 包读取 SKILL.md 后生成能力说明。', details: form.details.trim() || '等待服务端校验并解析 Skill 目录。', archiveName: form.archiveName, status: 'created' }, ...current])
      setActiveTab('created')
    }
    setShowEditor(false)
  }

  const submitForReview = (id: string, name: string, description: string) => {
    setSkills(current => current.map(skill => skill.id === id ? { ...skill, name, description, status: 'reviewing', submittedAt: '刚刚' } : skill))
    setPublishingId(null)
    setActiveTab('reviewing')
  }

  const takeOffline = (id: string) => {
    setSkills(current => current.map(skill => skill.id === id ? { ...skill, status: 'created', publishedAt: undefined } : skill))
    setActiveTab('created')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 28 }}>
        <div>
          <div style={eyebrowStyle}>// MY SKILLS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的 Skills</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理你创建的 Skills，并申请发布到 Skills 库</p>
        </div>
        <button type="button" onClick={openCreate} style={primaryButtonStyle}>+ 创建 Skill</button>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(tab => (
          <button type="button" key={tab} onClick={() => setActiveTab(tab)} style={{ ...tabStyle, borderBottomColor: activeTab === tab ? 'var(--action)' : 'transparent', color: activeTab === tab ? 'var(--action)' : 'var(--text-muted)' }}>
            {STATUS_LABEL[tab]}
            <span style={countStyle}>{skills.filter(skill => skill.status === tab).length}</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={emptyStyle}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 12 }}>该状态下还没有 Skill</div>
          {activeTab === 'created' && <button type="button" onClick={openCreate} style={primaryButtonStyle}>+ 创建 Skill</button>}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(skill => (
            <div key={skill.id} style={rowStyle}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{skill.name}</span>
                  <span style={{ ...statusStyle, background: STATUS_STYLE[skill.status].bg, color: STATUS_STYLE[skill.status].color }}>{STATUS_LABEL[skill.status]}</span>
                  {skill.calls !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{skill.calls} 次调用</span>}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 5 }}>{skill.description}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {skill.category}
                  {skill.publishedAt && ` · ${skill.publishedAt} 发布`}
                  {skill.submittedAt && ` · ${skill.submittedAt} 提交审核`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                {skill.status === 'created' && <><button type="button" onClick={() => openEdit(skill)} style={secondaryButtonStyle}>编辑</button><button type="button" onClick={() => setPublishingId(skill.id)} style={outlineActionStyle}>发布到 Skills 库</button></>}
                {skill.status === 'reviewing' && <span style={waitingStyle}>等待审核</span>}
                {skill.status === 'published' && <><button type="button" onClick={() => openEdit(skill)} style={secondaryButtonStyle}>编辑</button><button type="button" onClick={() => takeOffline(skill.id)} style={dangerButtonStyle}>下线</button></>}
              </div>
            </div>
          ))}
        </div>
      )}


      {publishingId && (() => {
        const skill = skills.find(item => item.id === publishingId)
        return skill ? <PublishDialog kindLabel="Skill" initialName={skill.name} initialDescription={skill.description} existingNames={[...skills.filter(item => item.status === 'published').map(item => item.name), '数据清洗', 'PDF 文本提取', '财务指标计算']} onClose={() => setPublishingId(null)} onSubmit={(name, description) => submitForReview(skill.id, name, description)} /> : null
      })()}

      {showEditor && (
        <>
          <div onClick={() => setShowEditor(false)} style={backdropStyle} />
          <div style={modalStyle}>
            <div style={modalHeaderStyle}><div><div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>{editingId ? '更新 Skill 文件' : '上传 Skill'}</div><div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>上传整个 Skill 目录的 ZIP 压缩包，根目录必须包含唯一的 SKILL.md。</div></div><button type="button" onClick={() => setShowEditor(false)} style={closeStyle}>×</button></div>
            <form onSubmit={saveSkill}>
              <input ref={archiveRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={event => { const file = event.target.files?.[0]; if (file) setForm(current => ({ ...current, archiveName: file.name })) }} />
              <button type="button" onClick={() => archiveRef.current?.click()} style={{ width: '100%', padding: '24px 18px', marginBottom: 14, border: '1px dashed var(--action-border)', borderRadius: 9, background: 'var(--action-light)', color: 'var(--action)', cursor: 'pointer', fontFamily: 'inherit' }}>
                <span style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{form.archiveName || '选择 ZIP 压缩包'}</span>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)' }}>解压后不超过 5 MB；仅允许文本与代码类附件</span>
              </button>
              <div style={{ padding: '10px 12px', marginBottom: 20, borderRadius: 7, background: 'var(--bg)', color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.65 }}>平台将从 SKILL.md 的 frontmatter 读取名称与描述，并校验路径穿越、符号链接、文件数量、压缩比和文件类型。</div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}><button type="button" onClick={() => setShowEditor(false)} style={secondaryButtonStyle}>取消</button><button type="submit" disabled={!formReady} style={{ ...primaryButtonStyle, background: formReady ? 'var(--action)' : 'var(--text-muted)', cursor: formReady ? 'pointer' : 'default' }}>{editingId ? '更新文件' : '上传并创建'}</button></div>
            </form>
          </div>
        </>
      )}
    </div>
  )
}

const eyebrowStyle: React.CSSProperties = { fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }
const primaryButtonStyle: React.CSSProperties = { padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }
const tabStyle: React.CSSProperties = { padding: '10px 20px', fontSize: 13, fontWeight: 500, background: 'none', border: 'none', borderBottom: '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit' }
const countStyle: React.CSSProperties = { marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }
const emptyStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' }
const rowStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }
const statusStyle: React.CSSProperties = { padding: '1px 7px', borderRadius: 10, fontSize: 11, fontWeight: 600 }
const secondaryButtonStyle: React.CSSProperties = { padding: '7px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }
const outlineActionStyle: React.CSSProperties = { ...secondaryButtonStyle, color: 'var(--action)', borderColor: 'var(--action-border)' }
const dangerButtonStyle: React.CSSProperties = { ...secondaryButtonStyle, color: '#DC2626', borderColor: '#FECACA' }
const waitingStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', padding: '7px 0' }
const backdropStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 300 }
const modalStyle: React.CSSProperties = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 500, maxHeight: 'calc(100vh - 64px)', overflowY: 'auto', padding: 30, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: '0 20px 60px rgba(11,46,92,0.2)', zIndex: 301 }
const modalHeaderStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 22 }
const closeStyle: React.CSSProperties = { border: 'none', background: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }
