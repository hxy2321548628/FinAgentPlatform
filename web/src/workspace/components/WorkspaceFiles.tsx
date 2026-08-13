import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface WorkspaceEntry {
  path: string
  is_dir: boolean
  size: number
  modified_at: string | null
}

interface FilePreview {
  path: string
  text: string
  isBinary: boolean
  rawUrl: string
}

interface WorkspaceFilesProps {
  threadId: string
  title?: string
  compact?: boolean
}

const FALLBACK_ENTRIES: WorkspaceEntry[] = [
  { path: 'inputs', is_dir: true, size: 0, modified_at: null },
  { path: 'inputs/portfolio_2026Q2.csv', is_dir: false, size: 1_258_291, modified_at: '2026-08-06T06:32:00Z' },
  { path: 'volatility_analysis.py', is_dir: false, size: 2_146, modified_at: '2026-08-06T06:35:00Z' },
  { path: 'outputs', is_dir: true, size: 0, modified_at: null },
  { path: 'outputs/volatility_chart.png', is_dir: false, size: 86_016, modified_at: '2026-08-06T06:36:00Z' },
  { path: 'outputs/rebalance_plan.csv', is_dir: false, size: 18_432, modified_at: '2026-08-06T06:36:00Z' },
]

const TEXT_EXTENSIONS = new Set(['csv', 'json', 'md', 'py', 'txt', 'yaml', 'yml', 'toml', 'log', 'sql', 'ts', 'tsx', 'js', 'jsx'])
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'])

function fileName(path: string) {
  return path.split('/').at(-1) ?? path
}

function directoryName(path: string) {
  const parts = path.split('/')
  parts.pop()
  return parts.join('/')
}

