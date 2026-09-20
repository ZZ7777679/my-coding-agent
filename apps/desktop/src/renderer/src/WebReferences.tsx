import { useState } from 'react'
import type { WebPageResult, WebSearchResult } from '../../generated/protocol'

/** 显示已校验来源与正文，不执行 HTML 或加载远程资源。 Show validated sources as inert text. */
export function WebReferences({ result }: { result: WebSearchResult | WebPageResult }) {
  const [error, setError] = useState('')
  /** 只响应用户点击，交给有限主进程入口。 Open via the restricted host only on user clicks. */
  const open = async (url: string) => {
    setError('')
    try {
      const response = await window.agent.openWebUrl(url)
      if (!response.ok) setError(response.error.message)
    } catch {
      setError('无法打开来源链接。')
    }
  }
  return (
    <details className="tool-entry web-references" data-testid="web-reference-card">
      <summary>
        {result.kind === 'web.search'
          ? `联网搜索 · ${result.model_id} · ${result.query}`
          : `已读取网页 · ${result.title}`}
      </summary>
      <p className="settings-hint">
        读取时间 {result.retrieved_at}
        {result.truncated && ' · 内容已截断'}
      </p>
      {result.kind === 'web.search' ? (
        <>
          <p>
            辅助模型请求 1 次 · 原生检索 {result.search_uses} 次 · 输入 / 输出 Token{' '}
            {result.usage.input_tokens ?? '未知'} / {result.usage.output_tokens ?? '未知'}
          </p>
          {result.actual_queries.length > 0 && <p>实际检索：{result.actual_queries.join('；')}</p>}
          {result.sources.length === 0 ? (
            <p>未返回可展示的公开来源。</p>
          ) : (
            <ul>
              {result.sources.map((source) => (
                <li key={source.url}>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => void open(source.url)}
                  >
                    {source.title}
                  </button>
                  <small>
                    {source.url}
                    {source.page_age ? ` · ${source.page_age}` : ''}
                  </small>
                  {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
                </li>
              ))}
            </ul>
          )}
          {result.summary && <pre>{result.summary}</pre>}
        </>
      ) : (
        <>
          <button type="button" className="text-button" onClick={() => void open(result.url)}>
            {result.url}
          </button>
          <p className="settings-hint">
            {result.status_code != null && `HTTP ${result.status_code} · `}
            {result.content_type} · 起始字符 {result.offset}
            {result.next_offset !== null ? ` · 可从 ${result.next_offset} 继续读取` : ''}
          </p>
          {result.redirects.length > 0 && <p>重定向：{result.redirects.join(' → ')}</p>}
          {result.download_truncated && (
            <p>下载达到本次文件容量上限；需要更多正文时可调整运行设置。</p>
          )}
          <pre>{result.content || '此页没有提取到正文；可能需要浏览器执行脚本。'}</pre>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </details>
  )
}
