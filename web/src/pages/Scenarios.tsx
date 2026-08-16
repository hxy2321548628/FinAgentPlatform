import { Link } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'

interface ScenarioProps {
  contextLabel: string
  contextText: string
  title: string
  quote: string
  steps: string[]
  outputs: string[]
  tags: string[]
  terminalTitle: string
  terminalTask: string
  terminalLogs: Array<{ status: 'done' | 'run' | 'pending', name: string, arg: string, time?: string }>
  terminalIndents: string[]
  terminalSummary: string
  reverse?: boolean
  bgSurface?: boolean
}

function Scenario({ contextLabel, contextText, title, quote, steps, outputs, tags, terminalTitle, terminalTask, terminalLogs, terminalIndents, terminalSummary, reverse, bgSurface }: ScenarioProps) {
  const iconColors = { done: '#10B981', run: '#1749C4', pending: '#8E9BB0' }
  const icons = {
    done: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>,
    run: <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg>,
    pending: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9"/></svg>,
  }

  const leftContent = (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, padding: '14px 18px', background: 'var(--bg)', borderLeft: '2px solid var(--action-border)', borderRadius: '0 6px 6px 0', marginBottom: 28 }}>
        <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>{contextLabel}</span>
        {contextText}
      </div>
      <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>{title}</h2>
      <p style={{ fontSize: 15, color: 'var(--text-secondary)', fontStyle: 'italic', lineHeight: 1.7, borderLeft: '2px solid var(--border)', paddingLeft: 16, marginBottom: 20 }}>{quote}</p>
      <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8, marginBottom: 20 }}>
        {steps.map((step, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
            <span style={{ color: '#10B981', flexShrink: 0, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>✓</span>
            {step}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8, paddingTop: 16, borderTop: '1px solid var(--border-light)', marginBottom: 16 }}>
        {outputs.map((o, i) => (
          <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, fontSize: 12, color: 'var(--text-secondary)' }}>{o}</span>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
        {tags.map((tag, i) => (
          <span key={i} style={{ padding: '3px 8px', fontSize: 10, fontWeight: 500, textTransform: 'uppercase' as const, letterSpacing: '0.1em', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>{tag}</span>
        ))}
      </div>
    </div>
  )

  const rightContent = (
    <div style={{ flexShrink: 0, width: 420 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', boxShadow: '0 4px 8px rgba(11,46,92,0.06), 0 12px 40px rgba(11,46,92,0.10)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', background: '#F7F9FC', borderBottom: '1px solid var(--border-light)' }}>
          {[0,1,2].map(i => <div key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border)' }} />)}
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em' }}>{terminalTitle}</span>
        </div>
        <div style={{ padding: 16, fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, lineHeight: 1.9, color: 'var(--text-secondary)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{terminalTask}</div>
          <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', margin: '8px 0' }} />
          {terminalLogs.map((log, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ color: iconColors[log.status], minWidth: 12, display: 'flex', alignItems: 'center' }}>{icons[log.status]}</span>
              <span style={{ minWidth: 76, color: log.status === 'pending' ? 'var(--text-muted)' : 'var(--text-secondary)' }}>{log.name}</span>
              <span style={{ color: 'var(--text-muted)', flex: 1, fontSize: 11 }}>{log.arg}</span>
              {log.time && <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{log.time}</span>}
            </div>
          ))}
          {terminalIndents.map((line, i) => (
            <span key={i} style={{ paddingLeft: 20, color: 'var(--text-muted)', fontSize: 11, display: 'block', lineHeight: 1.7 }}>{line}</span>
          ))}
          <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', margin: '8px 0' }} />
          <div style={{ color: '#10B981', fontWeight: 500 }}>{terminalSummary}</div>
        </div>
      </div>
    </div>
  )

  return (
    <section style={{ background: bgSurface ? 'var(--surface)' : 'var(--bg)', borderTop: '1px solid var(--border)' }}>
      <div style={{ maxWidth: 1300, margin: '0 auto', padding: 80, display: 'flex', gap: 60, alignItems: 'flex-start', flexDirection: reverse ? 'row-reverse' : 'row' }}>
        {leftContent}
        {rightContent}
      </div>
    </section>
  )
}

export function Scenarios() {
  return (
    <div>
      {/* Hero */}
      <section className="grid-bg" style={{ position: 'relative' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '80px 80px 72px', position: 'relative' }}>
          <DecoStamp style={{ top: 60, left: 80 }} />
          <DecoStamp style={{ bottom: 60, right: 80 }} />
          <div className="section-tag">// RESEARCH PARADIGM</div>
          <h1 style={{ fontSize: 40, fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 20 }}>
            AI 智能体正在重构金融学术研究的工作方式
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.8, maxWidth: 640 }}>
            从数据清洗到模型复现，从风险建模到报告生成——这些原本需要数天的环节，正在被压缩至对话级别。
            金融学院率先部署智能体科研环境，意味着师生正在以下一代研究范式开展工作。
          </p>
          <div style={{ marginTop: 24, fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
            演示 · 一次完整量化分析的典型流程 · 数据为示意
          </div>
        </div>
      </section>

      <Scenario
        bgSurface
        contextLabel="// SCENARIO 01 · STRATEGIC CONTEXT"
        contextText="企业风险研究是金融学院的核心教研领域之一。过去，这类分析依赖助研手工处理数据，周期长且难以复现。智能体将这一流程标准化，使每位教师都能独立完成原本需要团队配合的分析工作。"
        title="企业风险分析"
        quote="「分析这份上市公司财报，评估其短期偿债风险与盈利趋势」"
        steps={['读取财报数据，识别关键财务字段','编写指标计算代码（流动比率、ROE、毛利率）','执行计算，输出各年度对比数据','生成趋势图表，存入 outputs/']}
        outputs={['📊 财务指标趋势图','📄 可复用分析代码','📝 文字结论']}
        tags={['财务指标','偿债能力','ROE','流动比率']}
        terminalTitle="agent_executor · run_0xA1B2"
        terminalTask="任务：企业财务风险分析"
        terminalLogs={[
          { status: 'done', name: 'read_file',  arg: 'financial_data.csv',       time: '0.1s' },
          { status: 'done', name: 'write_file', arg: 'risk_analysis.py',         time: '0.1s' },
          { status: 'done', name: 'execute',    arg: 'python risk_analysis.py',  time: '3.2s' },
          { status: 'done', name: 'write_file', arg: 'outputs/risk_chart.png',   time: '0.1s' },
        ]}
        terminalIndents={['└─ Computing liquidity ratios...','└─ ROE trend: [0.12, 0.15, 0.18]']}
        terminalSummary="✓ 完成 · 用时 4.1s · 31,240 tokens"
      />

      <Scenario
        reverse
        contextLabel="// SCENARIO 02 · STRATEGIC CONTEXT"
        contextText="量化复现是检验研究可信度的基础，也是培养严谨学风的重要环节。智能体将原本需要数天的代码复现工作压缩至小时级，并生成可供后续研究引用的标准化分析脚本，形成学院可持续积累的量化研究资产库。"
        title="论文量化复现"
        quote="「用这份 A 股数据复现 Fama-French 三因子模型，验证 alpha 显著性」"
        steps={['读取历史行情数据，构建因子收益序列','编写三因子回归代码（statsmodels）','多次迭代执行，修正数据对齐问题','生成因子载荷图与回归结果表格']}
        outputs={['📊 因子载荷图','📋 回归系数表','📄 复现代码']}
        tags={['因子模型','回归分析','statsmodels','复现验证']}
        terminalTitle="agent_executor · run_0xC3D4"
        terminalTask="任务：Fama-French 三因子模型复现"
        terminalLogs={[
          { status: 'done', name: 'read_file',  arg: 'ashare_returns.csv',       time: '0.1s' },
          { status: 'done', name: 'write_file', arg: 'ff3_model.py',             time: '0.1s' },
          { status: 'done', name: 'execute',    arg: 'python ff3_model.py',      time: '8.4s' },
          { status: 'done', name: 'write_file', arg: 'outputs/ff3_results.png',  time: '0.1s' },
        ]}
        terminalIndents={['└─ Building factor portfolios...','└─ Running OLS regression...','└─ alpha t-stat: 2.34 (p=0.019)']}
        terminalSummary="✓ 完成 · 用时 9.3s · 28,640 tokens"
      />

      <Scenario
        bgSurface
        contextLabel="// SCENARIO 03 · STRATEGIC CONTEXT"
        contextText="课题研究中的数据分析环节往往消耗大量时间与人力。智能体使课题组成员——包括研究生——能够独立完成原本需要专业统计软件操作经验的分析工作，降低科研门槛，提升课题组整体产出效率。"
        title="课题数据分析"
        quote="「这是课题组的问卷数据，帮我做描述性统计和组间差异检验」"
        steps={['读取问卷数据，识别变量类型','编写描述统计与 T 检验代码','执行分析，输出各组均值与 p 值','生成分布图与箱线图']}
        outputs={['📊 分布箱线图','📋 统计检验结果','📝 结论摘要']}
        tags={['描述统计','假设检验','可视化','问卷数据']}
        terminalTitle="agent_executor · run_0xE5F6"
        terminalTask="任务：课题问卷数据统计分析"
        terminalLogs={[
          { status: 'done', name: 'read_file',  arg: 'survey_data.csv',           time: '0.1s' },
          { status: 'done', name: 'write_file', arg: 'stats_analysis.py',         time: '0.1s' },
          { status: 'done', name: 'execute',    arg: 'python stats_analysis.py',  time: '2.8s' },
          { status: 'done', name: 'write_file', arg: 'outputs/distribution.png',  time: '0.1s' },
        ]}
        terminalIndents={['└─ Group A mean: 4.23, Group B: 3.87','└─ t-stat: 2.81, p-value: 0.006']}
        terminalSummary="✓ 完成 · 用时 3.4s · 19,820 tokens"
      />

      {/* CTA */}
      <section style={{ textAlign: 'center', padding: 80, background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
        <div className="section-tag" style={{ justifyContent: 'center', display: 'flex' }}>// NEXT STEP</div>
        <h2 style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>已有数据，立即开始</h2>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 32 }}>选择一个场景，上传您的数据文件，直接开始分析</p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <a href="/workspace" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 24px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', textDecoration: 'none' }}>进入工作台，开始分析 →</a>
          <Link to="/capabilities" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 44, padding: '0 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: 'pointer', textDecoration: 'none' }}>了解技术底座 →</Link>
        </div>
      </section>
    </div>
  )
}
