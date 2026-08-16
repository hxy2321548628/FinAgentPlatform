import { useQuery } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../api/auth'
import { errorMessage } from '../api/request'
import { myUsage, usageKeys } from '../api/usage'
import type { UserRole } from '../api/types'
import { ThemeMenu } from '../components/ui/ThemeMenu'

const ROLE_LABEL: Record<UserRole, string> = {
  admin: '管理员',
  reviewer: '审核员',
  teacher: '教师',
  student: '学生',
}

function monthRange(): string {
  const now = new Date()
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}-${month}-01 ~ ${now.getFullYear()}-${month}-${last}`
}

export function Settings() {
  const account = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const usage = useQuery({ queryKey: usageKeys.mine(), queryFn: myUsage })

  return (
    <div className="grid-bg" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <div style={{ maxWidth: 820, margin: '0 auto', padding: 40 }}>

        <div style={{ marginBottom: 32 }}>
          <div className="section-tag">// USER SETTINGS</div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>设置</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>查看你的账号与本月用量</p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* 外观（DSD 第二章 §2.2 暗色色板，2026-08-16）。
              入口在公共顶栏对所有访问者开放，这里给登录后的工作台用户留同一入口 */}
          <SettingsCard>
            <div style={{ padding: '20px 24px 0' }}>
              <div style={cardTitleStyle}>外观</div>
              <div style={cardDescStyle}>浅色 / 深色 / 跟随系统；「跟随系统」会响应操作系统的明暗切换</div>
            </div>
            <div style={{ padding: '20px 24px 24px', display: 'flex', gap: 8 }}>
              <ThemeMenu />
            </div>
          </SettingsCard>

          {/* 本月用量 */}
          <SettingsCard>
            <div style={{ padding: '20px 24px 0' }}>
              <div style={cardTitleStyle}>本月用量</div>
              <div style={cardDescStyle}>统计周期：{monthRange()}</div>
            </div>
            <div style={{ padding: '20px 24px 24px' }}>
              {usage.isPending && <div style={mutedStyle}>正在读取…</div>}
              {usage.isError && <div role="alert" style={alertStyle}>{errorMessage(usage.error)}</div>}

              {/* **「没接账本」不能显示成一排 0。** 那样教师无从判断是自己没用过，
                  还是平台根本没在记 —— 而这两件事一个什么都不用做，一个要去配环境 */}
              {usage.data && !usage.data.available && (
                <div role="status" style={noticeStyle}>
                  用量账本未接入，因此这里暂时没有数据。这不影响分析功能，也不影响配额。
                </div>
              )}

              {usage.data?.available && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                  {[
                    { label: 'TOKENS', value: usage.data.tokens.toLocaleString(), unit: '本月累计' },
                    { label: 'MODEL CALLS', value: usage.data.observations.toLocaleString(), unit: '次模型调用' },
                    // 单价没注册时费用恒为 0，这时显示「未计价」比显示 $0.00 诚实
                    {
                      label: 'COST',
                      value: usage.data.cost > 0 ? `$${usage.data.cost.toFixed(2)}` : '未计价',
                      unit: '估算费用',
                      accent: true,
                    },
                  ].map(one => (
                    <div key={one.label} style={{ background: 'var(--bg)', border: '1px solid var(--border-light)', borderRadius: 8, padding: '14px 16px' }}>
                      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", marginBottom: 6 }}>{one.label}</div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: one.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{one.value}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{one.unit}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </SettingsCard>

          {/* 账号信息。**只读** —— 后端没有「改自己的资料」这条路径，
              改用户名要找管理员（用户名与邮箱都是登录凭据，全库唯一） */}
          <SettingsCard>
            <div style={{ padding: '20px 24px 0' }}>
              <div style={cardTitleStyle}>账号信息</div>
              <div style={cardDescStyle}>需要修改请联系管理员</div>
            </div>
            <div style={{ padding: '20px 24px 24px' }}>
              {account.isPending && <div style={mutedStyle}>正在读取…</div>}
              {account.isError && <div role="alert" style={alertStyle}>{errorMessage(account.error)}</div>}
              {account.data && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--action)', color: '#fff', fontSize: 22, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {account.data.name.slice(0, 1)}
                  </div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {account.data.name}
                      <span style={roleTagStyle}>{ROLE_LABEL[account.data.role]}</span>
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{account.data.email || '（没有邮箱）'}</div>
                  </div>
                </div>
              )}
            </div>
          </SettingsCard>

        </div>
      </div>
    </div>
  )
}

function SettingsCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {children}
    </div>
  )
}

const cardTitleStyle: React.CSSProperties = { fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }
const cardDescStyle: React.CSSProperties = { fontSize: 13, color: 'var(--text-secondary)' }
const mutedStyle: React.CSSProperties = { fontSize: 13, color: 'var(--text-muted)' }
const alertStyle: React.CSSProperties = { padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13 }
const noticeStyle: React.CSSProperties = { padding: '12px 14px', border: '1px solid #FDE68A', borderRadius: 8, background: 'var(--warn-bg)', color: 'var(--warn)', fontSize: 13, lineHeight: 1.7 }
const roleTagStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', marginLeft: 10, padding: '2px 8px',
  borderRadius: 4, fontSize: 11, fontWeight: 600, letterSpacing: '0.05em',
  background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE',
  fontFamily: "'JetBrains Mono', monospace", verticalAlign: 'middle',
}
