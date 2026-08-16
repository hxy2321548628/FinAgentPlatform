import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { applyForMcp, listCatalog as listMcpCatalog, mcpKeys } from '../../api/mcp'
import { ApiError, errorMessage } from '../../api/request'
import { listCatalog, listVersionFiles, readVersionFile, skillKeys } from '../../api/skills'
import type { McpServer, SkillFileEntry, SkillListing } from '../../api/types'
import { CatalogCard, CatalogControls, type CatalogFilter } from '../components/Catalog'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'
import { handOffConfig } from '../pickedAgent'
import { CodeSurface } from '../components/CodeSurface'
import { highlightCode, languageForPath, languageLabel } from '../components/codeHighlight'
import { ChevronDown, ChevronRight, FileText, Folder } from 'lucide-react'

export function SkillsLibrary() {
  const catalog = useQuery({ queryKey: skillKeys.catalog(), queryFn: listCatalog })
  const navigate = useNavigate()
  const handleUseSkill = (skillId: string) => { handOffConfig({ skills: [skillId] }); navigate('/workspace/chat') }
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
      <CatalogControls search={search} onSearch={setSearch} placeholder="搜索 Skill 名称、描述或作者…" filters={filters} activeFilter={activeFilter} onFilter={setActiveFilter} />
      {catalog.isPending && <Notice>正在加载 Skills…</Notice>}
      {catalog.isError && <Notice error>{errorMessage(catalog.error)}</Notice>}
      {!catalog.isPending && !catalog.isError && <SkillCards items={filtered} search={search} onSelect={setSelected} onUse={handleUseSkill} />}
      {selected && <SkillDetail item={selected} onUse={() => handleUseSkill(selected.id)} onClose={() => setSelected(null)} />}
    </LibraryPage>
  )
}

function SkillCards({ items, search, onSelect, onUse }: { items: SkillListing[]; search: string; onSelect: (item: SkillListing) => void; onUse: (skillId: string) => void }) {
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
            primaryAction={{ label: '使用 Skill', onClick: () => onUse(item.id) }}
          />
        ))}
      </div>
      <div style={countStyle}>共 {items.length} 个目录项</div>
    </div>
  )
}

