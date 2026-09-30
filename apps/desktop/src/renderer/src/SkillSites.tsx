/** 原站在应用内浏览，搜索和分页由站点处理。 Browse original websites with their own search and pagination. */
import { useEffect, useRef, useState } from 'react'
import defaults from '../../../../../src/my_agent/defaults.json'
import type { SkillSiteControl, SkillSiteSource, SkillSiteState } from '../../generated/protocol'

/** 用布局占位承载原生网页，切换离开后隐藏但保留当前网页。
 * Host a native website surface, hiding it on navigation while keeping the page alive.
 */
export function SkillSites({ onImport }: { onImport: (url: string) => void }) {
  const [state, setState] = useState<SkillSiteState | null>(null)
  const [address, setAddress] = useState('')
  const [sources, setSources] = useState<SkillSiteSource[] | null>(null)
  const [error, setError] = useState('')
  const [reading, setReading] = useState(false)
  const owner = useRef(crypto.randomUUID())
  const element = useRef<HTMLDivElement>(null)
  const editing = useRef(false)
  const mounted = useRef(true)
  const hasPage = Boolean(state?.url)
  const currentSite = defaults.skill_online.sites.find(
    (site) =>
      new URL(site.url).hostname.replace(/^www\./, '') ===
      new URL(state?.url || 'about:blank').hostname.replace(/^www\./, '')
  )?.url

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    /** 只读取状态；首次进入不替用户选择网站。 Read state without choosing a site on first entry. */
    async function poll() {
      try {
        const result = await window.agent.skillSiteControl({ action: 'status' })
        if (disposed) return
        if (result.ok) {
          setState(result.data)
          if (!editing.current) setAddress(result.data.url)
        } else setError(result.error.message)
      } catch {
        if (!disposed) setError('网站状态读取失败，可重新进入此页面。')
      }
      if (!disposed) timer = setTimeout(() => void poll(), 700)
    }
    void poll()
    return () => {
      disposed = true
      clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    const identity = owner.current
    let frame = 0
    let last = ''
    /** 采用可见矩形，原生网页不会盖住左侧栏和工具栏。 Use visible bounds without covering application navigation. */
    function layout() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (!element.current) return
        const rect = element.current.getBoundingClientRect()
        const x = Math.max(0, Math.round(rect.left))
        const y = Math.max(0, Math.round(rect.top))
        const bounds = {
          owner_id: identity,
          visible: hasPage,
          x,
          y,
          width: Math.max(0, Math.round(Math.min(window.innerWidth, rect.right) - x)),
          height: Math.max(0, Math.round(Math.min(window.innerHeight, rect.bottom) - y))
        }
        const key = JSON.stringify(bounds)
        if (key === last) return
        last = key
        void window.agent
          .skillSiteLayout(bounds)
          .then((r) => {
            if (mounted.current && !r.ok) setError(r.error.message)
          })
          .catch(() => {
            if (mounted.current) setError('网站显示区域更新失败。')
          })
      })
    }
    const observer = new ResizeObserver(layout)
    if (element.current) observer.observe(element.current)
    if (element.current?.parentElement) observer.observe(element.current.parentElement)
    window.addEventListener('resize', layout)
    window.addEventListener('scroll', layout, true)
    layout()
    return () => {
      mounted.current = false
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('resize', layout)
      window.removeEventListener('scroll', layout, true)
      void window.agent.skillSiteLayout({ owner_id: identity, visible: false }).catch(() => {})
    }
  }, [hasPage])

  /** 短控制请求不等待远程加载；加载错误仍显示在工具栏。 Do not hold navigation RPCs until the remote load finishes. */
  async function control(action: SkillSiteControl['action'], url = '') {
    setError('')
    setSources(null)
    editing.current = false
    try {
      const result = await window.agent.skillSiteControl({ action, url })
      if (!mounted.current) return
      if (result.ok) setState(result.data)
      else setError(result.error.message)
    } catch {
      if (mounted.current) setError('网站操作失败，请重试。')
    }
  }

  /** 只在点击导入后读取来源，多个候选交由用户选择。 Read sources on demand and let the user select a candidate. */
  async function findSources() {
    setReading(true)
    setError('')
    try {
      const result = await window.agent.skillSiteSources()
      if (!mounted.current) return
      if (result.ok) {
        if (result.data.sources.length === 1) onImport(result.data.sources[0].url)
        else setSources(result.data.sources)
      } else setError(result.error.message)
    } catch {
      if (mounted.current) setError('本页来源读取失败，可打开 Skill 详情或粘贴来源链接导入。')
    } finally {
      if (mounted.current) setReading(false)
    }
  }

  return (
    <section className="skill-sites" aria-label="Skill 网站浏览">
      <div className="site-toolbar">
        <select
          aria-label="Skill 聚合网站"
          value={currentSite ?? ''}
          onChange={(e) => void control('navigate', e.target.value)}
        >
          <option value="" disabled>
            {hasPage ? '自定义网站' : '选择聚合网站'}
          </option>
          {defaults.skill_online.sites.map((site) => (
            <option key={site.url} value={site.url}>
              {site.name}
            </option>
          ))}
        </select>
        <button
          aria-label="网页后退"
          disabled={!state?.can_back}
          onClick={() => void control('back')}
        >
          ←
        </button>
        <button
          aria-label="网页前进"
          disabled={!state?.can_forward}
          onClick={() => void control('forward')}
        >
          →
        </button>
        <button
          disabled={!hasPage}
          onClick={() => void control(state?.loading ? 'stop' : 'reload')}
        >
          {state?.loading ? '停止加载' : '刷新网页'}
        </button>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void control('navigate', address)
          }}
        >
          <input
            aria-label="网站地址"
            value={address}
            onChange={(e) => {
              editing.current = true
              setAddress(e.target.value)
            }}
            placeholder="输入聚合网站或 Skill 详情地址"
          />
          <button type="submit" disabled={!address.trim()}>
            访问
          </button>
        </form>
      </div>
      <div className="site-toolbar">
        <span className="muted">
          {state?.loading ? '网站加载中…' : state?.title || '使用原网站的搜索、分类和分页。'}
        </span>
        <button disabled={reading || !state?.url} onClick={() => void findSources()}>
          {reading ? '读取来源…' : '导入本页 Skill'}
        </button>
        <button
          disabled={!state?.url}
          onClick={() => state && void window.agent.openWebUrl(state.url)}
        >
          在系统浏览器打开
        </button>
      </div>
      {(error || state?.error) && <p role="alert">{error || state?.error}</p>}
      {sources && (
        <div className="site-sources">
          <div className="resource-item-heading">
            <strong>选择本页来源</strong>
            <button onClick={() => setSources(null)}>关闭来源</button>
          </div>
          {sources.length === 0 ? (
            <p>
              本页没有可识别的 SkillHub / GitHub / skills.sh 来源。请进入具体 Skill
              详情或点击其来源链接，再导入。
            </p>
          ) : (
            sources.map((source) => (
              <button key={source.url} onClick={() => onImport(source.url)}>
                {source.label}
                <small>{source.url}</small>
              </button>
            ))
          )}
        </div>
      )}
      <div
        className={`site-surface${hasPage ? '' : ' site-empty'}`}
        ref={element}
        aria-label="原网站页面"
      >
        {!hasPage && <p>请先选择聚合网站，或输入网址后点击“访问”。</p>}
      </div>
    </section>
  )
}
