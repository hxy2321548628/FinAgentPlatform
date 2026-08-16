import { useQuery } from '@tanstack/react-query'
import { adminKeys, systemStatus } from '../../../api/admin'
import { errorMessage } from '../../../api/request'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import { pageStyle } from './AdminStyles'

// 池状态每 10 秒刷一次。它是会变的量，而这一页正是为了看它变
const REFRESH_MS = 10_000

export function AdminSystem() {
  const status = useQuery({
    queryKey: adminKeys.system(),
    queryFn: systemStatus,
    refetchInterval: REFRESH_MS,
  })

  const data = status.data
  const capacity = data?.capacity ?? 0
  const inUse = data?.in_use ?? 0
  const pct = capacity > 0 ? Math.round((inUse / capacity) * 100) : 0

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// SYSTEM STATUS" title="系统状态" />

      {status.isError && <div role="alert" style={alertStyle}>{errorMessage(status.error)}</div>}

      {/* **broker 没应答时不能把 0 显示成「空闲」。** 那正是最需要看清状态的时刻，
          而「0 / 0，一片空闲」会让人以为平台好着 */}
      {data && !data.broker_reachable && (
        <div role="alert" style={noticeStyle}>
          broker 没有应答，下面的数字不可信。它持有 docker.sock 与沙箱池 ——
          它不在，任何人都建不了新会话。请检查 <code>zuel-platform-broker-1</code> 这个容器。
        </div>
      )}

      <AdminTableSection title="沙箱池">
        <div style={{ padding: '20px 18px' }}>
          {status.isPending ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>正在读取…</div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>当前资源占用</span>
                <span style={{ color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>
                  {data?.broker_reachable ? `${inUse} / ${capacity}` : '— / —'}
                </span>
              </div>
              <div style={{ height: 10, marginBottom: 8, overflow: 'hidden', borderRadius: 5, background: 'var(--border-light)' }}>
                <div style={{ width: `${pct}%`, height: '100%', borderRadius: 5, background: pct > 80 ? 'var(--status-warn)' : 'var(--action)', transition: 'width 0.4s' }} />
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                {data?.broker_reachable
                  ? `剩余 ${Math.max(capacity - inUse, 0)} 个沙箱可用 · gVisor 隔离`
                  : '数据不可用'}
              </div>
              {/* **排队人数要单独说。** 满池与「满池且还有人在等」是两种情况，
                  只看占用条的话它们长得一模一样 */}
              {data?.broker_reachable && data.queued > 0 && (
                <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 6, background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E', fontSize: 12 }}>
                  有 {data.queued} 个申请正在排队等沙箱 —— 池已经不够用了。
                </div>
              )}
            </>
          )}
        </div>
      </AdminTableSection>

      <AdminTableSection title="排障入口">
        <div style={{ padding: '18px', color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.9 }}>
          {/* 这一页曾经列着 Worker / Postgres / Redis / MinIO 四行写死的「● 在线」。
              MinIO 已于 2026-08-13 随可观测性一并撤除，另外三个的死活也不该由一行
              写死的绿点来回答 —— 它们真挂了的时候，这一页本身就打不开 */}
          三个进程都打 JSON 行日志，一条 run 的全过程这样捞：
          <pre style={codeStyle}>docker compose -f deploy/compose.yml logs worker | jq -c 'select(.run_id == "…")'</pre>
          模型链路与用量在 Langfuse 上看；这一页只回答「沙箱池还剩多少」——
          那是平台唯一一个会被抢光的资源。
        </div>
      </AdminTableSection>
    </div>
  )
}

const alertStyle: React.CSSProperties = { marginBottom: 14, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: '#FEF2F2', color: '#DC2626', fontSize: 13 }
const noticeStyle: React.CSSProperties = { marginBottom: 16, padding: '12px 14px', border: '1px solid #FECACA', borderRadius: 8, background: '#FEF2F2', color: '#991B1B', fontSize: 13, lineHeight: 1.7 }
const codeStyle: React.CSSProperties = { margin: '8px 0', padding: '10px 12px', borderRadius: 6, background: 'var(--bg)', border: '1px solid var(--border)', fontFamily: "'JetBrains Mono', monospace", fontSize: 11, overflowX: 'auto', color: 'var(--text-primary)' }
