import { describe, expect, it } from 'vitest'
import {
  MAX_SYSTEM_PROMPT_LENGTH,
  agentChoiceError,
  buildRunAgentConfig,
  describeAgentConfig,
  systemPromptError,
} from './config'

describe('buildRunAgentConfig', () => {
  it('omits the field when inheriting the thread default', () => {
    expect(buildRunAgentConfig('inherit', '不应使用')).toBeUndefined()
  })

  it('uses an explicit empty object to restore the platform default', () => {
    expect(buildRunAgentConfig('default', '不应使用')).toEqual({})
  })

  it('builds a custom system prompt without changing its text', () => {
    expect(buildRunAgentConfig('custom', '　你是风险分析师　')).toEqual({
      system_prompt: '　你是风险分析师　',
    })
  })

  it('rejects blank and overlong custom prompts', () => {
    expect(systemPromptError('   ')).toBe('请输入自定义提示词')
    expect(systemPromptError('x'.repeat(MAX_SYSTEM_PROMPT_LENGTH + 1))).toContain('4000')
    expect(systemPromptError('x'.repeat(MAX_SYSTEM_PROMPT_LENGTH))).toBeNull()
  })

  it('describes the actual run snapshot', () => {
    expect(describeAgentConfig({ system_prompt: '审慎分析' })).toBe('审慎分析')
    expect(describeAgentConfig({})).toBe('平台默认配置')
    expect(describeAgentConfig(null)).toBe('平台默认配置')
  })

  it('sends only the reference when an agent is picked', () => {
    // 同时带上 system_prompt 的话后端一律 422，而用户看到的是一句莫名其妙的报错
    expect(buildRunAgentConfig('agent', '不应使用', 'agent-1')).toEqual({ agent_id: 'agent-1' })
  })

  it('refuses to send an empty agent choice', () => {
    expect(agentChoiceError('')).toBe('请先选一个智能体')
    expect(agentChoiceError('agent-1')).toBeNull()
    expect(() => buildRunAgentConfig('agent', '', '')).toThrow('请先选一个智能体')
  })

  it('ignores the picked agent when the mode is not agent', () => {
    expect(buildRunAgentConfig('custom', '自己写的', 'agent-1')).toEqual({ system_prompt: '自己写的' })
    expect(buildRunAgentConfig('inherit', '', 'agent-1')).toBeUndefined()
    expect(buildRunAgentConfig('default', '', 'agent-1')).toEqual({})
  })

  it('names the agent and the frozen version when describing a reference snapshot', () => {
    const listing = {
      id: 'agent-1',
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
    } as const

    expect(describeAgentConfig({ agent_id: 'agent-1', agent_version: 1, system_prompt: '每句以喵开头' }, [listing]))
      .toBe('智能体：喵语老师 · v1')
    // 撤回共享之后这个 agent 已经不在可用列表里，仍要说得出「用的是哪一版」
    expect(describeAgentConfig({ agent_id: 'agent-9', agent_version: 3 }, [listing])).toBe('智能体：agent-9 · v3')
  })
})
