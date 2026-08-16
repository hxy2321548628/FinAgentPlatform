import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { Marketplace } from './Marketplace'

afterEach(cleanup)

/** 把当前 URL 暴露出来，验证筛选状态真的写进了 query（可分享、可后退）。 */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="loc">{location.search}</div>
}

function show(initial = '/marketplace') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Marketplace />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('Marketplace URL 状态同步', () => {
  it('默认落在精选场景 tab，URL 无参数', () => {
    show()
    expect(screen.getByRole('heading', { name: '精选分析场景' })).toBeTruthy()
    expect(screen.getByTestId('loc').textContent).toBe('')
  })

  it('点「所有智能体」把 tab 写进 URL', () => {
    show()
    fireEvent.click(screen.getByRole('button', { name: '所有智能体' }))
    expect(screen.getByRole('heading', { name: '所有智能体' })).toBeTruthy()
    expect(screen.getByTestId('loc').textContent).toBe('?tab=agents')
  })

  it('学科筛选写进 URL，且可切换回去', () => {
    show('/marketplace?tab=agents')
    fireEvent.click(screen.getByRole('button', { name: '量化投资' }))
    expect(screen.getByTestId('loc').textContent).toBe('?tab=agents&subject=%E9%87%8F%E5%8C%96%E6%8A%95%E8%B5%84')
    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(screen.getByTestId('loc').textContent).toBe('?tab=agents')
  })

  it('从带参数的 URL 进入时直接落在对应状态（可分享）', () => {
    show('/marketplace?tab=agents&subject=%E9%87%8F%E5%8C%96%E6%8A%95%E8%B5%84')
    expect(screen.getByRole('heading', { name: '所有智能体' })).toBeTruthy()
    // 量化投资学科下只剩一个 agent：量化因子筛选器
    expect(screen.getByText('量化因子筛选器')).toBeTruthy()
    expect(screen.queryByText('企业财务异常检测')).toBeNull()
  })
})
