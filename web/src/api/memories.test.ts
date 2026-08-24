import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ request: vi.fn() }))

vi.mock('./request', () => ({ request: mocks.request }))

import { deleteMemory, getMemory, listMemories } from './memories'

beforeEach(() => mocks.request.mockReset())

describe('thread memory API', () => {
  it('encodes the thread and slug in list, detail and delete requests', async () => {
    mocks.request.mockResolvedValue({ items: [] })

    await listMemories('thread/一')
    await getMemory('thread/一', 'risk/profile')
    await deleteMemory('thread/一', 'risk/profile')

    expect(mocks.request).toHaveBeenNthCalledWith(1, '/api/threads/thread%2F%E4%B8%80/memories')
    expect(mocks.request).toHaveBeenNthCalledWith(2, '/api/threads/thread%2F%E4%B8%80/memories/risk%2Fprofile')
    expect(mocks.request).toHaveBeenNthCalledWith(3, '/api/threads/thread%2F%E4%B8%80/memories/risk%2Fprofile', { method: 'DELETE' })
  })
})
