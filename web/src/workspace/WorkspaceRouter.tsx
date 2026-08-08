import { Routes, Route, Navigate } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { Chat } from './pages/Chat'

export function WorkspaceRouter() {
  const placeholder = (label: string) => (
    <div style={{ padding: 40, color: 'var(--text-secondary)', fontSize: 14 }}>{label}</div>
  )

  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="chat" element={<Chat />} />
      <Route path="chat/:threadId" element={<Chat />} />
      <Route path="scenarios" element={placeholder('场景库（Plan 3 实现）')} />
      <Route path="agents" element={placeholder('智能体广场（Plan 3 实现）')} />
      <Route path="agents/new" element={placeholder('发布智能体（Plan 3 实现）')} />
      <Route path="data" element={placeholder('我的数据（Plan 3 实现）')} />
      <Route path="my-agents" element={placeholder('我的智能体（Plan 3 实现）')} />
      <Route path="admin/*" element={placeholder('管理后台（Plan 4 实现）')} />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
