export const ADMIN_LIST_PAGE_SIZE = 10
export const ADMIN_DETAIL_PAGE_SIZE = 8
export const ADMIN_ACTION_PAGE_SIZE = 5
export const ADMIN_REVIEW_CARD_PAGE_SIZE = 2

export function paginateAdminItems<T>(items: T[], page: number, pageSize: number): { items: T[]; page: number } {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize))
  const safePage = Math.min(Math.max(page, 1), totalPages)
  return {
    items: items.slice((safePage - 1) * pageSize, safePage * pageSize),
    page: safePage,
  }
}
