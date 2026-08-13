import { useState } from 'react'
import { CatalogCard, CatalogControls, type CatalogFilter } from '../components/Catalog'

interface SkillFile {
  path: string
  content: string
}

interface SkillTreeNode {
  name: string
  path: string
  kind: 'folder' | 'file'
  children: SkillTreeNode[]
}

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
  files?: SkillFile[]
  tools?: McpCapability[]
  resources?: McpCapability[]
  prompts?: McpCapability[]
}

type LibraryKind = 'skill' | 'mcp'

const SKILL_FILTERS: CatalogFilter[] = ['全部', '数据处理', '金融分析', '科研分析', '结果呈现'].map(key => ({ key, label: key }))
const MCP_FILTERS: CatalogFilter[] = ['全部', '金融数据', '学术资源', '文件服务', '业务系统'].map(key => ({ key, label: key }))

function skillFiles(name: string, summary: string, script: string): SkillFile[] {
  return [
    { path: 'SKILL.md', content: `---\nname: ${name}\ndescription: ${summary}\n---\n\n# 使用说明\n\n${summary}\n\n## 执行步骤\n\n1. 检查输入文件格式与字段。\n2. 运行 scripts/${script}。\n3. 保存结果与处理记录。\n` },
    { path: `scripts/${script}`, content: '# Skill 执行脚本（只读预览）\n\ndef run(input_path: str) -> None:\n    """处理输入并生成结果。"""\n    print(input_path)\n' },
    { path: 'references/input-format.md', content: '# 输入格式\n\n请按能力卡片中列出的输入要求准备文件或参数。\n' },
  ]
}

function buildSkillTree(files: SkillFile[]): SkillTreeNode[] {
  const root: SkillTreeNode[] = []
  for (const file of files) {
    const parts = file.path.split('/')
    let siblings = root
    let currentPath = ''
    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part
      const kind = index === parts.length - 1 ? 'file' : 'folder'
      let node = siblings.find(item => item.name === part && item.kind === kind)
      if (!node) {
        node = { name: part, path: currentPath, kind, children: [] }
        siblings.push(node)
      }
      siblings = node.children
    })
  }

  const sortNodes = (nodes: SkillTreeNode[]) => {
    nodes.sort((left, right) => Number(right.kind === 'folder') - Number(left.kind === 'folder') || left.name.localeCompare(right.name, 'zh-CN'))
    nodes.forEach(node => sortNodes(node.children))
  }
  sortNodes(root)
  return root
}

function folderPaths(files: SkillFile[]) {
  const paths = new Set<string>()
  files.forEach(file => {
    const parts = file.path.split('/')
    parts.pop()
    parts.forEach((_, index) => paths.add(parts.slice(0, index + 1).join('/')))
  })
  return paths
}

const SKILLS: CapabilityItem[] = [
  { id: 'data-cleaning', name: '数据清洗', category: '数据处理', description: '识别缺失值、异常值与重复记录，并生成清洗步骤及质量摘要。', author: '平台能力目录', inputs: 'CSV / XLSX', tags: ['缺失值处理', '异常检测', '字段标准化'], details: '适用于分析前的数据质量检查。场景可组合该 Skill，引导智能体记录清洗规则与数据变化。', calls: 186, files: skillFiles('data-cleaning', '检查并清洗结构化数据，同时保留可复核的变更记录。', 'clean_data.py') },
  { id: 'pdf-extraction', name: 'PDF 文本提取', category: '数据处理', description: '提取论文、公告与财报中的正文和表格，保留页码定位信息。', author: '平台能力目录', inputs: 'PDF', tags: ['文本提取', '表格识别', '原文定位'], details: '为文档分析场景提供结构化输入，输出内容需要保留原文页码以便核查。', calls: 142, files: skillFiles('pdf-extraction', '从 PDF 提取正文与表格并保留页码。', 'extract_pdf.py') },
  { id: 'financial-metrics', name: '财务指标计算', category: '金融分析', description: '根据财务报表计算偿债、盈利、运营与成长能力指标。', author: '金融学院', inputs: '财务报表 CSV / XLSX', tags: ['比率分析', '财务报表', '证据链'], details: '定义常用财务指标口径，并要求输出公式、输入科目和计算结果，便于复核。', calls: 128, files: skillFiles('financial-metrics', '计算财务指标并输出公式与证据链。', 'calculate_metrics.py') },
  { id: 'regression-diagnostics', name: '回归诊断', category: '科研分析', description: '检查模型设定、共线性、异方差和稳健性检验，整理诊断结果。', author: '金融学院', inputs: '回归数据 / 模型结果', tags: ['计量经济学', '稳健性', '模型诊断'], details: '用于论文复现与实证研究场景，帮助智能体形成标准化的回归诊断清单。', calls: 94, files: skillFiles('regression-diagnostics', '执行回归诊断并形成标准化检查清单。', 'diagnose_regression.py') },
  { id: 'chart-generation', name: '图表生成', category: '结果呈现', description: '根据分析结果生成适合报告使用的趋势图、分布图与对比图。', author: '平台能力目录', inputs: '结构化分析结果', tags: ['可视化', '报告图表', '导出'], details: '约束图表标题、单位、图例和数据来源，输出文件保存在当前任务的工作目录中。', calls: 217, files: skillFiles('chart-generation', '生成符合报告规范的分析图表。', 'render_chart.py') },
]