/** 右侧抽屉（DSD 第二章 §2.7 的抽屉变体）：Radix Dialog 承担焦点陷阱/Esc/aria-modal。 */
function Drawer({ title, subtitle, onClose, children, wide = false }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <Dialog.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" onClick={onClose} />
        <Dialog.Content className={`dialog-content dialog-drawer${wide ? ' skill-browser-drawer' : ''}`} aria-describedby={undefined}>
          <div className="dialog-drawer-header">
            <Dialog.Title className="dialog-title" style={{ marginBottom: 0 }}>
              {title}
              {subtitle && <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginTop: 3 }}>{subtitle}</div>}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button aria-label="关闭" className="dialog-close-x" style={{ position: 'static' }}>×</button>
            </Dialog.Close>
          </div>
          <div className={`dialog-drawer-body${wide ? ' skill-browser-drawer-body' : ''}`}>{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function SkillDetail({ item, onUse, onClose }: { item: SkillListing; onUse: () => void; onClose: () => void }) {
  const files = useQuery({
    queryKey: skillKeys.files(item.id, item.version),
    queryFn: () => listVersionFiles(item.id, item.version),
  })
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  useEffect(() => {
    if (!files.data?.length) return
    setSelectedPath(current => current && files.data.some(file => file.path === current)
      ? current
      : files.data.find(file => file.path === 'SKILL.md')?.path ?? files.data[0].path)
  }, [files.data])
  const content = useQuery({
    queryKey: skillKeys.file(item.id, item.version, selectedPath ?? ''),
    queryFn: () => readVersionFile(item.id, item.version, selectedPath ?? ''),
    enabled: selectedPath !== null,
  })
  const previewText = content.data && !content.data.is_binary ? content.data.content : null
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null)
  useEffect(() => {
    if (!selectedPath || previewText === null) {
      setHighlightedHtml(null)
      return
    }
    const language = languageForPath(selectedPath)
    if (!language) {
      setHighlightedHtml(null)
      return
    }
    let cancelled = false
    setHighlightedHtml(null)
    void highlightCode(previewText, language).then(result => {
      if (!cancelled) setHighlightedHtml(result)
    })
    return () => { cancelled = true }
  }, [previewText, selectedPath])

  return (
    <Drawer wide title={item.name} subtitle={`${item.owner_name} · ${item.subject || '未分类'} · v${item.version}`} onClose={onClose}>
      <div className="skill-browser-summary">
        <div>
          <div style={sectionTitle}>功能描述</div>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{item.description || '（作者没有写说明）'}</p>
        </div>
        <div className="skill-browser-meta">
          <span>{item.file_count} 个文件</span><span>{formatBytes(item.total_bytes)}</span><span>{item.call_count} 次调用</span>
        </div>
        <Button onClick={onUse}>使用 Skill</Button>
      </div>
      <div className="skill-browser-workbench">
        <aside className="skill-browser-tree-panel">
          <div className="skill-browser-panel-title">发布版本文件</div>
          {files.isPending && <div className="skill-browser-state">正在读取文件清单…</div>}
          {files.isError && <div className="skill-browser-state error">{skillBrowserErrorMessage(files.error)}</div>}
          {files.data && files.data.length === 0 && <div className="skill-browser-state">该版本没有可预览文件</div>}
          {files.data && files.data.length > 0 && <SkillFileTree files={files.data} selectedPath={selectedPath} onSelect={setSelectedPath} />}
        </aside>
        <section className="skill-browser-preview">
          <div className="skill-browser-preview-header">
            <FileText size={14} strokeWidth={1.8} />
            <span>{selectedPath ?? '选择一个文件'}</span>
            <span className="skill-browser-readonly">只读</span>
          </div>
          <div className={`skill-browser-preview-body${previewText !== null ? ' code' : ''}`}>
            {!selectedPath && <div className="skill-browser-state">从左侧选择文件查看内容</div>}
            {content.isPending && selectedPath && <div className="skill-browser-state">正在读取文件…</div>}
            {content.isError && <div className="skill-browser-state error">{errorMessage(content.error)}</div>}
            {content.data?.is_binary && <div className="skill-browser-state">该文件无法进行文本预览。</div>}
            {previewText !== null && <CodeSurface path={selectedPath ?? ''} value={previewText} highlightedHtml={highlightedHtml} />}
          </div>
          {previewText !== null && selectedPath && (
            <div className="workspace-editor-status">
              <span>{languageLabel(selectedPath)}</span><span>UTF-8</span><span>{previewText.split('\n').length} 行</span><span>只读预览</span>
            </div>
          )}
        </section>
      </div>
    </Drawer>
  )
}

function skillBrowserErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404 && error.message === 'Not Found') {
    return '文件浏览服务尚未加载，请刷新页面后重试'
  }
  return errorMessage(error)
}

interface SkillTreeNode {
  name: string
  path: string
  file?: SkillFileEntry
  children: SkillTreeNode[]
}

function SkillFileTree({ files, selectedPath, onSelect }: { files: SkillFileEntry[]; selectedPath: string | null; onSelect: (path: string) => void }) {
  const roots = useMemo(() => buildSkillTree(files), [files])
  const [openDirectories, setOpenDirectories] = useState(() => new Set(files.flatMap(file => parentPaths(file.path))))
  const toggle = (path: string) => setOpenDirectories(current => {
    const next = new Set(current)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    return next
  })
  return <div className="skill-file-tree" role="tree">{roots.map(node => <SkillTreeBranch key={node.path} node={node} depth={0} openDirectories={openDirectories} selectedPath={selectedPath} onToggle={toggle} onSelect={onSelect} />)}</div>
}

