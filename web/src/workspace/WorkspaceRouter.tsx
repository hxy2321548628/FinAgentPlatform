import { Routes, Route, Navigate } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { Chat } from './pages/Chat'
import { AgentScenarios } from './pages/AgentScenarios'
import { AgentPlaza, PublishAgent } from './pages/AgentPlaza'
import { CreateAgent } from './pages/CreateAgent'
import { MyData } from './pages/MyData'
import { MyAgents } from './pages/MyAgents'
import { AdminLayout } from './pages/admin/AdminLayout'
import { AdminUsers } from './pages/admin/AdminUsers'
import { AdminAgents } from './pages/admin/AdminAgents'
import { AdminScenarios } from './pages/admin/AdminScenarios'
import { AdminUsage } from './pages/admin/AdminUsage'
import { AdminSystem } from './pages/admin/AdminSystem'

export function WorkspaceRouter() {
  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="chat" element={<Chat />} />
      <Route path="chat/:threadId" element={<Chat />} />
      <Route path="scenarios" element={<AgentScenarios />} />
      <Route path="agents" element={<AgentPlaza />} />
      <Route path="agents/publish" element={<PublishAgent />} />
      <Route path="data" element={<MyData />} />
      <Route path="my-agents" element={<MyAgents />} />
      <Route path="my-agents/create" element={<CreateAgent />} />
      <Route path="admin/*" element={<AdminLayout />}>
        <Route index element={<AdminUsers />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="agents" element={<AdminAgents />} />
        <Route path="scenarios" element={<AdminScenarios />} />
        <Route path="usage" element={<AdminUsage />} />
        <Route path="system" element={<AdminSystem />} />
      </Route>
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
