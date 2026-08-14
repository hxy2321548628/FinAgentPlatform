import { request } from './request'

export const groupKeys = {
  all: ['groups'] as const,
  mine: () => ['groups', 'mine'] as const,
}

export interface MyGroup {
  id: string
  name: string
  is_owner: boolean
  /** 邀请码只发给组主 —— 组员手上有码的话，招人这件事就绕开教师了。 */
  invite_code: string | null
}

/** 我所属的课题组。共享设置里只能勾这些 —— 后端也校验。 */
export function listMyGroups(): Promise<MyGroup[]> {
  return request('/api/groups/mine')
}
