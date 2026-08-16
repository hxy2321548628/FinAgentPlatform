import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/Toast'
import { WorkspaceFiles } from './WorkspaceFiles'

const mocks = vi.hoisted(() => ({
  listFiles: vi.fn(async () => ({
    truncated: false,
    entries: [
      { path: 'notes', is_dir: true, size: 0, modified_at: '2026-08-16T00:00:00Z' },
      { path: 'notes/rule.txt', is_dir: false, size: 8, modified_at: '2026-08-16T00:00:00Z' },
      { path: 'root.txt', is_dir: false, size: 4, modified_at: '2026-08-16T00:00:00Z' },
      { path: 'analysis.py', is_dir: false, size: 18, modified_at: '2026-08-16T00:00:00Z' },
    ],
  })),
  readFile: vi.fn(async (_threadId: string, path: string) => ({ path, text: path.endsWith('.py') ? 'print("hello")' : '原始内容', total_line: 1, start_line: 1, end_line: 1, is_binary: false, truncated: false })),
  writeFile: vi.fn(async () => undefined),
  createDirectory: vi.fn(async () => undefined),
  deleteFile: vi.fn(async () => undefined),
  uploadFile: vi.fn(async () => ({ filename: 'a.txt', path: 'a.txt', size: 1 })),
}))

vi.mock('../../api/files', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/files')>()),
  listFiles: mocks.listFiles,
  readFile: mocks.readFile,
  writeFile: mocks.writeFile,
  createDirectory: mocks.createDirectory,
  deleteFile: mocks.deleteFile,
  uploadFile: mocks.uploadFile,
}))

afterEach(() => { cleanup(); vi.clearAllMocks() })

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><ToastProvider><WorkspaceFiles threadId="thread-1" title="测试工作区" /></ToastProvider></QueryClientProvider>)
}

describe('WorkspaceFiles', () => {
  it('目录可展开，文件在右侧预览，并可取消或保存编辑', async () => {
    renderWorkspace()

    fireEvent.click(await screen.findByRole('button', { name: 'notes' }))
    fireEvent.click(screen.getByRole('button', { name: 'rule.txt' }))
    expect(await screen.findByText('原始内容')).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: '文件内容编辑器' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '编辑文件' }))
    expect(await screen.findByDisplayValue('原始内容')).toBeTruthy()
    fireEvent.change(screen.getByRole('textbox', { name: '文件内容编辑器' }), { target: { value: '未保存修改' } })
    fireEvent.click(screen.getByRole('button', { name: '取消编辑' }))
    expect(screen.getByText('原始内容')).toBeTruthy()
    expect(screen.queryByText('未保存修改')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '编辑文件' }))
    fireEvent.change(screen.getByRole('textbox', { name: '文件内容编辑器' }), { target: { value: '已保存内容' } })
    fireEvent.click(screen.getByRole('button', { name: '保存文件' }))

    await waitFor(() => expect(mocks.writeFile).toHaveBeenCalledWith('thread-1', 'notes/rule.txt', '已保存内容'))
    expect(await screen.findByText('已保存内容')).toBeTruthy()
  })
  it('按文件类型显示统一的带行号代码表面，点击编辑后保留高亮层', async () => {
    const { container } = renderWorkspace()

    fireEvent.click(await screen.findByRole('button', { name: 'analysis.py' }))

    await waitFor(() => expect(container.querySelector('.workspace-code-surface[data-language="python"]')).toBeTruthy())
    const surface = container.querySelector<HTMLElement>('.workspace-code-surface[data-language="python"]')
    expect(surface?.style.display).toBe('grid')
    expect(surface?.style.gridTemplateColumns).toBe('48px minmax(0, 1fr)')
    expect(screen.queryByRole('textbox', { name: '文件内容编辑器' })).toBeNull()
    expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    expect(container.querySelector('.workspace-code-gutter')?.textContent).toBe('1')
    await waitFor(() => expect(container.querySelector('.workspace-code-highlighted .shiki')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '编辑文件' }))

    const editor = await screen.findByDisplayValue('print("hello")')
    expect(editor.style.position).toBe('absolute')
    expect(editor.style.color).toBe('transparent')
    expect(container.querySelector('.workspace-code-surface.editing[data-language="python"]')).toBeTruthy()
    expect(container.querySelector<HTMLElement>('.workspace-code-surface.editing .workspace-code-highlight')?.style.position).toBe('absolute')
    expect(container.querySelector('.workspace-code-surface.editing .workspace-code-highlighted .shiki')).toBeTruthy()
    expect(container.querySelectorAll('.workspace-code-surface').length).toBe(1)
  })

})
