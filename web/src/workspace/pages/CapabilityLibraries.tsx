import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { errorMessage } from '../../api/request'
import { listCatalog, skillKeys } from '../../api/skills'
import type { SkillListing } from '../../api/types'
import { CatalogCard, CatalogControls, type CatalogFilter } from '../components/Catalog'

interface McpCapability {
  name: string
  description: string
}

interface CapabilityItem {
  id: string
  name: string
  category: string
  description: string
  author: string
  inputs: string
  tags: string[]
  details: string
  calls: number
  tools?: McpCapability[]
  resources?: McpCapability[]
  prompts?: McpCapability[]
}

const MCP_FILTERS: CatalogFilter[] = ['全部', '金融数据', '学术资源', '文件服务', '业务系统'].map(key => ({ key, label: key }))

const MCP_SERVERS: CapabilityItem[] = [
  { id: 'market-data', name: '学院行情数据服务', category: '金融数据', description: '为量化研究与资产定价场景提供经过平台审核的行情数据能力。', author: '金融学院', inputs: '证券代码、日期范围、频率', tags: ['行情', '证券数据', '时间序列'], details: '平台已放行的 MCP Server，调用范围由场景权限和用户数据权限共同决定。', calls: 164, tools: [{ name: 'get_market_bars', description: '查询证券在指定日期范围与频率下的行情序列。' }, { name: 'get_security_profile', description: '读取证券基本资料与交易状态。' }], resources: [{ name: 'market://calendar/{exchange}', description: '交易所交易日历。' }], prompts: [{ name: 'compare_volatility', description: '生成多证券波动率比较任务模板。' }] },
  { id: 'financial-reports', name: '财报检索服务', category: '金融数据', description: '按公司和报告期检索财务报告及公告元数据。', author: '金融学院', inputs: '公司标识、报告期、文档类型', tags: ['财报', '公告', '公司数据'], details: '平台已审核放行的 MCP Server。使用前应查看其能力清单，并对需要调用的工具显式授权。', calls: 119, tools: [{ name: 'search_reports', description: '按公司、报告期与文档类型检索报告。' }, { name: 'get_report_metadata', description: '读取报告标题、发布日期、来源与页数。' }, { name: 'extract_report_sections', description: '按章节或关键词提取报告内容并保留页码。' }], resources: [{ name: 'report://{company}/{period}/{document_id}', description: '财报文档及其元数据资源。' }], prompts: [{ name: 'financial_report_review', description: '生成财报核查与重点变化分析模板。' }] },
  { id: 'academic-search', name: '学术文献检索', category: '学术资源', description: '检索论文、作者与引文信息，为研究和综述场景提供资料。', author: '金融学院', inputs: '关键词、作者、年份范围', tags: ['论文检索', '引文', '研究综述'], details: '平台已放行的学术资源 MCP Server，具体数据范围以服务授权为准。', calls: 87, tools: [{ name: 'search_papers', description: '按关键词、作者与年份检索论文。' }, { name: 'get_citations', description: '读取论文的引用与被引关系。' }], resources: [{ name: 'paper://{paper_id}', description: '论文元数据与可访问全文。' }], prompts: [{ name: 'literature_review', description: '生成结构化文献综述任务模板。' }] },
  { id: 'workspace-files', name: '任务工作目录服务', category: '文件服务', description: '读写当前任务工作目录中的文件，支持场景处理过程产物。', author: '平台能力目录', inputs: '文件路径、内容或上传文件', tags: ['工作目录', '文件读写', '任务隔离'], details: '平台内置 MCP Server，仅允许访问当前分析对话的隔离工作目录。', calls: 256, tools: [{ name: 'read_file', description: '读取工作目录中的文本文件。' }, { name: 'write_file', description: '写入或更新工作目录文件。' }, { name: 'list_directory', description: '列出指定目录内容。' }], resources: [{ name: 'workspace://{path}', description: '当前分析对话内的文件资源。' }], prompts: [] },
]

