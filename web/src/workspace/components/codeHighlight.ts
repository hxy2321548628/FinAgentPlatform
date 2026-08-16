import { createCssVariablesTheme, createHighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'
import langBash from '@shikijs/langs/bash'
import langCss from '@shikijs/langs/css'
import langCsv from '@shikijs/langs/csv'
import langDockerfile from '@shikijs/langs/dockerfile'
import langHtml from '@shikijs/langs/html'
import langJavaScript from '@shikijs/langs/javascript'
import langJsx from '@shikijs/langs/jsx'
import langJson from '@shikijs/langs/json'
import langLatex from '@shikijs/langs/latex'
import langMarkdown from '@shikijs/langs/markdown'
import langPython from '@shikijs/langs/python'
import langR from '@shikijs/langs/r'
import langSql from '@shikijs/langs/sql'
import langToml from '@shikijs/langs/toml'
import langTsx from '@shikijs/langs/tsx'
import langTypeScript from '@shikijs/langs/typescript'
import langXml from '@shikijs/langs/xml'
import langYaml from '@shikijs/langs/yaml'
import type { HighlighterCore } from 'shiki/core'

/**
 * Shiki 按需高亮（方案 §4.3）。
 *
 * - 只加载智能体实际会输出的语言，控制 bundle；
 * - CSS 变量主题：token 颜色全部是 `var(--shiki-*)`，主题切换只需改 CSS 变量
 *   （选型文档 §4.2「一次配双主题」的落法）；
 * - JS 正则引擎，无 WASM，jsdom 单测与内网构建都零额外资产。
 */

const THEME_NAME = 'finagent-css-vars'

const SUPPORTED_LANGS = new Set([
  'python', 'json', 'bash', 'markdown', 'sql', 'r', 'latex', 'yaml',
  'javascript', 'typescript', 'jsx', 'tsx', 'html', 'css', 'xml', 'toml', 'csv', 'dockerfile',
])

const LANG_ALIASES: Record<string, string> = {
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  md: 'markdown',
  tex: 'latex',
  yml: 'yaml',
  js: 'javascript',
  ts: 'typescript',
  htm: 'html',
  svg: 'xml',
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  py: 'python', pyw: 'python', json: 'json', jsonl: 'json', sh: 'bash', bash: 'bash', zsh: 'bash',
  md: 'markdown', markdown: 'markdown', sql: 'sql', r: 'r', tex: 'latex', yml: 'yaml', yaml: 'yaml',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript', ts: 'typescript', mts: 'typescript', cts: 'typescript',
  jsx: 'jsx', tsx: 'tsx', html: 'html', htm: 'html', css: 'css', xml: 'xml', svg: 'xml', toml: 'toml', csv: 'csv',
}

const LANGUAGE_LABELS: Record<string, string> = {
  python: 'Python', json: 'JSON', bash: 'Shell', markdown: 'Markdown', sql: 'SQL', r: 'R', latex: 'LaTeX',
  yaml: 'YAML', javascript: 'JavaScript', typescript: 'TypeScript', jsx: 'JSX', tsx: 'TSX', html: 'HTML',
  css: 'CSS', xml: 'XML', toml: 'TOML', csv: 'CSV', dockerfile: 'Dockerfile',
}

const cssVariablesTheme = createCssVariablesTheme({
  name: THEME_NAME,
  variablePrefix: '--shiki-',
  variableDefaults: {},
})

let highlighterPromise: Promise<HighlighterCore> | null = null

export function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighterCore({
      themes: [cssVariablesTheme],
      langs: [
        langPython, langJson, langBash, langMarkdown, langSql, langR, langLatex, langYaml,
        langJavaScript, langTypeScript, langJsx, langTsx, langHtml, langCss, langXml, langToml,
        langCsv, langDockerfile,
      ],
      engine: createJavaScriptRegexEngine(),
    })
  }
  return highlighterPromise
}

/** 语言标注 → 规范语言 id；不在白名单内返回 null（渲染层走无高亮降级）。 */
export function normalizeLang(language: string | undefined): string | null {
  if (!language) return null
  const trimmed = language.trim().toLowerCase()
  const canonical = LANG_ALIASES[trimmed] ?? trimmed
  return SUPPORTED_LANGS.has(canonical) ? canonical : null
}

export function languageForPath(path: string): string | null {
  const name = path.split('/').at(-1)?.toLowerCase() ?? path.toLowerCase()
  if (name === 'dockerfile' || name.startsWith('dockerfile.')) return 'dockerfile'
  const extension = name.split('.').at(-1) ?? ''
  return normalizeLang(LANGUAGE_BY_EXTENSION[extension])
}

export function languageLabel(path: string): string {
  const language = languageForPath(path)
  return language ? LANGUAGE_LABELS[language] ?? language : 'Plain Text'
}

/** 高亮失败一律返回 null，由调用方降级为纯文本代码块 —— 渲染层不因高亮崩溃。 */
export async function highlightCode(code: string, language: string): Promise<string | null> {
  const lang = normalizeLang(language)
  if (!lang) return null
  try {
    const highlighter = await getHighlighter()
    return highlighter.codeToHtml(code, { lang, theme: THEME_NAME })
  } catch {
    return null
  }
}
