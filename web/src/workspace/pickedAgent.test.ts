import { afterEach, describe, expect, it } from 'vitest'
import { handOffAgent, handOffConfig, takeHandedOffAgent, takeHandedOffConfig } from './pickedAgent'

afterEach(() => sessionStorage.clear())

describe('聊天配置交接', () => {
  it('交接一份 Skill 配置且只取一次', () => {
    handOffConfig({ skills: ['skill-1'] })

    expect(takeHandedOffConfig()).toEqual({ skills: ['skill-1'] })
    expect(takeHandedOffConfig()).toBeUndefined()
  })

  it('保留智能体交接兼容接口', () => {
    handOffAgent('agent-1')

    expect(takeHandedOffAgent()).toBe('agent-1')
  })
})