function SkillTreeBranch({ node, depth, openDirectories, selectedPath, onToggle, onSelect }: { node: SkillTreeNode; depth: number; openDirectories: Set<string>; selectedPath: string | null; onToggle: (path: string) => void; onSelect: (path: string) => void }) {
  const directory = node.file === undefined
  const open = directory && openDirectories.has(node.path)
  return (
    <div role="treeitem" aria-expanded={directory ? open : undefined}>
      <button
        type="button"
        className={`skill-tree-row${node.path === selectedPath ? ' active' : ''}`}
        style={{ paddingLeft: 8 + depth * 16 }}
        aria-label={node.name}
        onClick={() => directory ? onToggle(node.path) : onSelect(node.path)}
      >
        {directory ? (open ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <span className="skill-tree-spacer" />}
        {directory ? <Folder size={14} /> : <FileText size={14} />}
        <span>{node.name}</span>
      </button>
      {open && node.children.map(child => <SkillTreeBranch key={child.path} node={child} depth={depth + 1} openDirectories={openDirectories} selectedPath={selectedPath} onToggle={onToggle} onSelect={onSelect} />)}
    </div>
  )
}

function buildSkillTree(files: SkillFileEntry[]): SkillTreeNode[] {
  const roots: SkillTreeNode[] = []
  for (const file of files) {
    let children = roots
    const parts = file.path.split('/')
    let path = ''
    parts.forEach((name, index) => {
      path = path ? `${path}/${name}` : name
      let node = children.find(item => item.name === name)
      if (!node) {
        node = { name, path, children: [], file: index === parts.length - 1 ? file : undefined }
        children.push(node)
      }
      children = node.children
    })
  }
  const sort = (nodes: SkillTreeNode[]) => {
    nodes.sort((a, b) => Number(a.file !== undefined) - Number(b.file !== undefined) || a.name.localeCompare(b.name, 'zh-CN'))
    nodes.forEach(node => sort(node.children))
  }
  sort(roots)
  return roots
}

function parentPaths(path: string): string[] {
  const parts = path.split('/')
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'))
}

function Info({ label, value }: { label: string; value: string }) {
  return <div style={{ padding: '12px 14px', border: '1px solid var(--border)', borderRadius: 7 }}><div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div><div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div></div>
}

export function McpLibrary() {
  const catalog = useQuery({ queryKey: mcpKeys.catalog(), queryFn: listMcpCatalog })
  const navigate = useNavigate()
  const handleUseMcp = (serverId: string) => { handOffConfig({ mcps: [serverId] }); navigate('/workspace/chat') }
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<McpServer | null>(null)
  const [applying, setApplying] = useState(false)
  const items = [...(catalog.data ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  const normalized = search.trim().toLocaleLowerCase('zh-CN')
  const filtered = items.filter(item => {
    const haystack = `${item.name} ${item.description} ${item.tool_names.join(' ')}`.toLocaleLowerCase('zh-CN')
    return !normalized || haystack.includes(normalized)
  })

  return (
    <LibraryPage eyebrow="// MCP LIBRARY" title="MCP 库" description={`浏览管理员放行的外部 MCP Server，共 ${items.length} 个目录项`}>
      {/* <div style={{ padding: '0 36px' }}> */}
      {/* </div> */}
      <CatalogControls search={search} onSearch={setSearch} placeholder="搜索 MCP Server 名称、描述或工具名…" filters={[]} activeFilter="" onFilter={() => undefined} />
      <div style={{ padding: '0 36px 12px' }}>
        <button type="button" onClick={() => setApplying(true)} style={applyButtonStyle}>申请添加 MCP</button>
      </div>
      {catalog.isPending && <Notice>正在加载 MCP 目录…</Notice>}
      {catalog.isError && <Notice error>{errorMessage(catalog.error)}</Notice>}
      {!catalog.isPending && !catalog.isError && (filtered.length === 0
        ? <Notice>{search ? `未找到与「${search}」相关的 MCP Server` : '还没有放行的 MCP Server。可以先提一份申请。'}</Notice>
        : (
          <div style={{ padding: '0 36px 32px' }}>
            <div style={gridStyle}>
              {filtered.map(item => (
                <CatalogCard
                  key={item.id}
                  title={item.name}
                  author={item.has_credential ? '平台已配置凭据' : '无需凭据'}
                  subject="外部服务"
                  description={item.description}
                  detail={`${item.tool_names.length} 个工具 · ${item.latency_note || '未声明耗时'}`}
                  badges={item.tool_names.slice(0, 3)}
                  metric="校外"
                  secondaryAction={{ label: '查看 MCP 能力', onClick: () => setSelected(item) }}
                  primaryAction={{ label: '使用 MCP', onClick: () => handleUseMcp(item.id) }}
                />
              ))}
            </div>
            <div style={countStyle}>共 {filtered.length} 个目录项</div>
          </div>
        ))}
      {selected && <McpDetail item={selected} onUse={() => handleUseMcp(selected.id)} onClose={() => setSelected(null)} />}
      {applying && <McpApplyDialog onClose={() => setApplying(false)} />}
    </LibraryPage>
  )
}

function McpDetail({ item, onUse, onClose }: { item: McpServer; onUse: () => void; onClose: () => void }) {
  return (
    <Drawer title={item.name} subtitle={item.url} onClose={onClose}>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75, marginBottom: 20 }}>{item.description || '（申请人没有写说明）'}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 20 }}>
        <Info label="传输方式" value={item.transport === 'sse' ? 'SSE' : 'Streamable HTTP'} />
        <Info label="耗时声明" value={item.latency_note || '未声明'} />
        <Info label="是否存储用户数据" value={item.stores_user_data ? '声明会存储' : '声明不存储'} />
        <Info label="是否再转发数据" value={item.sends_data_out ? '声明会转发给第三方' : '声明不转发'} />
      </div>
      <section>
        <div style={sectionTitle}>Tools（模型可调用的操作）</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {item.tool_names.map(name => <div key={name} style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 7 }}><code style={{ fontSize: 12, color: 'var(--action)' }}>{name}</code></div>)}
        </div>
        <p style={{ ...hintTextStyle, marginTop: 10 }}>
          这份清单是**上架时**记下的。平台在每次装配时会拿实际拿到的工具名与它比对，
          不一致只记日志、不拦截 —— 而与平台内置文件工具重名的外部工具一律被剔除。
        </p>
      </section>
      <Button onClick={onUse} style={{ marginTop: 18 }}>使用 MCP 开始分析</Button>
    </Drawer>
  )
}

