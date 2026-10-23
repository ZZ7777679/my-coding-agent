/** 真实 PTY 面板，导航与折叠只改变展示。 Real PTY panel; navigation only affects display. */
import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import type { SessionSummary, TerminalSummary } from '../../generated/protocol'
import '@xterm/xterm/css/xterm.css'
import './TerminalPanel.css'
import { useAppearance } from './Appearance'
import { palettes } from '../../shared/themes'

const alive = new Set<TerminalSummary['status']>(['starting', 'running', 'stopping'])
const statusLabels: Record<TerminalSummary['status'], string> = {
  starting: '正在启动',
  running: '运行中',
  stopping: '正在关闭',
  exited: '已退出',
  stopped: '已关闭',
  failed: '故障已停止',
  interrupted: '上次结果未确认'
}

type MemberChoice = { member_id: string; name: string; session_id: string | null }

/** 显示单终端并按序号消费输出，输入队列保持键盘先后顺序。 Consume output and serialize keystrokes. */
function TerminalScreen({
  summary,
  visible,
  onRefresh
}: {
  summary: TerminalSummary
  visible: boolean
  onRefresh: () => void
}): React.JSX.Element {
  const host = useRef<HTMLDivElement>(null)
  const { value: appearance } = useAppearance()
  const colors = palettes[appearance.preset]
  const [current, setCurrent] = useState(summary)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const owner = useRef(summary)
  const term = useRef<Terminal | null>(null)
  const generation = useRef(0)
  const refresh = useRef(onRefresh)
  refresh.current = onRefresh

  useEffect(() => {
    owner.current = summary
    setCurrent(summary)
  }, [summary])

  useEffect(() => {
    if (!visible || !host.current) return
    const epoch = ++generation.current
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: false,
      scrollback: 3000,
      fontSize: 13,
      fontFamily: 'Cascadia Mono, Consolas, monospace',
      theme: {
        background: colors.background,
        foreground: colors.text,
        cursor: appearance.accent ?? colors.accent
      },
      // 项目输出中的 OSC 链接和剪贴板指令不是浏览器操作授权。
      // OSC links and clipboard sequences in project output grant no browser-side authority.
      linkHandler: { activate: () => undefined }
    })
    const fit = new FitAddon()
    terminal.loadAddon(fit)
    terminal.open(host.current)
    term.current = terminal
    const clipboard = terminal.parser.registerOscHandler(52, () => true)
    const links = terminal.parser.registerOscHandler(8, () => true)
    let timer: ReturnType<typeof setTimeout> | undefined
    let resizeTimer: ReturnType<typeof setTimeout> | undefined
    let afterSeq = 0
    let pendingInput = ''
    let sendingInput = false
    let inputScheduled = false
    let truncationShown = false

    /** 写入仅使用最新后端控制归属，过期视图不继续发送输入。 Respect actual current control ownership. */
    async function send(text: string): Promise<void> {
      if (generation.current !== epoch) return
      if (owner.current.controller !== 'user' || !alive.has(owner.current.status)) {
        setError('终端当前不接受人工输入；成员控制时请先接管。')
        return
      }
      try {
        const response = await window.agent.writeTerminal({
          terminal_id: summary.terminal_id,
          text
        })
        if (generation.current !== epoch) return
        if (response.ok) {
          owner.current = response.data.summary
          setCurrent(response.data.summary)
          setError('')
        } else setError(response.error.message)
      } catch {
        if (generation.current === epoch) setError('终端输入未完成，请刷新查看实际状态。')
      }
    }
    /** 合并在途写入期间的后续字符，避免快速长行变成数百笔串行 RPC。
     * Coalesce later characters during an in-flight write instead of queuing one RPC per key.
     */
    async function flushInput(): Promise<void> {
      if (sendingInput) return
      sendingInput = true
      inputScheduled = false
      try {
        while (pendingInput && generation.current === epoch) {
          let end = Math.min(pendingInput.length, 64000)
          // 保留 UTF-16 代理对；后端额度按字符计算，64K UTF-16 单位不会超过额度。
          // Preserve surrogate pairs; 64K UTF-16 units stay within the backend character limit.
          if (end < pendingInput.length && /[\uD800-\uDBFF]/.test(pendingInput[end - 1])) end--
          const text = pendingInput.slice(0, end)
          pendingInput = pendingInput.slice(end)
          await send(text)
        }
      } finally {
        sendingInput = false
      }
    }
    const input = terminal.onData((text) => {
      pendingInput += text
      if (!sendingInput && !inputScheduled) {
        inputScheduled = true
        queueMicrotask(() => void flushInput())
      }
    })

    /** 屏幕按实际容器拟合，再更新同一后端 PTY。 Fit the container and resize the same backend PTY. */
    function resize(): void {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => {
        if (generation.current !== epoch || !host.current?.clientWidth) return
        fit.fit()
        if (!alive.has(owner.current.status)) return
        void window.agent
          .resizeTerminal({
            terminal_id: summary.terminal_id,
            cols: terminal.cols,
            rows: terminal.rows
          })
          .then((result) => {
            if (generation.current === epoch && !result.ok) setError(result.error.message)
          })
          .catch(() => {
            if (generation.current === epoch) setError('终端尺寸同步失败。')
          })
      }, 120)
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host.current)
    resize()

    /** 每轮读取完成后再调度，关闭和切换时释放轮询。 Schedule reads after completion and clean on unmount. */
    async function read(): Promise<void> {
      try {
        const response = await window.agent.readTerminal({
          terminal_id: summary.terminal_id,
          after_seq: afterSeq
        })
        if (generation.current !== epoch) return
        if (!response.ok) {
          setError(response.error.message)
          return
        }
        const view = response.data
        owner.current = view.summary
        setCurrent(view.summary)
        if (view.truncated && !truncationShown) {
          terminal.writeln('\r\n[仅保留有界输出，较早内容可能已截断]\r\n')
          truncationShown = true
        }
        for (const chunk of view.output) terminal.write(chunk.text)
        afterSeq = view.next_seq
        if (alive.has(view.summary.status)) timer = setTimeout(() => void read(), 160)
        else refresh.current()
      } catch {
        if (generation.current === epoch) setError('终端输出读取失败，请重新展开面板。')
      }
    }
    void read()
    return () => {
      generation.current++
      clearTimeout(timer)
      clearTimeout(resizeTimer)
      observer.disconnect()
      input.dispose()
      clipboard.dispose()
      links.dispose()
      terminal.dispose()
      term.current = null
    }
  }, [summary.terminal_id, visible])
  useEffect(() => {
    if (term.current)
      term.current.options.theme = {
        background: colors.background,
        foreground: colors.text,
        cursor: appearance.accent ?? colors.accent
      }
  }, [colors, appearance.accent])

  /** 中断与关闭分别作用于前台程序和整个终端进程树。 Interrupt foreground or close the entire tree. */
  async function control(action: 'interrupt' | 'close' | 'take'): Promise<void> {
    const epoch = generation.current
    setBusy(true)
    setError('')
    try {
      const params = { terminal_id: current.terminal_id }
      const response =
        action === 'interrupt'
          ? await window.agent.interruptTerminal(params)
          : action === 'close'
            ? await window.agent.closeTerminal(params)
            : await window.agent.controlTerminal({ ...params, controller: 'user' })
      if (epoch !== generation.current) return
      if (response.ok) {
        owner.current = response.data.summary
        setCurrent(response.data.summary)
        onRefresh()
        if (action === 'take') term.current?.focus()
      } else setError(response.error.message)
    } catch {
      if (epoch === generation.current) setError('终端操作未完成，未自动重试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="terminal-screen">
      <div className="terminal-toolbar">
        <span>
          {statusLabels[current.status]}
          {current.exit_code !== null && ` · 退出码 ${current.exit_code}`}
        </span>
        <span>{current.controller === 'user' ? '用户控制' : '成员控制'}</span>
        {alive.has(current.status) && (
          <>
            {current.controller === 'member' && (
              <button disabled={busy} onClick={() => void control('take')}>
                接管输入
              </button>
            )}
            <button
              disabled={busy || current.controller !== 'user'}
              onClick={() => void control('interrupt')}
            >
              中断 Ctrl+C
            </button>
            <button disabled={busy} onClick={() => void control('close')}>
              关闭终端进程
            </button>
          </>
        )}
      </div>
      <p className="settings-hint">
        {current.environment_name} · 本机直接运行 · 未隔离 · {current.cwd}
      </p>
      <p className="settings-hint">
        终端运行中并不表示其中命令已成功；是否等待输入由程序实际交互决定。
      </p>
      {current.message && <p role="status">{current.message}</p>}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="terminal-viewport" ref={host} aria-label="交互终端输出与输入" />
    </section>
  )
}

/** 项目终端集合、新建与显式交还；隐藏面板不会停止程序。 Project terminal collection and explicit control. */
export function TerminalPanel({
  projectId,
  sessionId = null,
  visible = true,
  selectedTerminalId = null,
  onClose,
  members = []
}: {
  projectId: string
  sessionId?: string | null
  visible?: boolean
  selectedTerminalId?: string | null
  onClose?: () => void
  members?: MemberChoice[]
}): React.JSX.Element {
  const [items, setItems] = useState<TerminalSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [open, setOpen] = useState(true)
  const [available, setAvailable] = useState(false)
  const [unavailable, setUnavailable] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [program, setProgram] = useState('powershell.exe')
  const [shellPreset, setShellPreset] = useState<'powershell' | 'cmd' | 'custom'>('powershell')
  const [argumentsText, setArgumentsText] = useState('["-NoLogo","-NoProfile"]')
  const [cwd, setCwd] = useState('.')
  const [recipient, setRecipient] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionCursor, setSessionCursor] = useState<string | null>(null)
  const [nextSessionCursor, setNextSessionCursor] = useState<string | null>(null)
  const generation = useRef(0)
  const current = items.find((item) => item.terminal_id === selected) ?? items[0] ?? null

  useEffect(() => {
    setItems([])
    setSelected(null)
    setRecipient('')
    setSessions([])
    setSessionCursor(null)
    setNextSessionCursor(null)
  }, [projectId])

  useEffect(() => {
    if (selectedTerminalId) {
      setSelected(selectedTerminalId)
      setOpen(true)
      setRevision((value) => value + 1)
    }
  }, [selectedTerminalId])

  useEffect(() => {
    if (!visible || !open) return
    let disposed = false
    /** 人工终端可显式关联项目已有会话，不自动创建或唤醒成员。 Associate existing sessions only. */
    async function loadSessions(): Promise<void> {
      try {
        const response = await window.agent.listSessions({
          project_id: projectId,
          cursor: sessionCursor,
          limit: 100
        })
        if (disposed) return
        if (response.ok) {
          setSessions((previous) =>
            sessionCursor ? [...previous, ...response.data.sessions] : response.data.sessions
          )
          setNextSessionCursor(response.data.next_cursor)
        } else setError(response.error.message)
      } catch {
        if (!disposed) setError('用于关联终端的会话列表无法读取。')
      }
    }
    void loadSessions()
    return () => {
      disposed = true
    }
  }, [projectId, visible, open, sessionCursor])

  useEffect(() => {
    if (!visible || !open) return
    const epoch = ++generation.current
    let timer: ReturnType<typeof setTimeout> | undefined
    /** 列表按项目读取，迟到响应不覆盖新的项目。 Scope list reads and ignore stale project responses. */
    async function load(): Promise<void> {
      try {
        const response = await window.agent.listTerminals({ project_id: projectId })
        if (generation.current !== epoch) return
        if (response.ok) {
          setItems(response.data.terminals)
          setAvailable(response.data.available)
          setUnavailable(response.data.unavailable_count)
          setError(response.data.message ?? '')
        } else setError(response.error.message)
      } catch {
        if (generation.current === epoch) setError('项目终端读取失败。')
      }
      if (generation.current === epoch) timer = setTimeout(() => void load(), 1500)
    }
    void load()
    return () => {
      generation.current++
      clearTimeout(timer)
    }
  }, [projectId, revision, visible, open])

  /** 新建使用程序和参数数组，按钮不偷偷初始化环境。 Launch explicit argv without environment setup. */
  async function launch(): Promise<void> {
    const epoch = generation.current
    setBusy(true)
    setError('')
    try {
      const decoded: unknown = JSON.parse(argumentsText)
      if (
        !Array.isArray(decoded) ||
        !decoded.every((item): item is string => typeof item === 'string')
      ) {
        setError('程序参数必须是 JSON 字符串数组。')
        return
      }
      const response = await window.agent.openTerminal({
        project_id: projectId,
        cwd,
        command: { kind: 'program', program, arguments: decoded },
        session_id: sessionId
      })
      if (epoch !== generation.current) return
      if (response.ok) {
        setItems((old) => [response.data.summary, ...old])
        setSelected(response.data.summary.terminal_id)
        setRevision((value) => value + 1)
      } else setError(response.error.message)
    } catch {
      if (epoch === generation.current) setError('终端未启动，请检查程序和 JSON 参数。')
    } finally {
      setBusy(false)
    }
  }

  /** 显式关联成员或当前会话，后端据此独占输入。 Explicitly assign member/current-session input. */
  async function handBack(): Promise<void> {
    if (!current) return
    const member = members.find((item) => item.member_id === recipient)
    const projectSession = sessions.find((item) => `session:${item.session_id}` === recipient)
    const targetSession =
      recipient === 'current' ? sessionId : (member?.session_id ?? projectSession?.session_id)
    if (!targetSession) {
      setError('请选择已绑定会话的成员。')
      return
    }
    const epoch = generation.current
    setBusy(true)
    try {
      const response = await window.agent.controlTerminal({
        terminal_id: current.terminal_id,
        controller: 'member',
        session_id: targetSession,
        member_id: member?.member_id ?? null
      })
      if (epoch !== generation.current) return
      if (response.ok) {
        setError('')
        setRevision((value) => value + 1)
      } else setError(response.error.message)
    } catch {
      if (epoch === generation.current) setError('控制归属保存失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <details
      className="terminal-panel"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>交互终端 · {items.filter((item) => alive.has(item.status)).length} 个运行中</summary>
      {onClose && (
        <button className="terminal-hide" onClick={onClose}>
          关闭面板
        </button>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {unavailable > 0 && <p role="alert">{unavailable} 条终端历史无法读取，原文件保留。</p>}
      <details className="terminal-launch">
        <summary>新建人工终端</summary>
        <label>
          终端 Shell
          <select
            value={shellPreset}
            onChange={(event) => {
              const preset = event.target.value
              if (preset === 'powershell') {
                setShellPreset(preset)
                setProgram('powershell.exe')
                setArgumentsText('["-NoLogo","-NoProfile"]')
              } else if (preset === 'cmd') {
                setShellPreset(preset)
                setProgram('cmd.exe')
                setArgumentsText('["/D"]')
              } else setShellPreset('custom')
            }}
          >
            <option value="powershell">PowerShell</option>
            <option value="cmd">CMD</option>
            <option value="custom">自定义程序</option>
          </select>
        </label>
        <label>
          程序
          <input
            value={program}
            onChange={(event) => {
              setProgram(event.target.value)
              setShellPreset('custom')
            }}
          />
        </label>
        <label>
          参数（JSON 字符串数组）
          <input
            value={argumentsText}
            onChange={(event) => {
              setArgumentsText(event.target.value)
              setShellPreset('custom')
            }}
          />
        </label>
        <label>
          项目内工作目录
          <input value={cwd} onChange={(event) => setCwd(event.target.value)} />
        </label>
        <button disabled={busy || !available || !program.trim()} onClick={() => void launch()}>
          启动终端
        </button>
      </details>
      <div className="terminal-tabs" role="tablist" aria-label="项目终端">
        {items.map((item) => (
          <button
            key={item.terminal_id}
            role="tab"
            aria-selected={current?.terminal_id === item.terminal_id}
            onClick={() => {
              setSelected(item.terminal_id)
              setRecipient('')
            }}
          >
            {item.command.kind === 'program' ? item.command.program : 'PowerShell 脚本'} ·{' '}
            {statusLabels[item.status]}
          </button>
        ))}
      </div>
      {!items.length && (
        <p className="settings-hint">尚无终端。人工新建默认用户控制，关联成员后才参与其工作。</p>
      )}
      {current && (
        <>
          {alive.has(current.status) && (
            <div className="terminal-assignment">
              <label>
                交还 / 关联给
                <select value={recipient} onChange={(event) => setRecipient(event.target.value)}>
                  <option value="">选择成员会话</option>
                  {sessionId && <option value="current">当前会话</option>}
                  {members
                    .filter((member) => member.session_id)
                    .map((member) => (
                      <option key={member.member_id} value={member.member_id}>
                        {member.name}
                      </option>
                    ))}
                  {sessions
                    .filter(
                      (item) =>
                        item.session_id !== sessionId &&
                        !members.some((member) => member.session_id === item.session_id)
                    )
                    .map((item) => (
                      <option key={item.session_id} value={`session:${item.session_id}`}>
                        {item.role || item.title} · {item.session_id.slice(0, 8)}
                      </option>
                    ))}
                </select>
              </label>
              <button disabled={busy || !recipient} onClick={() => void handBack()}>
                交还输入控制
              </button>
              {nextSessionCursor && (
                <button onClick={() => setSessionCursor(nextSessionCursor)}>更多会话</button>
              )}
              <span className="settings-hint">终端 ID {current.terminal_id}</span>
            </div>
          )}
          <TerminalScreen
            key={current.terminal_id}
            summary={current}
            visible={visible && open}
            onRefresh={() => setRevision((value) => value + 1)}
          />
        </>
      )}
    </details>
  )
}
