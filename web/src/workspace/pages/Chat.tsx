import { useRef, useState, useCallback } from 'react'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ChatInput } from '../components/ChatInput'
import { ArtifactPanel } from '../components/ArtifactPanel'

const MIN_PANEL_WIDTH = 200
const MAX_PANEL_WIDTH = 700
const DEFAULT_PANEL_WIDTH = 380

export function Chat() {
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [isRunning] = useState(false)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(DEFAULT_PANEL_WIDTH)

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = panelWidth

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - ev.clientX
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth.current + delta))
      setPanelWidth(newWidth)
    }
    const onMouseUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [panelWidth])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* 左侧会话列表 */}
      <ThreadSidebar />

      {/* 主对话区 */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        backgroundColor: 'var(--bg)',
        backgroundImage: 'linear-gradient(rgba(11,46,92,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(11,46,92,0.025) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}>
        <MessageList />
        <ChatInput isRunning={isRunning} />
      </div>

      {/* 拖拽分隔条 */}
      <div
        onMouseDown={onResizeStart}
        style={{
          width: 4, flexShrink: 0, cursor: 'col-resize',
          background: 'var(--border-light)',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--action)'}
        onMouseLeave={e => { if (!dragging.current) (e.currentTarget as HTMLElement).style.background = 'var(--border-light)' }}
      />

      {/* 右侧产物面板 */}
      <div style={{ width: panelWidth, flexShrink: 0 }}>
        <ArtifactPanel />
      </div>
    </div>
  )
}
