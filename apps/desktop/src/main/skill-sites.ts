/** 原站浏览使用独立 WebContents，没有应用 preload。
 * Browse original sites in a separate WebContents without the application preload.
 */
import { BrowserWindow, WebContentsView } from 'electron'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import type {
  SkillSiteControl,
  SkillSiteLayout,
  SkillSiteState,
  SkillSiteSources
} from '../generated/protocol'
import { BackendError } from './backend'
import { validate } from '../shared/validation'

/** 仅把网页 URL 送入网站视图，应用本地协议仍由应用自己处理。
 * Send web URLs to the site view while keeping local application protocols separate.
 */
function webAddress(value: string): string {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new BackendError({
      code: 'SITE_URL_INVALID',
      message: '请输入完整网站地址，例如 https://skills.sh/。',
      remediation: ''
    })
  }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password)
    throw new BackendError({
      code: 'SITE_URL_INVALID',
      message: '请输入 HTTP / HTTPS 网站地址。',
      remediation: ''
    })
  return url.href
}

/** 一份用户浏览页在管理页间保留，退出窗口时释放。
 * Keep one user browsing page across management views and release it with the window.
 */
export class SkillSites {
  private view: WebContentsView | null = null
  private owner = ''
  private error = ''
  private navigation = 0
  private requestedUrl = ''

  /** 关联宿主窗口；首次访问时才创建网站视图。 Bind the host; create the site view on demand. */
  constructor(
    private window: BrowserWindow,
    private dataDir: string
  ) {
    window.once('closed', () => this.close())
    window.webContents.on('did-start-navigation', (_event, _url, _inPlace, mainFrame) => {
      if (mainFrame) this.view?.setVisible(false)
    })
  }

