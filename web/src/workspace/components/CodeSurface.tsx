import { useCallback, useEffect, useRef } from 'react'
import { languageForPath } from './codeHighlight'

interface CodeSurfaceProps {
  path: string
  value: string
  highlightedHtml: string | null
  editing?: boolean
  onChange?: (value: string) => void
  onSave?: () => void
}

export function CodeSurface({ path, value, highlightedHtml, editing = false, onChange, onSave }: CodeSurfaceProps) {
  const gutterRef = useRef<HTMLPreElement>(null)
  const previewScrollRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const highlightRef = useRef<HTMLDivElement>(null)
  const scrollPosition = useRef({ top: 0, left: 0 })
  const lineCount = Math.max(1, value.split('\n').length)
  const lineNumbers = Array.from({ length: lineCount }, (_, index) => index + 1).join('\n')
  const language = languageForPath(path)
  const indentation = new Set(['json', 'yaml', 'javascript', 'typescript', 'jsx', 'tsx', 'html', 'css', 'xml']).has(language ?? '') ? '  ' : '    '

  const syncScroll = useCallback((top: number, left: number) => {
    scrollPosition.current = { top, left }
    if (gutterRef.current) gutterRef.current.scrollTop = top
    if (editing && highlightRef.current) highlightRef.current.style.transform = `translate(${-left}px, ${-top}px)`
  }, [editing])

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const target = editing ? editorRef.current : previewScrollRef.current
      if (!target) return
      target.scrollTop = scrollPosition.current.top
      target.scrollLeft = scrollPosition.current.left
      syncScroll(target.scrollTop, target.scrollLeft)
      if (editing) target.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [editing, syncScroll])

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      onSave?.()
      return
    }
    if (event.key !== 'Tab') return
    event.preventDefault()
    const field = event.currentTarget
    const start = field.selectionStart
    const end = field.selectionEnd
    onChange?.(`${value.slice(0, start)}${indentation}${value.slice(end)}`)
    requestAnimationFrame(() => {
      field.selectionStart = start + indentation.length
      field.selectionEnd = start + indentation.length
    })
  }

  const code = highlightedHtml ? (
    <div className="workspace-code-highlighted" dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
  ) : (
    <pre className="workspace-code-plain">{value}</pre>
  )
  const codeLayerStyle: React.CSSProperties = {
    minWidth: '100%',
    minHeight: '100%',
    padding: '14px 16px',
    boxSizing: 'border-box',
    color: 'var(--text-primary)',
    font: "12px/1.7 'JetBrains Mono', monospace",
    tabSize: 4,
    whiteSpace: 'pre',
  }

  return (
    <div
      className={`workspace-code-surface${editing ? ' editing' : ''}`}
      data-language={language ?? 'text'}
      style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '48px minmax(0, 1fr)', overflow: 'hidden' }}
    >
      <pre
        ref={gutterRef}
        className="workspace-code-gutter"
        aria-hidden="true"
        style={{ height: '100%', minHeight: 0, margin: 0, padding: '14px 10px', overflow: 'hidden', boxSizing: 'border-box', font: "11px/1.8545 'JetBrains Mono', monospace", textAlign: 'right' }}
      >{lineNumbers}</pre>
      <div className="workspace-code-stage" style={{ position: 'relative', minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
        {editing ? (
          <>
            <div ref={highlightRef} className="workspace-code-highlight" aria-hidden="true" style={{ ...codeLayerStyle, position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>{code}</div>
            <textarea
              ref={editorRef}
              value={value}
              onChange={event => onChange?.(event.target.value)}
              onKeyDown={handleKeyDown}
              onScroll={event => syncScroll(event.currentTarget.scrollTop, event.currentTarget.scrollLeft)}
              className="workspace-code-editor"
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', minHeight: 0, resize: 'none', boxSizing: 'border-box', padding: '14px 16px', overflow: 'auto', border: 0, outline: 0, background: 'transparent', color: 'transparent', WebkitTextFillColor: 'transparent', caretColor: 'var(--action)', font: "12px/1.7 'JetBrains Mono', monospace", tabSize: 4, whiteSpace: 'pre' }}
              aria-label="文件内容编辑器"
              wrap="off"
              spellCheck={false}
            />
          </>
        ) : (
          <div
            ref={previewScrollRef}
            className="workspace-code-scroll"
            style={{ position: 'absolute', inset: 0, overflow: 'auto' }}
            onScroll={event => syncScroll(event.currentTarget.scrollTop, event.currentTarget.scrollLeft)}
            aria-label="只读代码查看器"
            tabIndex={0}
          >
            <div className="workspace-code-highlight" style={codeLayerStyle}>{code}</div>
          </div>
        )}
      </div>
    </div>
  )
}
