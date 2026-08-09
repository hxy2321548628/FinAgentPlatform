import { useEffect, useState } from 'react'

interface DecoStampProps {
  style?: React.CSSProperties
  text?: string
}

export function DecoStamp({ style, text: textProp }: DecoStampProps) {
  const [autoText, setAutoText] = useState('')
  useEffect(() => {
    if (textProp !== undefined) return
    const update = () => {
      const now = new Date()
      const hh = String(now.getHours()).padStart(2, '0')
      const mm = String(now.getMinutes()).padStart(2, '0')
      setAutoText(`ANALYSIS · ${hh}:${mm}`)
    }
    update()
    const id = setInterval(update, 60000)
    return () => clearInterval(id)
  }, [textProp])

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
      {textProp ?? autoText}
    </span>
  )
}
