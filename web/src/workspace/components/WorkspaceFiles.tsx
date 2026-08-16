import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createDirectory, deleteFile as removeFile, fileKeys, listFiles, rawFileUrl, readFile, uploadFile, writeFile } from '../../api/files'
import { errorMessage } from '../../api/request'
import type { WorkspaceEntry } from '../../api/types'
import { ConfirmDialog } from './ConfirmDialog'
import { useToast } from '../../components/ui/toast-context'
import { Button } from '../../components/ui/Button'
import { highlightCode, languageForPath, languageLabel } from './codeHighlight'
import { CodeSurface } from './CodeSurface'
import * as Dialog from '@radix-ui/react-dialog'
import { ChevronDown, ChevronRight, Copy, Download, File, FilePlus2, Folder, FolderOpen, FolderPlus, Pencil, RefreshCw, Save, Trash2, Upload, X } from 'lucide-react'

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

interface WorkspaceTreeNode {
  entry: WorkspaceEntry
  children: WorkspaceTreeNode[]
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

export function WorkspaceFiles({ threadId, title, compact = false }: WorkspaceFilesProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const tree = useQuery({ queryKey: fileKeys.tree(threadId), queryFn: () => listFiles(threadId) })
  const entries = tree.data?.entries ?? EMPTY_ENTRIES
  const treeNodes = useMemo(() => buildWorkspaceTree(entries), [entries])
  const [currentDir, setCurrentDir] = useState('')
  const [openDirectories, setOpenDirectories] = useState<Set<string>>(new Set())
  const [preview, setPreview] = useState<FilePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editorText, setEditorText] = useState('')
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'file' | 'directory' | null>(null)
  const [dialogName, setDialogName] = useState('')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const uploadRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setCurrentDir('')
    setOpenDirectories(new Set())
    setPreview(null)
    setEditing(false)
    setHighlightedHtml(null)
    setDialog(null)
  }, [threadId])

  const openFile = async (entry: WorkspaceEntry) => {
    if (entry.is_dir) {
      setCurrentDir(entry.path)
      setOpenDirectories(current => toggled(current, entry.path))
      return
    }

    setCurrentDir(directoryName(entry.path))
    const ext = extension(entry.path)
    const rawUrl = rawFileUrl(threadId, entry.path)
    if (IMAGE_EXTENSIONS.has(ext)) {
      setPreview({ path: entry.path, text: '', isBinary: true, truncated: false, rawUrl })
      setEditing(false)
      setHighlightedHtml(null)
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

  const codeText = editing ? editorText : preview?.text ?? ''
  const previewPath = preview?.path ?? null
  const previewIsBinary = preview?.isBinary ?? false

  useEffect(() => {
    if (!previewPath || previewIsBinary) {
      setHighlightedHtml(null)
      return
    }
    const language = languageForPath(previewPath)
    if (!language) {
      setHighlightedHtml(null)
      return
    }
    let cancelled = false
    setHighlightedHtml(null)
    void highlightCode(codeText, language).then(result => {
      if (!cancelled) setHighlightedHtml(result)
    })
    return () => { cancelled = true }
  }, [codeText, previewIsBinary, previewPath])

  const uploadFiles = async (files: FileList | File[], directory = currentDir) => {
    setBusy(true)
    try {
      for (const file of Array.from(files)) await uploadFile(threadId, file, directory)
      toast({ title: '文件已上传', variant: 'success' })
      await queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) })
    } catch (error) {
      toast({ title: '上传失败', description: errorMessage(error), variant: 'error' })
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
      toast({ title: '删除失败', description: errorMessage(error), variant: 'error' })
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

  const cancelEditing = () => {
    if (preview) setEditorText(preview.text)
    setEditing(false)
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

  return (
    <div className={`workspace-explorer${compact ? ' compact' : ''}`}>
      <div className="workspace-explorer-main">
        <aside className="workspace-tree-pane">
          <div className="workspace-tree-header">
            <div className="workspace-tree-heading">
              <span>EXPLORER</span>
              <strong title={title}>{title ?? '工作目录'}</strong>
            </div>
            <div className="workspace-files-actions" role="toolbar" aria-label="工作区文件操作">
              <button type="button" className="workspace-entry-icon" disabled={busy} onClick={() => { setDialogName(''); setDialog('file') }} aria-label="新建文件" title="新建文件"><FilePlus2 size={14} strokeWidth={1.8} /></button>
              <button type="button" className="workspace-entry-icon" disabled={busy} onClick={() => { setDialogName(''); setDialog('directory') }} aria-label="新建文件夹" title="新建文件夹"><FolderPlus size={14} strokeWidth={1.8} /></button>
              <button type="button" className="workspace-entry-icon" disabled={busy} onClick={() => uploadRef.current?.click()} aria-label="上传文件" title="上传文件"><Upload size={14} strokeWidth={1.8} /></button>
              <button type="button" className="workspace-entry-icon" disabled={tree.isFetching} onClick={() => void tree.refetch()} aria-label="刷新文件" title="刷新文件"><RefreshCw size={14} strokeWidth={1.8} /></button>
              <input ref={uploadRef} type="file" multiple hidden onChange={event => { if (event.target.files?.length) void uploadFiles(event.target.files) }} />
            </div>
          </div>
          <button type="button" className={`workspace-root-row${currentDir === '' ? ' active' : ''}`} onClick={() => setCurrentDir('')}>
            <FolderOpen size={14} />
            <span>工作区根目录</span>
          </button>
          {currentDir && <div className="workspace-target-directory" title={currentDir}>新内容将创建在 /{currentDir}</div>}
          <div className="workspace-tree-scroll" role="tree" aria-label="工作区文件树">
            {tree.isPending && <div className="workspace-tree-state">正在加载文件…</div>}
            {tree.isError && <div role="alert" className="workspace-tree-state error">{errorMessage(tree.error)}</div>}
            {!tree.isPending && !tree.isError && treeNodes.length === 0 && <div className="workspace-tree-state">这里还没有文件。可用上方图标新建或上传。</div>}
            {treeNodes.map(node => (
              <WorkspaceTreeBranch
                key={node.entry.path}
                node={node}
                depth={0}
                busy={busy}
                openDirectories={openDirectories}
                selectedPath={preview?.path ?? null}
                selectedDirectory={currentDir}
                threadId={threadId}
                onOpen={entry => void openFile(entry)}
                onCopy={path => void copyPath(path)}
                onDelete={setPendingDelete}
              />
            ))}
            {tree.data?.truncated && <div className="workspace-tree-state">文件较多，仅展示前一部分。</div>}
          </div>
        </aside>

        <section className="workspace-editor-pane">
          {preview ? (
            <>
              <div className="workspace-editor-header">
                <File size={14} />
                <span className="workspace-editor-path" title={preview.path}>{preview.path}</span>
                <span className="workspace-editor-language">{languageLabel(preview.path)}</span>
                {!preview.isBinary && !preview.truncated && !editing && <button type="button" className="workspace-entry-icon" disabled={busy} onClick={() => setEditing(true)} aria-label="编辑文件" title="编辑文件"><Pencil size={13} /></button>}
                {editing && <button type="button" className="workspace-entry-icon" disabled={busy} onClick={cancelEditing} aria-label="取消编辑" title="取消编辑"><X size={13} /></button>}
                {editing && <button type="button" className="workspace-entry-icon primary" disabled={busy || editorText === preview.text} onClick={() => void saveEditedFile()} aria-label="保存文件" title="保存文件"><Save size={13} /></button>}
                <button type="button" className="workspace-entry-icon" onClick={() => void copyPath(preview.path)} aria-label="复制文件路径" title="复制文件路径"><Copy size={13} /></button>
                <a className="workspace-entry-icon" href={rawFileUrl(threadId, preview.path, true)} aria-label="下载文件" title="下载文件"><Download size={13} /></a>
                <button type="button" className="workspace-entry-icon" onClick={() => { setPreview(null); setEditing(false) }} aria-label="关闭预览" title="关闭预览"><X size={13} /></button>
              </div>
              <div
                className={`workspace-editor-content${!preview.isBinary && !IMAGE_EXTENSIONS.has(extension(preview.path)) ? ' code' : ''}`}
                style={!preview.isBinary && !IMAGE_EXTENSIONS.has(extension(preview.path)) ? { display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 } : undefined}
              >
                {preview.truncated && <div className="workspace-preview-warning">文件较长，当前仅展示开头部分；为避免覆盖未加载内容，该文件仅可预览或下载。</div>}
                {IMAGE_EXTENSIONS.has(extension(preview.path)) ? (
                  <img src={preview.rawUrl} alt={fileName(preview.path)} className="workspace-image-preview" />
                ) : preview.isBinary ? (
                  <div className="workspace-editor-empty">该文件不支持文本预览，请点击下载查看。</div>
                ) : (
                  <CodeSurface
                    path={preview.path}
                    value={editing ? editorText : preview.text}
                    highlightedHtml={highlightedHtml}
                    editing={editing}
                    onChange={setEditorText}
                    onSave={() => void saveEditedFile()}
                  />
                )}
              </div>
              {!preview.isBinary && <div className="workspace-editor-status"><span>{languageLabel(preview.path)}</span><span>UTF-8</span><span>{(editing ? editorText : preview.text).split('\n').length} 行</span><span>{editing ? editorText === preview.text ? '已保存' : '有未保存修改' : '只读预览'}</span></div>}
            </>
          ) : (
            <div className="workspace-editor-empty">
              <File size={28} strokeWidth={1.3} />
              <strong>选择文件进行预览</strong>
              <span>文本文件默认只读预览，可通过编辑按钮修改；图片可预览，其他文件可下载。</span>
            </div>
          )}
        </section>
      </div>

      <Dialog.Root open={dialog !== null} onOpenChange={open => { if (!open) setDialog(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" onClick={() => setDialog(null)} />
          <Dialog.Content className="dialog-content" style={{ width: 'min(360px, 100%)' }} aria-describedby={undefined}>
            <Dialog.Title className="dialog-title">{dialog === 'directory' ? '新建文件夹' : '新建文件'}</Dialog.Title>
            <p className="dialog-desc">创建位置：/{currentDir || '工作区根目录'}</p>
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

function WorkspaceTreeBranch({ node, depth, busy, openDirectories, selectedPath, selectedDirectory, threadId, onOpen, onCopy, onDelete }: {
  node: WorkspaceTreeNode
  depth: number
  busy: boolean
  openDirectories: Set<string>
  selectedPath: string | null
  selectedDirectory: string
  threadId: string
  onOpen: (entry: WorkspaceEntry) => void
  onCopy: (path: string) => void
  onDelete: (path: string) => void
}) {
  const { entry } = node
  const open = entry.is_dir && openDirectories.has(entry.path)
  const active = entry.is_dir ? selectedDirectory === entry.path : selectedPath === entry.path
  return (
    <div role="treeitem" aria-expanded={entry.is_dir ? open : undefined}>
      <div className={`workspace-tree-row${active ? ' active' : ''}`} style={{ paddingLeft: 8 + depth * 15 }}>
        <button type="button" className="workspace-tree-main" aria-label={fileName(entry.path)} onClick={() => onOpen(entry)}>
          {entry.is_dir ? (open ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <span className="workspace-tree-spacer" />}
          {entry.is_dir ? (open ? <FolderOpen size={14} /> : <Folder size={14} />) : <File size={14} />}
          <span>{fileName(entry.path)}</span>
          {!entry.is_dir && <small>{formatSize(entry.size)}</small>}
        </button>
        {!entry.is_dir && <div className="workspace-tree-actions">
          <button type="button" onClick={() => onCopy(entry.path)} aria-label={`复制路径：${fileName(entry.path)}`} title="复制路径"><Copy size={12} /></button>
          <a href={rawFileUrl(threadId, entry.path, true)} aria-label={`下载：${fileName(entry.path)}`} title="下载"><Download size={12} /></a>
          <button type="button" disabled={busy} onClick={() => onDelete(entry.path)} aria-label={`删除：${fileName(entry.path)}`} title="删除"><Trash2 size={12} /></button>
        </div>}
      </div>
      {open && node.children.map(child => <WorkspaceTreeBranch key={child.entry.path} node={child} depth={depth + 1} busy={busy} openDirectories={openDirectories} selectedPath={selectedPath} selectedDirectory={selectedDirectory} threadId={threadId} onOpen={onOpen} onCopy={onCopy} onDelete={onDelete} />)}
    </div>
  )
}

function buildWorkspaceTree(entries: WorkspaceEntry[]): WorkspaceTreeNode[] {
  const roots: WorkspaceTreeNode[] = []
  for (const entry of entries) {
    const parts = entry.path.split('/').filter(Boolean)
    let children = roots
    let path = ''
    parts.forEach((name, index) => {
      path = path ? `${path}/${name}` : name
      let node = children.find(item => item.entry.path === path)
      if (!node) {
        const final = index === parts.length - 1
        node = {
          entry: final ? entry : { path, is_dir: true, size: 0, modified_at: entry.modified_at },
          children: [],
        }
        children.push(node)
      } else if (index === parts.length - 1) {
        node.entry = entry
      }
      children = node.children
    })
  }
  const sort = (nodes: WorkspaceTreeNode[]) => {
    nodes.sort((a, b) => Number(b.entry.is_dir) - Number(a.entry.is_dir) || a.entry.path.localeCompare(b.entry.path, 'zh-CN'))
    nodes.forEach(node => sort(node.children))
  }
  sort(roots)
  return roots
}

function toggled(current: Set<string>, path: string): Set<string> {
  const next = new Set(current)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  return next
}
