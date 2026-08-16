import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { agentKeys, listPublicCatalog } from '../api/agents'
import { errorMessage } from '../api/request'
import type { PublicAgentListing } from '../api/types'
import { CatalogCard } from '../workspace/components/Catalog'
import { Skeleton } from '../components/ui/Skeleton'
import { isScenario } from '../workspace/agent'

// ── 子组件 ────────────────────────────────────────────────────

/** 场景 = 挂了子智能体的 agent（与工作台场景库同一判据，P6-decision G2）。 */
function SceneCard({ scene, onUse }: { scene: PublicAgentListing; onUse: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <article
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--action-border)' : 'var(--border)'}`,
        borderRadius: 12,
        overflow: 'hidden',
        boxShadow: hovered ? '0 8px 32px rgba(23,73,196,0.10)' : '0 1px 4px rgba(11,46,92,0.05)',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        display: 'flex', flexDirection: 'column' as const,
      }}
    >
      <div style={{ height: 4, background: 'var(--action)' }} />
      <div style={{ padding: '24px 28px', flex: 1, display: 'flex', flexDirection: 'column' as const, gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--action)', background: 'var(--action-light)', padding: '2px 8px', borderRadius: 4, border: '1px solid var(--action-border)' }}>{scene.subject || '未分类'}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>▶ {scene.call_count} 次调用</span>
          </div>
          <h3 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>{scene.name}</h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{scene.description || '（作者没有写说明）'}</p>
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.15em', marginBottom: 8 }}>由以下智能体协作</div>
          <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
            {(scene.subagent_refs ?? []).map(ref => (
              <span key={`${ref.agent_id}:${ref.version}`} style={{ fontSize: 12, padding: '3px 10px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, color: 'var(--text-secondary)' }}>
                {ref.name}
              </span>
            ))}
            <span style={{ fontSize: 12, padding: '3px 10px', background: 'var(--action-light)', border: '1px solid var(--action-border)', borderRadius: 5, color: 'var(--action)' }}>
              {scene.name}（主）
            </span>
          </div>
        </div>
      </div>
      <div style={{ padding: '16px 28px', borderTop: '1px solid var(--border-light)', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>v{scene.version} · {scene.owner_name}</span>
        <button
          onClick={onUse}
          style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          进入工作台使用
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
    </article>
  )
}

// ── 主页面 ────────────────────────────────────────────────────
export function Marketplace() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab: 'scenes' | 'agents' = searchParams.get('tab') === 'agents' ? 'agents' : 'scenes'
  const activeSubject = searchParams.get('subject') ?? '全部'
  const catalog = useQuery({ queryKey: agentKeys.publicCatalog(), queryFn: listPublicCatalog })

  // 派生全部依赖 `catalog.data`（查询缓存里的稳定引用），不要依赖每次渲染新建的数组
  const data = catalog.data
  const items = data ?? []
  const scenes = useMemo(() => (data ?? []).filter(isScenario), [data])
  const subjects = useMemo(() => ['全部', ...Array.from(new Set((data ?? []).map(one => one.subject).filter(Boolean)))], [data])
  const stats = useMemo(() => {
    const list = data ?? []
    return {
      teachers: new Set(list.map(one => one.owner_name)).size,
      calls: list.reduce((sum, one) => sum + one.call_count, 0),
      scenes: list.filter(isScenario).length,
      subjects: new Set(list.map(one => one.subject).filter(Boolean)).size,
    }
  }, [data])

  const setActiveTab = (key: 'scenes' | 'agents') => {
    const next = new URLSearchParams(searchParams)
    if (key === 'scenes') next.delete('tab')
    else next.set('tab', key)
    setSearchParams(next)
  }

  const setActiveSubject = (subject: string) => {
    const next = new URLSearchParams(searchParams)
    if (subject === '全部') next.delete('subject')
    else next.set('subject', subject)
    setSearchParams(next)
  }

  const filteredAgents = items.filter(one => !isScenario(one) && (activeSubject === '全部' || one.subject === activeSubject))

  return (
    <div>
      {/* Hero 区 */}
      <section className="grid-bg" style={{ position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '72px 80px 60px', position: 'relative' }}>
          <div style={{ maxWidth: 720 }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 16 }}>
              // AGENT MARKETPLACE
            </div>
            <h1 style={{ fontSize: 40, fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 16 }}>
              金融学院智能体市场
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 12 }}>
              将老师们的方法论封装成可复用的智能体与场景。每个场景由多个智能体协作完成，从数据到报告，全程自动化。
            </p>
            <p style={{ fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.7 }}>
              教师提交自己的分析方法 → 平台封装为智能体 → 组合成完整分析场景 → 形成学院可持续积累的 Know-How 资产库
            </p>
          </div>

          {/* 数字统计：来自真实目录，随数据实时变化 */}
          <div style={{ display: 'flex', gap: 40, marginTop: 40, paddingTop: 32, borderTop: '1px solid var(--border-light)' }}>
            {catalog.isPending && Array.from({ length: 4 }, (_, i) => <div key={i}><Skeleton width={64} height={28} /><Skeleton width={130} height={13} style={{ marginTop: 6 }} /></div>)}
            {catalog.isError && <div role="alert" style={{ fontSize: 13, color: 'var(--danger)' }}>{errorMessage(catalog.error, '目录加载失败')}</div>}
            {!catalog.isPending && !catalog.isError && (
              <>
                <Stat num={String(stats.teachers)} label="位教师发布过智能体" />
                <Stat num={String(stats.calls)} label="次智能体调用" />
                <Stat num={String(stats.scenes)} label="个协作场景" />
                <Stat num={String(stats.subjects)} label="个金融学科覆盖" />
              </>
            )}
          </div>
        </div>
      </section>

      {/* Tab 切换：协作场景 / 全部智能体 */}
      <section style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', position: 'sticky', top: 56, zIndex: 50 }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '0 80px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex' }}>
            {([['scenes', '协作场景'], ['agents', '全部智能体']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                style={{ padding: '16px 24px', fontSize: 14, fontWeight: activeTab === key ? 600 : 400, background: 'none', border: 'none', borderBottom: activeTab === key ? '2px solid var(--action)' : '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit', color: activeTab === key ? 'var(--action)' : 'var(--text-muted)', transition: 'color 0.15s' }}
              >{label}</button>
            ))}
          </div>
          <button
            onClick={() => navigate('/workspace')}
            style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >进入工作台使用 →</button>
        </div>
      </section>

      {/* 协作场景 */}
      {activeTab === 'scenes' && (
        <section style={{ background: 'var(--bg)' }}>
          <div style={{ maxWidth: 1300, margin: '0 auto', padding: '48px 80px 72px' }}>
            <div style={{ marginBottom: 32 }}>
              <h2 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>协作场景</h2>
              <p style={{ fontSize: 14, color: 'var(--text-muted)' }}>挂了子智能体的智能体即场景 —— 一个主智能体调度多个专业智能体，完成一类完整分析任务</p>
            </div>
            {catalog.isPending && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} height={220} radius={12} />)}</div>}
            {catalog.isError && <div role="alert" style={{ padding: 40, textAlign: 'center', color: 'var(--danger)' }}>{errorMessage(catalog.error, '目录加载失败')}</div>}
            {!catalog.isPending && !catalog.isError && scenes.length === 0 && (
              <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
                还没有审核通过的场景。登录工作台，把你的智能体挂上子智能体，发布后经过审核就会出现在这里。
              </div>
            )}
            {!catalog.isPending && scenes.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>
                {scenes.map(scene => (
                  <SceneCard key={scene.id} scene={scene} onUse={() => navigate('/workspace/scenarios')} />
                ))}
              </div>
            )}

            {/* 场景构成说明 */}
            <div style={{ marginTop: 48, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '32px 40px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 40, flexWrap: 'wrap' as const }}>
                <div style={{ flex: 1, minWidth: 280 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>场景是如何形成的？</h3>
                  <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                    教师将自己的分析方法和经验封装成智能体，经平台审核发布。当智能体挂上子智能体、能解决一类完整的分析任务时，它就成为一个「场景」，进入场景库供全院师生一键使用。
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
                  {['教师方法论', '封装为 Agent', '组合成场景', '学院 Know-How'].map((s, i, arr) => (
                    <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                      <div style={{ textAlign: 'center' as const }}>
                        <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--action-light)', border: '1px solid var(--action-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 8px', fontSize: 18 }}>
                          {['01', '02', '03', '04'][i]}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const }}>{s}</div>
                      </div>
                      {i < arr.length - 1 && <span style={{ color: 'var(--border)', fontSize: 20, marginBottom: 20 }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 全部智能体 */}
      {activeTab === 'agents' && (
        <section style={{ background: 'var(--bg)' }}>
          <div style={{ maxWidth: 1300, margin: '0 auto', padding: '48px 80px 72px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
              <div>
                <h2 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>全部智能体</h2>
                <p style={{ fontSize: 14, color: 'var(--text-muted)' }}>由学院老师发布、经平台审核通过，可独立调用或组合成场景</p>
              </div>
              {/* 学科筛选：选项来自真实数据 */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {subjects.map(s => (
                  <button
                    key={s}
                    onClick={() => setActiveSubject(s)}
                    style={{ padding: '6px 14px', borderRadius: 20, border: `1px solid ${activeSubject === s ? 'var(--action)' : 'var(--border)'}`, background: activeSubject === s ? 'var(--action)' : 'var(--surface)', color: activeSubject === s ? '#fff' : 'var(--text-secondary)', fontSize: 12, fontWeight: activeSubject === s ? 600 : 400, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.15s, color 0.15s, border-color 0.15s' }}
                  >{s}</button>
                ))}
              </div>
            </div>
            {catalog.isPending && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height={180} radius={10} />)}</div>}
            {catalog.isError && <div role="alert" style={{ padding: '60px 0', textAlign: 'center', color: 'var(--danger)' }}>{errorMessage(catalog.error, '目录加载失败')}</div>}
            {!catalog.isPending && !catalog.isError && filteredAgents.length === 0 && (
              <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
                {items.length === 0
                  ? '还没有审核通过的智能体。登录工作台发布你的第一个智能体，经过审核后就会出现在这里。'
                  : `「${activeSubject}」学科下还没有审核通过的智能体`}
              </div>
            )}
            {!catalog.isPending && filteredAgents.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                {filteredAgents.map(agent => (
                  <CatalogCard
                    key={agent.id}
                    title={agent.name}
                    version={`v${agent.version}`}
                    author={agent.owner_name}
                    subject={agent.subject || '未分类'}
                    description={agent.description || '（作者没有写说明）'}
                    detail="广场可见 · 已过审核"
                    metric={`${agent.call_count} 次调用`}
                  />
                ))}
              </div>
            )}

            {/* CTA */}
            <div style={{ marginTop: 40, textAlign: 'center' as const }}>
              <p style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 16 }}>你也有方法论想分享给学院？</p>
              <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '10px 28px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                发布你的智能体
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

function Stat({ num, label }: { num: string; label: string }) {
  return (
    <div>
      <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--action)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{num}</div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>{label}</div>
    </div>
  )
}
