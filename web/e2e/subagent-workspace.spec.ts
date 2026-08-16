import { expect, test, type Page } from '@playwright/test'

/** P9⑥：浏览器里配置子智能体，并展开消息流中的嵌套过程。 */

test.setTimeout(300_000)

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')
const SUBAGENT_NAME = required('E2E_SUBAGENT_NAME')
const QUESTION = process.env.E2E_SUBAGENT_QUESTION ?? [
  '只做这一件事：固定收益率数组 [0.01,-0.005,0.008,-0.002,0.006] 的样本标准差是 0.00654217089351845，乘以 sqrt(252) 后年化波动率是 0.10385374331241026。',
  '如果存在名为 volatility-expert 的可委派子智能体，必须把整项工作委派给它，自己不得代做。',
  '只调用一次 write_file，把这段计算写进 outputs/p9-browser.txt；不调用其他工具。完成后只回答输出文件名。',
].join(' ')

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少环境变量 ${name}：P9⑥ 需要 verify.sh 先准备好账号和子智能体`)
  return value
}

async function signIn(page: Page, name: string) {
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByPlaceholder('用户名或邮箱都可以').fill(name)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: '登录系统' }).click()
  await expect(page).toHaveURL(/\/workspace/)
}

test('新会话配置子智能体后，消息流显示可展开的命名嵌套工具过程', async ({ page }) => {
  await signIn(page, AUTHOR)
  await page.goto('/workspace/chat')
  await page.getByRole('button', { name: '＋ 新建分析' }).click()
  await expect(page).toHaveURL(/\/workspace\/chat\/[^/]+$/)

  await page.getByRole('button', { name: /本轮智能体配置/ }).click()
  // **按名字定位会命中两个**：P9③ 让同组的 B 也建了一个叫 volatility-expert 的
  // 子智能体并共享进同一个组（那条判据验的就是同名闸门），于是候选列表里同名两项。
  // 用属主那一行钉到作者自己的那一个 —— 挂错人的同名 agent 会跑出另一份提示词。
  const child = page.locator('label').filter({ hasText: AUTHOR })
    .getByRole('checkbox', { name: SUBAGENT_NAME, exact: true })
  await expect(child).toHaveCount(1)
  await expect(child).toBeVisible()
  await child.check()
  // 配置面板是覆盖整屏的模态框，不关掉它，发送按钮被遮罩挡着点不到
  await page.getByRole('button', { name: '完成' }).click()
  await expect(page.getByRole('dialog', { name: '智能体配置' })).toHaveCount(0)

  const input = page.getByPlaceholder(/输入分析需求/)
  await input.fill(QUESTION)
  await page.getByTitle('发送').click()

  const nested = page.locator(`details[data-subagent="${SUBAGENT_NAME}"]`)
  await expect(nested).toBeVisible({ timeout: 240_000 })
  await expect(nested.locator('summary')).toContainText(SUBAGENT_NAME)

  // 开工时先用不存在的 data-subagent 名称跑过一次，确认断言会因页面映射缺失而失败；
  // 正式判据锁定真实名称，避免 uuid 回退或嵌套事件平铺时误报通过。
  await nested.locator('summary').click()
  await expect(nested.getByRole('button', { name: /write_file/ })).toBeVisible()
})
