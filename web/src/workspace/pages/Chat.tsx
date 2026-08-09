import { useRef, useState, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ChatInput } from '../components/ChatInput'
import { ArtifactPanel } from '../components/ArtifactPanel'

const MIN_PANEL_WIDTH = 200
const MAX_PANEL_WIDTH = 700
const DEFAULT_PANEL_WIDTH = 380

interface AgentContext {
  agentId: string
  agentName: string
  agentAuthor: string
  agentDataNeeded: string
}

// 对话结束后的评分组件
function RatingWidget({ agentName, onRate }: { agentName: string; onRate: (star: number) => void }) {
  const [hovered, setHovered] = useState(0)
  const [rated, setRated] = useState(0)

  if (rated > 0) {
    return (
      <div style={{ padding: '10px 32px', background: 'var(--surface)', borderTop: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--status-done)' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
        感谢评价！已为「{agentName}」记录 {rated} 星
      </div>
    )
  }

  return (
    <div style={{ padding: '10px 32px', background: 'var(--surface)', borderTop: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 16 }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>如何评价这次「{agentName}」的分析效果？</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {[1, 2, 3, 4, 5].map(star => (
          <button
            key={star}
            onMouseEnter={() => setHovered(star)}
            onMouseLeave={() => setHovered(0)}
            onClick={() => { setRated(star); onRate(star) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 22, lineHeight: 1, color: star <= (hovered || rated) ? '#F59E0B' : 'var(--border)', transition: 'color 0.1s' }}
          >★</button>
        ))}
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>本次评价将计入广场评分</span>
    </div>
  )
}

export function Chat() {
  const location = useLocation()
  const agentCtx = (location.state as AgentContext | null)

  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [panelVisible, setPanelVisible] = useState(true)
  const [isRunning] = useState(false)
  const [resizerHovered, setResizerHovered] = useState(false)
  const [showRating] = useState(!!agentCtx)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(DEFAULT_PANEL_WIDTH)

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    if (!panelVisible) return
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
  }, [panelWidth, panelVisible])

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
        {agentCtx && (
          <div style={{ padding: '10px 24px', background: 'var(--action-light)', borderBottom: '1px solid var(--action-border)', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--action)', flexShrink: 0 }}>
              <circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/>
            </svg>
            <span style={{ fontSize: 13, color: 'var(--action)', fontWeight: 500 }}>
              当前使用：<strong>{agentCtx.agentName}</strong>
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>· {agentCtx.agentAuthor}</span>
            {agentCtx.agentDataNeeded && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 4 }}>· 建议上传：{agentCtx.agentDataNeeded}</span>
            )}
          </div>
        )}

        <MessageList />

        {showRating && agentCtx && (
          <RatingWidget agentName={agentCtx.agentName} onRate={() => {}} />
        )}

        <ChatInput isRunning={isRunning} />
      </div>

      {/* 拖拽分隔条 + 收起/展开触发器 */}
      <div
        onMouseDown={onResizeStart}
        style={{
          width: panelVisible ? 4 : 24,
          flexShrink: 0,
          cursor: panelVisible ? 'col-resize' : 'default',
          background: panelVisible
            ? ((resizerHovered || dragging.current) ? 'var(--action)' : 'var(--border-light)')
            : 'var(--border-light)',
          transition: 'background 0.15s, width 0.2s',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative',
        }}
        onMouseEnter={() => setResizerHovered(true)}
        onMouseLeave={() => setResizerHovered(false)}
      >
        {/* 收起/展开按钮 */}
        <button
          onClick={(e) => { e.stopPropagation(); setPanelVisible(v => !v) }}
          title={panelVisible ? '收起面板' : '展开面板'}
          style={{
            position: 'absolute',
            top: '50%', transform: 'translateY(-50%)',
            width: 20, height: 36,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: panelVisible ? '4px 0 0 4px' : '0 4px 4px 0',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: 10,
            left: panelVisible ? -20 : 0,
            zIndex: 10,
            transition: 'left 0.2s, color 0.15s',
            boxShadow: '-2px 0 6px rgba(11,46,92,0.06)',
          }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--action)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          {panelVisible ? '›' : '‹'}
        </button>
      </div>

      {/* 右侧产物面板 */}
      {panelVisible && (
        <div style={{ width: panelWidth, flexShrink: 0 }}>
          <ArtifactPanel />
        </div>
      )}
    </div>
  )
}