function extension(path: string) {
  return fileName(path).split('.').at(-1)?.toLowerCase() ?? ''
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function rawFileUrl(threadId: string, path: string, download = false) {
  const query = new URLSearchParams({ path, download: String(download) })
  return `/api/threads/${encodeURIComponent(threadId)}/files/raw?${query}`
}

function fallbackText(path: string) {
  if (path.endsWith('.csv')) return 'industry,weight,annual_volatility\n科技,0.183,0.312\n能源,0.124,0.241\n材料,0.051,0.228\n'
  if (path.endsWith('.py')) return '# 波动率分析脚本\nimport pandas as pd\n\nportfolio = pd.read_csv("inputs/portfolio_2026Q2.csv")\n'
  return `# ${fileName(path)}\n\n当前展示的是原型数据。连接 API 后将读取 thread ${path} 的真实文件内容。`
}

function EntryIcon({ entry }: { entry: WorkspaceEntry }) {
  if (entry.is_dir) {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
  }
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
}

export function WorkspaceFiles({ threadId, title, compact = false }: WorkspaceFilesProps) {
  const [entries, setEntries] = useState<WorkspaceEntry[]>(FALLBACK_ENTRIES)
  const [currentDir, setCurrentDir] = useState('')
  const [preview, setPreview] = useState<FilePreview | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [usingFallback, setUsingFallback] = useState(false)
  const uploadRef = useRef<HTMLInputElement>(null)

  const loadEntries = useCallback(async () => {
    try {
      const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/files`, { credentials: 'include' })
      if (!response.ok) throw new Error('工作目录读取失败')
      const body = await response.json() as { entries: WorkspaceEntry[] }
      setEntries(body.entries)
      setUsingFallback(false)
    } catch {
      setEntries(FALLBACK_ENTRIES)
      setUsingFallback(true)
    }
  }, [threadId])

  useEffect(() => {
    setCurrentDir('')
    setPreview(null)
    setEditing(false)
    void loadEntries()
  }, [loadEntries])

  const visibleEntries = useMemo(() => entries.filter(entry => {
    const parent = directoryName(entry.path)
    return parent === currentDir
  }).sort((a, b) => Number(b.is_dir) - Number(a.is_dir) || a.path.localeCompare(b.path, 'zh-CN')), [currentDir, entries])

  const openFile = async (entry: WorkspaceEntry) => {
    if (entry.is_dir) {
      setCurrentDir(entry.path)
      setPreview(null)
      setEditing(false)
      return
    }

    const ext = extension(entry.path)
    const rawUrl = rawFileUrl(threadId, entry.path)
    if (IMAGE_EXTENSIONS.has(ext)) {
      setPreview({ path: entry.path, text: '', isBinary: true, rawUrl })
      setEditing(false)
      return
    }

    if (!TEXT_EXTENSIONS.has(ext)) {
      setPreview({ path: entry.path, text: '', isBinary: true, rawUrl })
      setEditing(false)
      return
    }

    try {
      const query = new URLSearchParams({ path: entry.path })
      const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/files/content?${query}`, { credentials: 'include' })
      if (!response.ok) throw new Error('文件预览失败')
      const body = await response.json() as { text: string; is_binary: boolean }
      const next = { path: entry.path, text: body.text, isBinary: body.is_binary, rawUrl }
      setPreview(next)
      setDraft(body.text)
    } catch {
      const text = fallbackText(entry.path)
      setPreview({ path: entry.path, text, isBinary: false, rawUrl })
      setDraft(text)
    }
    setEditing(false)
  }

  const uploadFiles = async (files: FileList | File[], directory = currentDir) => {
    setBusy(true)
    setNotice('')
    try {
      for (const file of Array.from(files)) {
        if (usingFallback) {
          const path = directory ? `${directory}/${file.name}` : file.name
          setEntries(previous => [...previous.filter(entry => entry.path !== path), { path, is_dir: false, size: file.size, modified_at: new Date().toISOString() }])
          continue
        }
        const form = new FormData()
        form.append('file', file)
        form.append('directory', directory)
        const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/files`, { method: 'POST', body: form, credentials: 'include' })
        if (!response.ok) throw new Error(`上传失败：${file.name}`)
      }
      setNotice('文件已上传')
      if (!usingFallback) await loadEntries()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '上传失败')
    } finally {
      setBusy(false)
      if (uploadRef.current) uploadRef.current.value = ''
    }
  }

  const saveFile = async () => {
    if (!preview) return
    const blob = new File([draft], fileName(preview.path), { type: 'text/plain;charset=utf-8' })
    await uploadFiles([blob], directoryName(preview.path))
    setPreview({ ...preview, text: draft })
    setEditing(false)
  }

  const deleteFile = async (path: string) => {
    if (!window.confirm(`确认删除 ${path}？此操作不可撤销。`)) return
    setBusy(true)
    setNotice('')
    try {
      if (!usingFallback) {
        const query = new URLSearchParams({ path })
        const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/files?${query}`, { method: 'DELETE', credentials: 'include' })
        if (!response.ok) throw new Error('删除失败')
        await loadEntries()
      } else {
        setEntries(previous => previous.filter(entry => entry.path !== path))
      }
      if (preview?.path === path) setPreview(null)
      setNotice('文件已删除')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  const copyPath = async (path: string) => {
    await navigator.clipboard.writeText(`/workspace/${path}`)
    setNotice('已复制工作路径')
  }

  const crumbs = currentDir ? currentDir.split('/') : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: compact ? 0 : 560, background: 'var(--surface)', overflow: 'hidden' }}>
      <div style={{ padding: compact ? '12px 14px' : '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.16em', color: 'var(--text-muted)' }}>THREAD WORKSPACE</div>
          <div style={{ fontSize: compact ? 12 : 13, color: 'var(--text-primary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title ?? '工作目录'}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <input ref={uploadRef} type="file" multiple style={{ display: 'none' }} onChange={event => event.target.files && void uploadFiles(event.target.files)} />
          <button type="button" disabled={busy} onClick={() => uploadRef.current?.click()} style={{ padding: '6px 10px', border: 'none', borderRadius: 6, background: 'var(--action)', color: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>上传</button>
          <button type="button" onClick={() => void loadEntries()} title="刷新" style={{ width: 30, border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>↻</button>
        </div>
      </div>

      <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 5, minHeight: 38, fontSize: 11, color: 'var(--text-muted)', overflowX: 'auto' }}>
        <button type="button" onClick={() => { setCurrentDir(''); setPreview(null) }} style={{ border: 'none', background: 'none', color: currentDir ? 'var(--action)' : 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11 }}>/workspace</button>
        {crumbs.map((crumb, index) => {
          const path = crumbs.slice(0, index + 1).join('/')
          return <span key={path} style={{ display: 'inline-flex', gap: 5 }}><span>/</span><button type="button" onClick={() => { setCurrentDir(path); setPreview(null) }} style={{ border: 'none', background: 'none', color: index === crumbs.length - 1 ? 'var(--text-primary)' : 'var(--action)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11 }}>{crumb}</button></span>
        })}
      </div>

      <div style={{ flex: preview ? '0 0 auto' : 1, maxHeight: preview ? (compact ? 250 : 300) : undefined, overflowY: 'auto' }}>
        {currentDir && (
          <button type="button" onClick={() => { setCurrentDir(directoryName(currentDir)); setPreview(null) }} style={{ width: '100%', padding: '9px 14px', border: 'none', borderBottom: '1px solid var(--border-light)', background: 'transparent', color: 'var(--text-secondary)', textAlign: 'left', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>← 返回上一级</button>
        )}
        {visibleEntries.length === 0 ? (
          <div style={{ padding: 28, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>目录为空，可上传文件到这里</div>
        ) : visibleEntries.map(entry => (
          <div key={entry.path} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: compact ? '9px 12px' : '11px 16px', borderBottom: '1px solid var(--border-light)', background: preview?.path === entry.path ? 'var(--action-light)' : 'transparent' }}>
            <button type="button" onClick={() => void openFile(entry)} style={{ minWidth: 0, flex: 1, display: 'flex', alignItems: 'center', gap: 9, border: 'none', background: 'none', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', color: entry.is_dir ? 'var(--action)' : 'var(--text-primary)' }}>
              <span style={{ display: 'flex', flexShrink: 0 }}><EntryIcon entry={entry} /></span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span style={{ display: 'block', fontSize: 12, fontWeight: entry.is_dir ? 600 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fileName(entry.path)}</span>
                {!entry.is_dir && <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{formatSize(entry.size)}</span>}
              </span>
            </button>
            {!entry.is_dir && (
              <div style={{ display: 'flex', gap: 3, flexShrink: 0 }}>
                <button type="button" title="复制路径" onClick={() => void copyPath(entry.path)} style={iconButtonStyle}>复制</button>
                <a title="下载" href={rawFileUrl(threadId, entry.path, true)} style={{ ...iconButtonStyle, textDecoration: 'none' }}>下载</a>
                <button type="button" title="删除" disabled={busy} onClick={() => void deleteFile(entry.path)} style={{ ...iconButtonStyle, color: '#DC2626' }}>删除</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {preview && (
        <div style={{ flex: 1, minHeight: compact ? 220 : 300, borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 6, borderBottom: '1px solid var(--border-light)', background: 'var(--bg)' }}>
            <span style={{ flex: 1, minWidth: 0, fontSize: 11, fontFamily: "'JetBrains Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{preview.path}</span>
            {!preview.isBinary && !editing && <button type="button" onClick={() => { setDraft(preview.text); setEditing(true) }} style={smallButtonStyle}>编辑</button>}
            {editing && <><button type="button" disabled={busy} onClick={() => void saveFile()} style={{ ...smallButtonStyle, background: 'var(--action)', color: '#fff', borderColor: 'var(--action)' }}>保存</button><button type="button" onClick={() => setEditing(false)} style={smallButtonStyle}>取消</button></>}
            <button type="button" onClick={() => { setPreview(null); setEditing(false) }} style={smallButtonStyle}>关闭</button>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: 12, background: '#F8FAFD' }}>
            {editing ? (
              <textarea value={draft} onChange={event => setDraft(event.target.value)} style={{ width: '100%', height: '100%', minHeight: 220, resize: 'none', border: '1px solid var(--border)', borderRadius: 6, padding: 12, outline: 'none', fontSize: 12, lineHeight: 1.65, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-primary)', background: 'var(--surface)' }} />
            ) : IMAGE_EXTENSIONS.has(extension(preview.path)) ? (
              <img src={preview.rawUrl} alt={fileName(preview.path)} style={{ display: 'block', maxWidth: '100%', maxHeight: 360, margin: '0 auto', objectFit: 'contain' }} />
            ) : preview.isBinary ? (
              <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>该文件不支持文本预览，请点击“下载”查看。</div>
            ) : (
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11, lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{preview.text}</pre>
            )}
          </div>
        </div>
      )}

      {notice && <div style={{ padding: '7px 12px', borderTop: '1px solid var(--border-light)', fontSize: 11, color: notice.includes('失败') ? '#DC2626' : 'var(--status-done)', background: 'var(--surface)' }}>{notice}</div>}
    </div>
  )
}

const iconButtonStyle: React.CSSProperties = {
  padding: '3px 5px', border: 'none', background: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 10, fontFamily: 'inherit', borderRadius: 4,
}

const smallButtonStyle: React.CSSProperties = {
  padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 10, fontFamily: 'inherit',
}
