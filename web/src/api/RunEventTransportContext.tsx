import { createContext, useContext } from 'react'
import type { RunEventTransport } from './events'

const RunEventTransportContext = createContext<RunEventTransport | null>(null)

export function RunEventTransportProvider({
  transport,
  children,
}: {
  transport: RunEventTransport
  children: React.ReactNode
}) {
  return <RunEventTransportContext value={transport}>{children}</RunEventTransportContext>
}

// oxlint-disable-next-line react/only-export-components -- provider 与它的唯一读取 hook 共用同一个私有 context。
export function useRunEventTransport(): RunEventTransport | null {
  return useContext(RunEventTransportContext)
}