  /** 网页与应用拥有不同 session，不向网页暴露文件和 RPC 能力。
   * Give the page a separate session without filesystem or application RPC access.
   */
  private ensure(): WebContentsView {
    if (this.view) return this.view
    const view = new WebContentsView({
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        partition: 'persist:skill-sites'
      }
    })
    this.view = view
    view.setVisible(false)
    this.window.contentView.addChildView(view)
    const contents = view.webContents
    contents.session.setPermissionRequestHandler((_wc, permission, callback) =>
      callback(permission === 'clipboard-sanitized-write')
    )
    contents.on('will-navigate', (event, url) => {
      try {
        webAddress(url)
      } catch {
        event.preventDefault()
        this.error = '此链接不是网页，可使用页面中的 GitHub 来源导入。'
      }
    })
    contents.on('will-redirect', (event, url) => {
      try {
        webAddress(url)
      } catch {
        event.preventDefault()
        this.error = '网站跳转到了非网页地址。'
      }
    })
    contents.setWindowOpenHandler(({ url }) => {
      try {
        this.navigate(webAddress(url))
      } catch {
        this.error = '此链接不是可浏览的网页地址。'
      }
      return { action: 'deny' }
    })
    contents.on('did-fail-load', (_event, code, description, _url, mainFrame) => {
      if (mainFrame && code !== -3)
        this.error = `页面加载失败：${description} (${code})，可刷新或在系统浏览器打开。`
    })
    contents.on('did-start-navigation', (_event, _url, _inPlace, mainFrame) => {
      if (mainFrame) this.error = ''
    })
    contents.on('render-process-gone', (_event, details) => {
      this.error = `网页进程已退出（${details.reason}），可刷新页面。`
    })
    // 网页下载仍使用 Chromium 的保存界面；缺省目录归应用数据根。
    // Chromium owns ordinary downloads; its default directory stays under the app data root.
    contents.session.on('will-download', (_event, item, owner) => {
      if (owner !== contents) return
      const directory = path.join(this.dataDir, 'site-downloads')
      try {
        mkdirSync(directory, { recursive: true })
      } catch {
        item.cancel()
        this.error = '无法创建网站下载目录，请检查应用数据目录的可写状态。'
        return
      }
      item.setSaveDialogOptions({
        defaultPath: path.join(directory, path.basename(item.getFilename()))
      })
    })
    return view
  }

  /** 发起导航后立即返回，完成状态由 WebContents 提供。 Start navigation and expose its real state separately. */
  private navigate(url: string): void {
    const contents = this.ensure().webContents
    const generation = ++this.navigation
    this.error = ''
    this.requestedUrl = url
    void contents.loadURL(url).catch(() => {
      if (generation === this.navigation && !contents.isDestroyed() && !this.error)
        this.error = '页面导航未完成，可刷新重试。'
    })
  }

  /** 同步工具栏状态，不抓取网站正文。 Return toolbar facts without collecting page text. */
  status(): SkillSiteState {
    const contents = this.view?.webContents
    return {
      url: contents?.getURL() || this.requestedUrl,
      title: contents?.getTitle() ?? '',
      loading: contents?.isLoading() ?? false,
      can_back: contents?.navigationHistory.canGoBack() ?? false,
      can_forward: contents?.navigationHistory.canGoForward() ?? false,
      error: this.error
    }
  }

  /** 用户在网页内直接使用站内搜索和分页，这里只管理浏览器导航。
   * Search and pagination stay on the original site; this handles browser navigation only.
   */
  control(params: SkillSiteControl): SkillSiteState {
    if (params.action === 'status') return this.status()
    const contents = this.ensure().webContents
    if (params.action !== 'navigate') {
      // 用户停止或换页后，不让旧 loadURL 的中止回调显示成新页面错误。
      // User controls invalidate old loadURL failures instead of displaying stale errors.
      ++this.navigation
      this.error = ''
    }
    if (params.action === 'navigate') this.navigate(webAddress(params.url ?? ''))
    else if (params.action === 'back' && contents.navigationHistory.canGoBack())
      contents.navigationHistory.goBack()
    else if (params.action === 'forward' && contents.navigationHistory.canGoForward())
      contents.navigationHistory.goForward()
    else if (params.action === 'reload') {
      this.error = ''
      contents.reload()
    } else if (params.action === 'stop') contents.stop()
    return this.status()
  }

  /** 原生视图使用窗口 DIP 边界，旧页面隐藏请求不能隐藏新页面。
   * Position the native view in window DIPs; old owners cannot hide a new page.
   */
  layout(params: SkillSiteLayout): SkillSiteState {
    if (!params.visible) {
      if (this.owner === params.owner_id) this.view?.setVisible(false)
      return this.status()
    }
    const view = this.ensure()
    this.owner = params.owner_id
    const [width, height] = this.window.getContentSize()
    const x = Math.min(width, Math.max(0, params.x ?? 0))
    const y = Math.min(height, Math.max(0, params.y ?? 0))
    view.setBounds({
      x,
      y,
      width: Math.max(0, Math.min(params.width ?? 0, width - x)),
      height: Math.max(0, Math.min(params.height ?? 0, height - y))
    })
    view.setVisible((params.width ?? 0) > 0 && (params.height ?? 0) > 0)
    return this.status()
  }

  /** 用户点击导入时只提取当前页实际存在的来源链接。
   * Extract only observed source links when the user explicitly requests an import.
   */
  async sources(): Promise<SkillSiteSources> {
    const contents = this.view?.webContents
    if (!contents) return { page_url: '', sources: [] }
    const page = contents.getURL()
    // 常量脚本不插入页面字符串；返回值按公开 DTO 校验。
    // A constant script contains no interpolated page strings; validate its returned DTO.
    const data: unknown = await contents.executeJavaScript(`(() => {
      const links = [{href: location.href, label: document.title}, ...Array.from(document.querySelectorAll('a[href]')).map(a => ({href: a.href, label: a.textContent || ''}))];
      const found = new Map();
      for (const link of links) {
        let url; try { url = new URL(link.href); } catch { continue; }
        const parts = url.pathname.split('/').filter(Boolean);
        const github = url.hostname === 'github.com' && parts.length >= 2 && (parts.length === 2 || ['tree', 'blob'].includes(parts[2]));
        const skills = ['skills.sh','www.skills.sh'].includes(url.hostname) && parts.length === 3 && parts[0] !== 'site';
        const skillhub = link.href === location.href && ['skillhub.cn','www.skillhub.cn'].includes(url.hostname) && parts[0] === 'skills' && [2, 3].includes(parts.length);
        if (url.protocol !== 'https:' || !(github || skills || skillhub)) continue;
        url.search = ''; url.hash = '';
        if (link.href === location.href) return {page_url:location.href, sources:[{url:url.href,label:document.title || url.href}]};
        if (!found.has(url.href)) found.set(url.href, {url: url.href, label: link.label.trim().slice(0, 150) || url.href});
      }
      return {page_url: location.href, sources: Array.from(found.values()).slice(0, 100)};
    })()`)
    if (contents.getURL() !== page)
      throw new BackendError({
        code: 'SITE_CHANGED',
        message: '页面已跳转，请在目标详情页再次点击导入。',
        remediation: ''
      })
    return validate('SkillSiteSources', data)
  }

  /** 窗口退出显式销毁子视图，避免残留网站进程。 Destroy the child view so website processes do not linger. */
  close(): void {
    if (!this.view) return
    if (!this.view.webContents.isDestroyed()) this.view.webContents.close()
    this.view = null
  }
}