const EMPTY_APPLICATION = {
  name: '',
  description: '',
  url: '',
  toolNames: '',
  latencyNote: '',
  credentialKey: '',
  storesUserData: false,
  sendsDataOut: true,
  hasWriteOperation: false,
}

function McpApplyDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY_APPLICATION)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const submit = useMutation({
    mutationFn: () => {
      const tools = form.toolNames.split(/[\n,，]/).map(one => one.trim()).filter(Boolean)
      if (!form.name.trim()) throw new Error('请填写服务名')
      if (!/^https?:\/\//.test(form.url.trim())) throw new Error('地址必须是 http:// 或 https:// 开头的完整 URL')
      if (tools.length === 0) throw new Error('请至少填一个工具名')
      return applyForMcp({
        name: form.name.trim(),
        description: form.description.trim(),
        url: form.url.trim(),
        transport: 'streamable_http',
        credential_key: form.credentialKey.trim() || null,
        tool_names: tools,
        latency_note: form.latencyNote.trim(),
        stores_user_data: form.storesUserData,
        sends_data_out: form.sendsDataOut,
        has_write_operation: form.hasWriteOperation,
      })
    },
    async onSuccess() {
      setDone(true)
      setError('')
      await queryClient.invalidateQueries({ queryKey: mcpKeys.all })
    },
    onError(reason) {
      setError(reason instanceof Error ? reason.message : errorMessage(reason, '提交失败'))
    },
  })

  return (
    <Drawer title="申请添加 MCP" onClose={onClose}>
      <p style={{ ...hintTextStyle, marginBottom: 16 }}>
        管理员放行之后全平台都能勾选它。**四项声明请如实填写** —— 声明有写操作的一律不批：
        平台目前既不拦截审批也不传幂等键，而队列是至少一次投递。
      </p>
      <TextField label="服务名" value={form.name} onChange={value => setForm(one => ({ ...one, name: value }))} placeholder="如：校内论文检索" />
      <TextField label="一句话说明" value={form.description} onChange={value => setForm(one => ({ ...one, description: value }))} placeholder="它能做什么" />
      <TextField label="地址" value={form.url} onChange={value => setForm(one => ({ ...one, url: value }))} placeholder="https://mcp.example.edu/mcp" />
      <TextField label="工具清单" value={form.toolNames} onChange={value => setForm(one => ({ ...one, toolNames: value }))} placeholder="一行一个，或用逗号分隔" multiline />
      <TextField label="耗时声明" value={form.latencyNote} onChange={value => setForm(one => ({ ...one, latencyNote: value }))} placeholder="典型 1 秒，最坏 10 秒" />
      <TextField label="凭据键名（可选）" value={form.credentialKey} onChange={value => setForm(one => ({ ...one, credentialKey: value }))} placeholder="值由管理员写进 .env，不要填在这里" />
      <CheckField label="会存储用户数据" checked={form.storesUserData} onChange={value => setForm(one => ({ ...one, storesUserData: value }))} />
      <CheckField label="会把数据再转发给第三方" checked={form.sendsDataOut} onChange={value => setForm(one => ({ ...one, sendsDataOut: value }))} />
      <CheckField label="工具里有写操作（写库、发消息、扣费）" checked={form.hasWriteOperation} onChange={value => setForm(one => ({ ...one, hasWriteOperation: value }))} />
      {error && <div role="alert" style={{ margin: '10px 0', color: 'var(--danger)', fontSize: 12 }}>{error}</div>}
      {done && <div role="status" style={{ margin: '10px 0', color: 'var(--status-done)', fontSize: 12 }}>已提交，等待管理员放行</div>}
      <Button disabled={submit.isPending || done} onClick={() => submit.mutate()}>{submit.isPending ? '提交中…' : '提交申请'}</Button>
    </Drawer>
  )
}

