import type { AgentListing, AgentSource, AgentVersion, MyAgent, ReviewStatus } from '../api/types'

/**
 * 「我的智能体」的三个页签。
 *
 * 后端给的是五个事实（版本 draft / released，审核 pending / approved / rejected），
 * 合成三个页签的规则写在这里而不是散在渲染里 —— **映错了的表现是「我的东西不见了」**，
 * 那种缺陷没有报错，只有一通电话。
 */
export const AGENT_TABS = ['draft', 'reviewing', 'published'] as const

export type AgentTab = (typeof AGENT_TABS)[number]

export const AGENT_TAB_LABEL: Record<AgentTab, string> = {
  draft: '草稿',
  reviewing: '待审核',
  published: '已发布',
}

export const AGENT_TAB_EMPTY: Record<AgentTab, string> = {
  draft: '还没有草稿状态的智能体',
  reviewing: '没有在等审核的智能体',
  published: '还没有发布过版本的智能体',
}

export interface AgentState {
  tab: AgentTab
  /** 当前那个草稿；已经定稿且没再改过时为空。 */
  draft: AgentVersion | null
  /** 最新那个已发布的版本 —— 组员引用到的正是它。 */
  released: AgentVersion | null
  /** 最新那个已发布版本的审核状态。**没提审过是 null，不是「未通过」**。 */
  reviewStatus: ReviewStatus | null
  /** 被拒时的理由，一字不差。 */
  rejectedReason: string | null
}

/**
 * 把一个 agent 的版本与审核事实合成页签所需的状态。
 *
 * **优先级是「待审 > 已发布 > 草稿」**：一个 agent 可以同时有已发布版本与一条待审
 * 记录，而作者这时最关心的是审核走到哪了。
 */
export function agentState(agent: MyAgent): AgentState {
  const draft = agent.versions.find(one => one.status === 'draft') ?? null
  const released = [...agent.versions].reverse().find(one => one.status === 'released') ?? null
  const reviewStatus = released?.review_status ?? null
  const rejectedReason = reviewStatus === 'rejected' ? (released?.review_reason ?? null) : null
  const waiting = reviewStatus === 'pending' || reviewStatus === 'rejected'
  return {
    tab: waiting ? 'reviewing' : released ? 'published' : 'draft',
    draft,
    released,
    reviewStatus,
    rejectedReason,
  }
}

/**
 * 这个 agent 现在被谁看得见。
 *
 * **两档可以同时成立**：一个共享给组的 agent 也可以有一版过了审进了广场。
 * 拿单个标签表示会漏掉其中一档，而漏掉的那一档正是作者最该知道的。
 */
export function visibilityBadges(agent: MyAgent): string[] {
  const badges: string[] = []
  if (agent.in_catalog) badges.push('平台广场')
  if (agent.visibility === 'group' && agent.group_ids.length > 0) {
    badges.push(`组内共享 · ${agent.group_ids.length} 个组`)
  }
  if (badges.length === 0) badges.push('私有')
  return badges
}

const SOURCE_LABEL: Record<AgentSource, string> = {
  owned: '我创建的',
  group: '组内共享',
  catalog: '平台广场',
}

/**
 * 一个 agent 是凭哪一条进到「我能引用的」列表里的。
 *
 * **展示错了会让人以为「组内的东西上了广场」** —— 那会让作者以为自己的提示词
 * 已经对全院可见。
 */
export function sourceLabel(source: AgentSource): string {
  return SOURCE_LABEL[source]
}

/** 列表行上那句「谁的、哪一版」。引用了什么必须写在每一轮旁边，否则说不清是谁在生效。 */
export function listingCaption(listing: AgentListing): string {
  return `${listing.owner_name} · v${listing.version} · ${sourceLabel(listing.source)}`
}

/**
 * 一个条目是「场景」还是「智能体」。
 *
 * **判据是客观事实，不是一个人工标注的类型字段** —— 挂了子智能体的就是场景。
 * 这条规则由 P6-decision G2 定下，后端的 `subagent-candidates` 一直按它过滤；
 * 前端沿用同一条，两边才不会各算各的。
 *
 * 加一个 `kind` 列会造出第二个真相源：一旦出现「kind=agent 却挂着子智能体」的行，
 * 候选列表该信哪一个就说不清了。
 */
export function isScenario(item: { subagent_refs?: unknown[] | null }): boolean {
  return (item.subagent_refs?.length ?? 0) > 0
}

/** 智能体广场上该出现的：没挂子智能体的那些，它们同时也是子智能体的候选。 */
export function onlyAgents<T extends { subagent_refs?: unknown[] | null }>(items: T[]): T[] {
  return items.filter(one => !isScenario(one))
}

/** 场景库里该出现的：挂了子智能体的那些。 */
export function onlyScenarios<T extends { subagent_refs?: unknown[] | null }>(items: T[]): T[] {
  return items.filter(isScenario)
}