const MCP_SERVERS: CapabilityItem[] = [
  { id: 'market-data', name: '学院行情数据服务', category: '金融数据', description: '为量化研究与资产定价场景提供经过平台审核的行情数据能力。', author: '金融学院', inputs: '证券代码、日期范围、频率', tags: ['行情', '证券数据', '时间序列'], details: '平台已放行的 MCP Server，调用范围由场景权限和用户数据权限共同决定。', calls: 164, tools: [{ name: 'get_market_bars', description: '查询证券在指定日期范围与频率下的行情序列。' }, { name: 'get_security_profile', description: '读取证券基本资料与交易状态。' }], resources: [{ name: 'market://calendar/{exchange}', description: '交易所交易日历。' }], prompts: [{ name: 'compare_volatility', description: '生成多证券波动率比较任务模板。' }] },
  { id: 'financial-reports', name: '财报检索服务', category: '金融数据', description: '按公司和报告期检索财务报告及公告元数据。', author: '金融学院', inputs: '公司标识、报告期、文档类型', tags: ['财报', '公告', '公司数据'], details: '平台已审核放行的 MCP Server。使用前应查看其能力清单，并对需要调用的工具显式授权。', calls: 119, tools: [{ name: 'search_reports', description: '按公司、报告期与文档类型检索报告。' }, { name: 'get_report_metadata', description: '读取报告标题、发布日期、来源与页数。' }, { name: 'extract_report_sections', description: '按章节或关键词提取报告内容并保留页码。' }], resources: [{ name: 'report://{company}/{period}/{document_id}', description: '财报文档及其元数据资源。' }], prompts: [{ name: 'financial_report_review', description: '生成财报核查与重点变化分析模板。' }] },
  { id: 'academic-search', name: '学术文献检索', category: '学术资源', description: '检索论文、作者与引文信息，为研究和综述场景提供资料。', author: '金融学院', inputs: '关键词、作者、年份范围', tags: ['论文检索', '引文', '研究综述'], details: '平台已放行的学术资源 MCP Server，具体数据范围以服务授权为准。', calls: 87, tools: [{ name: 'search_papers', description: '按关键词、作者与年份检索论文。' }, { name: 'get_citations', description: '读取论文的引用与被引关系。' }], resources: [{ name: 'paper://{paper_id}', description: '论文元数据与可访问全文。' }], prompts: [{ name: 'literature_review', description: '生成结构化文献综述任务模板。' }] },
  { id: 'workspace-files', name: '任务工作目录服务', category: '文件服务', description: '读写当前任务工作目录中的文件，支持场景处理过程产物。', author: '平台能力目录', inputs: '文件路径、内容或上传文件', tags: ['工作目录', '文件读写', '任务隔离'], details: '平台内置 MCP Server，仅允许访问当前分析对话的隔离工作目录。', calls: 256, tools: [{ name: 'read_file', description: '读取工作目录中的文本文件。' }, { name: 'write_file', description: '写入或更新工作目录文件。' }, { name: 'list_directory', description: '列出指定目录内容。' }], resources: [{ name: 'workspace://{path}', description: '当前分析对话内的文件资源。' }], prompts: [] },
]

