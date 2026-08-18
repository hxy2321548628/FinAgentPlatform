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
 * 账号与课题组由 `script/test/verify.sh` 造好，从环境变量传进来：平台没有公开的
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

/**
 * 登录并落到 `landing` 指的那一页。
 *
 * **落点是按角色分的**：教师进工作台，而审核员 2026-08-16 起直接进后台的审核队列 ——
 * 此前它被送去工作台，而工作台里一个后台入口都没有，等于进不去（P11 §8.8b）。
 * 因此这里不写死 `/workspace`：**审核员那几次调用正是在验它自己走得到队列**，
 * 而不是靠测试代码 `goto` 过去。
 */
async function signIn(page: Page, name: string, landing: RegExp = /\/workspace/) {
  // 每次换人都要先把上一个人的登录态清掉 —— 同一个 Cookie 名，不清的话
  // 「别组看不见」会在作者自己的身份下跑，而那当然是看得见的
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByPlaceholder('用户名或邮箱都可以').fill(name)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: '登录系统' }).click()
  await expect(page).toHaveURL(landing)
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
 * 「看不见」的话，页面还停在骨架屏时它必然成立，那是最典型的假绿。
 *
 * 等的是 `data-loaded` 而不是一句加载文案：文案改掉之后 `toHaveCount(0)` 会变成
 * 恒真，这一层保护就在没人察觉的情况下消失了（2026-08-17 实际发生过一次）。 */
async function settled(page: Page) {
  await expect(page.getByTestId('agent-plaza-list')).toHaveAttribute('data-loaded', 'true')
}

/**
 * 在当前这一档审核列表里翻到指定的那一条。
 *
 * **必须翻页**：待审按提交时间升序，队列里压着几条早先提交的，刚提审的那条就不在
 * 第一页。2026-08-18 这条走查正是这么红的 —— 报的是「元素找不到」，一个字都没提分页。
 */
async function reviewRow(page: Page, name: string) {
  const row = page.getByTestId('review-row').filter({ hasText: name })
  const next = page.getByRole('button', { name: '下一页' })
  while ((await row.count()) === 0 && (await next.count()) > 0 && (await next.isEnabled())) {
    await next.click()
  }
  await expect(row).toBeVisible()
  return row
}

test('三档可见性：组内看得见、别组看不见，审核通过之后才上广场', async ({ page }) => {
  // ---- A：建一个 agent、写提示词、发布一版、共享给自己的组 ----
  await signIn(page, AUTHOR)
  await page.goto('/workspace/my-agents/create')
  // **编辑器是分步的**：名称在第一步，提示词在第二步，不切步就根本没渲染出来。
  // 两个输入框都按 testid 找 —— 占位文案改一次这条链路就整条走不下去
  await page.getByTestId('agent-name').fill(AGENT_NAME)
  await page.getByRole('button', { name: '行为设定' }).click()
  await page.getByTestId('agent-system-prompt').fill(PROMPT)
  await page.getByRole('button', { name: '创建草稿' }).click()
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
  await signIn(page, REVIEWER, /\/admin\/agents/)
  const queued = await reviewRow(page, AGENT_NAME)
  // **提示词全文在详情抽屉里，不在卡片上** —— 卡片只摆一句说明
  await queued.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('dialog')).toContainText(PROMPT)
  await page.getByRole('button', { name: '关闭详情' }).click()
  await queued.getByRole('button', { name: '通过' }).click()

  // 通过之后它离开待审队列，进「最近处理」。**状态钉 data-status 不钉中文文案**：
  // 那句文案已经从「已通过」改成「已上架 / 已下架」，而走查是靠它红了才发现的
  await page.getByRole('button', { name: /^最近处理/ }).click()
  const decided = await reviewRow(page, AGENT_NAME)
  await expect(decided.getByTestId('review-status')).toHaveAttribute('data-status', 'approved')

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
