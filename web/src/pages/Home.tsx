import { Link } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'
import { DashboardCard } from '../components/DashboardCard'

const TICKER_ITEMS = ['持仓分析','波动率计算','收益归因','风险敞口','相关性矩阵','回测验证','因子模型','行业比较','时间序列','数据清洗','统计检验','论文复现','课题分析','可视化图表','财务报表','宏观指标']

const VALUE_CARDS = [
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>,
    title: '科研范式升级',
    body: '将重复性数据处理工作自动化，让科研精力聚焦于真正的学术创新，使每位教师都能独立开展数据驱动研究。',
    list: ['论文量化复现：数天 → 小时级', '企业风险分析：人工计算 → 对话完成', '数据分析报告：助研支持 → 自主完成'],
    delay: '0.05s',
  },
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
    title: 'AI 原生人才培养',
    body: '学生在真实智能体环境中完成课题研究，毕业即具备 AI 辅助科研能力，对标国际顶尖商学院 AI 教研体系。',
    list: ['学生用 AI 完成作业、课题、论文辅助', '形成可量化的教育数字化成果', '在新一轮教育 AI 竞争中建立先发优势'],
    delay: '0.1s',
  },
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>,
    title: '自主知识资产沉淀',
    body: '每次分析的代码、数据与结论留存于学院服务器，形成可复用的知识资产，而非消耗在商业 SaaS 平台上。',
    list: ['数据不出校园，部署在学院内网', '代码库持续积累，可供后续师生复用', '学院自主掌控，不受单一商业平台绑定'],
    delay: '0.15s',
  },
]

const ENTRY_CARDS = [
  {
    to: '/workspace',
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
    title: '开始分析对话',
    desc: '直接用自然语言描述分析需求，智能体立即编写代码、执行并返回结果。无需任何编程基础。',
    link: '开始对话 →',
  },
  {
    to: '/data',
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>,
    title: '上传数据文件',
    desc: '将 CSV、Excel、PDF 数据文件上传至您的专属工作区，上传后即可在对话中直接引用分析。',
    link: '了解数据接入 →',
  },
  {
    to: '/scenarios',
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
    title: '浏览研究场景',
    desc: '企业风险分析、论文量化复现、课题数据分析——查看典型场景的完整流程，找到最适合您的起点。',
    link: '浏览场景 →',
  },
]

export function Home() {
  const doubled = [...TICKER_ITEMS, ...TICKER_ITEMS]

  return (
    <div>
      {/* Hero */}
      <section className="grid-bg" style={{ position: 'relative', overflow: 'hidden' }}>
        <div style={{ padding: '100px 80px 90px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 60, maxWidth: 1300, margin: '0 auto', minHeight: 560 }}>
          <DecoStamp style={{ top: 60, left: 80 }} />
          <DecoStamp style={{ bottom: 60, right: 80 }} />

          <div style={{ flex: 1, maxWidth: 560 }}>
            <div className="status-badge" style={{ marginBottom: 32 }}>
              <span className="dot" />
              智能体系统运行中 · 金融学院 AI 基础设施
            </div>
            <h1 style={{ fontSize: 56, fontWeight: 900, lineHeight: 1.15, marginBottom: 20 }}>
              <span style={{ color: 'var(--text-primary)', display: 'block' }}>当技术执行归于智能体</span>
              <span style={{ color: 'var(--action)', display: 'block' }}>
                学术思考回归学者
                <span style={{ display: 'inline-block', width: 3, height: '0.85em', background: 'var(--action)', verticalAlign: 'text-bottom', marginLeft: 4, animation: 'blink 1.1s step-end infinite' }} />
              </span>
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.75, marginBottom: 12, maxWidth: 460 }}>
              以智能体技术重构金融研究工作流，让学术判断力成为科研的唯一瓶颈。
            </p>
            <p style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 36, lineHeight: 1.7 }}>
              金融学院 AI 原生科研环境，下一代研究者的工作方式。
            </p>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <a href="/workspace" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 48, padding: '0 28px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer', textDecoration: 'none', transition: 'background 0.2s' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                进入平台
              </a>
              <Link to="/scenarios" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 48, padding: '0 24px', background: 'transparent', color: 'var(--text-primary)', border: '1.5px solid var(--border)', borderRadius: 8, fontSize: 15, fontWeight: 500, cursor: 'pointer', textDecoration: 'none', transition: 'all 0.2s' }}>
                了解研究范式 →
              </Link>
            </div>
          </div>

          <div style={{ flexShrink: 0 }}>
            <DashboardCard />
          </div>
        </div>
      </section>

      {/* 战略价值区 */}
      <section style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '80px 80px 60px' }}>
          <div className="section-tag">// STRATEGIC VALUE</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 40 }}>为金融学院创造的三项核心价值</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
            {VALUE_CARDS.map((card, i) => (
              <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '32px 28px', display: 'flex', flexDirection: 'column', gap: 14, animation: `card-enter 0.4s ease-out ${card.delay} both`, transition: 'border-color 0.2s, box-shadow 0.2s' }}>
                <div style={{ width: 44, height: 44, background: 'var(--action-light)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--action)', flexShrink: 0 }}>
                  {card.icon}
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{card.title}</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{card.body}</div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {card.list.map((item, j) => (
                    <li key={j} style={{ fontSize: 13, color: 'var(--text-muted)', paddingLeft: 16, position: 'relative' }}>
                      <span style={{ position: 'absolute', left: 0, color: 'var(--action)', fontSize: 11 }}>→</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        {/* 战略横幅 */}
        <div style={{ background: 'var(--brand)', backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)', backgroundSize: '40px 40px', padding: '48px 80px', textAlign: 'center' }}>
          <p style={{ fontSize: 15, color: 'rgba(255,255,255,0.75)', lineHeight: 1.9, maxWidth: 860, margin: '0 auto' }}>
            <strong style={{ color: '#fff', fontWeight: 600 }}>响应新质生产力发展战略 · 推进教育数字化转型</strong><br />
            将大模型与智能体技术深度融入金融学科教学科研体系<br />
            构建学院自主可控的 AI 基础设施，在新一轮教育 AI 竞争中建立先发优势
          </p>
        </div>
      </section>

      {/* Ticker */}
      <div style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '20px 0', overflow: 'hidden' }}>
        <div style={{ textAlign: 'center', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.28em', color: 'var(--text-muted)', marginBottom: 14, fontFamily: "'JetBrains Mono', monospace" }}>
          // ANALYSIS CAPABILITIES
        </div>
        <div style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', animation: 'ticker-scroll 40s linear infinite', width: 'max-content' }}>
            {doubled.map((item, i) => (
              <span key={i} style={{ padding: '0 28px', fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', borderRight: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 快速入口区 */}
      <section className="grid-bg" style={{ position: 'relative' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80, position: 'relative' }}>
          <DecoStamp style={{ top: 40, right: 80 }} />
          <div className="section-tag">// GET STARTED</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>开始使用</h2>
          <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 40, maxWidth: 560, lineHeight: 1.7 }}>
            三条路径快速上手，从第一个问题到第一份分析结果。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
            {ENTRY_CARDS.map((card, i) => (
              <Link key={i} to={card.to} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 12, textDecoration: 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}>
                <div style={{ width: 40, height: 40, borderRadius: 8, background: 'var(--action-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--action)' }}>
                  {card.icon}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>{card.title}</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7, flex: 1 }}>{card.desc}</div>
                <div style={{ fontSize: 13, color: 'var(--action)', fontWeight: 500 }}>{card.link}</div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
