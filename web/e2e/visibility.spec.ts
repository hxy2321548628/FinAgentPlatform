import { expect, test, type Page } from '@playwright/test'

/**
 * P7⑥：在浏览器里把三档可见性的主链路走一遍。
 *
 * **为什么只有这一条**：它是本期唯一一条**跨三个账号来回切换**的链路，人工走查最
 * 容易漏 —— P6 的 11 条走查里有 4 条至今只是「部分观察」，而那还是单账号的。
 *
 * **这条断言链先红过一次才写成现在这样。** 开工时先写的是「C 看得见 A 的私有
 * agent」，跑出来确实是红的，再改成正确的方向 —— 选择器匹配不到元素而断言照样通过，
 * 是端到端测试最常见的假绿形态，不先让它红一次就分不清「过了」和「压根没跑到」。
 *
 * 账号与课题组由 `deploy/test/verify.sh` 造好，从环境变量传进来：平台没有公开的
 * 教师注册入口，建号要进容器算哈希、进库插行 —— 那不是浏览器干得了的事。
 */

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')
const TEAMMATE = required('E2E_TEAMMATE')
const OUTSIDER = required('E2E_OUTSIDER')
const REVIEWER = required('E2E_REVIEWER')
const TAG = process.env.E2E_TAG ?? String(Date.now())

const AGENT_NAME = `P7 走查 ${TAG}`
const PROMPT = `每一句都以「喵」开头。走查标记 ${TAG}`

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少环境变量 ${name}：这条走查要由 verify.sh 造好账号再跑`)
  return value
}

async function signIn(page: Page, name: string) {
  // 每次换人都要先把上一个人的登录态清掉 —— 同一个 Cookie 名，不清的话
  // 「别组看不见」会在作者自己的身份下跑，而那当然是看得见的
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByPlaceholder('用户名或邮箱都可以').fill(name)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: '登录系统' }).click()
  await expect(page).toHaveURL(/\/workspace/)
}

/**
 * 打开智能体广场，回到一个稳定的起点。
 *
 * **广场只剩一份列表**（`d0ef3d0` 之前是「平台广场 / 我能用的」两档）：现在一进来
 * 就是「我此刻能引用的」，卡片上的可见范围标出它是我的、组内共享还是广场可见。
 * 三档可见性因此改由卡片在不在、标的是哪一档来断言。
 */
async function openPlaza(page: Page) {
  await page.goto('/workspace/agents')
  await expect(page.getByRole('heading', { name: '智能体广场' })).toBeVisible()
}

/** 列表加载完之后，这个 agent 的卡片在不在。**等列表真的加载完再断言** —— 直接断言
 * 「看不见」的话，页面还停在「正在加载…」时它必然成立，那是最典型的假绿。 */
async function settled(page: Page) {
  await expect(page.getByText('正在加载…')).toHaveCount(0)
}

test('三档可见性：组内看得见、别组看不见，审核通过之后才上广场', async ({ page }) => {
  // ---- A：建一个 agent、写提示词、发布一版、共享给自己的组 ----
  await signIn(page, AUTHOR)
  await page.goto('/workspace/my-agents/create')
  await page.getByPlaceholder('如：企业财务异常检测').fill(AGENT_NAME)
  await page.getByPlaceholder(/你是一位专业的财务分析师/).fill(PROMPT)
  await page.getByRole('button', { name: '创建' }).click()
  await expect(page).toHaveURL(/\/workspace\/my-agents$/)

  const row = page.getByTestId('my-agent-row').filter({ hasText: AGENT_NAME })
  await page.getByRole('button', { name: '草稿', exact: false }).click()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /^发布 v1$/ }).click()

  await page.getByRole('button', { name: /^已发布/ }).click()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '共享设置' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox').first().check()
  await dialog.getByRole('checkbox').nth(1).check()
  await dialog.getByRole('button', { name: '保存共享设置' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(row.getByText(/组内共享/)).toBeVisible()

  // ---- B：同组看得见，且在详情抽屉里读得到提示词全文 ----
  await signIn(page, TEAMMATE)
  await openPlaza(page)
  await settled(page)
  const card = page.getByRole('article').filter({ hasText: AGENT_NAME })
  await expect(card).toBeVisible()
  await expect(card.getByText('可见范围：组内共享')).toBeVisible()
  await card.getByRole('button', { name: '查看提示词' }).click()
  await expect(page.getByTestId('agent-prompt')).toHaveText(PROMPT)
  await page.getByRole('button', { name: '关闭' }).click()

  // ---- C：别组看不见 ----
  await signIn(page, OUTSIDER)
  await openPlaza(page)
  await settled(page)
  await expect(page.getByRole('article').filter({ hasText: AGENT_NAME })).toHaveCount(0)

  // ---- A：提审 ----
  await signIn(page, AUTHOR)
  await page.goto('/workspace/my-agents')
  await page.getByRole('button', { name: /^已发布/ }).click()
  await row.getByRole('button', { name: '提交审核' }).click()
  const submitDialog = page.getByRole('dialog')
  await submitDialog.getByRole('checkbox').check()
  await submitDialog.getByRole('button', { name: '提交审核' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: /^待审核/ }).click()
  await expect(row.getByText('待审核')).toBeVisible()

  // ---- reviewer：队列里有它，通过 ----
  await signIn(page, REVIEWER)
  await page.goto('/admin/agents')
  const queued = page.getByTestId('review-row').filter({ hasText: AGENT_NAME })
  await expect(queued).toBeVisible()
  await expect(queued.getByText(PROMPT)).toBeVisible()
  await queued.getByRole('button', { name: '通过' }).click()
  await expect(page.getByTestId('review-row').filter({ hasText: AGENT_NAME }).getByText('已通过')).toBeVisible()

  // ---- C：现在广场上看得见了 ----
  await signIn(page, OUTSIDER)
  await openPlaza(page)
  await settled(page)
  const listed = page.getByRole('article').filter({ hasText: AGENT_NAME })
  await expect(listed).toBeVisible()
  // **断言的是「可见范围」那一行而不是徽章**：卡片上「广场可见」出现两次，
  // 直接找它会撞上 strict mode，而那种失败读起来像「元素不存在」
  await expect(listed.getByText('可见范围：广场可见')).toBeVisible()
})
