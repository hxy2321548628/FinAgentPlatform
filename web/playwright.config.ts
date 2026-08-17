import { defineConfig, devices } from '@playwright/test'

/**
 * 端到端走查配置：三档可见性（P7⑥）与 Skill 上传校验（P8⑥）。
 *
 * **不进 `make all`。** 那是纯本地门禁，跑它不需要任何服务起着；而这些走查要六个
 * 服务、真账号、真库。塞进去等于让每一次 `git push` 都依赖一整套 compose 栈起着 ——
 * 那道门禁会在第一次没起服务的机器上变成一条永远红的判据。它进的是
 * `script/test/verify.sh` 的 `P7⑥`，缺浏览器二进制时记「未验」。
 *
 * **账号由 verify.sh 造好再从环境变量传进来**：平台没有公开的教师注册入口，
 * 建号要进容器算哈希、进库插行 —— 那不是浏览器干得了的事。
 *
 * `webServer` 起的是 vite 开发服务器，它把 `/api` 代理到 nginx。**走查看的是工作区里
 * 的前端，不是镜像里那份** —— nginx 现在也发前端（`web/Dockerfile` 把 dist 烤了进去），
 * 但那份要重建镜像才更新，拿它走查等于验上一次构建。
 */
const PORT = Number(process.env.E2E_PORT ?? 5174)

export default defineConfig({
  testDir: './e2e',
  // **一个 worker、不重试。** 走查会在多个账号之间切登录态，并行跑会互相
  // 顶掉 cookie；而自动重试会把「第一次红、第二次绿」的偶发问题藏起来
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
  },
  // **走完整的 chromium 而不是默认的 headless shell。** 后者是另一份要单独下载的
  // 二进制，而 `playwright install chromium` 装上完整浏览器之后它未必也在 ——
  // 缺它时报的是「Executable doesn't exist」，看起来像根本没装浏览器
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chromium' } }],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
