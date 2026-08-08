import { Routes, Route, Navigate } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { Chat } from './pages/Chat'
import { AgentScenarios } from './pages/AgentScenarios'
import { AgentPlaza, PublishAgent } from './pages/AgentPlaza'
import { MyData } from './pages/MyData'
import { MyAgents } from './pages/MyAgents'

export function WorkspaceRouter() {
  const placeholder = (label: string) => (
    <div style={{ padding: 40, color: 'var(--text-secondary)', fontSize: 14 }}>{label}</div>
  )

  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="chat" element={<Chat />} />
      <Route path="chat/:threadId" element={<Chat />} />
      <Route path="scenarios" element={<AgentScenarios />} />
      <Route path="agents" element={<AgentPlaza />} />
      <Route path="agents/new" element={<PublishAgent />} />
      <Route path="data" element={<MyData />} />
      <Route path="my-agents" element={<MyAgents />} />
      <Route path="admin/*" element={placeholder('管理后台（Plan 4 实现）')} />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
