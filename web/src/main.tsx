import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import './styles/theme.css'
import 'katex/dist/katex.min.css'
import App from './App.tsx'
import { setUnauthorizedHandler } from './api/request.ts'
import { runEventTransport } from './api/runEventTransport.ts'
import { RunEventTransportProvider } from './api/RunEventTransportContext.tsx'
import { queryClient } from './queryClient.ts'
import { ToastProvider } from './components/ui/Toast.tsx'
import { initTheme } from './components/ui/theme.ts'

setUnauthorizedHandler(() => {
  queryClient.clear()
  if (window.location.pathname !== '/login') window.location.assign('/login')
})

// 首帧前应用主题（避免亮暗闪跳），并监听系统偏好变化
initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RunEventTransportProvider transport={runEventTransport}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <App />
        </ToastProvider>
      </QueryClientProvider>
    </RunEventTransportProvider>
  </StrictMode>,
)
