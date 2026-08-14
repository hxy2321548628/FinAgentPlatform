import { describe, expect, it } from 'vitest'
import { MAX_SYSTEM_PROMPT_LENGTH, buildRunAgentConfig, describeAgentConfig, systemPromptError } from './config'

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
})
