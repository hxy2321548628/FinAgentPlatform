import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { agentKeys, listAvailable } from '../../api/agents'
import { onlyAgents } from '../agent'
import { errorMessage } from '../../api/request'
import type { AgentListing } from '../../api/types'
import { sourceLabel } from '../agent'
import { handOffAgent } from '../pickedAgent'
import { CatalogCard, CatalogControls } from '../components/Catalog'
import { Skeleton } from '../../components/ui/Skeleton'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'

const SUBJECT_FILTERS = ['全部', '公司金融', '量化投资', '资产管理', '风险管理', '学术科研', '会计审计', '其他']

/**
 * 智能体广场。
 *
 * **两个范围是两条不同的查询，不是同一份数据的筛选**：广场只有审核通过的那些
 * （展示的是过审的那一版），「我能用的」还包含我自己的与共享给我所在组的
 * （展示的是最新已发布的那一版）。合成一个列表再前端过滤，就等于把可见性判断
 * 搬到了浏览器里 —— 那是本期最不该出现的形状。
 */
export function AgentPlaza() {
  const navigate = useNavigate()
  const [subject, setSubject] = useState('全部')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<AgentListing | null>(null)

  const current = useQuery({ queryKey: agentKeys.available(), queryFn: listAvailable })

  // **广场只放智能体，场景在场景库。** 判据是「有没有挂子智能体」这个客观事实
  // （P6-decision G2），与后端 subagent-candidates 用的是同一条
  const shown = onlyAgents(current.data ?? []).filter(one => {
    const bySubject = subject === '全部' || one.subject === subject
    const byText = !search || one.name.includes(search) || one.description.includes(search) || one.owner_name.includes(search)
    return bySubject && byText
  }).sort((a, b) => b.call_count - a.call_count || a.name.localeCompare(b.name, 'zh-CN'))

  const startAnalysis = (agent: AgentListing) => {
    handOffAgent(agent.id)
    navigate('/workspace/chat')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0' }}>
        <div className="page-eyebrow">// AGENT PLAZA</div>
        <h1 className="page-title">智能体广场</h1>
        <p className="page-desc">你此刻能引用的全部智能体，广场可见优先展示审核通过的版本</p>
      </div>

      <CatalogControls
        search={search}
        onSearch={setSearch}
        placeholder="搜索名称、说明或作者…"
        filters={SUBJECT_FILTERS.map(key => ({ key, label: key }))}
        activeFilter={subject}
        onFilter={setSubject}
      />

      {/* data-loaded 是端到端走查唯一能等的「列表已加载完」信号：断言「别组看不见」
          时列表若还停在骨架屏，那一条必然成立，而那是最典型的假绿 */}
      <div data-testid="agent-plaza-list" data-loaded={String(!current.isPending)} style={{ padding: '0 36px 32px' }}>
        {current.isPending && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {Array.from({ length: 6 }, (_, i) => <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column', gap: 10 }}><Skeleton width="55%" height={15} /><Skeleton width="30%" height={12} /><Skeleton width="100%" height={12} /><Skeleton width="85%" height={12} /></div>)}
          </div>
        )}
        {current.isError && <div role="alert" style={{ padding: '60px 0', textAlign: 'center', color: 'var(--danger)' }}>{errorMessage(current.error)}</div>}
        {!current.isPending && shown.length === 0 && (
          <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            {search ? `未找到与「${search}」相关的智能体` : '还没有你能引用的智能体'}
          </div>
        )}
        {shown.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {shown.map(agent => (
              <CatalogCard
                key={agent.id}
                title={agent.name}
                version={`v${agent.version}`}
                author={agent.owner_name}
                subject={agent.subject || '未分类'}
                description={agent.description || '（作者没有写说明）'}
                detail={`可见范围：${agent.source === 'catalog' ? '广场可见' : agent.source === 'group' ? '组内共享' : '仅自己可用'}`}
                badges={[agent.source === 'catalog' ? '广场可见' : agent.source === 'group' ? '组内共享' : '我的智能体']}
                metric={`${agent.call_count} 次调用`}
                secondaryAction={{ label: '查看提示词', onClick: () => setDetail(agent) }}
                primaryAction={{ label: '用它开始分析', onClick: () => startAnalysis(agent) }}
              />
            ))}
          </div>
        )}
        {shown.length > 0 && <div style={{ padding: '20px 0 0', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>共 {shown.length} 个智能体</div>}
      </div>

      {detail && <PromptDrawer agent={detail} onClose={() => setDetail(null)} onUse={() => { setDetail(null); startAnalysis(detail) }} />}
    </div>
  )
}

/**
 * 详情抽屉，**渲染提示词全文**。
 *
 * 看不到内容就判断不了一个 agent 值不值得用，而「共享出去的东西别人看得见内容」
 * 本来就是共享的含义。
 */
function PromptDrawer({ agent, onClose, onUse }: { agent: AgentListing; onClose: () => void; onUse: () => void }) {
  return (
    <Dialog.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" onClick={onClose} />
        <Dialog.Content className="dialog-content dialog-drawer" aria-describedby={undefined}>
          <div className="dialog-drawer-header">
            <Dialog.Title className="dialog-title" style={{ marginBottom: 3 }}>
              {agent.name}
              <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginTop: 3 }}>
                {agent.owner_name} · {agent.subject || '未分类'} · v{agent.version} · {sourceLabel(agent.source)}
              </div>
            </Dialog.Title>
            <Dialog.Close asChild>
              <button aria-label="关闭" className="dialog-close-x" style={{ position: 'static' }}>×</button>
            </Dialog.Close>
          </div>
          <div className="dialog-drawer-body">
            <div style={{ marginBottom: 16 }}>
              <div style={sectionTitle}>功能描述</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{agent.description || '（作者没有写说明）'}</div>
            </div>
            <div>
              <div style={sectionTitle}>系统提示词全文</div>
              <div data-testid="agent-prompt" style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
                {agent.system_prompt}
              </div>
            </div>
          </div>
          <div className="dialog-drawer-footer">
            <Button style={{ width: '100%' }} size="lg" onClick={onUse}>用它开始分析 →</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const sectionTitle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase',
  letterSpacing: '0.1em', marginBottom: 8,
}
