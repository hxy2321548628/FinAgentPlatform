import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { agentKeys, listCatalog, listMine } from '../../api/agents'
import { errorMessage } from '../../api/request'
import type { AgentListing, MyAgent } from '../../api/types'
import { handOffAgent } from '../pickedAgent'
import { CatalogCard } from '../components/Catalog'
import { isScenario, onlyScenarios } from '../agent'

export function ScenarioLibrary() {
  const query = useQuery({ queryKey: agentKeys.catalog(), queryFn: listCatalog })
  return <ScenarioPage title="场景库" description="浏览平台审核通过的可复用分析场景" loading={query.isPending} error={query.isError ? errorMessage(query.error) : null}>
    <ListingCards items={query.data ?? []} />
  </ScenarioPage>
}

export function MyScenarios() {
  const query = useQuery({ queryKey: agentKeys.mine(), queryFn: listMine })
  const items = (query.data ?? []).filter(one => !one.is_deleted)
  return <ScenarioPage title="我的场景" description="管理你保存的分析配置与个人场景" loading={query.isPending} error={query.isError ? errorMessage(query.error) : null}>
    <MyScenarioCards items={items} />
  </ScenarioPage>
}

function ScenarioPage({ title, description, loading, error, children }: { title: string; description: string; loading: boolean; error: string | null; children: React.ReactNode }) {
  return <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
    <div style={{ padding: '28px 36px 20px' }}>
      <div className="page-eyebrow">// SCENARIO LIBRARY</div>
      <h1 className="page-title">{title}</h1>
      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{description}</p>
    </div>
    {loading && <div style={noticeStyle}>正在加载…</div>}
    {error && <div role="alert" style={{ ...noticeStyle, color: 'var(--danger)' }}>{error}</div>}
    {!loading && !error && children}
  </div>
}

function ListingCards({ items }: { items: AgentListing[] }) {
  const navigate = useNavigate()
  // **场景库只放场景** —— 只有提示词的那些是「智能体」，它们在广场
  const shown = onlyScenarios(items).sort((a, b) => b.call_count - a.call_count || a.name.localeCompare(b.name, 'zh-CN'))
  if (shown.length === 0) return <div style={noticeStyle}>暂无可用场景</div>
  return <div style={gridStyle}>{shown.map(item => <CatalogCard key={item.id} title={item.name} version={`v${item.version}`} author="我" subject={item.subject || '未分类'} description={item.description || '（作者没有写说明）'} detail={`${item.subagent_refs?.length ?? 0} 个子智能体 · ${item.skill_refs?.length ?? 0} 个 Skill`} badges={['广场可见']} metric={`${item.call_count} 次调用`} primaryAction={{ label: '使用场景', onClick: () => { handOffAgent(item.id); navigate('/workspace/chat') } }} />)}</div>
}

function MyScenarioCards({ items }: { items: MyAgent[] }) {
  const navigate = useNavigate()
  // 「我的场景」同样只列挂了子智能体的；纯提示词的那些在「我的智能体」。
  // **按最新一版判**：作者可能刚给一个智能体加上子智能体，那一刻它就变成场景了
  const shown = items
    .filter(one => {
      const latest = one.versions.at(-1)
      return latest !== undefined && isScenario(latest)
    })
    .sort((a, b) => b.call_count - a.call_count || a.name.localeCompare(b.name, 'zh-CN'))
  if (shown.length === 0) return <div style={noticeStyle}>还没有保存过场景</div>
  return <div style={gridStyle}>{shown.map(item => {
    const released = [...item.versions].reverse().find(one => one.status === 'released') ?? item.versions.at(-1)
    const skillCount = released?.skill_refs?.length ?? 0
    const subagentCount = released?.subagent_refs?.length ?? 0
    return <CatalogCard key={item.id} title={item.name} version={released ? `v${released.version}` : undefined} author="我" subject={item.subject || '未分类'} description={item.description || '（没有写说明）'} detail={`${subagentCount} 个子智能体 · ${skillCount} 个 Skill`} badges={['我的场景']} metric={`${item.call_count} 次调用`} primaryAction={{ label: '编辑场景', onClick: () => navigate(`/workspace/my-agents/${item.id}/edit`) }} />
  })}</div>
}

const gridStyle: React.CSSProperties = { padding: '0 36px 32px', display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }
const noticeStyle: React.CSSProperties = { padding: '60px 36px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }
