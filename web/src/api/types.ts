export type UserRole = 'admin' | 'reviewer' | 'teacher' | 'student'

export interface RegisterResponse {
  id: string
  name: string
  role: UserRole
  is_active: boolean
  group_name: string | null
}

export interface Me {
  id: string
  name: string
  email: string
  role: UserRole
}

/** 后台账号列表里的一行。配额两项留空表示「跟着角色的默认档走」，不是「没有配额」。 */
export interface AdminUser {
  id: string
  name: string
  email: string
  dept: string
  role: UserRole
  is_active: boolean
  quota_tokens_daily: number | null
  quota_concurrent_runs: number | null
}

/**
 * 一段窗口里的用量。
 *
 * `available` 为 false 时下面三个数**不是「零用量」，是「没数」** —— 一串 0 会让
 * 「没接账本」与「这个月还没人用」长得一模一样。
 */
export interface Usage {
  available: boolean
  tokens: number
  cost: number
  observations: number
}

export interface UserUsage {
  user_id: string
  name: string
  tokens: number
  cost: number
  observations: number
}

export interface UsageRanking {
  available: boolean
  total: Usage
  items: UserUsage[]
}

/** 沙箱池的占用。`broker_reachable` 为 false 时三个数都是 0，**不是真的空闲**。 */
export interface SystemStatus {
  broker_reachable: boolean
  in_use: number
  capacity: number
  queued: number
}

/**
 * 一次 run 实际生效的配置。
 *
 * 提交时只能给 `system_prompt` 与 `agent_id` 其中一个，同时给一律 422；
 * 回来的快照里两者都在 —— 引用在提交那一刻已经解析成了具体版本与那一版的原文。
 */
export interface SkillReference {
  skill_id: string
  version: number
  name: string
}

export interface SubagentReference {
  agent_id: string
  version: number
  name: string
}

/**
 * 一次 run 快照里冻结的一条 MCP 目录记录。
 *
 * **只有两个字段，因为能冻住的只有这两个。** Skill 与子智能体冻的是内容（版本号 +
 * 内容在平台手里）；MCP 的内容在校外那台机器上，冻得住的只是「用了哪一条目录记录」。
 */
export interface McpReference {
  server_id: string
  name: string
}

export interface AgentConfig {
  system_prompt?: string | null
  agent_id?: string | null
  agent_version?: number | null
  /** 请求时是 Skill ID，响应与历史快照里是冻结三元组。 */
  skills?: string[] | SkillReference[] | null
  /** 请求时是 Agent ID，响应与历史快照里是冻结三元组。 */
  subagents?: string[] | SubagentReference[] | null
  /** 请求时是 MCP 目录 ID，响应与历史快照里是 {server_id, name}。 */
  mcps?: string[] | McpReference[] | null
}

export type McpTransport = 'streamable_http' | 'sse'

export type McpStatus = 'pending' | 'enabled' | 'disabled' | 'rejected'

/**
 * 目录里的一条 MCP。**不含凭据** —— 库里存的本来就只有键名。
 *
 * `sends_data_out` 是申请人对「我会不会把数据再转发给第三方」的声明；它与平台对
 * **所有** MCP 一律显示的那句外发标注不是一回事 —— 只要服务在校外，勾上它就意味着
 * 数据出校，这与申请人怎么声明无关。
 */
export interface McpServer {
  id: string
  name: string
  description: string
  url: string
  transport: McpTransport
  has_credential: boolean
  tool_names: string[]
  latency_note: string
  stores_user_data: boolean
  sends_data_out: boolean
  has_write_operation: boolean
  status: McpStatus
  disabled_reason: string | null
  created_at: string
  updated_at: string
}

/** 管理员后台多看到的两样：谁提的，以及此刻连续失败了几次。 */
export interface AdminMcpServer extends McpServer {
  submitted_by: string
  submitter_name: string
  failure_count: number
}

/** 一次「测试连接」的结果。 */
export interface McpProbe {
  reachable: boolean
  tool_names: string[]
  declared_only: string[]
  undeclared: string[]
  failure_count: number
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
  skill_refs?: SkillReference[] | null
  subagent_refs?: SubagentReference[] | null
  mcp_refs?: McpReference[] | null
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
  catalog_enabled: boolean
  catalog_disabled_reason: string | null
  catalog_disabled_by: string | null
  catalog_disabled_at: string | null
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
  skill_refs?: SkillReference[] | null
  subagent_refs?: SubagentReference[] | null
  mcp_refs?: McpReference[] | null
  source: AgentSource
  updated_at: string
}

/** 公开目录投影（落地页市场区，匿名可读）：后端已删掉提示词/MCP/owner_id 等字段。 */
export interface PublicAgentListing {
  id: string
  owner_name: string
  name: string
  description: string
  subject: string
  call_count: number
  version: number
  skill_refs?: SkillReference[] | null
  subagent_refs?: SubagentReference[] | null
  updated_at: string
}

/** 审核队列里的一条。 */
export interface ReviewItem {
  id: string
  target_kind: 'agent' | 'skill'
  target_id: string
  status: ReviewStatus
  responsibility_confirmed: boolean
  reason: string | null
  created_at: string
  decided_at: string | null
  owner_name: string
  description: string
  subject: string
  version: number
  agent_id: string | null
  agent_name: string | null
  system_prompt: string | null
  skill_refs: SkillReference[] | null
  subagent_refs: SubagentReference[] | null
  mcp_refs: McpReference[] | null
  skill_id: string | null
  skill_name: string | null
  file_count: number | null
  total_bytes: number | null
  catalog_enabled: boolean
  catalog_disabled_reason: string | null
  catalog_disabled_by: string | null
  catalog_disabled_at: string | null
}

export type SkillSource = 'owned' | 'group' | 'catalog'

export interface SkillVersion {
  id: string
  version: number
  status: VersionStatus
  description: string
  file_count: number
  total_bytes: number
  created_at: string
  released_at: string | null
  review_id: string | null
  review_status: ReviewStatus | null
  review_reason: string | null
}

export interface MySkill {
  id: string
  owner_name: string
  name: string
  subject: string
  visibility: Visibility
  call_count: number
  is_deleted: boolean
  in_catalog: boolean
  catalog_enabled: boolean
  catalog_disabled_reason: string | null
  catalog_disabled_by: string | null
  catalog_disabled_at: string | null
  group_ids: string[]
  versions: SkillVersion[]
  created_at: string
  updated_at: string
}

export interface SkillListing {
  id: string
  owner_id: string
  owner_name: string
  name: string
  description: string
  subject: string
  visibility: Visibility
  call_count: number
  version: number
  file_count: number
  total_bytes: number
  source: SkillSource
  updated_at: string
}

export interface SkillFileEntry {
  path: string
  size: number
}

export interface SkillFileContent {
  path: string
  size: number
  content: string | null
  is_binary: boolean
}

export interface ThreadSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  /** 这个会话现在还在跑的 run 的状态；没有就是 null（会话侧栏的「进行中」状态点）。 */
  live_run_status?: RunStatus | null
}

export interface ThreadDetail extends ThreadSummary {
  agent_config: AgentConfig
}

export type MemoryType = 'user' | 'feedback' | 'project' | 'reference'

/** 教师可管理的 thread 私有记忆短索引，不含宿主路径与模型审计。 */
export interface MemorySummary {
  slug: string
  name: string
  description: string
  type: MemoryType
  updated_at: string
}

export interface MemoryDetail extends MemorySummary {
  content: string
}

export interface MemoryListResponse {
  items: MemorySummary[]
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

export type RunStatus = 'queued' | 'running' | 'waiting_approval' | 'succeeded' | 'failed' | 'cancelled'

export type RunErrorCode = 'SANDBOX_QUEUE_TIMEOUT' | 'ORPHANED' | 'INTERNAL' | 'RECURSION_LIMIT'

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
