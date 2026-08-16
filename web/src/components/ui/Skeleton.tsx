/**
 * 骨架屏（DSD 第二章 §2.4）：替换「正在加载…」文字。
 * 装饰性元素，aria-hidden，对读屏无噪音。
 */
export function Skeleton({ width, height, radius = 6, style }: { width?: number | string; height?: number | string; radius?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" aria-hidden="true" style={{ width, height, borderRadius: radius, ...style }} />
}
