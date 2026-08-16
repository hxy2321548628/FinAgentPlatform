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

setUnauthorizedHandler(() => {
  queryClient.clear()
  if (window.location.pathname !== '/login') window.location.assign('/login')
})

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
