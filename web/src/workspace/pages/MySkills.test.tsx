import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/request'
import { MySkills } from './MySkills'

const mocks = vi.hoisted(() => ({
  listMine: vi.fn(async () => []),
  createSkill: vi.fn(),
}))

vi.mock('../../api/skills', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/skills')>()),
  listMine: mocks.listMine,
  createSkill: mocks.createSkill,
}))

afterEach(() => {
  mocks.listMine.mockClear()
  mocks.createSkill.mockReset()
  cleanup()
})

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MySkills /></QueryClientProvider>)
}

describe('MySkills', () => {
  it('逐条显示上传校验返回的八条理由', async () => {
    const reasons = [
      '路径不合法：../../etc/passwd',
      '不允许符号链接：link',
      '解压后总大小超过上限',
      '文件数量超过上限',
      '压缩比超过 100:1',
      '文件扩展名不允许：run.sh',
      '单文件超过上限：large.md',
      'skill 的 name 必须等于目录名',
    ]
    mocks.createSkill.mockRejectedValue(new ApiError(422, 'VALIDATION_ERROR', reasons.join('；')))
    mount()

    fireEvent.click(screen.getByRole('button', { name: '+ 创建 Skill' }))
    const file = new File(['bad'], 'bad.zip', { type: 'application/zip' })
    fireEvent.change(screen.getByLabelText('Skill 文件'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '上传并创建' }))

    for (const reason of reasons) {
      await waitFor(() => expect(screen.getByText(reason)).toBeTruthy())
    }
  })

  it('把合法文件与所选学科提交给真实创建接口', async () => {
    mocks.createSkill.mockResolvedValue({})
    mount()

    fireEvent.click(screen.getByRole('button', { name: '+ 创建 Skill' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '量化投资' } })
    const file = new File(['---\nname: annualized-252\ndescription: 年化换算\n---'], 'SKILL.md', { type: 'text/markdown' })
    fireEvent.change(screen.getByLabelText('Skill 文件'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '上传并创建' }))

    await waitFor(() => expect(mocks.createSkill).toHaveBeenCalledWith(file, '量化投资'))
  })

  it('允许选择 ZIP 或单个 Markdown 文件', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: '+ 创建 Skill' }))
    expect(screen.getByLabelText('Skill 文件').getAttribute('accept')).toContain('.zip')
    expect(screen.getByLabelText('Skill 文件').getAttribute('accept')).toContain('.md')
    expect(screen.getByText(/允许 Markdown、文本、HTML/)).toBeTruthy()
  })
})
