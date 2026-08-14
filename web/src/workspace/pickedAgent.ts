const KEY = 'zuel.picked-agent'

/**
 * 广场「用它开始分析」→ 聊天页配置面板的交接。
 *
 * **走 sessionStorage 而不是路由 state**：从广场跳过去时多半还没有会话，教师要先点一下
 * 「新建分析」，而那一下是一次不带 state 的跳转 —— 路由 state 在那一步就丢了，
 * 于是这个按钮看起来什么都没做。
 *
 * **取走即清掉**：留着的话，下一次自己开一个新会话时会莫名其妙地预选上一个 agent。
 */
export function handOffAgent(agentId: string): void {
  sessionStorage.setItem(KEY, agentId)
}

export function takeHandedOffAgent(): string | undefined {
  const value = sessionStorage.getItem(KEY)
  if (value) sessionStorage.removeItem(KEY)
  return value ?? undefined
}