export function SkillsLibrary() {
  const catalog = useQuery({ queryKey: skillKeys.catalog(), queryFn: listCatalog })
  const [activeFilter, setActiveFilter] = useState('全部')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<SkillListing | null>(null)
  const items = [...(catalog.data ?? [])].sort((a, b) => b.call_count - a.call_count || a.name.localeCompare(b.name, 'zh-CN'))
  const filters: CatalogFilter[] = ['全部', ...new Set(items.map(one => one.subject || '未分类'))].map(key => ({ key, label: key }))
  const normalized = search.trim().toLocaleLowerCase('zh-CN')
  const filtered = items.filter(item => {
    const matchesSubject = activeFilter === '全部' || (item.subject || '未分类') === activeFilter
    const haystack = `${item.name} ${item.description} ${item.owner_name}`.toLocaleLowerCase('zh-CN')
    return matchesSubject && (!normalized || haystack.includes(normalized))
  })

  return (
    <LibraryPage eyebrow="// SKILLS LIBRARY" title="Skills 库" description={`浏览审核通过的能力目录，共 ${items.length} 个目录项`}>
      <CatalogControls search={search} onSearch={setSearch} placeholder="搜索 Skill 名称、描述或作者..." filters={filters} activeFilter={activeFilter} onFilter={setActiveFilter} />
      {catalog.isPending && <Notice>正在加载 Skills…</Notice>}
      {catalog.isError && <Notice error>{errorMessage(catalog.error)}</Notice>}
      {!catalog.isPending && !catalog.isError && <SkillCards items={filtered} search={search} onSelect={setSelected} />}
      {selected && <SkillDetail item={selected} onClose={() => setSelected(null)} />}
    </LibraryPage>
  )
}

function SkillCards({ items, search, onSelect }: { items: SkillListing[]; search: string; onSelect: (item: SkillListing) => void }) {
  if (items.length === 0) return <Notice>{search ? `未找到与「${search}」相关的 Skill` : '该分类暂时没有 Skill'}</Notice>
  return (
    <div style={{ padding: '0 36px 32px' }}>
      <div style={gridStyle}>
        {items.map(item => (
          <CatalogCard
            key={item.id}
            title={item.name}
            version={`v${item.version}`}
            author={item.owner_name}
            subject={item.subject || '未分类'}
            description={item.description}
            detail={`${item.file_count} 个文件 · ${formatBytes(item.total_bytes)}`}
            badges={[sourceLabel(item.source)]}
            metric={`${item.call_count} 次调用`}
            secondaryAction={{ label: '查看详情', onClick: () => onSelect(item) }}
          />
        ))}
      </div>
      <div style={countStyle}>共 {items.length} 个目录项</div>
    </div>
  )
}

function SkillDetail({ item, onClose }: { item: SkillListing; onClose: () => void }) {
  return (
    <>
      <div onClick={onClose} style={backdropStyle} />
      <aside role="dialog" aria-label={`${item.name} Skill 详情`} style={drawerStyle}>
        <div style={drawerHeaderStyle}><div><div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{item.name}</div><div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{item.owner_name} · {item.subject || '未分类'} · v{item.version}</div></div><button type="button" aria-label="关闭" onClick={onClose} style={closeButtonStyle}>×</button></div>
        <div style={{ overflowY: 'auto', padding: 24 }}>
          <div style={{ marginBottom: 20 }}><div style={sectionTitle}>功能描述</div><p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{item.description || '（作者没有写说明）'}</p></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 20 }}>
            <Info label="文件数量" value={`${item.file_count} 个`} /><Info label="体积" value={formatBytes(item.total_bytes)} /><Info label="调用次数" value={`${item.call_count} 次`} /><Info label="可见范围" value={item.source === 'catalog' ? '广场可见' : item.source === 'group' ? '组内共享' : '我创建的'} />
          </div>
          <div><div style={sectionTitle}>使用说明</div><p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>该 Skill 已通过平台审核，可在聊天页的智能体配置中选择。实际可用文件以发布版本为准。</p></div>
        </div>
      </aside>
    </>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return <div style={{ padding: '12px 14px', border: '1px solid var(--border)', borderRadius: 7 }}><div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div><div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div></div>
}

