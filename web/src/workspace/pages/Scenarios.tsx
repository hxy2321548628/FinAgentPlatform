import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { agentKeys, listCatalog } from '../../api/agents'
import { errorMessage } from '../../api/request'
import type { AgentListing } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { CatalogCard, CatalogControls, type CatalogFilter } from '../components/Catalog'
import { onlyScenarios } from '../agent'
import { handOffAgent } from '../pickedAgent'
import { MyAgents } from './MyAgents'

export function ScenarioLibrary() {
  const navigate = useNavigate()
  const query = useQuery({ queryKey: agentKeys.catalog(), queryFn: listCatalog })
  const [search, setSearch] = useState('')
  const [subject, setSubject] = useState('全部')
  const [detail, setDetail] = useState<AgentListing | null>(null)
  const items = onlyScenarios(query.data ?? []).sort((a, b) => b.call_count - a.call_count || a.name.localeCompare(b.name, 'zh-CN'))
  const filters: CatalogFilter[] = ['全部', ...new Set(items.map(one => one.subject || '未分类'))].map(key => ({ key, label: key }))
  const normalized = search.trim().toLocaleLowerCase('zh-CN')
  const shown = items.filter(item => {
    const matchesSubject = subject === '全部' || (item.subject || '未分类') === subject
    const haystack = `${item.name} ${item.description} ${item.owner_name}`.toLocaleLowerCase('zh-CN')
    return matchesSubject && (!normalized || haystack.includes(normalized))
  })
  const handleUseScenario = (item: AgentListing) => {
    handOffAgent(item.id)
    navigate('/workspace/chat')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0' }}>
        <div className="page-eyebrow">// SCENARIO LIBRARY</div>
        <h1 className="page-title">场景库</h1>
        <p className="page-desc">浏览平台审核通过的完整分析配置：系统提示词、Skills、MCP 与子智能体</p>
      </div>
      <CatalogControls search={search} onSearch={setSearch} placeholder="搜索场景名称、说明或作者…" filters={filters} activeFilter={subject} onFilter={setSubject} />
      <div style={{ padding: '0 36px 32px' }}>
        {query.isPending && <ScenarioNotice>正在加载场景…</ScenarioNotice>}
        {query.isError && <ScenarioNotice error>{errorMessage(query.error)}</ScenarioNotice>}
        {!query.isPending && !query.isError && shown.length === 0 && (
          <div style={emptyStyle}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>◇</div>
            <div style={{ fontSize: 15, fontWeight: 650, color: 'var(--text-primary)', marginBottom: 6 }}>
              {normalized ? `未找到与「${search}」相关的场景` : '还没有审核通过的场景'}
            </div>
            <p style={{ margin: '0 0 18px', fontSize: 13, lineHeight: 1.7 }}>你可以先创建一份场景配置，发布并提交审核；通过后会自动进入这里供其他教师使用。</p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
              <Button variant="secondary" onClick={() => navigate('/workspace/chat')}>开始新分析</Button>
              <Button onClick={() => navigate('/workspace/my-scenarios/create')}>创建场景</Button>
            </div>
          </div>
        )}
        {shown.length > 0 && <>
          <div style={gridStyle}>
            {shown.map(item => (
              <CatalogCard
                key={item.id}
                title={item.name}
                version={`v${item.version}`}
                author={item.owner_name}
                subject={item.subject || '未分类'}
                description={item.description || '（作者没有写说明）'}
                detail={`${item.subagent_refs?.length ?? 0} 个子智能体 · ${item.skill_refs?.length ?? 0} 个 Skill · ${item.mcp_refs?.length ?? 0} 个 MCP`}
                badges={['平台场景']}
                metric={`${item.call_count} 次调用`}
                secondaryAction={{ label: '查看配置', onClick: () => setDetail(item) }}
                primaryAction={{ label: '使用场景', onClick: () => handleUseScenario(item) }}
              />
            ))}
          </div>
          <div style={{ paddingTop: 20, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>共 {shown.length} 个场景</div>
        </>}
      </div>
      {detail && <ScenarioDetail item={detail} onUse={() => handleUseScenario(detail)} onClose={() => setDetail(null)} />}
    </div>
  )
}

export function MyScenarios() {
  return <MyAgents kind="scenario" />
}

function ScenarioDetail({ item, onUse, onClose }: { item: AgentListing; onUse: () => void; onClose: () => void }) {
  return (
    <Dialog.Root defaultOpen onOpenChange={open => { if (!open) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" onClick={onClose} />
        <Dialog.Content className="dialog-content dialog-drawer" aria-describedby={undefined}>
          <div className="dialog-drawer-header">
            <Dialog.Title className="dialog-title" style={{ marginBottom: 0 }}>{item.name}<div style={{ marginTop: 3, fontSize: 12, fontWeight: 400, color: 'var(--text-muted)' }}>{item.owner_name} · {item.subject || '未分类'} · v{item.version}</div></Dialog.Title>
            <Dialog.Close asChild><button aria-label="关闭" className="dialog-close-x" style={{ position: 'static' }}>×</button></Dialog.Close>
          </div>
          <div className="dialog-drawer-body">
            <p style={{ margin: '0 0 18px', fontSize: 13, lineHeight: 1.75, color: 'var(--text-secondary)' }}>{item.description || '（作者没有写说明）'}</p>
            <DetailSection title="系统提示词"><pre style={promptStyle}>{item.system_prompt}</pre></DetailSection>
            <DetailSection title={`Skills（${item.skill_refs?.length ?? 0}）`}><ReferenceList items={(item.skill_refs ?? []).map(one => `${one.name} · v${one.version}`)} empty="未挂载 Skill" /></DetailSection>
            <DetailSection title={`MCP（${item.mcp_refs?.length ?? 0}）`}><ReferenceList items={(item.mcp_refs ?? []).map(one => one.name)} empty="未挂载 MCP" /></DetailSection>
            <DetailSection title={`子智能体（${item.subagent_refs?.length ?? 0}）`}><ReferenceList items={(item.subagent_refs ?? []).map(one => `${one.name} · v${one.version}`)} empty="未挂载子智能体" /></DetailSection>
            <Button onClick={onUse} style={{ marginTop: 6 }}>使用场景开始分析</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section style={{ marginBottom: 18 }}><div style={{ marginBottom: 8, fontSize: 12, fontWeight: 650, color: 'var(--text-primary)' }}>{title}</div>{children}</section>
}

function ReferenceList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{empty}</div>
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{items.map(item => <span key={item} style={{ padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 5, fontSize: 12, color: 'var(--text-secondary)' }}>{item}</span>)}</div>
}

function ScenarioNotice({ error = false, children }: { error?: boolean; children: React.ReactNode }) {
  return <div role={error ? 'alert' : undefined} style={{ padding: '60px 0', textAlign: 'center', color: error ? 'var(--danger)' : 'var(--text-muted)', fontSize: 14 }}>{children}</div>
}

const gridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }
const emptyStyle: React.CSSProperties = { padding: '58px 24px', textAlign: 'center', color: 'var(--text-muted)', background: 'var(--surface)', border: '1px dashed var(--border)', borderRadius: 12 }
const promptStyle: React.CSSProperties = { margin: 0, padding: '12px 14px', maxHeight: 240, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--input-bg)', color: 'var(--text-primary)', fontSize: 12, lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace" }
