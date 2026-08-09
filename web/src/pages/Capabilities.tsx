import { Link } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'

const CAP_CARDS = [
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
    title: '对话驱动分析',
    desc: '用自然语言描述分析需求，无需编程。平台理解金融领域语境，自动拆解任务步骤，调用合适的工具完成计算。',
    note: '降低科研技术门槛，使全体教师都能独立开展数据驱动研究',
    tags: ['DeepAgents','LangGraph','deepseek-v4-pro'],
  },
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>,
    title: '代码自动执行',
    desc: 'agent 编写 Python 分析脚本，在 gVisor 隔离沙箱中真实执行，返回计算结果与图表。pandas / numpy / matplotlib 开箱即用。',
    note: '生成的代码留存于学院服务器，形成可复用的量化研究资产',
    tags: ['Python','pandas','matplotlib','Sandbox'],
  },
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
    title: '实时流式输出',
    desc: 'SSE 长连接推送，执行过程实时可见——思考步骤、工具调用、代码输出逐条展示。断线重连自动补齐，长任务不丢失进度。',
    note: '全程可观测，每一步推理有据可查，满足学术研究的可追溯要求',
    tags: ['SSE','实时推送','断线重连'],
  },
  {
    icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
    title: '安全隔离执行',
    desc: '每个会话独享 gVisor 隔离容器，代码执行不影响宿主机与其他用户。支持人工介入（HITL）审批敏感操作。',
    note: '院内部署，数据不经过任何商业云服务，满足学术数据保密要求',
    tags: ['gVisor','容器隔离','HITL'],
  },
]

const SECURITY_ITEMS = [
  { title: '数据不出校园', desc: '部署在学院内网服务器，所有数据存储于本地 MinIO，不上传商业云' },
  { title: '用户数据严格隔离', desc: '每个账号拥有独立 workspace，管理员无法查看他人数据内容' },
  { title: '代码执行沙箱隔离', desc: 'gVisor 容器化执行，内存 2GB 上限，磁盘 5GB 配额，零外网访问' },
  { title: '操作全程可审计', desc: '每次分析的步骤、代码、结果完整记录，可供学院管理层查阅用量与成本' },
]

export function Capabilities() {
  return (
    <div>
      {/* Hero */}
      <section className="grid-bg" style={{ position: 'relative' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '80px 80px 72px', position: 'relative' }}>
          <DecoStamp style={{ top: 60, left: 80 }} />
          <DecoStamp style={{ bottom: 60, right: 80 }} />
          <div className="section-tag">// INFRASTRUCTURE</div>
          <h1 style={{ fontSize: 40, fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 20 }}>
            自主可控的 AI 基础设施
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.8, maxWidth: 640 }}>
            不依赖商业 SaaS 平台，部署在学院服务器，数据不出校园，技术栈完全开源可审计。
            <br /><br />
            基于 LangGraph 智能体框架与 DeepSeek 大模型构建，具备持续演进能力，不受单一供应商绑定。
          </p>
        </div>
      </section>

      {/* 四大能力 */}
      <section style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80 }}>
          <div className="section-tag">// CAPABILITIES</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>四大核心能力</h2>
          <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 40, maxWidth: 560, lineHeight: 1.7 }}>
            每项能力都经过实际工程验证，在真实分析任务中稳定运行。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 }}>
            {CAP_CARDS.map((card, i) => (
              <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 12, transition: 'border-color 0.2s, box-shadow 0.2s' }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--action-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--action)' }}>
                  {card.icon}
                </div>
                <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>{card.title}</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7, flex: 1 }}>{card.desc}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 10, borderTop: '1px solid var(--border-light)', lineHeight: 1.6 }}>{card.note}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
                  {card.tags.map((tag, j) => (
                    <span key={j} style={{ padding: '3px 8px', fontSize: 10, fontWeight: 500, textTransform: 'uppercase' as const, letterSpacing: '0.1em', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>{tag}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 安全隔离专区 — 灰底，与四大能力白底区隔 */}
      <section className="grid-bg" style={{ borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80, display: 'flex', gap: 60, alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <div className="section-tag">// SECURITY ARCHITECTURE</div>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 24 }}>数据流转路径</h2>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', boxShadow: '0 2px 8px rgba(11,46,92,0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', background: '#F7F9FC', borderBottom: '1px solid var(--border-light)' }}>
                {[0,1,2].map(i => <div key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border)' }} />)}
                <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6, fontFamily: "'JetBrains Mono', monospace" }}>data_flow.txt</span>
              </div>
              <div style={{ padding: '20px 24px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, lineHeight: 2.2, color: 'var(--text-secondary)' }}>
                教师提问<br />
                <span style={{ color: 'var(--text-muted)', paddingLeft: 16 }}>↓</span><br />
                DeepSeek 推理（仅传输问题文本）<br />
                <span style={{ color: 'var(--text-muted)', paddingLeft: 16 }}>↓</span><br />
                生成代码 → gVisor 隔离容器执行<br />
                <span style={{ color: 'var(--text-muted)', paddingLeft: 16 }}>↓（容器零出网）</span><br />
                结果返回 · 图表产出<br />
                <span style={{ color: 'var(--text-muted)', paddingLeft: 16 }}>↓</span><br />
                存储于学院 MinIO · 不经过任何商业云
              </div>
            </div>
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, gap: 20 }}>
            {SECURITY_ITEMS.map((item, i) => (
              <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--action-light)', color: 'var(--action)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 12, fontWeight: 700, marginTop: 2 }}>✓</div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{item.title}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA — 白底，与安全区灰底区隔 */}
      <section style={{ textAlign: 'center', padding: 80, background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
        <div className="section-tag" style={{ justifyContent: 'center', display: 'flex' }}>// GET STARTED</div>
        <h2 style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>了解更多，立即体验</h2>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 32 }}>查看数据接入方式，或直接进入工作台开始第一次分析</p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <a href="/workspace" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 24px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', textDecoration: 'none' }}>进入工作台 →</a>
          <Link to="/data" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: 'pointer', textDecoration: 'none' }}>数据要素 →</Link>
        </div>
      </section>
    </div>
  )
}
