import { expect, test, type Page } from '@playwright/test'

/** P14④：浏览器里看任务清单在勾，并回答智能体的提问让它接着跑。 */

test.setTimeout(420_000)

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')

// **提问那一半必须点名要它调工具。** 「什么时候该问」由模型自己判断，
// 而走查要的是一个确定会停下来的中断 —— 判据验的是平台把提问渲染成什么、
// 教师答完能不能接着跑，不是模型的判断力（那一条归 §2.7 的实测）。
const QUESTION = process.env.E2E_TODO_QUESTION ?? [
  '这件事分几步做，请先用 write_todos 把步骤列出来再动手。',
  '第一步之前，先调用 ask_user_question 问我一句「年化因子用 252 还是 250」，等我回答再继续，不要自己定。',
  '任务是：在 outputs/ 下写一个 volatility.txt，里面写上收益率数组 [0.01,-0.005,0.008] 的样本标准差乘以 sqrt(年化因子) 的结果。',
  '最后把年化因子的取值写进答复里。',
].join(' ')

const ANSWER = '用 250'

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少环境变量 ${name}：P14④ 需要 verify.sh 先准备好账号`)
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

test('任务清单随事件刷新并勾得动，提问答完之后 run 接着跑', async ({ page }) => {
  await signIn(page, AUTHOR)
  await page.goto('/workspace/chat')
  await page.getByRole('button', { name: '＋ 新建分析' }).click()
  await expect(page).toHaveURL(/\/workspace\/chat$/)

  await page.getByPlaceholder(/输入分析需求/).fill(QUESTION)
  await page.getByTitle('发送').click()
  await expect(page).toHaveURL(/\/workspace\/chat\/[^/]+$/)

  // ---- 清单区：随事件出现，条目是中文
  const todos = page.locator('[data-testid="todo-list"]')
  await expect(todos).toBeVisible({ timeout: 300_000 })
  await expect(todos.locator('[data-status]').first()).toBeVisible()
  expect(await todos.locator('[data-status]').count()).toBeGreaterThan(1)
  expect(await todos.innerText()).toMatch(/[一-鿿]/)

  // ---- `write_todos` 不再以工具卡片出现。**不查这一条的话，教师会同时看到
  // 一张中文清单和一张正文是英文 `Updated todo list to [...]` 的工具卡**
  await expect(page.getByText('write_todos')).toHaveCount(0)
  await expect(page.getByText('Updated todo list to')).toHaveCount(0)

  // ---- 提问卡片：显示问题原文，不显示工具名与参数 JSON
  const asking = page.getByText(/年化因子用 252 还是 250/)
  await expect(asking).toBeVisible({ timeout: 300_000 })
  await expect(page.getByText('ask_user_question')).toHaveCount(0)
  const answer = page.getByLabel(/回答第 \d+ 个问题/)
  await expect(answer).toBeVisible()

  await answer.fill(ANSWER)
  await page.getByRole('button', { name: '提交回答' }).click()

  // ---- 答完接着跑：中断卡片消失，清单最终全部勾掉
  await expect(answer).toHaveCount(0, { timeout: 60_000 })
  await expect(page.getByText(/已完成 (\d+)\/\1$/)).toBeVisible({ timeout: 300_000 })
})
