import { expect, test, type Page } from '@playwright/test'

/** P9⑥：浏览器里配置子智能体，并展开消息流中的嵌套过程。 */

test.setTimeout(300_000)

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')
const SUBAGENT_NAME = required('E2E_SUBAGENT_NAME')
const QUESTION = process.env.E2E_SUBAGENT_QUESTION ?? [
  '只做这一件事：固定收益率数组 [0.01,-0.005,0.008,-0.002,0.006] 的样本标准差是 0.00654217089351845，乘以 sqrt(252) 后年化波动率是 0.10385374331241026。',
  '如果存在名为 volatility-expert 的可委派子智能体，必须把整项工作委派给它，自己不得代做。',
  '只调用一次 write_file，把这段计算写进 outputs/volatility-result.txt；不调用其他工具。完成后只回答输出文件名。',
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
  // **会话是懒创建的**：「新建分析」只把人带到欢迎页，第一次发送才真的建会话，
  // 因此这里还没有会话 id —— 断言它出现要等到发送之后
  await expect(page).toHaveURL(/\/workspace\/chat$/)

  await page.getByRole('button', { name: /本轮智能体配置/ }).click()
  // 配置面板分了页签，子智能体那一页不切过去就是 hidden，勾不到也看不见
  await page.getByRole('tab', { name: '子智能体' }).click()
  // **候选只渲染前 12 个**，验收环境里的子智能体一轮轮累积，目标多半在第一页之外；
  // 候选不足 7 个时面板不给筛选框，那时直接找就够了
  const search = page.locator('#config-panel-subagent').getByRole('textbox')
  if (await search.count() > 0) await search.fill(SUBAGENT_NAME)
  // **按名字定位会命中两个**：P9③ 让同组的 B 也建了一个叫 volatility-expert 的
  // 子智能体并共享进同一个组（那条判据验的就是同名闸门），于是候选列表里同名两项。
  // 用属主那一行钉到作者自己的那一个 —— 挂错人的同名 agent 会跑出另一份提示词。
  //
  // **点的是整张卡片而不是 checkbox**：真正的 input 是 `opacity: 0` 且
  // `pointer-events: none` 的无障碍载体，`check()` 点它必然超时在「卡片挡住了点击」上。
  const child = page.locator('label')
    .filter({ has: page.getByRole('checkbox', { name: SUBAGENT_NAME, exact: true }) })
    .filter({ hasText: AUTHOR })
  await expect(child).toHaveCount(1)
  await child.click()
  await expect(child.getByRole('checkbox', { name: SUBAGENT_NAME, exact: true })).toBeChecked()
  // 配置面板是覆盖整屏的模态框，不关掉它，发送按钮被遮罩挡着点不到
  await page.getByRole('button', { name: '完成' }).click()
  await expect(page.getByRole('dialog', { name: '智能体配置' })).toHaveCount(0)

  const input = page.getByPlaceholder(/输入分析需求/)
  await input.fill(QUESTION)
  await page.getByTitle('发送').click()
  // 发送成功才建会话并跳过去：会话 id 出现在地址栏，说明这一轮真的提交了
  await expect(page).toHaveURL(/\/workspace\/chat\/[^/]+$/)

  const nested = page.locator(`details[data-subagent="${SUBAGENT_NAME}"]`)
  await expect(nested).toBeVisible({ timeout: 240_000 })
  // **只认直属的那个 summary**：折叠块里还套着「分析思路」自己的 details，
  // 写成 `locator('summary')` 会一次命中两个而红在 strict mode 上
  const header = nested.locator('> summary')
  await expect(header).toContainText(SUBAGENT_NAME)

  // 开工时先用不存在的 data-subagent 名称跑过一次，确认断言会因页面映射缺失而失败；
  // 正式判据锁定真实名称，避免 uuid 回退或嵌套事件平铺时误报通过。
  await header.click()
  await expect(nested.getByRole('button', { name: /write_file/ })).toBeVisible()
})
