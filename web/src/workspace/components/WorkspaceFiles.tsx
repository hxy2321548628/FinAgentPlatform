import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createDirectory, deleteFile as removeFile, fileKeys, listFiles, rawFileUrl, readFile, uploadFile, writeFile } from '../../api/files'
import { errorMessage } from '../../api/request'
import type { WorkspaceEntry } from '../../api/types'
import { ConfirmDialog } from './ConfirmDialog'
import { useToast } from '../../components/ui/toast-context'
import { Button } from '../../components/ui/Button'
import * as Dialog from '@radix-ui/react-dialog'
import { Copy, Download, FilePlus2, FolderPlus, Pencil, RefreshCw, Save, Trash2, Upload, X } from 'lucide-react'

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
  const { toast } = useToast()
  const tree = useQuery({ queryKey: fileKeys.tree(threadId), queryFn: () => listFiles(threadId) })
  const entries = tree.data?.entries ?? EMPTY_ENTRIES
  const [currentDir, setCurrentDir] = useState('')
  const [preview, setPreview] = useState<FilePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editorText, setEditorText] = useState('')
  const [dialog, setDialog] = useState<'file' | 'directory' | null>(null)
  const [dialogName, setDialogName] = useState('')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const uploadRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setCurrentDir('')
    setPreview(null)
    setEditing(false)
    setDialog(null)
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
      setEditorText(body.text)
      setEditing(false)
    } catch (error) {
      setPreview(null)
      toast({ title: '文件预览失败', description: errorMessage(error), variant: 'error' })
    }
  }

  const uploadFiles = async (files: FileList | File[], directory = currentDir) => {
    setBusy(true)
    try {
      for (const file of Array.from(files)) {
        await uploadFile(threadId, file, directory)
      }
      toast({ title: '文件已上传', variant: 'success' })
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
    } catch (error) {
      toast({ title: '上传失败', description: error instanceof Error ? error.message : '请重试', variant: 'error' })
    } finally {
      setBusy(false)
      if (uploadRef.current) uploadRef.current.value = ''
    }
  }

  const deleteFile = async (path: string) => {
    setBusy(true)
    try {
      await removeFile(threadId, path)
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
      if (preview?.path === path) setPreview(null)
      toast({ title: '文件已删除', variant: 'success' })
    } catch (error) {
      toast({ title: '删除失败', description: error instanceof Error ? error.message : '请重试', variant: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const saveEditedFile = async () => {
    if (!preview || preview.isBinary) return
    setBusy(true)
    try {
      await writeFile(threadId, preview.path, editorText)
      setPreview({ ...preview, text: editorText, truncated: false })
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
      await queryClient.invalidateQueries({ queryKey: fileKeys.content(threadId, preview.path) })
      setEditing(false)
      toast({ title: '文件已保存', variant: 'success' })
    } catch (error) {
      toast({ title: '保存失败', description: errorMessage(error), variant: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const createEntry = async () => {
    const name = dialogName.trim()
    if (!name || name.includes('/') || name === '.' || name === '..') {
      toast({ title: '名称不合法', description: '名称不能为空，且不能包含路径分隔符', variant: 'error' })
      return
    }
    const path = currentDir ? `${currentDir}/${name}` : name
    setBusy(true)
    try {
      if (dialog === 'directory') await createDirectory(threadId, path)
      else await writeFile(threadId, path, '')
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
      setDialog(null)
      setDialogName('')
      toast({ title: dialog === 'directory' ? '文件夹已创建' : '文件已创建', variant: 'success' })
    } catch (error) {
      toast({ title: dialog === 'directory' ? '创建文件夹失败' : '创建文件失败', description: errorMessage(error), variant: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const copyPath = async (path: string) => {
    await navigator.clipboard.writeText(`/workspace/${path}`)
    toast({ title: '已复制工作路径', variant: 'success' })
  }

  const crumbs = currentDir ? currentDir.split('/') : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: compact ? 0 : 560, background: 'var(--surface)', overflow: 'hidden' }}>
      <div className="workspace-files-header" style={{ padding: compact ? '14px 16px 12px' : '16px 18px' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.16em', color: 'var(--text-muted)' }}>THREAD WORKSPACE</div>
          <div style={{ marginTop: 4, fontSize: compact ? 13 : 14, color: 'var(--text-primary)', fontWeight: 650, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title ?? '工作目录'}</div>
        </div>
        <div className="workspace-files-actions" role="toolbar" aria-label="工作区文件操作">
          <button type="button" className="workspace-icon-button" disabled={busy} onClick={() => { setDialogName(''); setDialog('file') }} aria-label="新建文件" title="新建文件"><FilePlus2 size={16} strokeWidth={1.8} /></button>
          <button type="button" className="workspace-icon-button" disabled={busy} onClick={() => { setDialogName(''); setDialog('directory') }} aria-label="新建文件夹" title="新建文件夹"><FolderPlus size={16} strokeWidth={1.8} /></button>
          <input ref={uploadRef} type="file" multiple style={{ display: 'none' }} onChange={event => event.target.files && void uploadFiles(event.target.files)} />
          <button type="button" className="workspace-icon-button primary" disabled={busy} onClick={() => uploadRef.current?.click()} aria-label="上传文件" title="上传文件"><Upload size={16} strokeWidth={1.8} /></button>
          <button type="button" className="workspace-icon-button" disabled={tree.isFetching} onClick={() => void tree.refetch()} aria-label="刷新文件列表" title="刷新文件列表"><RefreshCw size={16} strokeWidth={1.8} /></button>
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
        {tree.isError && <div role="alert" style={{ padding: 20, color: 'var(--danger)', fontSize: 12 }}>{errorMessage(tree.error, '工作目录读取失败')}</div>}
        {tree.data?.truncated && <div style={{ padding: '7px 12px', background: 'var(--warn-bg)', color: 'var(--warn)', fontSize: 11 }}>文件过多，当前只显示部分条目。</div>}
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
              <div className="workspace-entry-actions">
                <button type="button" className="workspace-entry-icon" title="复制路径" aria-label={`复制路径：${fileName(entry.path)}`} onClick={() => void copyPath(entry.path)}><Copy size={13} strokeWidth={1.8} /></button>
                <a className="workspace-entry-icon" title="下载" aria-label={`下载：${fileName(entry.path)}`} href={rawFileUrl(threadId, entry.path, true)}><Download size={13} strokeWidth={1.8} /></a>
                <button type="button" className="workspace-entry-icon danger" title="删除" aria-label={`删除：${fileName(entry.path)}`} disabled={busy} onClick={() => setPendingDelete(entry.path)}><Trash2 size={13} strokeWidth={1.8} /></button>
              </div>
            )}
          </div>
        ))}
      </div>

      {preview && (
        <div style={{ flex: 1, minHeight: compact ? 220 : 300, borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 6, borderBottom: '1px solid var(--border-light)', background: 'var(--bg)' }}>
            <span style={{ flex: 1, minWidth: 0, fontSize: 11, fontFamily: "'JetBrains Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{preview.path}</span>
            {!preview.isBinary && <button type="button" className="workspace-entry-icon" disabled={busy} onClick={() => setEditing(value => !value)} aria-label={editing ? '取消编辑' : '编辑文件'} title={editing ? '取消编辑' : '编辑文件'}>{editing ? <X size={13} /> : <Pencil size={13} />}</button>}
            {editing && <button type="button" className="workspace-entry-icon primary" disabled={busy} onClick={() => void saveEditedFile()} aria-label="保存文件" title="保存文件"><Save size={13} /></button>}
            <a className="workspace-entry-icon" href={rawFileUrl(threadId, preview.path, true)} aria-label="下载文件" title="下载文件"><Download size={13} /></a>
            <button type="button" className="workspace-entry-icon" onClick={() => setPreview(null)} aria-label="关闭预览" title="关闭预览"><X size={13} /></button>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: 12, background: 'var(--preview-bg, #F8FAFD)' }}>
            {preview.truncated && <div style={{ marginBottom: 10, padding: '7px 9px', borderRadius: 5, background: 'var(--warn-bg)', color: 'var(--warn)', fontSize: 11 }}>文件较长，当前仅展示开头部分；下载可查看完整内容。</div>}
            {IMAGE_EXTENSIONS.has(extension(preview.path)) ? (
              <img src={preview.rawUrl} alt={fileName(preview.path)} width="100%" height="240" style={{ display: 'block', maxWidth: '100%', height: 240, width: '100%', margin: '0 auto', objectFit: 'contain' }} />
            ) : preview.isBinary ? (
              <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>该文件不支持文本预览，请点击“下载”查看。</div>
            ) : editing ? (
              <textarea value={editorText} onChange={event => setEditorText(event.target.value)} style={{ width: '100%', minHeight: 240, resize: 'vertical', border: '1px solid var(--border)', borderRadius: 6, padding: 10, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 11, lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace", boxSizing: 'border-box' }} aria-label="文件内容编辑器" />
            ) : (
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11, lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{preview.text}</pre>
            )}
          </div>
        </div>
      )}

      <Dialog.Root open={dialog !== null} onOpenChange={open => {
        if (!open) setDialog(null)
      }}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" onClick={() => setDialog(null)} />
          <Dialog.Content className="dialog-content" style={{ width: 'min(360px, 100%)' }} aria-describedby={undefined}>
            <Dialog.Title className="dialog-title">{dialog === 'directory' ? '新建文件夹' : '新建文件'}</Dialog.Title>
            <form onSubmit={event => { event.preventDefault(); void createEntry() }}>
              <input autoFocus value={dialogName} onChange={event => setDialogName(event.target.value)} placeholder={dialog === 'directory' ? '文件夹名称' : '文件名，例如 analysis.py'} aria-label="名称" style={{ width: '100%', boxSizing: 'border-box', padding: '9px 10px', border: '1px solid var(--border)', borderRadius: 6, fontFamily: 'inherit', fontSize: 12, marginTop: 12 }} />
              <div className="dialog-actions">
                <Button variant="secondary" size="sm" onClick={() => setDialog(null)}>取消</Button>
                <Button variant="primary" size="sm" type="submit" disabled={busy}>创建</Button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除文件"
        message={`确认删除 ${pendingDelete ?? ''}？此操作不可撤销。`}
        confirmLabel="删除"
        danger
        onConfirm={() => {
          if (pendingDelete) void deleteFile(pendingDelete)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
