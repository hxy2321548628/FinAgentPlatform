export type UserRole = 'admin' | 'reviewer' | 'teacher' | 'student'

export interface Me {
  id: string
  name: string
  role: UserRole
}

/**
 * 一次 run 实际生效的配置。
 *
 * 提交时只能给 `system_prompt` 与 `agent_id` 其中一个，同时给一律 422；
 * 回来的快照里两者都在 —— 引用在提交那一刻已经解析成了具体版本与那一版的原文。
 */
export interface AgentConfig {
  system_prompt?: string | null
  agent_id?: string | null
  agent_version?: number | null
}

export type Visibility = 'private' | 'group'

export type VersionStatus = 'draft' | 'released'

export type ReviewStatus = 'pending' | 'approved' | 'rejected'

/** 一个 agent 出现在「我能引用的」列表里，是凭哪一条。 */
export type AgentSource = 'owned' | 'group' | 'catalog'

export interface AgentVersion {
  id: string
  version: number
  status: VersionStatus
  system_prompt: string
  created_at: string
  released_at: string | null
  review_id: string | null
  review_status: ReviewStatus | null
  review_reason: string | null
}

/** 作者视角的一个智能体。 */
export interface MyAgent {
  id: string
  name: string
  description: string
  subject: string
  visibility: Visibility
  call_count: number
  is_deleted: boolean
  in_catalog: boolean
  group_ids: string[]
  versions: AgentVersion[]
  created_at: string
  updated_at: string
}

/** 广场与「我能引用的」共用的一行，**带提示词全文**。 */
export interface AgentListing {
  id: string
  owner_id: string
  owner_name: string
  name: string
  description: string
  subject: string
  visibility: Visibility
  call_count: number
  version: number
  system_prompt: string
  source: AgentSource
  updated_at: string
}

/** 审核队列里的一条。 */
export interface ReviewItem {
  id: string
  target_kind: 'agent'
  target_id: string
  status: ReviewStatus
  responsibility_confirmed: boolean
  reason: string | null
  created_at: string
  decided_at: string | null
  agent_id: string
  agent_name: string
  owner_name: string
  description: string
  subject: string
  version: number
  system_prompt: string
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
