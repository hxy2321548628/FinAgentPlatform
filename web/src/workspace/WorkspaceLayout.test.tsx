import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { WorkspaceLayout } from './WorkspaceLayout'

vi.mock('./WorkspaceSidebar', () => ({ WorkspaceSidebar: () => <aside>侧栏</aside> }))

afterEach(cleanup)

describe('WorkspaceLayout', () => {
  it('由布局统一提供工作台页面网格背景', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/workspace']}>
        <Routes>
          <Route path="/workspace" element={<WorkspaceLayout />}>
            <Route index element={<div>工作台内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(container.querySelector('#workspace-main')?.classList.contains('page-grid-surface')).toBe(true)
  })
})
