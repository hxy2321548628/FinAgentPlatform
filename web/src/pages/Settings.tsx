import { useState } from 'react'

type Section = 'model' | 'notify' | 'account'
type ModelRole = 'fast' | 'deep' | 'embed'

const MODEL_STATS = {
  fast:  { sessions: 15, input: '800K', output: '200K', outputUnit: 'tokens', cost: '¥1.2', costUnit: '快速模型', inputBarVal: '800K / 5M',  inputBarPct: 16, costBarVal: '¥1.2 / ¥200', costBarPct: 1 },
  deep:  { sessions: 9,  input: '350K', output: '90K',  outputUnit: 'tokens', cost: '¥2.8', costUnit: '思考模型', inputBarVal: '350K / 5M',  inputBarPct:  7, costBarVal: '¥2.8 / ¥200', costBarPct: 1 },
  embed: { sessions: 89, input: '1.2M', output: '2.8K', outputUnit: 'vectors', cost: '¥0.8', costUnit: '嵌入模型', inputBarVal: '1.2M / 10M', inputBarPct: 12, costBarVal: '¥0.8 / ¥200', costBarPct: 1 },
}

export function Settings() {
  const [section, setSection] = useState<Section>('model')
  const [modelRole, setModelRole] = useState<ModelRole>('fast')

  const NAV = [
    { key: 'model' as Section, label: '模型配置', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg> },
    { key: 'notify' as Section, label: '通知', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg> },
    { key: 'account' as Section, label: '账号', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
  ]

  const stats = MODEL_STATS[modelRole]

  return (
    <div className="grid-bg" style={{ minHeight: '100vh' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: 40 }}>

        {/* 页头 */}
        <div style={{ marginBottom: 32 }}>
          <div className="section-tag">// USER SETTINGS</div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>设置</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>配置您的模型、API 接入参数与通知方式，设置仅对您本人生效</p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 24, alignItems: 'start' }}>

          {/* 左侧导航 */}
          <nav style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden', position: 'sticky', top: 76 }}>
            {NAV.map((item, i) => (
              <div key={item.key}>
                {i > 0 && <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />}
                <div onClick={() => setSection(item.key)} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '12px 16px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
                  borderLeft: section === item.key ? '2px solid var(--action)' : '2px solid transparent',
                  background: section === item.key ? 'var(--action-light)' : 'transparent',
                  color: section === item.key ? 'var(--action)' : 'var(--text-secondary)',
                  transition: 'all 0.15s',
                }}>
                  <span style={{ opacity: section === item.key ? 1 : 0.7 }}>{item.icon}</span>
                  {item.label}
                </div>
              </div>
            ))}
          </nav>

          {/* 右侧内容 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* ① 模型配置 */}
            {section === 'model' && (
              <>
                {/* 本月用量 */}
                <SettingsCard>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, padding: '20px 24px 0' }}>
                    <div>
                      <div style={cardTitleStyle}>本月用量</div>
                      <div style={cardDescStyle}>统计周期：2026-08-01 ~ 2026-08-31</div>
                    </div>
                    <div style={{ display: 'inline-flex', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: 3, gap: 2 }}>
                      {(['fast', 'deep', 'embed'] as ModelRole[]).map(role => (
                        <button key={role} onClick={() => setModelRole(role)} style={{
                          display: 'flex', alignItems: 'center', gap: 7,
                          padding: '7px 14px', border: 'none', borderRadius: 6,
                          fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                          background: modelRole === role ? 'var(--surface)' : 'transparent',
                          color: modelRole === role ? 'var(--text-primary)' : 'var(--text-secondary)',
                          boxShadow: modelRole === role ? '0 1px 4px rgba(11,46,92,0.1)' : 'none',
                          transition: 'all 0.15s',
                        }}>
                          <span style={roleTagStyle(role)}>{role.toUpperCase()}</span>
                          {role === 'fast' ? '快速回复' : role === 'deep' ? '深度思考' : '嵌入模型'}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div style={{ padding: '20px 24px 24px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
                      {[
                        { label: 'SESSIONS', value: stats.sessions.toString(), unit: '次调用' },
                        { label: 'INPUT', value: stats.input, unit: 'tokens' },
                        { label: 'OUTPUT', value: stats.output, unit: stats.outputUnit },
                        { label: 'COST', value: stats.cost, unit: stats.costUnit, accent: true },
                      ].map(s => (
                        <div key={s.label} style={{ background: 'var(--bg)', border: '1px solid var(--border-light)', borderRadius: 8, padding: '14px 16px' }}>
                          <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", marginBottom: 6 }}>{s.label}</div>
                          <div style={{ fontSize: 22, fontWeight: 700, color: s.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{s.value}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{s.unit}</div>
                        </div>
                      ))}
                    </div>
                    <UsageBar label="Input Tokens 月度消耗" val={stats.inputBarVal} pct={stats.inputBarPct} />
                    <UsageBar label="估算费用" val={stats.costBarVal} pct={stats.costBarPct} />
                  </div>
                </SettingsCard>

                {/* 模型配置卡片 */}
                {modelRole === 'fast' && <ModelCard role="fast" title="快速回复模型" desc="用于常规对话、工具结果汇总，优先速度与低延迟" modelName="deepseek-v4-flash" provider="DeepSeek" apiKey="sk-••••••••••••••••••••••••••••••••Ax1m" baseUrl="https://api.deepseek.com/v1" inputPrice="0.001" outputPrice="0.002" cost="¥1.2" />}
                {modelRole === 'deep'  && <ModelCard role="deep"  title="深度思考模型" desc="用于复杂推理、量化分析，优先准确性与分析深度" modelName="deepseek-v4-pro" provider="DeepSeek" apiKey="sk-••••••••••••••••••••••••••••••••Bk2p" baseUrl="https://api.deepseek.com/v1" inputPrice="0.004" outputPrice="0.016" cost="¥2.8" />}
                {modelRole === 'embed' && <EmbedCard />}
              </>
            )}

            {/* ② 通知 */}
            {section === 'notify' && <NotifySection />}

            {/* ③ 账号 */}
            {section === 'account' && <AccountSection />}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── 子组件 ── */

function SettingsCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {children}
    </div>
  )
}

function CardFooter({ left, right }: { left?: React.ReactNode; right: React.ReactNode }) {
  return (
    <div style={{ padding: '16px 24px', background: '#FAFBFD', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border-light)' }}>
      <div>{left}</div>
      <div>{right}</div>
    </div>
  )
}

function UsageBar({ label, val, pct }: { label: string; val: string; pct: number }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-primary)' }}>{val}</span>
      </div>
      <div style={{ height: 6, background: 'var(--border-light)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--action)', borderRadius: 3, transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

function SaveFeedback({ show }: { show: boolean }) {
  return (
    <span style={{ fontSize: 12, color: 'var(--status-done)', display: 'flex', alignItems: 'center', gap: 5, opacity: show ? 1 : 0, transition: 'opacity 0.3s' }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>已保存
    </span>
  )
}

function TestBtn({ onTest }: { onTest: () => void }) {
  const [result, setResult] = useState<'idle' | 'ok'>('idle')
  const handleTest = () => {
    setResult('idle')
    setTimeout(() => { setResult('ok'); onTest() }, 800)
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <button onClick={handleTest} style={{ height: 34, padding: '0 16px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>测试连接</button>
      {result === 'ok' && <span style={{ fontSize: 12, color: 'var(--status-done)' }}>✓ 连接成功</span>}
    </div>
  )
}

function ApiKeyField({ defaultValue }: { defaultValue: string }) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label style={formLabelStyle}>API Key</label>
      <div style={{ position: 'relative' }}>
        <input type={show ? 'text' : 'password'} defaultValue={defaultValue}
          style={{ ...formInputStyle, width: '100%', paddingRight: 60, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }} />
        <button onClick={() => setShow(s => !s)} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', height: 24, padding: '0 8px', border: 'none', background: 'transparent', fontSize: 11, color: 'var(--action)', cursor: 'pointer', fontFamily: 'inherit' }}>
          {show ? '隐藏' : '显示'}
        </button>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>API Key 经 AES-256 加密存储</span>
    </div>
  )
}

function ModelCard({ role, title, desc, modelName, provider, apiKey, baseUrl, inputPrice, outputPrice, cost }:
  { role: ModelRole; title: string; desc: string; modelName: string; provider: string; apiKey: string; baseUrl: string; inputPrice: string; outputPrice: string; cost: string }) {
  const [showSave, setShowSave] = useState(false)
  const handleSave = () => {
    setShowSave(true)
    setTimeout(() => setShowSave(false), 2500)
  }
  return (
    <SettingsCard>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={roleTagStyle(role)}>{role.toUpperCase()}</span>
          <div>
            <div style={cardTitleStyle}>{title}</div>
            <div style={cardDescStyle}>{desc}</div>
          </div>
        </div>
      </div>
      <div style={{ padding: '20px 24px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={formLabelStyle}>模型名称</label>
            <input type="text" defaultValue={modelName} placeholder="模型 ID" style={{ ...formInputStyle, width: '100%' }} />
          </div>
          <div>
            <label style={formLabelStyle}>提供商</label>
            <input type="text" defaultValue={provider} placeholder="如 DeepSeek、OpenAI" style={{ ...formInputStyle, width: '100%' }} />
          </div>
        </div>
        <ApiKeyField defaultValue={apiKey} />
        <div>
          <label style={formLabelStyle}>API Base URL</label>
          <input type="text" defaultValue={baseUrl} style={{ ...formInputStyle, width: '100%', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={formLabelStyle}>Input 单价</label>
            <div style={{ position: 'relative' }}>
              <input type="number" step="0.001" defaultValue={inputPrice} readOnly style={{ ...formInputStyle, width: '100%', paddingRight: 60, cursor: 'default', color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace" }} />
              <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", pointerEvents: 'none' }}>元 / 1K</span>
            </div>
          </div>
          <div>
            <label style={formLabelStyle}>Output 单价</label>
            <div style={{ position: 'relative' }}>
              <input type="number" step="0.001" defaultValue={outputPrice} readOnly style={{ ...formInputStyle, width: '100%', paddingRight: 60, cursor: 'default', color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace" }} />
              <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", pointerEvents: 'none' }}>元 / 1K</span>
            </div>
          </div>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>单价由模型提供商定价，随模型名称自动填入，不可手动修改</span>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', background: 'var(--bg)', border: '1px solid var(--border-light)', borderRadius: 7 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>本月该模型估算费用</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--action)', fontFamily: "'JetBrains Mono', monospace" }}>{cost}</span>
        </div>
      </div>
      <CardFooter
        left={<TestBtn onTest={() => {}} />}
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SaveFeedback show={showSave} />
            <button onClick={handleSave} style={primaryBtnStyle}>保存</button>
          </div>
        }
      />
    </SettingsCard>
  )
}

function EmbedCard() {
  const [showSave, setShowSave] = useState(false)
  const handleSave = () => { setShowSave(true); setTimeout(() => setShowSave(false), 2500) }
  return (
    <SettingsCard>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={roleTagStyle('embed')}>EMBED</span>
          <div>
            <div style={cardTitleStyle}>向量嵌入模型</div>
            <div style={cardDescStyle}>用于知识库文档切片的向量化与语义检索，模型固定为 bge-m3</div>
          </div>
        </div>
      </div>
      <div style={{ padding: '20px 24px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={formLabelStyle}>模型名称</label>
            <input type="text" defaultValue="bge-m3" readOnly style={{ ...formInputStyle, width: '100%', cursor: 'default', color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace" }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>模型固定，不可更改</span>
          </div>
          <div>
            <label style={formLabelStyle}>向量维度</label>
            <input type="text" defaultValue="1024" readOnly style={{ ...formInputStyle, width: '100%', cursor: 'default', color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace" }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>由 bge-m3 默认输出维度决定</span>
          </div>
        </div>
        <ApiKeyField defaultValue="sk-••••••••••••••••••••••••••••••••Em3k" />
        <div>
          <label style={formLabelStyle}>API Base URL</label>
          <input type="text" defaultValue="https://api.siliconflow.cn/v1" style={{ ...formInputStyle, width: '100%', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>支持接入第三方嵌入服务或私有部署</span>
        </div>
      </div>
      <CardFooter
        left={<TestBtn onTest={() => {}} />}
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SaveFeedback show={showSave} />
            <button onClick={handleSave} style={primaryBtnStyle}>保存</button>
          </div>
        }
      />
    </SettingsCard>
  )
}

function NotifySection() {
  const [showSave, setShowSave] = useState(false)
  const [testSent, setTestSent] = useState(false)
  const handleSave = () => { setShowSave(true); setTimeout(() => setShowSave(false), 2500) }
  const handleTest = () => { setTestSent(false); setTimeout(() => setTestSent(true), 600) }
  return (
    <SettingsCard>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={cardTitleStyle}>飞书机器人通知</div>
        <div style={cardDescStyle}>分析任务完成后，自动向飞书群发送报告摘要与链接</div>
      </div>
      <div style={{ padding: '20px 24px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 7, fontSize: 13, color: '#065F46' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
          Webhook 已配置，上次推送成功：2026-08-06 14:32
        </div>
        <div>
          <label style={formLabelStyle}>Webhook URL</label>
          <input type="text" defaultValue="https://open.feishu.cn/open-apis/bot/v2/hook/••••••••-••••-••••"
            style={{ ...formInputStyle, width: '100%', fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>在飞书群设置 → 群机器人 → 添加机器人 → 自定义机器人中获取</span>
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 10 }}>推送内容</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {['报告标题与摘要（前 500 字）', '报告访问链接', 'Token 用量与费用'].map((item, i) => (
              <label key={item} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <input type="checkbox" defaultChecked={i < 2} style={{ accentColor: 'var(--action)', width: 14, height: 14 }} />
                {item}
              </label>
            ))}
          </div>
        </div>
      </div>
      <CardFooter
        left={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={handleTest} style={{ height: 34, padding: '0 16px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>发送测试消息</button>
            {testSent && <span style={{ fontSize: 12, color: 'var(--status-done)' }}>✓ 测试消息已发送</span>}
          </div>
        }
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SaveFeedback show={showSave} />
            <button onClick={handleSave} style={primaryBtnStyle}>保存</button>
          </div>
        }
      />
    </SettingsCard>
  )
}

function AccountSection() {
  const [showAccountSave, setShowAccountSave] = useState(false)
  const handleAccountSave = () => { setShowAccountSave(true); setTimeout(() => setShowAccountSave(false), 2500) }
  return (
    <>
      {/* 账号信息 */}
      <SettingsCard>
        <div style={{ padding: '20px 24px 0' }}>
          <div style={cardTitleStyle}>账号信息</div>
        </div>
        <div style={{ padding: '20px 24px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
            <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--action)', color: '#fff', fontSize: 22, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>张</div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>张老师</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>zhang@fin.edu.cn</div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={formLabelStyle}>用户名</label>
              <input type="text" defaultValue="张老师" style={{ ...formInputStyle, width: '100%' }} />
            </div>
            <div>
              <label style={formLabelStyle}>邮箱</label>
              <input type="email" defaultValue="zhang@fin.edu.cn" style={{ ...formInputStyle, width: '100%' }} />
            </div>
          </div>
        </div>
        <CardFooter
          left={<span style={{ fontSize: 12, color: 'var(--text-muted)' }}>注册时间：2026-01-15</span>}
          right={
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <SaveFeedback show={showAccountSave} />
              <button onClick={handleAccountSave} style={primaryBtnStyle}>保存</button>
            </div>
          }
        />
      </SettingsCard>

      {/* 修改密码 */}
      <SettingsCard>
        <div style={{ padding: '20px 24px 0' }}>
          <div style={cardTitleStyle}>修改密码</div>
        </div>
        <div style={{ padding: '20px 24px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={formLabelStyle}>当前密码</label>
            <input type="password" placeholder="输入当前密码" style={{ ...formInputStyle, width: '100%' }} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={formLabelStyle}>新密码</label>
              <input type="password" placeholder="至少 8 位" style={{ ...formInputStyle, width: '100%' }} />
            </div>
            <div>
              <label style={formLabelStyle}>确认新密码</label>
              <input type="password" placeholder="再次输入新密码" style={{ ...formInputStyle, width: '100%' }} />
            </div>
          </div>
        </div>
        <CardFooter right={<button style={primaryBtnStyle}>更新密码</button>} />
      </SettingsCard>

      {/* 危险区 */}
      <div style={{ border: '1px solid #FECACA', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', background: '#FEF2F2', borderBottom: '1px solid #FECACA' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#DC2626' }}>危险操作</div>
        </div>
        <div style={{ padding: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--surface)' }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>注销账号</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>永久删除您的账号及所有数据，此操作不可撤销</div>
          </div>
          <button style={{ height: 36, padding: '0 18px', background: '#DC2626', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>注销账号</button>
        </div>
      </div>
    </>
  )
}

/* ── 样式常量 ── */
const cardTitleStyle: React.CSSProperties = { fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }
const cardDescStyle: React.CSSProperties = { fontSize: 13, color: 'var(--text-secondary)' }
const formLabelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const formInputStyle: React.CSSProperties = {
  height: 38, padding: '0 12px', border: '1px solid var(--border)', borderRadius: 7,
  fontSize: 13, color: 'var(--text-primary)', background: '#F7F9FC',
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const primaryBtnStyle: React.CSSProperties = {
  height: 34, padding: '0 18px', background: 'var(--action)', color: '#fff',
  border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600,
  cursor: 'pointer', fontFamily: 'inherit',
}

function roleTagStyle(role: ModelRole): React.CSSProperties {
  const map = {
    fast:  { background: '#ECFDF5', color: '#059669', border: '1px solid #A7F3D0' },
    deep:  { background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' },
    embed: { background: '#FFFBEB', color: '#D97706', border: '1px solid #FDE68A' },
  }
  return {
    display: 'inline-flex', alignItems: 'center', padding: '2px 8px',
    borderRadius: 4, fontSize: 11, fontWeight: 600, letterSpacing: '0.05em',
    fontFamily: "'JetBrains Mono', monospace", flexShrink: 0,
    ...map[role],
  }
}
