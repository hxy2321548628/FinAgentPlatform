import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { agentKeys, listMine } from '../../api/agents'
import { errorMessage } from '../../api/request'
import { listThreads, threadKeys } from '../../api/threads'
import { myUsage, usageKeys } from '../../api/usage'
import type { ThreadSummary } from '../../api/types'
import { Skeleton } from '../../components/ui/Skeleton'

const QUICK_ACTIONS = [
  { label: '新建分析对话', desc: '直接描述需求，智能体开始工作', to: '/workspace/chat',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> },
  { label: '浏览场景库', desc: '从预设分析场景快速启动', to: '/workspace/scenarios',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
  { label: '配置我的智能体', desc: '组合提示词、Skills 与 MCP 能力', to: '/workspace/my-agents',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="1" fill="currentColor"/></svg> },
]

function isThisMonth(iso: string): boolean {
  const at = new Date(iso)
  const now = new Date()
  return at.getFullYear() === now.getFullYear() && at.getMonth() === now.getMonth()
}

function relativeTime(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  return days < 30 ? `${days} 天前` : new Date(iso).toLocaleDateString('zh-CN')
}

function StatCard({ label, value, unit, hint }: { label: string; value: string; unit: string; hint?: string }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '18px 20px',
    }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase' as const, letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", fontVariantNumeric: 'tabular-nums', lineHeight: 1, marginBottom: 4 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{unit}</div>
      {hint && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>{hint}</div>}
    </div>
  )
}

function ActionBanner() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: 'var(--bg)', border: '1px solid var(--border)',
      borderLeft: '4px solid var(--border)',
      borderRadius: 8, padding: '14px 20px', marginBottom: 20,
    }}>
      <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>从场景库开始你的下一次分析</span>
      <Link
        to="/workspace/scenarios"
        style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, textDecoration: 'none' }}
      >
        浏览场景库 →
      </Link>
    </div>
  )
}

export function Overview() {
  const [hoveredSession, setHoveredSession] = useState<string | null>(null)
  const [hoveredAction, setHoveredAction] = useState<string | null>(null)

  // **必须与 ThreadSidebar / MyData 一样用 useInfiniteQuery。**
  // 同一个 queryKey 在 React Query 里只有一份缓存，而两种 hook 存的形状不同
  // （infinite 是 {pages:[…]}，普通 query 是 {items:…}）—— 混用的话谁先加载
  // 谁的形状占住这个键，另一边读到的字段全是 undefined，页面就是一片空白。
  // 保持一致还顺带让两边共享缓存：总览加载过，进对话时侧边栏立刻就有内容
  const threads = useInfiniteQuery({
    queryKey: threadKeys.list(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listThreads(pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })
  const usage = useQuery({ queryKey: usageKeys.mine(), queryFn: myUsage })
  const agents = useQuery({ queryKey: agentKeys.mine(), queryFn: listMine })

  // **「本月会话」是对全量的统计，只数第一页会静默偏小。** 有界地翻完剩余页
  // （最多 10 页/200 条，教师量级碰不到上限；超过时统计仍偏小但不阻塞页面），
  // 翻进来的页落在共享缓存里，侧边栏顺带受益。
  useEffect(() => {
    if (!threads.hasNextPage || threads.isFetchingNextPage) return
    if ((threads.data?.pages.length ?? 0) < 10) void threads.fetchNextPage()
  }, [threads])

  const items: ThreadSummary[] = threads.data?.pages.flatMap(page => page.items) ?? []
  const recent = items.slice(0, 5)
  const monthlyThreads = items.filter(one => isThisMonth(one.created_at)).length
  const agentCalls = (agents.data ?? []).reduce((sum, one) => sum + one.call_count, 0)

  // **没接账本与「这个月还没用」要显示得不一样。** 都写 0 的话，教师看到的是
  // 一个说不清是真是假的数字
  const tokenValue = usage.data?.available ? `${(usage.data.tokens / 1000).toFixed(1)}K` : '—'
  const tokenHint = usage.data && !usage.data.available ? '用量账本未接入' : undefined
  const callValue = usage.data?.available ? String(usage.data.observations) : '—'

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ marginBottom: 24 }}>
        <div className="page-eyebrow">
          // OVERVIEW
        </div>
        <h1 className="page-title">总览</h1>
        <p className="page-desc">
          {new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
        </p>
      </div>

      <ActionBanner />

      {/* 统计卡片。**四张都有真实来源** —— 配额进度条去掉了：配额按天算，
          这一排看的是本月，两个口径凑成一个百分比只会得出一个没有意义的数 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
        <StatCard label="本月会话" value={String(monthlyThreads)} unit="个会话" />
        <StatCard label="Token 消耗" value={tokenValue} unit="本月累计" hint={tokenHint} />
        <StatCard label="模型调用" value={callValue} unit="次（本月）" />
        <StatCard label="Agent 调用" value={String(agentCalls)} unit="次（我发布的）" />
      </div>

      {/* 下半部分：最近会话 + 快速入口 */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>

        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>最近会话</div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
            {threads.isPending && Array.from({ length: 4 }, (_, i) => <div key={i} style={{ padding: '12px 16px', borderBottom: i < 3 ? '1px solid var(--border-light)' : 'none', display: 'flex', flexDirection: 'column', gap: 6 }}><Skeleton width="55%" height={13} /><Skeleton width="30%" height={11} /></div>)}
            {threads.isError && <div role="alert" style={{ ...emptyStyle, color: 'var(--danger)' }}>{errorMessage(threads.error)}</div>}
            {!threads.isPending && !threads.isError && recent.length === 0 && (
              <div style={emptyStyle}>还没有会话，从右边开一个吧</div>
            )}
            {recent.map((session, i) => (
              <Link
                key={session.id}
                to={`/workspace/chat/${session.id}`}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderBottom: i < recent.length - 1 ? '1px solid var(--border-light)' : 'none',
                  textDecoration: 'none',
                  transition: 'background 0.15s',
                  background: hoveredSession === session.id ? 'var(--bg)' : 'transparent',
                }}
                onMouseEnter={() => setHoveredSession(session.id)}
                onMouseLeave={() => setHoveredSession(null)}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 3 }}>
                    {session.title || '（未命名会话）'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                    {relativeTime(session.updated_at)}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>快速入口</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {QUICK_ACTIONS.map(item => (
              <Link
                key={item.to}
                to={item.to}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 8, padding: '14px 16px',
                  textDecoration: 'none',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                  borderColor: hoveredAction === item.to ? 'var(--action-border)' : 'var(--border)',
                  boxShadow: hoveredAction === item.to ? '0 2px 8px rgba(23,73,196,0.08)' : 'none',
                }}
                onMouseEnter={() => setHoveredAction(item.to)}
                onMouseLeave={() => setHoveredAction(null)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ display: 'flex', alignItems: 'center', color: 'var(--action)' }}>{item.icon}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingLeft: 24 }}>{item.desc}</div>
              </Link>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}

const emptyStyle: React.CSSProperties = { padding: '40px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }
