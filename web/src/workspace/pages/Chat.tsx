import { useRef, useState, useCallback } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ChatInput } from '../components/ChatInput'
import { ArtifactPanel } from '../components/ArtifactPanel'

// 多智能体协作的 mock 消息（公司全面风险评估场景）
const MULTI_AGENT_MESSAGES = [
  { type: 'user' as const, text: '帮我对格力电器（000651）做一个全面的风险评估，包括财务异常检测、公告风险信号识别、以及信用风险评估，最后整合成一份综合报告。', attachments: [{ name: 'gree_2025_annual.csv' }] },
  { type: 'reasoning' as const, done: true, text: '用户需要对格力电器做多维度风险评估，需要依次调用三个专业智能体：\n1. 企业财务异常检测（张老师）— 核查财报关键科目\n2. 公告语义分析（平台公共）— 识别近期公告风险信号\n3. 信用风险评估（刘老师）— 计算违约概率\n最后整合三个智能体的输出，生成综合风险报告。' },
  { type: 'agent' as const, markdown: `**正在调用：企业财务异常检测**（张老师）\n\n开始对格力电器 2025 年报进行财务核查...` },
  { type: 'tool' as const, status: 'done' as const, name: 'read_file', arg: 'gree_2025_annual.csv', time: '0.2s' },
  { type: 'tool' as const, status: 'done' as const, name: 'execute', arg: 'python financial_check.py', time: '2.8s', output: ['核查流动比率、速动比率、应收账款周转率...', '识别到 2 个异常指标', '应收账款周转率较行业均值偏低 1.8 个标准差'] },
  { type: 'agent' as const, markdown: `**企业财务异常检测 完成 ✓**\n\n发现异常指标 **2 项**：\n- 应收账款周转率：8.2次（行业均值 12.4次），偏低 34%\n- 存货周转天数：68天（行业均值 45天），偏高 51%\n\n其余指标正常，流动比率 1.8、速动比率 1.2 均在合理区间。` },
  { type: 'agent' as const, markdown: `**正在调用：公告语义分析**（平台 · 公共）\n\n分析格力电器近 6 个月公告...` },
  { type: 'tool' as const, status: 'done' as const, name: 'execute', arg: 'python announcement_analysis.py', time: '3.1s', output: ['分析公告 23 份', '识别到治理类风险信号 1 项', '识别到经营类风险信号 2 项'] },
  { type: 'agent' as const, markdown: `**公告语义分析 完成 ✓**\n\n识别风险信号 **3 项**：\n- 🔴 治理类：2 名独立董事更换（2025-08-01 公告），变动频率偏高\n- 🟡 经营类：空调出货量同比下滑 8.3%（2025-07 月报）\n- 🟡 经营类：原材料铜价上涨，原材料成本占比提升至 38%` },
  { type: 'agent' as const, markdown: `**正在调用：信用风险评估**（刘老师）\n\n计算信用评分与违约概率...` },
  { type: 'tool' as const, status: 'done' as const, name: 'execute', arg: 'python credit_risk.py', time: '1.9s', output: ['Altman Z-Score 计算完成', 'Z = 3.42（安全区间 > 2.99）', '违约概率估计：4.2%'] },
  { type: 'agent' as const, markdown: `**信用风险评估 完成 ✓**\n\nAltman Z-Score：**3.42**（安全区间 > 2.99，当前处于安全区）\n违约概率估计：**4.2%**（行业中等水平）` },
  {
    type: 'agent' as const,
    markdown: `## 格力电器（000651）综合风险评估报告

三个智能体分析完成，以下是整合结论：

| 维度 | 风险等级 | 核心发现 |
|------|---------|---------|
| 财务异常 | 🟡 中等 | 应收账款周转率偏低，存货周转偏慢 |
| 公告信号 | 🟡 中等 | 独立董事更换 + 出货量下滑 |
| 信用风险 | 🟢 较低 | Z-Score 3.42，处于安全区间 |

**综合评级：中等关注（风险可控，建议持续跟踪）**

**主要关注点：**
1. 经营效率有所下滑，应收账款管理需关注
2. 治理层面人员变动频繁，建议关注后续公告
3. 信用基本面稳健，短期违约风险较低

**建议：** 维持现有仓位，设置季度复检节点，重点关注下季度应收账款数据及新任独立董事背景。`,
  },
]

const MIN_PANEL_WIDTH = 200
const MAX_PANEL_WIDTH = 700
const DEFAULT_PANEL_WIDTH = 380

interface AgentContext {
  agentId: string
  agentName: string
  agentAuthor: string
  agentDataNeeded: string
}

// 对话结束后的评分组件
function RatingWidget({ agentName, onRate }: { agentName: string; onRate: (star: number) => void }) {
  const [hovered, setHovered] = useState(0)
  const [rated, setRated] = useState(0)

  if (rated > 0) {
    return (
      <div style={{ padding: '10px 32px', background: 'var(--surface)', borderTop: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--status-done)' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
        感谢评价！已为「{agentName}」记录 {rated} 星
      </div>
    )
  }

  return (
    <div style={{ padding: '10px 32px', background: 'var(--surface)', borderTop: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 16 }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>如何评价这次「{agentName}」的分析效果？</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {[1, 2, 3, 4, 5].map(star => (
          <button
            key={star}
            onMouseEnter={() => setHovered(star)}
            onMouseLeave={() => setHovered(0)}
            onClick={() => { setRated(star); onRate(star) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 22, lineHeight: 1, color: star <= (hovered || rated) ? '#F59E0B' : 'var(--border)', transition: 'color 0.1s' }}
          >★</button>
        ))}
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>本次评价将计入广场评分</span>
    </div>
  )
}

export function Chat() {
  const location = useLocation()
  const { threadId } = useParams()
  const agentCtx = (location.state as AgentContext | null)
  const isMultiAgent = threadId === 'multi'

  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [panelVisible, setPanelVisible] = useState(true)
  const [isRunning] = useState(false)
  const [resizerHovered, setResizerHovered] = useState(false)
  const [showRating] = useState(!!agentCtx && !isMultiAgent)

  // 申请发布为场景弹窗
  const [showSceneModal, setShowSceneModal] = useState(false)
  const [sceneName, setSceneName] = useState('公司全面风险评估')
  const [sceneDesc, setSceneDesc] = useState('依次调用财务异常检测、公告语义分析、信用风险评估三个智能体，整合输出综合风险报告。')
  const [sceneSubmitted, setSceneSubmitted] = useState(false)

  const handleSceneSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!sceneName.trim()) return
    setSceneSubmitted(true)
    setTimeout(() => { setShowSceneModal(false); setSceneSubmitted(false) }, 1500)
  }
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(DEFAULT_PANEL_WIDTH)

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    if (!panelVisible) return
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = panelWidth

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - ev.clientX
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth.current + delta))
      setPanelWidth(newWidth)
    }
    const onMouseUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [panelWidth, panelVisible])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* 左侧会话列表 */}
      <ThreadSidebar />

      {/* 主对话区 */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        backgroundColor: 'var(--bg)',
        backgroundImage: 'linear-gradient(rgba(11,46,92,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(11,46,92,0.025) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}>
        {agentCtx && (
          <div style={{ padding: '10px 24px', background: 'var(--action-light)', borderBottom: '1px solid var(--action-border)', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--action)', flexShrink: 0 }}>
              <circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/>
            </svg>
            <span style={{ fontSize: 13, color: 'var(--action)', fontWeight: 500 }}>
              当前使用：<strong>{agentCtx.agentName}</strong>
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>· {agentCtx.agentAuthor}</span>
            {agentCtx.agentDataNeeded && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 4 }}>· 建议上传：{agentCtx.agentDataNeeded}</span>
            )}
          </div>
        )}

        {/* 多 Agent 协作标题横幅 */}
        {isMultiAgent && (
          <div style={{ padding: '10px 24px', background: '#F5F3FF', borderBottom: '1px solid #DDD6FE', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            <span style={{ fontSize: 13, color: '#7C3AED', fontWeight: 600 }}>🤖 多智能体协作 · 公司全面风险评估</span>
            <span style={{ fontSize: 12, color: '#7C3AED', opacity: 0.7 }}>调用了 3 个智能体 · 分析完成</span>
            <button
              onClick={() => setShowSceneModal(true)}
              style={{ marginLeft: 'auto', padding: '5px 14px', background: '#7C3AED', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
            >申请发布为场景 →</button>
          </div>
        )}

        <MessageList messages={isMultiAgent ? MULTI_AGENT_MESSAGES as never : undefined} />

        {showRating && agentCtx && (
          <RatingWidget agentName={agentCtx.agentName} onRate={() => {}} />
        )}

        <ChatInput isRunning={isRunning} />
      </div>

      {/* 拖拽分隔条 */}
      {panelVisible && (
        <div
          onMouseDown={onResizeStart}
          style={{
            width: 4, flexShrink: 0, cursor: 'col-resize',
            background: (resizerHovered || dragging.current) ? 'var(--action)' : 'var(--border-light)',
            transition: 'background 0.15s',
          }}
          onMouseEnter={() => setResizerHovered(true)}
          onMouseLeave={() => setResizerHovered(false)}
        />
      )}

      {/* 右侧产物面板 + 展开按钮（面板隐藏时显示） */}
      {!panelVisible && (
        <button
          onClick={() => setPanelVisible(true)}
          title="展开面板"
          style={{
            width: 24, flexShrink: 0, border: 'none', cursor: 'pointer',
            background: 'var(--border-light)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-muted)', fontSize: 12, transition: 'background 0.15s, color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--action-light)'; e.currentTarget.style.color = 'var(--action)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--border-light)'; e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
      )}
      {panelVisible && (
        <div style={{ width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column' as const, overflow: 'hidden' }}>
          {/* 面板顶部控制条 */}
          <div style={{ height: 32, flexShrink: 0, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 12px', background: 'var(--surface)' }}>
            <span style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>分析面板</span>
            <button
              onClick={() => setPanelVisible(false)}
              title="收起面板"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', padding: 4, borderRadius: 4, transition: 'color 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--action)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
            </button>
          </div>
          <ArtifactPanel />
        </div>
      )}

      {/* 申请发布为场景弹窗 */}
      {showSceneModal && (
        <>
          <div onClick={() => setShowSceneModal(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 300 }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, width: 480, zIndex: 301, boxShadow: '0 20px 60px rgba(11,46,92,0.2)' }}>
            {sceneSubmitted ? (
              <div style={{ textAlign: 'center' as const, padding: '24px 0' }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>🎯</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>申请已提交</div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理员审核通过后将出现在场景库</div>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>申请发布为场景</div>
                  <button onClick={() => setShowSceneModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20, lineHeight: 1.6 }}>
                  将本次多智能体协作的工作流申请发布为场景，供其他师生一键复用。管理员审核通过后进入场景库。
                </div>
                <form onSubmit={handleSceneSubmit}>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>场景名称 <span style={{ color: '#DC2626' }}>*</span></label>
                    <input value={sceneName} onChange={e => setSceneName(e.target.value)} placeholder="如：公司全面风险评估" style={{ width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)' }} />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>场景描述</label>
                    <textarea value={sceneDesc} onChange={e => setSceneDesc(e.target.value)} placeholder="描述这个场景能解决什么问题，适合什么情况使用" style={{ width: '100%', minHeight: 80, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as const, background: 'var(--surface)', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)' }} />
                  </div>
                  <div style={{ background: 'var(--bg)', borderRadius: 8, padding: '12px 14px', marginBottom: 20 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>本次对话调用的智能体</div>
                    {['企业财务异常检测（张老师）', '公告语义分析（平台 · 公共）', '信用风险评估（刘老师）'].map((a, i) => (
                      <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ color: 'var(--status-done)', fontWeight: 700 }}>✓</span>{a}
                      </div>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                    <button type="button" onClick={() => setShowSceneModal(false)} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
                    <button type="submit" style={{ padding: '9px 20px', background: '#7C3AED', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>提交申请</button>
                  </div>
                </form>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
