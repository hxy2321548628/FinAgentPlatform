export type UserRole = 'admin' | 'teacher' | 'student'

export interface Me {
  id: string
  name: string
  role: UserRole
}

export interface AgentConfig {
  system_prompt?: string | null
}

export interface ThreadSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ThreadDetail extends ThreadSummary {
  agent_config: AgentConfig
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

export type RunStatus = 'queued' | 'running' | 'waiting_approval' | 'succeeded' | 'failed' | 'cancelled'

export type RunErrorCode = 'SANDBOX_QUEUE_TIMEOUT' | 'ORPHANED' | 'INTERNAL'

export interface RunSummary {
  id: string
  thread_id: string
  status: RunStatus
  agent_config: AgentConfig
}

export interface RunHistory {
  id: string
  status: RunStatus
  content: string | null
  agent_config: AgentConfig
  error_code: RunErrorCode | null
  error_message: string | null
  started_at: string
  ended_at: string | null
}

export type DecisionType = 'approve' | 'reject' | 'edit' | 'respond'

export interface EditedAction {
  name: string
  args: Record<string, unknown>
}

export interface Decision {
  index: number
  type: DecisionType
  message?: string
  edited_action?: EditedAction
}

export interface WorkspaceEntry {
  path: string
  is_dir: boolean
  size: number
  modified_at: string
}

export interface WorkspaceTree {
  entries: WorkspaceEntry[]
  truncated: boolean
}

export interface FileContent {
  path: string
  text: string
  total_line: number
  start_line: number
  end_line: number
  is_binary: boolean
  truncated: boolean
}

export interface UploadResult {
  filename: string
  path: string
  size: number
}
