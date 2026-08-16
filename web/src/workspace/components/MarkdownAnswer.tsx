import { memo, useEffect, useMemo, useState } from 'react'
import ReactMarkdown, { type Components, type Options } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { highlightCode, normalizeLang } from './codeHighlight'
import { rawFileUrl } from '../../api/files'

/**
 * 智能体答复的 Markdown 渲染器（方案 doc/02visual/04 §4）。
 *
 * 双管线：流式态轻量（仅 GFM，不碰 Shiki/KaTeX —— 未闭合的代码围栏与 $$ 是常态，
 * 高亮器与公式器不该面对它们）；终态升格完整管线（+块级公式 +代码高亮）。
 *
 * 安全边界（§4.5/§4.6）：不装 rehype-raw（LLM 输出按不可信文本对待）、
 * 图片相对路径仅 outputs/ 白名单、链接协议白名单、外链 noopener。
 */

const OUTPUT_PREFIX = 'outputs/'

/** 相对路径必须落在 outputs/ 内且不含 `..` 段；否则返回 null（降级渲染）。 */
function rewriteRelativePath(src: string, threadId: string | undefined, download: boolean): string | null {
  const normalized = src.replace(/^\.\//, '').trim()
  if (!normalized || !normalized.startsWith(OUTPUT_PREFIX)) return null
  if (normalized.split('/').includes('..') || normalized.split('/').includes('.')) return null
  if (!threadId) return null
  return rawFileUrl(threadId, normalized, download)
}

/** 仅允许 http/https/mailto 与站内相对路径；其余（javascript: 等）替换为不可点击。 */
function sanitizeHref(href: string | undefined): string {
  if (!href) return '#'
  const trimmed = href.trim()
  if (/^(https?:|mailto:)/i.test(trimmed) || trimmed.startsWith('/') || trimmed.startsWith('#')) return trimmed
  return '#'
}

interface CodeBlockProps {
  code: string
  language: string | undefined
  streaming: boolean
}

function CodeBlock({ code, language, streaming }: CodeBlockProps) {
  const [html, setHtml] = useState<string | null>(null)
  const lang = normalizeLang(language)

  useEffect(() => {
    if (streaming || !lang) {
      setHtml(null)
      return
    }
    let cancelled = false
    void highlightCode(code, lang).then(result => {
      if (!cancelled) setHtml(result)
    })
    return () => {
      cancelled = true
    }
  }, [code, lang, streaming])

  return (
    <div className="code-block" role="region" aria-label="代码">
      {lang && <span className="code-block-lang" aria-hidden="true">{lang}</span>}
      {html !== null ? (
        // Shiki 输出会转义代码文本，语言名经 normalizeLang 白名单 —— 无注入面
        <div dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <pre className="shiki finagent-css-vars" data-unhighlighted="true"><code>{code}</code></pre>
      )}
    </div>
  )
}

interface MarkdownAnswerProps {
  text: string
  /** 提供后，outputs/ 相对路径才会重写为下载 URL；不提供时降级为文本。 */
  threadId?: string
  streaming?: boolean
}

export const MarkdownAnswer = memo(function MarkdownAnswer({ text, threadId, streaming = false }: MarkdownAnswerProps) {
  const components = useMemo<Components>(() => ({
    code({ className, children }) {
      const codeText = String(children ?? '').replace(/\n$/, '')
      const match = /language-([\w-]+)/.exec(className ?? '')
      // 围栏块：带 language-x 类名，或未标语言但含换行；否则按行内 code 处理
      if (match || /\n/.test(codeText)) {
        return <CodeBlock code={codeText} language={match?.[1]} streaming={streaming} />
      }
      return <code className="inline-code">{codeText}</code>
    },
    a({ href, children }) {
      return (
        <a href={sanitizeHref(href)} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      )
    },
    img({ src, alt }) {
      if (!src) return null
      const absolute = /^(https?:)?\/\//i.test(src)
      if (absolute) {
        return <img src={src} alt={alt ?? ''} loading="lazy" decoding="async" referrerPolicy="no-referrer" />
      }
      const rewritten = rewriteRelativePath(src, threadId, false)
      if (!rewritten) return <span className="md-img-fallback">{alt || src}</span>
      return <img src={rewritten} alt={alt ?? src} loading="lazy" decoding="async" />
    },
    table({ children }) {
      return <div className="md-table-wrap"><table>{children}</table></div>
    },
  }), [streaming, threadId])

  // 两个小数组，直接按 react-markdown 的 PluggableList 形状声明；组件本身已 memo，
  // 无需再包一层 useMemo
  const remarkPlugins: Options['remarkPlugins'] = streaming
    ? [remarkGfm]
    : [remarkGfm, [remarkMath, { singleDollarTextMath: false }]]
  const rehypePlugins: Options['rehypePlugins'] = streaming ? [] : [rehypeKatex]

  return (
    <div className="markdown-answer">
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  )
})
