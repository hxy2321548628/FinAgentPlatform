import type { AgentConfig } from '../api/types'

export const MAX_SYSTEM_PROMPT_LENGTH = 4000

export type AgentConfigMode = 'inherit' | 'default' | 'custom'

export function systemPromptError(prompt: string): string | null {
  if (!prompt.trim()) return '请输入自定义提示词'
  if (prompt.length > MAX_SYSTEM_PROMPT_LENGTH) return '自定义提示词不能超过 4000 字符'
  return null
}

export function buildRunAgentConfig(mode: AgentConfigMode, prompt: string): AgentConfig | undefined {
  if (mode === 'inherit') return undefined
  if (mode === 'default') return {}
  const error = systemPromptError(prompt)
  if (error) throw new Error(error)
  return { system_prompt: prompt }
}

export function describeAgentConfig(config: AgentConfig | null | undefined): string {
  const prompt = config?.system_prompt
  return prompt ? prompt : '平台默认配置'
}
