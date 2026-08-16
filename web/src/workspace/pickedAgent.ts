import type { AgentConfig } from '../api/types'

const KEY = 'zuel.picked-agent-config'

/**
 * 能力目录「使用」→ 新分析页配置面板的交接。
 *
 * **走 sessionStorage 而不是路由 state**：从目录跳过去时多半还没有会话，教师要先点一下
 * 「新建分析」，而那一下是一次不带 state 的跳转 —— 路由 state 在那一步就丢了。
 *
 * **取走即清掉**：留着的话，下一次自己开一个新会话时会莫名其妙地沿用上一次配置。
 */
export function handOffConfig(config: AgentConfig): void {
  sessionStorage.setItem(KEY, JSON.stringify(config))
}

export function takeHandedOffConfig(): AgentConfig | undefined {
  const value = sessionStorage.getItem(KEY)
  if (!value) return undefined
  sessionStorage.removeItem(KEY)
  try {
    return JSON.parse(value) as AgentConfig
  } catch {
    return undefined
  }
}

/** 兼容智能体广场的已有调用。 */
export function handOffAgent(agentId: string): void {
  handOffConfig({ agent_id: agentId })
}

/** 兼容旧调用；非纯智能体交接返回 undefined。 */
export function takeHandedOffAgent(): string | undefined {
  return takeHandedOffConfig()?.agent_id ?? undefined
}
