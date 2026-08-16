import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fileKeys, listFiles, rawFileUrl } from '../../api/files'
import type { WorkspaceEntry } from '../../api/types'

/**
 * 本轮产物区（方案 doc/02visual/04 §5）。
 *
 * run 终态后按「outputs/ 前缀 + modified_at ≥ run.started_at」过滤文件树，
 * 把本轮生成的图表/报表直接列在答复下方 —— 不依赖模型是否在正文里引用产物。
 * 文件树拉取失败或为空时整体不渲染，答复不受影响。
 */

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'])
const MAX_VISIBLE = 6

function fileName(path: string): string {
  return path.split('/').at(-1) ?? path
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function isImage(entry: WorkspaceEntry): boolean {
  const ext = fileName(entry.path).split('.').at(-1)?.toLowerCase() ?? ''
  return IMAGE_EXTENSIONS.has(ext)
}

interface ArtifactStripProps {
  threadId: string
  /** run.started_at；比它更早修改的文件属于之前的轮次，不显示。 */
  startedAt: string
}

export function ArtifactStrip({ threadId, startedAt }: ArtifactStripProps) {
  const [showAll, setShowAll] = useState(false)
  const tree = useQuery({ queryKey: fileKeys.tree(threadId), queryFn: () => listFiles(threadId) })

  const artifacts = useMemo(() => {
    const started = Date.parse(startedAt)
    if (!Number.isFinite(started)) return []
    return (tree.data?.entries ?? [])
      .filter(one => !one.is_dir)
      .filter(one => one.path.startsWith('outputs/'))
      .filter(one => Date.parse(one.modified_at) >= started)
      .sort((a, b) => b.modified_at.localeCompare(a.modified_at))
  }, [tree.data, startedAt])

  if (tree.isPending || tree.isError) return null
  if (artifacts.length === 0) return null

  const visible = showAll ? artifacts : artifacts.slice(0, MAX_VISIBLE)

  return (
    <section className="artifact-strip" aria-label={`本轮产物（${artifacts.length} 个）`}>
      <div className="artifact-title">本轮产物（{artifacts.length}）</div>
      <div className="artifact-grid">
        {visible.map(entry => {
          const name = fileName(entry.path)
          if (isImage(entry)) {
            return (
              <a key={entry.path} className="artifact-image" href={rawFileUrl(threadId, entry.path)} target="_blank" rel="noopener noreferrer">
                <img src={rawFileUrl(threadId, entry.path)} alt={name} loading="lazy" decoding="async" />
                <span className="artifact-caption">{name} · {formatSize(entry.size)}</span>
              </a>
            )
          }
          return (
            <div key={entry.path} className="artifact-file">
              <div className="artifact-file-info">
                <span className="artifact-file-name">{name}</span>
                <span className="artifact-file-size">{formatSize(entry.size)}</span>
              </div>
              <a className="artifact-download" href={rawFileUrl(threadId, entry.path, true)}>下载</a>
            </div>
          )
        })}
      </div>
      {artifacts.length > MAX_VISIBLE && (
        <button type="button" className="artifact-more" onClick={() => setShowAll(value => !value)}>
          {showAll ? '收起' : `展开其余 ${artifacts.length - MAX_VISIBLE} 个`}
        </button>
      )}
    </section>
  )
}
