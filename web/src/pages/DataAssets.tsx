import { Link } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'

const MARKET_ITEMS = [
  { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>, label: 'A 股日 K / 分钟线行情' },
  { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/><line x1="8" y1="21" x2="8" y2="9"/></svg>, label: '上市公司财务报表（三张表）' },
  { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>, label: '宏观经济指标（GDP / CPI / M2）' },
  { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 0 0 4H8"/><line x1="12" y1="6" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="18"/></svg>, label: '基金净值与持仓历史' },
  { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>, label: '汇率与大宗商品价格' },
]

const SECURITY_COLS = [
  { title: '研究资产完整留存', desc: '每次分析的数据、代码与结论统一归档，成熟成果可进一步沉淀为智能体与场景模板' },
  { title: '用户数据隔离', desc: '每位用户独立 workspace，管理员无法查看数据内容，严格权限隔离' },
  { title: '操作全程可审计', desc: '分析记录、代码与结论完整留存，学院可查阅完整使用记录与成本' },
]

const FORMAT_ROWS = [
  { ext: '.csv', desc: '逗号分隔数值文件', usage: '持仓数据、行情数据、问卷结果' },
  { ext: '.xlsx / .xls', desc: 'Excel 工作表', usage: '财务报表、调研数据' },
  { ext: '.pdf', desc: 'PDF 文档', usage: '年报、研究报告（agent 可提取文本内容）' },
  { ext: '.txt', desc: '纯文本', usage: '数据说明文档、文字资料' },
]

export function DataAssets() {
  return (
    <div>
      {/* Hero 浅色 grid-bg */}
      <section className="grid-bg" style={{ position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '80px 80px 72px', position: 'relative' }}>
          <DecoStamp style={{ top: 60, left: 80 }} />
          <DecoStamp style={{ bottom: 60, right: 80 }} />
          <div className="section-tag">// DATA ASSETS</div>
          <h1 style={{ fontSize: 40, fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 20 }}>
            数据是学院最重要的科研资产
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.8, maxWidth: 640 }}>
            过去，师生的分析数据散落在个人电脑，随人员流动而流失，无法沉淀为学院资产。
            <br /><br />
            平台将每次分析的数据、代码与结论统一归档，成熟成果还可封装为智能体与场景模板，供后续师生持续复用。
          </p>
          <p style={{ fontSize: 15, color: 'var(--action)', fontWeight: 600, marginTop: 20, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em' }}>
            沉淀科研资产，复用智能体与场景。
          </p>
        </div>
      </section>

      {/* 数据安全 — white，与 Hero 的灰底区隔 */}
      <section style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '60px 80px' }}>
          <div className="section-tag">// DATA SECURITY</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 32 }}>您的数据安全</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
            {SECURITY_COLS.map((col, i) => (
              <div key={i} style={{ background: 'var(--bg)', borderRadius: 10, padding: 24, borderLeft: '4px solid var(--action)' }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>{col.title}</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{col.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 数据生命周期 — grid-bg 灰底 */}
      <section className="grid-bg" style={{ borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80 }}>
          <div className="section-tag">// DATA LIFECYCLE · 从输入到资产</div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, marginTop: 24, maxWidth: 900, margin: '24px auto 0' }}>
            {[
              { step: '01', title: '教师上传数据', items: ['持仓 CSV', '财报 Excel', '公开市场行情', '课题问卷数据'] },
              { step: '02', title: '智能体分析产出', items: ['分析代码（.py 文件）', '可视化图表（PNG）', '文字结论（Markdown）', '统计报表'] },
              { step: '03', title: '学院知识资产', items: ['代码库持续积累', '可供后续师生复用', '研究成果有据可查', '不受人员流动影响'] },
            ].map((col, i, arr) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--action-light)', border: '1.5px solid var(--action-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--action)', fontFamily: "'JetBrains Mono', monospace" }}>{col.step}</span>
                    </div>
                    {i < arr.length - 1 && (
                      <div style={{ flex: 1, borderTop: '1px dashed var(--border)', margin: '0 12px' }} />
                    )}
                  </div>
                  <div style={{ paddingRight: i < arr.length - 1 ? 32 : 0 }}>
                    <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 12 }}>{col.title}</div>
                    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
                      {col.items.map((item, j) => (
                        <div key={j} style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ color: 'var(--action-border)', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, flexShrink: 0 }}>·</span>{item}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* DATA ONBOARDING — white */}
      <section style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80 }}>
          <div className="section-tag">// DATA ONBOARDING</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>如何使用数据</h2>
          <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 40, maxWidth: 560, lineHeight: 1.7 }}>两条路径，覆盖学院主要的数据来源场景</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            {/* 手动上传 */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '32px 28px', display: 'flex', flexDirection: 'column' as const, gap: 20 }}>
              <div className="section-tag">// PATH 01 · 手动上传</div>
              <div style={{ border: '1.5px dashed var(--border)', borderRadius: 8, padding: '32px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.8, background: 'var(--bg)' }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ margin: '0 auto 12px', display: 'block', color: 'var(--action-border)' }}>
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                拖拽文件到此处，或点击上传<br />单文件最大 50MB
                <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
                  {['CSV','XLSX','PDF','TXT'].map(f => (
                    <span key={f} style={{ padding: '3px 8px', fontSize: 10, fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.1em', color: 'var(--action)', background: 'var(--action-light)', border: '1px solid var(--action-border)', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>{f}</span>
                  ))}
                </div>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                上传后，直接在对话中引用：<br />
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', fontSize: 12 }}>「用 portfolio_2026Q2.csv 计算年化波动率」</span>
                <br /><br />
                文件存储于您的专属 workspace，其他用户无法访问。
              </p>
            </div>
            {/* 市场数据 */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '32px 28px', display: 'flex', flexDirection: 'column' as const, gap: 20 }}>
              <div className="section-tag">// PATH 02 · 市场数据接口</div>
              <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                通过 AkShare 接口，agent 可实时拉取以下数据，在对话中直接描述需求，无需额外配置。
              </p>
              <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 10 }}>
                {MARKET_ITEMS.map((item, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
                    <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--action-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, color: 'var(--action)' }}>{item.icon}</div>
                    {item.label}
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', lineHeight: 1.7, background: 'var(--bg)', padding: '10px 14px', borderRadius: 6, borderLeft: '2px solid var(--border)' }}>
                「拉取贵州茅台近三年日 K，<br />计算年化波动率并画图」
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 格式表 — grid-bg 灰底，与上方白底区隔 */}
      <section className="grid-bg" style={{ borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80 }}>
          <div className="section-tag">// SUPPORTED FORMATS</div>
          <h2 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 32 }}>支持的文件格式</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {['格式','说明','典型用途'].map(h => (
                  <th key={h} style={{ textTransform: 'uppercase' as const, letterSpacing: '0.12em', fontSize: 10, color: 'var(--text-muted)', padding: '10px 16px', textAlign: 'left', borderBottom: '1px solid var(--border)', fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FORMAT_ROWS.map((row, i) => (
                <tr key={i}>
                  <td style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-light)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--action)', fontWeight: 500 }}>{row.ext}</td>
                  <td style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>{row.desc}</td>
                  <td style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-light)', color: 'var(--text-muted)' }}>{row.usage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* CTA — white，与上方灰底区隔 */}
      <section style={{ textAlign: 'center', padding: 80, background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
        <div className="section-tag" style={{ justifyContent: 'center', display: 'flex' }}>// GET STARTED</div>
        <h2 style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>数据已就绪，开始分析</h2>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 32 }}>上传您的第一份数据文件，或直接提问让 agent 从公开市场接口拉取数据</p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <a href="/workspace" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 24px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', textDecoration: 'none' }}>进入工作台，开始分析 →</a>
          <Link to="/capabilities" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: 'pointer', textDecoration: 'none' }}>了解平台能力 →</Link>
        </div>
      </section>
    </div>
  )
}