function TextField({ label, value, onChange, placeholder, multiline = false }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; multiline?: boolean }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <span style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 5 }}>{label}</span>
      {multiline
        ? <textarea value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={{ ...fieldStyle, minHeight: 72, resize: 'vertical' }} />
        : <input value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={fieldStyle} />}
    </label>
  )
}

function CheckField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label style={{ display: 'flex', gap: 7, alignItems: 'center', marginBottom: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
      <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} />
      {label}
    </label>
  )
}

function LibraryPage({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0' }}>
        <div className="page-eyebrow">{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{description}</p>
      </div>
      {children}
    </div>
  )
}

function Notice({ error = false, children }: { error?: boolean; children: React.ReactNode }) {
  return <div role={error ? 'alert' : undefined} style={{ padding: '60px 36px', textAlign: 'center', color: error ? 'var(--danger)' : 'var(--text-muted)', fontSize: 14 }}>{children}</div>
}

function sourceLabel(source: SkillListing['source']): string {
  return source === 'owned' ? '我创建的' : source === 'group' ? '组内共享' : '平台目录'
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

const sectionTitle: React.CSSProperties = { fontSize: 12, fontWeight: 650, color: 'var(--text-primary)', marginBottom: 8 }
const gridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }
const countStyle: React.CSSProperties = { padding: '20px 0 0', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }
const applyButtonStyle: React.CSSProperties = { padding: '8px 14px', border: '1px solid var(--action-border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--action)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }
const fieldStyle: React.CSSProperties = { width: '100%', padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: 'var(--input-bg)', color: 'var(--text-primary)', boxSizing: 'border-box' }
const hintTextStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7 }