export function McpLibrary() {
  const [activeFilter, setActiveFilter] = useState('全部')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<CapabilityItem | null>(null)
  const normalized = search.trim().toLocaleLowerCase('zh-CN')
  const filtered = [...MCP_SERVERS].sort((a, b) => b.calls - a.calls || a.name.localeCompare(b.name, 'zh-CN')).filter(item => {
    const matchesCategory = activeFilter === '全部' || item.category === activeFilter
    const haystack = `${item.name} ${item.description} ${item.tags.join(' ')}`.toLocaleLowerCase('zh-CN')
    return matchesCategory && (!normalized || haystack.includes(normalized))
  })

  return (
    <LibraryPage eyebrow="// MCP LIBRARY" title="MCP 库" description={`浏览平台审核放行的 MCP Server 及其协议能力，共 ${MCP_SERVERS.length} 个目录项`}>
      <CatalogControls search={search} onSearch={setSearch} placeholder="搜索 MCP Server 名称、描述或标签..." filters={MCP_FILTERS} activeFilter={activeFilter} onFilter={setActiveFilter} />
      {filtered.length === 0 ? <Notice>{search ? `未找到与「${search}」相关的 MCP Server` : '该分类暂时没有 MCP Server'}</Notice> : (
        <div style={{ padding: '0 36px 32px' }}>
          <div style={gridStyle}>
            {filtered.map(item => <CatalogCard key={item.id} title={item.name} author={item.author} subject={item.category} description={item.description} detail={`${item.tools?.length ?? 0} Tools · ${item.resources?.length ?? 0} Resources · ${item.prompts?.length ?? 0} Prompts`} badges={item.tags} metric={`${item.calls} 次调用`} secondaryAction={{ label: '查看 MCP 能力', onClick: () => setSelected(item) }} />)}
          </div>
          <div style={countStyle}>共 {filtered.length} 个目录项</div>
        </div>
      )}
      {selected && <McpDetail item={selected} onClose={() => setSelected(null)} />}
    </LibraryPage>
  )
}

function LibraryPage({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0' }}>
        <div style={eyebrowStyle}>{eyebrow}</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{description}</p>
      </div>
      {children}
    </div>
  )
}

function Notice({ error = false, children }: { error?: boolean; children: React.ReactNode }) {
  return <div role={error ? 'alert' : undefined} style={{ padding: '60px 36px', textAlign: 'center', color: error ? '#DC2626' : 'var(--text-muted)', fontSize: 14 }}>{children}</div>
}

function McpDetail({ item, onClose }: { item: CapabilityItem; onClose: () => void }) {
  return (
    <>
      <div onClick={onClose} style={backdropStyle} />
      <aside role="dialog" aria-label={`${item.name} MCP 能力`} style={drawerStyle}>
        <div style={drawerHeaderStyle}><div><div style={{ fontSize: 16, fontWeight: 700 }}>{item.name}</div><div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{item.author} · {item.category} · 只读</div></div><button type="button" aria-label="关闭" onClick={onClose} style={closeButtonStyle}>×</button></div>
        <div style={{ overflowY: 'auto', padding: 24 }}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75, marginBottom: 20 }}>{item.details}</p>
          <McpSection title="Tools" description="模型可调用的操作" items={item.tools ?? []} />
          <McpSection title="Resources" description="可读取或订阅的数据资源" items={item.resources ?? []} />
          <McpSection title="Prompts" description="Server 提供的任务模板" items={item.prompts ?? []} />
        </div>
      </aside>
    </>
  )
}

function McpSection({ title, description, items }: { title: string; description: string; items: McpCapability[] }) {
  if (items.length === 0) return null
  return <section style={{ marginBottom: 22 }}><h3 style={{ fontSize: 14, color: 'var(--text-primary)', marginBottom: 9 }}>{title} <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>{description} · {items.length}</span></h3><div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{items.map(item => <div key={item.name} style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 7 }}><code style={{ fontSize: 12, color: 'var(--action)' }}>{item.name}</code><div style={{ marginTop: 5, fontSize: 12, color: 'var(--text-secondary)' }}>{item.description}</div></div>)}</div></section>
}

function sourceLabel(source: SkillListing['source']): string {
  return source === 'owned' ? '我创建的' : source === 'group' ? '组内共享' : '平台目录'
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

const sectionTitle: React.CSSProperties = { fontSize: 12, fontWeight: 650, color: 'var(--text-primary)', marginBottom: 8 }
const eyebrowStyle: React.CSSProperties = { fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }
const gridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }
const countStyle: React.CSSProperties = { padding: '20px 0 0', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }
const backdropStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.35)', zIndex: 200 }
const drawerStyle: React.CSSProperties = { position: 'fixed', top: 0, right: 0, bottom: 0, width: 560, maxWidth: 'calc(100vw - 40px)', background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, boxShadow: '-8px 0 24px rgba(11,46,92,0.12)', display: 'flex', flexDirection: 'column' }
const drawerHeaderStyle: React.CSSProperties = { padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }
const closeButtonStyle: React.CSSProperties = { background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20 }
