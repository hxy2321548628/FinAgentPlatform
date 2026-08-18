import { useQuery } from '@tanstack/react-query'
import { adminKeys, systemStatus } from '../../../api/admin'
import { errorMessage } from '../../../api/request'
import { AdminPageHeader, AdminTableSection } from './AdminUi'

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
    <div className="admin-page">
      <AdminPageHeader eyebrow="OPERATIONS · SYSTEM" title="系统状态" description="监控沙箱池容量、当前占用与排队压力；数据每 10 秒自动刷新。" />

      {status.isError && <div role="alert" className="admin-alert">{errorMessage(status.error)}</div>}

      {/* **broker 没应答时不能把 0 显示成「空闲」。** 那正是最需要看清状态的时刻，
          而「0 / 0，一片空闲」会让人以为平台好着 */}
      {data && !data.broker_reachable && (
        <div role="alert" className="admin-notice danger">
          broker 没有应答，下面的数字不可信。它持有 docker.sock 与沙箱池 ——
          它不在，任何人都建不了新会话。请检查 <code>zuel-platform-broker-1</code> 这个容器。
        </div>
      )}

      <AdminTableSection title="沙箱池">
        <div className="admin-system-card">
          {status.isPending ? (
            <div className="admin-system-loading" role="status">正在读取沙箱池状态…</div>
          ) : (
            <>
              <div className="admin-system-metric">
                <span>当前资源占用</span>
                <strong>
                  {data?.broker_reachable ? `${inUse} / ${capacity}` : '— / —'}
                </strong>
              </div>
              <div className="admin-capacity-track" role="progressbar" aria-label="沙箱池占用率" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                <div className={pct > 80 ? 'warning' : ''} style={{ width: `${pct}%` }} />
              </div>
              <div className="admin-system-caption">
                {data?.broker_reachable
                  ? `剩余 ${Math.max(capacity - inUse, 0)} 个沙箱可用 · gVisor 隔离`
                  : '数据不可用'}
              </div>
              {/* **排队人数要单独说。** 满池与「满池且还有人在等」是两种情况，
                  只看占用条的话它们长得一模一样 */}
              {data?.broker_reachable && data.queued > 0 && (
                <div className="admin-inline-notice warning">
                  有 {data.queued} 个申请正在排队等沙箱 —— 池已经不够用了。
                </div>
              )}
            </>
          )}
        </div>
      </AdminTableSection>

      <AdminTableSection title="排障入口">
        <div className="admin-troubleshooting">
          {/* 这一页曾经列着 Worker / Postgres / Redis / MinIO 四行写死的「● 在线」。
              MinIO 已于 2026-08-13 随可观测性一并撤除，另外三个的死活也不该由一行
              写死的绿点来回答 —— 它们真挂了的时候，这一页本身就打不开 */}
          三个进程都打 JSON 行日志，一条 run 的全过程这样捞：
          <pre className="admin-code">docker compose -f docker/compose.yml logs worker | jq -c 'select(.run_id == "…")'</pre>
          模型链路与用量在 Langfuse 上看；这一页只回答「沙箱池还剩多少」——
          那是平台唯一一个会被抢光的资源。
        </div>
      </AdminTableSection>
    </div>
  )
}
