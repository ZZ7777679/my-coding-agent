import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode
} from 'react'
import type { AppearanceSettings } from '../../generated/protocol'
import { accentInk, contrastRatio, defaultAppearance, palettes } from '../../shared/themes'

type AppearanceContext = {
  saved: AppearanceSettings
  value: AppearanceSettings
  ready: boolean
  error: string
  preview: (value: AppearanceSettings) => void
  save: (value: AppearanceSettings) => Promise<boolean>
}
const Context = createContext<AppearanceContext | null>(null)

/** 外观更改只影响展示；保留预览与已保存设置的区别。 Keep preview separate from persisted appearance. */
export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState(defaultAppearance)
  const [value, preview] = useState(defaultAppearance)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const saving = useRef(false)
  useEffect(() => {
    let active = true
    void window.agent
      .getAppearance()
      .then((result) => {
        if (!active) return
        if (result.ok) {
          setSaved(result.data)
          preview(result.data)
        } else setError(result.error.message)
      })
      .catch(() => {
        if (active) setError('无法读取外观设置，本次使用默认外观。')
      })
      .finally(() => {
        if (active) setReady(true)
      })
    return () => {
      active = false
    }
  }, [])
  useLayoutEffect(() => {
    const palette = palettes[value.preset]
    const root = document.documentElement
    root.dataset.theme = value.preset
    root.dataset.tone = palette.dark ? 'dark' : 'light'
    root.style.colorScheme = palette.dark ? 'dark' : 'light'
    for (const [key, color] of Object.entries({
      bg: palette.background,
      panel: palette.panel,
      text: palette.text,
      accent: value.accent ?? palette.accent,
      'accent-ink': accentInk(value.accent ?? palette.accent)
    }))
      root.style.setProperty(`--${key}`, color)
    root.style.setProperty(
      '--sidebar-width',
      `${value.sidebar_collapsed ? 58 : value.sidebar_width}px`
    )
  }, [value])
  /** 单次持久化保持写入次序；失败保留预览和原偏好。 Serialize saves and preserve preview on failure. */
  async function save(next: AppearanceSettings): Promise<boolean> {
    if (saving.current) return false
    saving.current = true
    try {
      const result = await window.agent.saveAppearance(next)
      if (!result.ok) {
        setError(result.error.message)
        return false
      }
      setSaved(result.data)
      preview(result.data)
      setError('')
      return true
    } catch {
      setError('保存外观未确认，请重试。')
      return false
    } finally {
      saving.current = false
    }
  }
  return (
    <Context.Provider value={{ saved, value, ready, error, preview, save }}>
      {children}
    </Context.Provider>
  )
}

/** 读取应用外观，不依赖后端连接或业务运行。 Consume appearance independently of backend availability. */
export function useAppearance() {
  const context = useContext(Context)
  if (!context) throw new Error('AppearanceProvider missing')
  return context
}

/** 五种预设与自定义主色直接预览，保存后跨启动恢复。 Preview presets and persist a custom accent. */
export function AppearanceSettingsPanel() {
  const { value, saved, ready, error, preview, save } = useAppearance()
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [hex, setHex] = useState('')
  const accent = value.accent ?? palettes[value.preset].accent
  useEffect(() => setHex(accent), [accent])
  return (
    <section className="detail-card appearance-settings" aria-label="外观设置">
      <div className="section-heading">
        <div>
          <h2>外观</h2>
          <p className="muted">即时预览 · 保存到当前应用数据目录 · 不影响运行</p>
        </div>
        <span>{JSON.stringify(value) === JSON.stringify(saved) ? '已保存' : '预览中'}</span>
      </div>
      <div className="palette-grid">
        {Object.entries(palettes).map(([id, palette]) => (
          <button
            key={id}
            aria-label={palette.name}
            type="button"
            disabled={!ready || busy}
            aria-pressed={value.preset === id}
            onClick={() => {
              preview({ ...value, preset: id as AppearanceSettings['preset'], accent: null })
              setStatus('')
            }}
          >
            <span
              className="palette-swatch"
              style={{
                background: palette.background,
                color: palette.text,
                borderColor: palette.accent
              }}
            >
              <span style={{ background: palette.panel }}>Aa</span>
              <i style={{ background: palette.accent }} />
            </span>
            {palette.name}
          </button>
        ))}
      </div>
      <div className="appearance-actions">
        <label>
          主色{' '}
          <input
            aria-label="选择主色"
            type="color"
            value={accent}
            disabled={!ready || busy}
            onChange={(e) => preview({ ...value, accent: e.target.value })}
          />
        </label>
        <input
          aria-label="主色 HEX"
          value={hex}
          onChange={(e) => {
            setHex(e.target.value)
            if (/^#[\da-f]{6}$/i.test(e.target.value)) preview({ ...value, accent: e.target.value })
          }}
        />
        <button disabled={!ready || busy} onClick={() => preview({ ...value, accent: null })}>
          恢复预设主色
        </button>
        <button
          disabled={!ready || busy}
          onClick={() => {
            preview(saved)
            setStatus('已还原已保存外观')
          }}
        >
          取消预览
        </button>
        <button
          className="primary-button"
          disabled={!ready || busy}
          onClick={async () => {
            setBusy(true)
            if (await save(value)) setStatus('外观已保存')
            setBusy(false)
          }}
        >
          保存外观
        </button>
      </div>
      {hex !== accent && <p>HEX 需为 # 加六位颜色值；当前仍显示上一个有效主色。</p>}
      {contrastRatio(accent, palettes[value.preset].panel) < 4.5 && (
        <p className="muted">
          主色与面板较接近，链接可能不易阅读；可点击“恢复预设主色”。仍可保存当前选择。
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
    </section>
  )
}

/** 可拖动与键盘调整的导航边界，释放后保存；不重建业务页面。 Resize navigation without remounting work. */
export function SidebarResize() {
  const { value, preview, save, ready } = useAppearance()
  const start = useRef<number | null>(null)
  const width = useRef(value.sidebar_width)
  if (value.sidebar_collapsed) return null
  return (
    <div
      className="sidebar-resize"
      role="separator"
      aria-label="调整侧栏宽度"
      aria-orientation="vertical"
      aria-valuemin={190}
      aria-valuemax={440}
      aria-valuenow={value.sidebar_width}
      tabIndex={0}
      onPointerDown={(e) => {
        if (!ready) return
        start.current = e.clientX
        width.current = value.sidebar_width
        e.currentTarget.setPointerCapture(e.pointerId)
      }}
      onPointerMove={(e) => {
        if (start.current !== null)
          preview({
            ...value,
            sidebar_width: Math.round(
              Math.max(190, Math.min(440, width.current + e.clientX - start.current))
            )
          })
      }}
      onPointerUp={() => {
        if (start.current !== null) {
          start.current = null
          void save(value)
        }
      }}
      onKeyDown={(e) => {
        if (['ArrowLeft', 'ArrowRight'].includes(e.key)) {
          e.preventDefault()
          void save({
            ...value,
            sidebar_width: Math.max(
              190,
              Math.min(440, value.sidebar_width + (e.key === 'ArrowLeft' ? -10 : 10))
            )
          })
        }
      }}
    />
  )
}