export function SkillsLibrary() {
  return <CapabilityLibrary kind="skill" eyebrow="// SKILLS LIBRARY" title="Skills 库" description="浏览可用于智能体配置的能力目录" items={SKILLS} filters={SKILL_FILTERS} noun="Skill" />
}

export function McpLibrary() {
  return <CapabilityLibrary kind="mcp" eyebrow="// MCP LIBRARY" title="MCP 库" description="浏览平台审核放行的 MCP Server 及其协议能力" items={MCP_SERVERS} filters={MCP_FILTERS} noun="MCP Server" actionLabel="+ 申请添加 MCP" />
}

function CapabilityLibrary({ kind, eyebrow, title, description, items, filters, noun, actionLabel }: { kind: LibraryKind; eyebrow: string; title: string; description: string; items: CapabilityItem[]; filters: CatalogFilter[]; noun: string; actionLabel?: string }) {
  const [activeFilter, setActiveFilter] = useState('全部')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<CapabilityItem | null>(null)
  const [selectedFile, setSelectedFile] = useState('SKILL.md')
  const [showRequest, setShowRequest] = useState(false)
  const [requestName, setRequestName] = useState('')
  const [requestCategory, setRequestCategory] = useState('')
  const [requestDescription, setRequestDescription] = useState('')
  const [requestDetails, setRequestDetails] = useState('')
  const [requestSubmitted, setRequestSubmitted] = useState(false)

  const filtered = items.filter(item => {
    const matchCategory = activeFilter === '全部' || item.category === activeFilter
    const matchSearch = !search || item.name.includes(search) || item.description.includes(search) || item.tags.some(tag => tag.includes(search))
    return matchCategory && matchSearch
  })

  const openDetail = (item: CapabilityItem) => {
    setSelected(item)
    setSelectedFile(item.files?.[0]?.path ?? '')
  }

  const requestReady = Boolean(requestName.trim() && requestCategory.trim() && requestDescription.trim() && requestDetails.trim())
  const submitRequest = (event: React.FormEvent) => {
    event.preventDefault()
    if (!requestReady) return
    setRequestSubmitted(true)
    setTimeout(() => {
      setShowRequest(false)
      setRequestSubmitted(false)
      setRequestName('')
      setRequestCategory('')
      setRequestDescription('')
      setRequestDetails('')
    }, 1200)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24 }}>
        <div>
          <div style={eyebrowStyle}>{eyebrow}</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{title}</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{description}，共 {items.length} 个目录项</p>
        </div>
        {actionLabel && <button type="button" onClick={() => setShowRequest(true)} style={headerActionStyle}>{actionLabel}</button>}
      </div>

      <CatalogControls search={search} onSearch={setSearch} placeholder={`搜索${noun}名称、描述或标签...`} filters={filters} activeFilter={activeFilter} onFilter={setActiveFilter} />

      <div style={{ padding: '0 36px' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>{search ? `未找到与「${search}」相关的${noun}` : `该分类暂时没有${noun}`}</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
            {filtered.map(item => <CatalogCard key={item.id} title={item.name} author={item.author} subject={item.category} description={item.description} detail={kind === 'skill' ? `输入：${item.inputs}` : `${item.tools?.length ?? 0} Tools · ${item.resources?.length ?? 0} Resources · ${item.prompts?.length ?? 0} Prompts`} badges={item.tags} metric={`${item.calls} 次调用`} secondaryAction={{ label: kind === 'skill' ? '查看文件' : '查看 MCP 能力', onClick: () => openDetail(item) }} />)}
          </div>
        )}
        <div style={{ padding: '20px 0 32px', textAlign: 'center' }}><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>共 {filtered.length} 个目录项</span></div>
      </div>

      {selected && <CapabilityDetail kind={kind} item={selected} selectedFile={selectedFile} onSelectFile={setSelectedFile} onClose={() => setSelected(null)} />}

      {showRequest && (
        <>
          <div onClick={() => setShowRequest(false)} style={backdropStyle} />
          <div style={modalStyle}>
            {requestSubmitted ? (
              <div style={{ textAlign: 'center', padding: '24px 0' }}><div style={{ fontSize: 36, marginBottom: 12 }}>✓</div><div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>申请已提交</div><div style={{ fontSize: 13, color: 'var(--text-muted)' }}>平台审核后会同步处理结果</div></div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}><div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>申请添加 MCP Server</div><button type="button" onClick={() => setShowRequest(false)} style={closeButtonStyle}>×</button></div>
                <div style={modalNoticeStyle}>请说明 Server 的接入方式，以及其 Tools、Resources、Prompts 与权限边界；请勿填写密钥等敏感凭据。</div>
                <form onSubmit={submitRequest}>
                  <FormField label="MCP Server 名称" value={requestName} onChange={setRequestName} placeholder="请输入 MCP Server 名称" />
                  <FormField label="分类" value={requestCategory} onChange={setRequestCategory} placeholder="如：金融数据 / 学术资源" />
                  <FormTextArea label="服务用途" value={requestDescription} onChange={setRequestDescription} placeholder="说明服务提供的能力和使用场景" />
                  <FormTextArea label="接入地址、能力清单与权限范围" value={requestDetails} onChange={setRequestDetails} placeholder="列出 Tools、Resources、Prompts、部署方式与所需权限" />
                  <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}><button type="button" onClick={() => setShowRequest(false)} style={secondaryButtonStyle}>取消</button><button type="submit" disabled={!requestReady} style={{ ...primaryButtonStyle, background: requestReady ? 'var(--action)' : 'var(--text-muted)', cursor: requestReady ? 'pointer' : 'default' }}>提交审核</button></div>
                </form>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function CapabilityDetail({ kind, item, selectedFile, onSelectFile, onClose }: { kind: LibraryKind; item: CapabilityItem; selectedFile: string; onSelectFile: (path: string) => void; onClose: () => void }) {
  const currentFile = item.files?.find(file => file.path === selectedFile) ?? item.files?.[0]
  const files = item.files ?? []
  const tree = buildSkillTree(files)
  const [expandedFolders, setExpandedFolders] = useState(() => folderPaths(files))
  const toggleFolder = (path: string) => {
    setExpandedFolders(current => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
      <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: kind === 'skill' ? 720 : 560, maxWidth: 'calc(100vw - 40px)', background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, boxShadow: '-8px 0 24px rgba(11,46,92,0.12)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div><div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{item.name}</div><div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{item.author} · {item.category} · 只读</div></div>
          <button type="button" onClick={onClose} aria-label="关闭" style={closeButtonStyle}>×</button>
        </div>
        {kind === 'skill' ? (
          <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '250px minmax(0, 1fr)' }}>
            <aside style={{ overflowY: 'auto', borderRight: '1px solid var(--border)', background: 'var(--bg)', padding: '14px 10px' }}>
              <div style={{ padding: '0 10px 10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-light)', marginBottom: 7 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.08em' }}>文件树</span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{files.length} 个文件</span>
              </div>
              <div role="tree" aria-label={`${item.name} 文件树`}>
                {tree.map(node => <SkillTreeRow key={node.path} node={node} depth={0} selectedFile={selectedFile} expandedFolders={expandedFolders} onToggleFolder={toggleFolder} onSelectFile={onSelectFile} />)}
              </div>
            </aside>
            <section style={{ minWidth: 0, overflow: 'auto', padding: 22 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>{currentFile?.path}</div>
              <pre style={{ margin: 0, padding: 16, minHeight: 360, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: '#0D1829', color: '#D8E4F5', borderRadius: 8, fontSize: 12, lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace" }}>{currentFile?.content}</pre>
            </section>
          </div>
        ) : (
          <div style={{ overflowY: 'auto', padding: 24 }}>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75, marginBottom: 20 }}>{item.details}</p>
            <McpSection title="Tools" description="模型可调用的操作" items={item.tools ?? []} />
            <McpSection title="Resources" description="可读取或订阅的数据资源" items={item.resources ?? []} />
            <McpSection title="Prompts" description="Server 提供的任务模板" items={item.prompts ?? []} />
          </div>
        )}
      </div>
    </>
  )
}

function SkillTreeRow({ node, depth, selectedFile, expandedFolders, onToggleFolder, onSelectFile }: { node: SkillTreeNode; depth: number; selectedFile: string; expandedFolders: Set<string>; onToggleFolder: (path: string) => void; onSelectFile: (path: string) => void }) {
  const isFolder = node.kind === 'folder'
  const expanded = isFolder && expandedFolders.has(node.path)
  const selected = !isFolder && selectedFile === node.path
  return (
    <div role="treeitem" aria-expanded={isFolder ? expanded : undefined} aria-selected={selected || undefined}>
      <button
        type="button"
        onClick={() => isFolder ? onToggleFolder(node.path) : onSelectFile(node.path)}
        title={node.path}
        style={{
          width: '100%', minHeight: 32, padding: '5px 8px', paddingLeft: 8 + depth * 16,
          display: 'flex', alignItems: 'center', gap: 6, border: 'none', borderRadius: 5,
          background: selected ? 'var(--action-light)' : 'transparent',
          color: selected ? 'var(--action)' : isFolder ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: isFolder ? 600 : 400, textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit',
        }}
      >
        {isFolder ? <ChevronIcon expanded={expanded} /> : <span style={{ width: 12, flexShrink: 0 }} />}
        {isFolder ? <FolderIcon expanded={expanded} /> : <FileIcon path={node.path} />}
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{node.name}</span>
      </button>
      {expanded && node.children.length > 0 && (
        <div role="group" style={{ marginLeft: 13 + depth * 16, borderLeft: '1px solid var(--border)', paddingLeft: 2 }}>
          {node.children.map(child => <SkillTreeRow key={child.path} node={child} depth={depth + 1} selectedFile={selectedFile} expandedFolders={expandedFolders} onToggleFolder={onToggleFolder} onSelectFile={onSelectFile} />)}
        </div>
      )}
    </div>
  )
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true" style={{ flexShrink: 0, transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}><path d="M4.5 2.5 8 6 4.5 9.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
}

function FolderIcon({ expanded }: { expanded: boolean }) {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ flexShrink: 0, color: '#D59B2B' }}><path d={expanded ? 'M3 7h7l2 2h9l-2 10H5L3 7Z' : 'M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z'} stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg>
}

function FileIcon({ path }: { path: string }) {
  const codeFile = /\.(py|js|jsx|ts|tsx|json|ya?ml|toml)$/i.test(path)
  return codeFile
    ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ flexShrink: 0, color: '#4B78C5' }}><path d="m8 9-3 3 3 3m8-6 3 3-3 3m-2-9-4 12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
    : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ flexShrink: 0, color: '#718096' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" stroke="currentColor" strokeWidth="1.5"/><path d="M14 2v6h6M8 13h8M8 17h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
}

function McpSection({ title, description, items }: { title: string; description: string; items: McpCapability[] }) {
  if (items.length === 0) return null
  return <section style={{ marginBottom: 22 }}><div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 9 }}><h3 style={{ fontSize: 14, color: 'var(--text-primary)' }}>{title}</h3><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{description} · {items.length}</span></div><div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{items.map(capability => <div key={capability.name} style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 7 }}><code style={{ fontSize: 12, color: 'var(--action)' }}>{capability.name}</code><div style={{ marginTop: 5, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{capability.description}</div></div>)}</div></section>
}

