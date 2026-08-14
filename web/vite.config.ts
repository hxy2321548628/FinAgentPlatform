import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 开发服务器把 `/api` 转给平台。**默认指向 nginx 的 80 端口**（compose 里那一层），
// 端到端走查在别的端口上起栈时用 `E2E_API_TARGET` 覆盖 —— 在这里写死第二个默认值的话，
// 猜错了不会报错，只会让走查在一套空库上跑。
const API_TARGET = process.env.E2E_API_TARGET ?? 'http://127.0.0.1:80'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: false,
      },
    },
  },
})
