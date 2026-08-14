import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteFile as removeFile, fileKeys, listFiles, rawFileUrl, readFile, uploadFile } from '../../api/files'
import { errorMessage } from '../../api/request'
import type { WorkspaceEntry } from '../../api/types'

interface FilePreview {
  path: string
  text: string
  isBinary: boolean
  truncated: boolean
  rawUrl: string
}

interface WorkspaceFilesProps {
  threadId: string
  title?: string
  compact?: boolean
}

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'])
const EMPTY_ENTRIES: WorkspaceEntry[] = []

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

function EntryIcon({ entry }: { entry: WorkspaceEntry }) {
  if (entry.is_dir) {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
  }
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
}

export function WorkspaceFiles({ threadId, title, compact = false }: WorkspaceFilesProps) {
  const queryClient = useQueryClient()
  const tree = useQuery({ queryKey: fileKeys.tree(threadId), queryFn: () => listFiles(threadId) })
  const entries = tree.data?.entries ?? EMPTY_ENTRIES
  const [currentDir, setCurrentDir] = useState('')
  const [preview, setPreview] = useState<FilePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const uploadRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setCurrentDir('')
    setPreview(null)
    setNotice('')
  }, [threadId])

  const visibleEntries = useMemo(() => entries.filter(entry => {
    const parent = directoryName(entry.path)
    return parent === currentDir
  }).sort((a, b) => Number(b.is_dir) - Number(a.is_dir) || a.path.localeCompare(b.path, 'zh-CN')), [currentDir, entries])

  const openFile = async (entry: WorkspaceEntry) => {
    if (entry.is_dir) {
      setCurrentDir(entry.path)
      setPreview(null)
      return
    }

    const ext = extension(entry.path)
    const rawUrl = rawFileUrl(threadId, entry.path)
    if (IMAGE_EXTENSIONS.has(ext)) {
      setPreview({ path: entry.path, text: '', isBinary: true, truncated: false, rawUrl })
      return
    }

    try {
      const body = await queryClient.fetchQuery({
        queryKey: fileKeys.content(threadId, entry.path),
        queryFn: () => readFile(threadId, entry.path),
      })
      const next = { path: entry.path, text: body.text, isBinary: body.is_binary, truncated: body.truncated, rawUrl }
      setPreview(next)
    } catch (error) {
      setPreview(null)
      setNotice(errorMessage(error, '文件预览失败'))
    }
  }

  const uploadFiles = async (files: FileList | File[], directory = currentDir) => {
    setBusy(true)
    setNotice('')
    try {
      for (const file of Array.from(files)) {
        await uploadFile(threadId, file, directory)
      }
      setNotice('文件已上传')
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '上传失败')
    } finally {
      setBusy(false)
      if (uploadRef.current) uploadRef.current.value = ''
    }
  }

  const deleteFile = async (path: string) => {
    if (!window.confirm(`确认删除 ${path}？此操作不可撤销。`)) return
    setBusy(true)
    setNotice('')
    try {
      await removeFile(threadId, path)
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
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
          <button type="button" onClick={() => void tree.refetch()} title="刷新" style={{ width: 30, border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>↻</button>
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
        {tree.isPending && <div style={{ padding: 28, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>正在加载工作目录…</div>}
        {tree.isError && <div role="alert" style={{ padding: 20, color: '#DC2626', fontSize: 12 }}>{errorMessage(tree.error, '工作目录读取失败')}</div>}
        {tree.data?.truncated && <div style={{ padding: '7px 12px', background: '#FFFBEB', color: '#92400E', fontSize: 11 }}>文件过多，当前只显示部分条目。</div>}
        {currentDir && (
          <button type="button" onClick={() => { setCurrentDir(directoryName(currentDir)); setPreview(null) }} style={{ width: '100%', padding: '9px 14px', border: 'none', borderBottom: '1px solid var(--border-light)', background: 'transparent', color: 'var(--text-secondary)', textAlign: 'left', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>← 返回上一级</button>
        )}
        {!tree.isPending && !tree.isError && visibleEntries.length === 0 ? (
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
            <button type="button" onClick={() => setPreview(null)} style={smallButtonStyle}>关闭</button>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: 12, background: '#F8FAFD' }}>
            {preview.truncated && <div style={{ marginBottom: 10, padding: '7px 9px', borderRadius: 5, background: '#FFFBEB', color: '#92400E', fontSize: 11 }}>文件较长，当前仅展示开头部分；下载可查看完整内容。</div>}
            {IMAGE_EXTENSIONS.has(extension(preview.path)) ? (
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
