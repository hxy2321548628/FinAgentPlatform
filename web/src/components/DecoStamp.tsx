import { useEffect, useState } from 'react'

interface DecoStampProps {
  style?: React.CSSProperties
}

export function DecoStamp({ style }: DecoStampProps) {
  const [text, setText] = useState('')
  useEffect(() => {
    const update = () => {
      const now = new Date()
      const hh = String(now.getHours()).padStart(2, '0')
      const mm = String(now.getMinutes()).padStart(2, '0')
      setText(`ANALYSIS · ${hh}:${mm}`)
    }
    update()
    const id = setInterval(update, 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <span
      aria-hidden="true"
      style={{
        position: 'absolute',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: '0.2em',
        color: 'rgba(11,46,92,0.12)',
        transform: 'rotate(-45deg)',
        userSelect: 'none',
        pointerEvents: 'none',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {text}
    </span>
  )
}
