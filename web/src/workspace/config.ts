import type { AgentConfig, AgentListing } from '../api/types'

export const MAX_SYSTEM_PROMPT_LENGTH = 4000

/**
 * 本轮配置的四种模式，**互斥**。
 *
 * `agent` 与 `custom` 是同一件事的两条路（这一轮用谁的角色段），后端拿到两样一律 422。
 * **互斥规则错了的表现是 422 而不是崩溃** —— 用户看到的是一句莫名其妙的报错，
 * 因此这一层的职责是让那种请求根本发不出去。
 */
export type AgentConfigMode = 'inherit' | 'default' | 'custom' | 'agent'

export const AGENT_CONFIG_MODES = ['inherit', 'default', 'agent', 'custom'] as const

export const AGENT_CONFIG_MODE_LABEL: Record<AgentConfigMode, string> = {
  inherit: '继承会话默认',
  default: '恢复平台默认',
  agent: '选一个智能体',
  custom: '本轮自定义提示词',
}

export function systemPromptError(prompt: string): string | null {
  if (!prompt.trim()) return '请输入自定义提示词'
  if (prompt.length > MAX_SYSTEM_PROMPT_LENGTH) return '自定义提示词不能超过 4000 字符'
  return null
}

export function agentChoiceError(agentId: string): string | null {
  return agentId ? null : '请先选一个智能体'
}

/**
 * 按当前模式拼出这一轮要发的 `agent_config`。
 *
 * @returns `undefined` 表示这一轮不带这个字段（继承会话默认）；空对象表示整块改回
 *   平台默认。**这两者不是同一件事**，合并的话「恢复平台默认」会静默变成「继承」。
 * @throws 模式要求的输入没填全。
 */
export function buildRunAgentConfig(
  mode: AgentConfigMode,
  prompt: string,
  agentId = '',
  skillIds: string[] = [],
  subagentIds: string[] = [],
): AgentConfig | undefined {
  const additions: AgentConfig = {}
  if (skillIds.length > 0) additions.skills = skillIds
  if (subagentIds.length > 0) additions.subagents = subagentIds
  const hasAdditions = Object.keys(additions).length > 0
  if (mode === 'inherit') return hasAdditions ? additions : undefined
  if (mode === 'default') return additions
  if (mode === 'agent') {
    const error = agentChoiceError(agentId)
    if (error) throw new Error(error)
    return { agent_id: agentId, ...additions }
  }
  const error = systemPromptError(prompt)
  if (error) throw new Error(error)
  return { system_prompt: prompt, ...additions }
}

/**
 * 把一份配置说成一句人话。
 *
 * **引用要说清是谁的哪一版**：只说「使用了一个智能体」的话，作者发了新版本之后，
 * 历史那几轮到底按哪一版跑的就再也说不清了。
 */
export function describeAgentConfig(
  config: AgentConfig | null | undefined,
  available: readonly AgentListing[] = [],
): string {
  let role: string
  if (config?.agent_id) {
    const found = available.find(one => one.id === config.agent_id)
    const version = config.agent_version ? ` · v${config.agent_version}` : ''
    role = `智能体：${found ? found.name : config.agent_id}${version}`
  } else {
    role = config?.system_prompt ? config.system_prompt : '平台默认配置'
  }
  const skills = config?.skills?.filter((one): one is import('../api/types').SkillReference => typeof one !== 'string') ?? []
  return skills.length > 0 ? `${role}
Skills：${skills.map(one => `${one.name} · v${one.version}`).join('、')}` : role
}
