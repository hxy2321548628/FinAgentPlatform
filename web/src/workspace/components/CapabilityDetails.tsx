import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { ChevronDown, ChevronRight, FileText, Folder } from 'lucide-react'
import { ApiError, errorMessage } from '../../api/request'
import type { McpServer, SkillFileContent, SkillFileEntry } from '../../api/types'
import { CodeSurface } from './CodeSurface'
import { highlightCode, languageForPath, languageLabel } from './codeHighlight'

export function CatalogDrawer({ title, subtitle, onClose, children, wide = false }: {
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  return (
    <Dialog.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" onClick={onClose} />
        <Dialog.Content className={`dialog-content dialog-drawer${wide ? ' skill-browser-drawer' : ''}`} aria-describedby={undefined}>
          <div className="dialog-drawer-header">
            <div className="catalog-drawer-heading">
              <Dialog.Title className="dialog-title" style={{ marginBottom: 0 }}>{title}</Dialog.Title>
              {subtitle && <div className="catalog-drawer-subtitle">{subtitle}</div>}
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="关闭" className="dialog-close-x catalog-drawer-close">×</button>
            </Dialog.Close>
          </div>
          <div className={`dialog-drawer-body${wide ? ' skill-browser-drawer-body' : ''}`}>{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function SkillVersionDrawer({ title, subtitle, description, fileCount, totalBytes, callCount, cacheKey, loadFiles, loadFile, context, action, onClose }: {
  title: string
  subtitle: string
  description: string
  fileCount: number
  totalBytes: number
  callCount?: number
  cacheKey: readonly unknown[]
  loadFiles: () => Promise<SkillFileEntry[]>
  loadFile: (path: string) => Promise<SkillFileContent>
  context?: ReactNode
  action?: ReactNode
  onClose: () => void
}) {
  const files = useQuery({ queryKey: [...cacheKey, 'files'], queryFn: loadFiles })
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  useEffect(() => {
    if (!files.data?.length) return
    setSelectedPath(current => current && files.data.some(file => file.path === current)
      ? current
      : files.data.find(file => file.path === 'SKILL.md')?.path ?? files.data[0].path)
  }, [files.data])
  const content = useQuery({
    queryKey: [...cacheKey, 'file', selectedPath ?? ''],
    queryFn: () => loadFile(selectedPath ?? ''),
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
    <CatalogDrawer wide title={title} subtitle={subtitle} onClose={onClose}>
      <div className="skill-browser-summary">
        <div>
          <div style={sectionTitle}>功能描述</div>
          <p className="catalog-detail-description">{description || '（作者没有写说明）'}</p>
        </div>
        <div className="skill-browser-meta">
          <span>{fileCount} 个文件</span>
          <span>{formatBytes(totalBytes)}</span>
          {callCount !== undefined && <span>{callCount} 次调用</span>}
        </div>
        {action}
      </div>
      {context && <div className="catalog-detail-context">{context}</div>}
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
    </CatalogDrawer>
  )
}

export function McpCapabilityDrawer({ item, context, action, onClose }: {
  item: McpServer
  context?: ReactNode
  action?: ReactNode
  onClose: () => void
}) {
  return (
    <CatalogDrawer title={item.name} subtitle={item.url} onClose={onClose}>
      <p className="catalog-detail-description catalog-detail-description--spaced">{item.description || '（申请人没有写说明）'}</p>
      {context && <div className="catalog-detail-context compact">{context}</div>}
      <div className="catalog-detail-info-grid">
        <Info label="传输方式" value={item.transport === 'sse' ? 'SSE' : 'Streamable HTTP'} />
        <Info label="耗时声明" value={item.latency_note || '未声明'} />
        <Info label="是否存储用户数据" value={item.stores_user_data ? '声明会存储' : '声明不存储'} />
        <Info label="是否再转发数据" value={item.sends_data_out ? '声明会转发给第三方' : '声明不转发'} />
        <Info label="平台凭据" value={item.has_credential ? '已配置' : '未配置'} />
        <Info label="写操作" value={item.has_write_operation ? '包含，不可放行' : '不包含'} />
      </div>
      <section>
        <div style={sectionTitle}>Tools（模型可调用的操作）</div>
        <div className="catalog-detail-tools">
          {item.tool_names.map(name => <div key={name}><code>{name}</code></div>)}
        </div>
        <p className="catalog-detail-hint">
          这份清单是上架时记录的。平台装配时会与服务实际返回的工具名比对；与平台内置文件工具重名的外部工具会被剔除。
        </p>
      </section>
      {action && <div className="catalog-detail-action">{action}</div>}
    </CatalogDrawer>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="catalog-detail-info"><span>{label}</span><strong>{value}</strong></div>
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
  return <ul className="skill-file-tree" aria-label="发布版本文件">{roots.map(node => <SkillTreeBranch key={node.path} node={node} depth={0} openDirectories={openDirectories} selectedPath={selectedPath} onToggle={toggle} onSelect={onSelect} />)}</ul>
}

function SkillTreeBranch({ node, depth, openDirectories, selectedPath, onToggle, onSelect }: { node: SkillTreeNode; depth: number; openDirectories: Set<string>; selectedPath: string | null; onToggle: (path: string) => void; onSelect: (path: string) => void }) {
  const directory = node.file === undefined
  const open = directory && openDirectories.has(node.path)
  return (
    <li>
      <button
        type="button"
        className={`skill-tree-row${node.path === selectedPath ? ' active' : ''}`}
        style={{ paddingLeft: 8 + depth * 16 }}
        aria-label={node.name}
        aria-expanded={directory ? open : undefined}
        aria-current={!directory && node.path === selectedPath ? 'true' : undefined}
        onClick={() => directory ? onToggle(node.path) : onSelect(node.path)}
      >
        {directory ? (open ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <span className="skill-tree-spacer" />}
        {directory ? <Folder size={14} /> : <FileText size={14} />}
        <span>{node.name}</span>
      </button>
      {open && <ul className="skill-file-tree-group">{node.children.map(child => <SkillTreeBranch key={child.path} node={child} depth={depth + 1} openDirectories={openDirectories} selectedPath={selectedPath} onToggle={onToggle} onSelect={onSelect} />)}</ul>}
    </li>
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
    nodes.sort((left, right) => Number(left.file !== undefined) - Number(right.file !== undefined) || left.name.localeCompare(right.name, 'zh-CN'))
    nodes.forEach(node => sort(node.children))
  }
  sort(roots)
  return roots
}

function parentPaths(path: string): string[] {
  const parts = path.split('/')
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'))
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

const sectionTitle: React.CSSProperties = { fontSize: 12, fontWeight: 650, color: 'var(--text-primary)', marginBottom: 8 }
