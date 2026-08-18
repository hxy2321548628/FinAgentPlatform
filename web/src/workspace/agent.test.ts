import { describe, expect, it } from 'vitest'
import type { AgentListing, AgentVersion, MyAgent, ReviewStatus, VersionStatus } from '../api/types'
import { agentState, listingCaption, sourceLabel, visibilityBadges } from './agent'

function version(
  number: number,
  status: VersionStatus,
  review: ReviewStatus | null = null,
  reason: string | null = null,
): AgentVersion {
  return {
    id: `v${number}`,
    version: number,
    status,
    system_prompt: `第 ${number} 版`,
    created_at: '2026-08-14T00:00:00Z',
    released_at: status === 'released' ? '2026-08-14T01:00:00Z' : null,
    review_id: review ? `r${number}` : null,
    review_status: review,
    review_reason: reason,
  }
}

function agent(versions: AgentVersion[], extra: Partial<MyAgent> = {}): MyAgent {
  return {
    id: 'a1',
    name: '喵语老师',
    description: '说话带喵',
    subject: '金融学',
    visibility: 'private',
    call_count: 0,
    is_deleted: false,
    in_catalog: false,
    catalog_enabled: true,
    catalog_disabled_reason: null,
    catalog_disabled_by: null,
    catalog_disabled_at: null,
    group_ids: [],
    versions,
    created_at: '2026-08-14T00:00:00Z',
    updated_at: '2026-08-14T00:00:00Z',
    ...extra,
  }
}

describe('agentState', () => {
  it('puts an agent that never released anything in the draft tab', () => {
    expect(agentState(agent([version(1, 'draft')])).tab).toBe('draft')
  })

  it('puts a released but never submitted agent in the published tab', () => {
    // 已发布 = 定稿、组员用得上。**进不进广场是另一回事**
    const state = agentState(agent([version(1, 'released')]))

    expect(state.tab).toBe('published')
    expect(state.reviewStatus).toBeNull()
  })

  it('puts a pending review in the reviewing tab even when a version is already on the plaza', () => {
    // 一个 agent 可以同时在广场上、又有一版在等审 —— 作者这时最关心的是审核走到哪了
    const state = agentState(
      agent([version(1, 'released', 'approved'), version(2, 'released', 'pending')], { in_catalog: true }),
    )

    expect(state.tab).toBe('reviewing')
    expect(state.released?.version).toBe(2)
  })

  it('keeps a rejected agent in the reviewing tab with its reason word for word', () => {
    const state = agentState(agent([version(1, 'released', 'rejected', '提示词过于宽泛')]))

    expect(state.tab).toBe('reviewing')
    expect(state.rejectedReason).toBe('提示词过于宽泛')
  })

  it('does not report a reason when the review passed', () => {
    const state = agentState(agent([version(1, 'released', 'approved')], { in_catalog: true }))

    expect(state.tab).toBe('published')
    expect(state.rejectedReason).toBeNull()
  })

  it('reports the newest released version and the current draft separately', () => {
    const state = agentState(agent([version(1, 'released'), version(2, 'released'), version(3, 'draft')]))

    expect(state.released?.version).toBe(2)
    expect(state.draft?.version).toBe(3)
    // 改了一版没发布，不该把它从「已发布」页签里挪走
    expect(state.tab).toBe('published')
  })

  it('reads the review status off the newest released version, not the oldest', () => {
    const state = agentState(agent([version(1, 'released', 'approved'), version(2, 'released')], { in_catalog: true }))

    expect(state.reviewStatus).toBeNull()
    expect(state.tab).toBe('published')
  })
})

describe('visibilityBadges', () => {
  it('says private when nobody else can see it', () => {
    expect(visibilityBadges(agent([version(1, 'draft')]))).toEqual(['私有'])
  })

  it('shows both the plaza and the group sharing at once', () => {
    const badges = visibilityBadges(
      agent([version(1, 'released', 'approved')], { in_catalog: true, visibility: 'group', group_ids: ['g1', 'g2'] }),
    )

    expect(badges).toEqual(['平台广场', '组内共享 · 2 个组'])
  })

  it('does not claim group sharing when the visibility was turned back to private', () => {
    // 共享的组行留着，闸门是可见性那一档 —— 显示成「还共享着」会让作者以为没撤回成功
    const badges = visibilityBadges(agent([version(1, 'released')], { visibility: 'private', group_ids: ['g1'] }))

    expect(badges).toEqual(['私有'])
  })
})

describe('sourceLabel', () => {
  it('never calls a group share a plaza listing', () => {
    expect(sourceLabel('owned')).toBe('我创建的')
    expect(sourceLabel('group')).toBe('组内共享')
    expect(sourceLabel('catalog')).toBe('平台广场')
  })

  it('captions a listing with its author, version and source', () => {
    const listing: AgentListing = {
      id: 'a1',
      owner_id: 'u1',
      owner_name: '张老师',
      name: '喵语老师',
      description: '',
      subject: '金融学',
      visibility: 'group',
      call_count: 3,
      version: 2,
      system_prompt: '每句以喵开头',
      source: 'group',
      updated_at: '2026-08-14T00:00:00Z',
    }

    expect(listingCaption(listing)).toBe('张老师 · v2 · 组内共享')
  })
})
