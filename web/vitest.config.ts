import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    // **`e2e/` 不归 vitest 管。** 那一整目录要浏览器与一整套 compose 栈，由 playwright
    // 跑、进 verify.sh 的 P7⑥；混进单测里会让 `make all` 变成依赖服务起着
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    coverage: {
      provider: 'v8',
      include: [
        'src/api/request.ts',
        'src/api/events.ts',
        'src/api/runEventTransport.ts',
        'src/hooks/useRunEvents.ts',
        'src/workspace/agent.ts',
        'src/workspace/config.ts',
        'src/workspace/decisions.ts',
        'src/workspace/eventReducer.ts',
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
  },
})
