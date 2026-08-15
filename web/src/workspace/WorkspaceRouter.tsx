import { Routes, Route } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { Chat } from './pages/Chat'
import { AgentPlaza } from './pages/AgentPlaza'
import { CreateAgent } from './pages/CreateAgent'
import { MyData } from './pages/MyData'
import { MyAgents } from './pages/MyAgents'
import { MySkills } from './pages/MySkills'
import { ScenarioLibrary, MyScenarios } from './pages/Scenarios'
import { Settings } from '../pages/Settings'
import { NotFound } from '../components/NotFound'
import { McpLibrary, SkillsLibrary } from './pages/CapabilityLibraries'

export function WorkspaceRouter() {
  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="chat" element={<Chat />} />
      <Route path="chat/:threadId" element={<Chat />} />
      <Route path="agents" element={<AgentPlaza />} />
      <Route path="scenarios" element={<ScenarioLibrary />} />
      <Route path="my-scenarios" element={<MyScenarios />} />
      <Route path="skills" element={<SkillsLibrary />} />
      <Route path="mcp" element={<McpLibrary />} />
      <Route path="data" element={<MyData />} />
      <Route path="my-agents" element={<MyAgents />} />
      <Route path="my-skills" element={<MySkills />} />
      <Route path="my-agents/create" element={<CreateAgent />} />
      <Route path="my-agents/:agentId/edit" element={<CreateAgent />} />
      <Route path="settings" element={<Settings />} />
      <Route path="*" element={<NotFound title="工作台页面不存在" description="该工作台地址不存在，请返回总览或开始新的分析对话。" primaryTo="/workspace" primaryLabel="返回总览" secondaryTo="/workspace/chat" secondaryLabel="开始分析对话" />} />
    </Routes>
  )
}
