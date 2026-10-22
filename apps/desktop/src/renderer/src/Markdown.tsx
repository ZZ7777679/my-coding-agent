/** 渲染模型 Markdown，远程资源不自动加载。 Render model Markdown without automatically loading remote resources. */
import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './Markdown.css'

/** 保留流式文本与安全的表格、代码块；不执行原始 HTML。 Preserve streaming text, tables and code without executing raw HTML. */
export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          img: ({ alt }) => <span>[图片链接：{alt ?? ''}]</span>,
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={(event) => {
                event.preventDefault()
                if (href && /^https?:\/\//i.test(href)) void window.agent.openWebUrl(href)
              }}
            >
              {children}
            </a>
          ),
          pre: ({ children }) => (
            <div className="markdown-code">
              <button
                type="button"
                onClick={(event) => {
                  const code = event.currentTarget.parentElement?.querySelector('code')?.textContent
                  if (code) void navigator.clipboard.writeText(code)
                }}
              >
                复制代码
              </button>
              <pre>{children}</pre>
            </div>
          )
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
})
