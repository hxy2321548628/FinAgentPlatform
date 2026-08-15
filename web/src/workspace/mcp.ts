import type { AgentListing, McpServer } from '../api/types'

/**
 * 外发标注：**每一条 MCP 都要显示它，与申请人怎么声明无关。**
 *
 * 平台的 MCP 一律部署在校外（这是 F3 定的前提），于是勾上任何一条就意味着这次分析
 * 的数据会离开校园网。教师是否知情是平台唯一还握在手里的东西 —— 代码通读与隔离部署
 * 两样在改成全外网之后都没有了。
 *
 * **两条路径都要看得见**：直接勾一个 MCP，以及选一个自带 MCP 的智能体 / 子智能体。
 * 漏掉后一条的话，「组合起来才出现的风险」就退回敞着的状态 —— 教师以为自己什么都
 * 没勾，实际那个场景背后连着一台校外机器。
 */
export const DATA_LEAVES_CAMPUS = '此服务位于校外，调用时你的数据会发送至外部'

/** 一条要展示的 MCP：可能来自直接勾选，也可能是某个智能体自带的。 */
export interface MountedMcp {
  serverId: string
  name: string
  /** 它是怎么被挂上的，界面据此说清「你没勾但它在」。 */
  via: string | null
}

/**
 * 把「直接勾的」与「所选智能体 / 子智能体自带的」合成一份最终清单。
 *
 * **子智能体那一条不能漏。** `P10⑥` 的第二条链路走的正是它：教师一个 MCP 都没勾，
 * 只选了一个场景，而那个场景背后的子智能体连着校外机器。漏掉它的话，这条组合风险
 * 就从「已缓解」退回「敞着」—— 而界面上看不出任何异样。
 *
 * 自带的排在前面，与后端解析时的顺序一致 —— 两边顺序不同的话，界面上说的
 * 「最终挂载」与快照里冻结的那一份对不上，而对不上时没有任何一处会报错。
 */
export function mountedMcps(
  carriers: readonly (AgentListing | undefined)[],
  selected: readonly McpServer[],
): MountedMcp[] {
  const bundled: MountedMcp[] = carriers.flatMap(carrier =>
    (carrier?.mcp_refs ?? []).map(one => ({ serverId: one.server_id, name: one.name, via: carrier?.name ?? null })),
  )
  const picked: MountedMcp[] = selected.map(one => ({ serverId: one.id, name: one.name, via: null }))
  const merged = new Map<string, MountedMcp>()
  for (const one of [...bundled, ...picked]) {
    if (!merged.has(one.serverId)) merged.set(one.serverId, one)
  }
  return [...merged.values()]
}
