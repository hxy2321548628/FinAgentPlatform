import { expect, test, type Page } from '@playwright/test'

/** P8⑥：上传拒绝理由、合法包元数据、发布提审与审核通过。 */

const PASSWORD = required('E2E_PASSWORD')
const AUTHOR = required('E2E_AUTHOR')
const REVIEWER = required('E2E_REVIEWER')
const TAG = process.env.E2E_TAG ?? String(Date.now())

const SKILL_NAME = `p8-upload-${TAG}`.toLowerCase()
const DESCRIPTION = `P8 浏览器走查 ${TAG}：名称与描述必须来自 frontmatter。`

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少环境变量 ${name}：这条走查要由 verify.sh 造好账号再跑`)
  return value
}

async function signIn(page: Page, name: string) {
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(name)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: '登录系统' }).click()
  await expect(page).toHaveURL(/\/workspace/)
}

function zip(entries: Array<{ name: string; content: string }>): Buffer {
  const localParts: Buffer[] = []
  const centralParts: Buffer[] = []
  let offset = 0

  for (const entry of entries) {
    const name = Buffer.from(entry.name)
    const content = Buffer.from(entry.content)
    const checksum = crc32(content)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt32LE(checksum, 14)
    local.writeUInt32LE(content.length, 18)
    local.writeUInt32LE(content.length, 22)
    local.writeUInt16LE(name.length, 26)
    localParts.push(local, name, content)

    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50, 0)
    central.writeUInt16LE(20, 4)
    central.writeUInt16LE(20, 6)
    central.writeUInt32LE(checksum, 16)
    central.writeUInt32LE(content.length, 20)
    central.writeUInt32LE(content.length, 24)
    central.writeUInt16LE(name.length, 28)
    central.writeUInt32LE(offset, 42)
    centralParts.push(central, name)
    offset += local.length + name.length + content.length
  }

  const centralDirectory = Buffer.concat(centralParts)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(entries.length, 8)
  end.writeUInt16LE(entries.length, 10)
  end.writeUInt32LE(centralDirectory.length, 12)
  end.writeUInt32LE(offset, 16)
  return Buffer.concat([...localParts, centralDirectory, end])
}

function crc32(content: Buffer): number {
  let crc = 0xffffffff
  for (const byte of content) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
  }
  return (crc ^ 0xffffffff) >>> 0
}

function skillMarkdown(name: string): string {
  return `---\nname: ${name}\ndescription: ${DESCRIPTION}\n---\n\n所有结果都要写清口径。\n`
}

test('越界包显示具体理由且不新增，合法包可发布、提审并通过', async ({ page }) => {
  await signIn(page, AUTHOR)
  await page.goto('/workspace/my-skills')
  await page.getByRole('button', { name: '+ 创建 Skill' }).first().click()

  const invalidRoot = `p8-invalid-${TAG}`.toLowerCase()
  await page.getByLabel('Skill 文件').setInputFiles({
    name: 'path-traversal.zip',
    mimeType: 'application/zip',
    buffer: zip([
      { name: `${invalidRoot}/SKILL.md`, content: skillMarkdown(invalidRoot) },
      { name: `${invalidRoot}/../../escape.txt`, content: '越界内容' },
    ]),
  })
  await page.getByRole('button', { name: '上传并创建' }).click()
  await expect(page.getByRole('alert')).toContainText('路径不合法')
  // 开工时曾故意写成 `toHaveCount(1)` 并实际跑红，确认这不是页面尚未加载导致的假绿。
  await expect(page.getByTestId('my-skill-row').filter({ hasText: invalidRoot })).toHaveCount(0)

  await page.getByLabel('Skill 文件').setInputFiles({
    name: `${SKILL_NAME}.zip`,
    mimeType: 'application/zip',
    buffer: zip([{ name: `${SKILL_NAME}/SKILL.md`, content: skillMarkdown(SKILL_NAME) }]),
  })
  await page.getByRole('button', { name: '上传并创建' }).click()

  const row = page.getByTestId('my-skill-row').filter({ hasText: SKILL_NAME })
  await expect(row).toBeVisible()
  await expect(row).toContainText(DESCRIPTION)
  await row.getByRole('button', { name: '发布 v1' }).click()

  await page.getByRole('button', { name: /^已发布/ }).click()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '提交审核' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '提交审核' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(row.getByText('待审核')).toBeVisible()

  await signIn(page, REVIEWER)
  await page.goto('/admin/skills')
  const queued = page.getByTestId('review-row').filter({ hasText: SKILL_NAME })
  await expect(queued).toBeVisible()
  await expect(queued).toContainText(DESCRIPTION)
  await queued.getByRole('button', { name: '通过' }).click()
  await expect(page.getByTestId('review-row').filter({ hasText: SKILL_NAME }).getByText('已通过')).toBeVisible()
})