function FormField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <div style={{ marginBottom: 16 }}><label style={labelStyle}>{label} <span style={{ color: '#DC2626' }}>*</span></label><input value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={inputStyle} /></div>
}

function FormTextArea({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <div style={{ marginBottom: 16 }}><label style={labelStyle}>{label} <span style={{ color: '#DC2626' }}>*</span></label><textarea value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={{ ...inputStyle, minHeight: 86, resize: 'vertical' }} /></div>
}

const eyebrowStyle: React.CSSProperties = { fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }
const headerActionStyle: React.CSSProperties = { padding: '9px 18px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }
const backdropStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 300 }
const modalStyle: React.CSSProperties = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 520, maxHeight: 'calc(100vh - 64px)', overflowY: 'auto', padding: 30, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: '0 20px 60px rgba(11,46,92,0.2)', zIndex: 301 }
const modalNoticeStyle: React.CSSProperties = { marginBottom: 18, padding: '10px 12px', borderRadius: 7, background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E', fontSize: 12, lineHeight: 1.6 }
const closeButtonStyle: React.CSSProperties = { background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit', outline: 'none' }
const primaryButtonStyle: React.CSSProperties = { padding: '9px 20px', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, fontFamily: 'inherit' }
const secondaryButtonStyle: React.CSSProperties = { padding: '9px 18px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }
