import { expect, test, type Page } from '@playwright/test'

/**
 * P10⑥：浏览器里两条路径都看得见外发标注。
 *
 * **这条判据是 F12 组合风险唯一的守卫。** 风险登记 §10.2.1 写着：「若 P9/P10
 * 落地时漏掉这一条，这条风险就从『已缓解』退回『敞着』」——「敞着」的样子是：
 * 教师一个 MCP 都没勾，只选了一个场景，而那个场景背后的子智能体连着一台校外机器，
 * 而界面上看不出任何异样。**这种失败形态只有界面看得见**，后端每一条断言都是绿的。
 *
 * 两条路径：
 *   1. 直接勾一个 MCP；
 *   2. 只选一个自带 MCP 的子智能体，一个 MCP 都不勾。
 *
 * **不跑分析，因此不花钱。** 验的是配置面板上看不看得见，不是模型调没调那个工具 ——
 * 后者是 `P10①` 的事。
 */

test.setTimeout(120_000)

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')
const MCP_NAME = required('E2E_MCP_NAME')
const SCENE_NAME = required('E2E_MCP_SCENE_NAME')

const OUTBOUND_NOTICE = '此服务位于校外，调用时你的数据会发送至外部'

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少环境变量 ${name}：P10⑥ 需要 verify.sh 先准备好账号、MCP 与场景`)
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

async function openConfig(page: Page) {
  await page.goto('/workspace/chat')
  await page.getByRole('button', { name: '＋ 新建分析' }).click()
  await expect(page).toHaveURL(/\/workspace\/chat\/[^/]+$/)
  await page.getByRole('button', { name: /本轮智能体配置/ }).click()
  await expect(page.getByRole('dialog', { name: '智能体配置' })).toBeVisible()
}

test('直接勾一个 MCP，配置面板上出现外发标注', async ({ page }) => {
  await signIn(page, AUTHOR)
  await openConfig(page)

  // 勾之前不该有标注 —— 只断言「勾完有」的话，一个永远显示的横幅也能让它绿
  await expect(page.getByTestId('mcp-outbound')).toHaveCount(0)

  await page.getByRole('checkbox', { name: MCP_NAME, exact: true }).check()

  const notice = page.getByTestId('mcp-outbound')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText(OUTBOUND_NOTICE)
  await expect(notice).toContainText(MCP_NAME)
})

test('只选一个自带 MCP 的子智能体，同样看得见它会连哪台校外服务', async ({ page }) => {
  await signIn(page, AUTHOR)
  await openConfig(page)

  // **一个 MCP 都不勾。** 这正是 F12 那条组合风险的形状
  await expect(page.getByRole('checkbox', { name: MCP_NAME, exact: true })).not.toBeChecked()

  const scene = page.locator('label').filter({ hasText: AUTHOR })
    .getByRole('checkbox', { name: SCENE_NAME, exact: true })
  await expect(scene).toHaveCount(1)
  await scene.check()

  const notice = page.getByTestId('mcp-outbound')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText(OUTBOUND_NOTICE)
  // **要说清它是谁带来的。** 只显示服务名的话，教师看到一个自己没勾过的名字，
  // 第一反应是「这是哪来的」——而那正是这条标注要回答的问题
  await expect(notice).toContainText(`${MCP_NAME}（来自 ${SCENE_NAME}）`)
})
