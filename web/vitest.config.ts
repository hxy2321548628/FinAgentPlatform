import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    coverage: {
      provider: 'v8',
      include: [
        'src/api/request.ts',
        'src/api/events.ts',
        'src/api/runEventTransport.ts',
        'src/hooks/useRunEvents.ts',
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
