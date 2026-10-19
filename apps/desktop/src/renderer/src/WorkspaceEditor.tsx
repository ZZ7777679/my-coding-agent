/** 项目文件、可恢复草稿和选定修改比较。 Project files, recoverable drafts and selected change comparisons. */
import { useCallback, useEffect, useRef, useState } from 'react'
import Editor, { DiffEditor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import JsonWorker from 'monaco-editor/language/json/json.worker.js?worker'
import CssWorker from 'monaco-editor/language/css/css.worker.js?worker'
import HtmlWorker from 'monaco-editor/language/html/html.worker.js?worker'
import TsWorker from 'monaco-editor/language/typescript/ts.worker.js?worker'
import type {
  ChangeSummary,
  DocumentDiff,
  DocumentListing,
  DocumentMatch,
  DocumentView,
  DocumentOperationParams,
  OperationResult,
  LanguageResult,
  LanguageQuery
} from '../../generated/protocol'
import {
  bindEditorIntelligence,
  codeModelUri,
  codeRenameTargets,
  type EditorLanguageBinding
} from './EditorIntelligence'
import { EditorIntelligenceView } from './EditorIntelligenceView'
import './WorkspaceEditor.css'

// Monaco 与 workers 均来自打包资源；不从 CDN 载入代码。
// Bundle Monaco and workers locally without loading CDN code.
self.MonacoEnvironment = {
  getWorker(_moduleId, label) {
    if (label === 'json') return new JsonWorker()
    if (label === 'css' || label === 'scss' || label === 'less') return new CssWorker()
    if (label === 'html' || label === 'handlebars' || label === 'razor') return new HtmlWorker()
    if (label === 'typescript' || label === 'javascript') return new TsWorker()
    return new EditorWorker()
  }
}
loader.config({ monaco })
// 项目语义来自真实 LSP，避免内置单文件服务重复返回建议。
// Project semantics come from real LSP rather than duplicate single-file providers.
for (const defaults of [
  monaco.typescript.typescriptDefaults,
  monaco.typescript.javascriptDefaults
]) {
  defaults.setModeConfiguration({
    completionItems: false,
    hovers: false,
    documentSymbols: false,
    definitions: false,
    references: false,
    documentHighlights: false,
    rename: false,
    diagnostics: false,
    documentRangeFormattingEdits: false,
    signatureHelp: false
  })
}

export type DocumentReference = {
  path: string
  content: string
  start_line: number
  end_line: number
  draft: boolean
}
type Props = { sessionId: string | null; onReference?: (reference: DocumentReference) => void }
type Buffer = DocumentView & { base: string; disk?: string; missing?: boolean }
type WorkbenchState = { buffers: Buffer[]; active: string; directory: string }
const cached = new Map<string, WorkbenchState>()

/** 编辑器使用 LF；磁盘保存仍由后端保留原换行。 Use LF in the editor while backend preserves disk line endings. */
function editorText(text: string): string {
  return text.replace(/\r\n|\r/g, '\n')
}

/** 根据文件扩展名选择编辑器语言，不推断实际项目环境。 Select editor language from extension without assuming project tooling. */
function language(path: string): string {
  const extension = path.split('.').pop()?.toLowerCase()
  const languages: Record<string, string> = {
    py: 'python',
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    json: 'json',
    css: 'css',
    scss: 'scss',
    html: 'html',
    md: 'markdown',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'ini',
    xml: 'xml',
    sql: 'sql',
    sh: 'shell',
    ps1: 'powershell'
  }
  return languages[extension ?? ''] ?? 'plaintext'
}

/** 隔离会话视图，切换后旧响应不改写新会话。 Isolate session views against late responses after navigation. */
export function WorkspaceEditor({ sessionId, onReference }: Props) {
  if (!sessionId)
    return (
      <section className="workspace-editor">
        <p>选择会话后浏览和编辑项目文件。</p>
      </section>
    )
  return <FileWorkbench key={sessionId} sessionId={sessionId} onReference={onReference} />
}

/** 多标签编辑保存、草稿、冲突和文件操作。 Handle tabs, saves, drafts, conflicts and file operations. */
function FileWorkbench({
  sessionId,
  onReference
}: {
  sessionId: string
  onReference?: Props['onReference']
}) {
  const [state, setState] = useState<WorkbenchState>(
    () =>
      cached.get(sessionId) ?? {
        buffers: [],
        active: '',
        directory: '.'
      }
  )
  const [listing, setListing] = useState<DocumentListing | null>(null)
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<DocumentMatch[]>([])
  const [searchMode, updateSearchMode] = useState(false)
  const searchModeRef = useRef(false)
  /** 立即停止文件名筛选计时器，防止其丢弃内容搜索响应。 Stop pending filename filtering immediately. */
  const setSearchMode = (value: boolean): void => {
    searchModeRef.current = value
    updateSearchMode(value)
  }
  const [regex, setRegex] = useState(false)
  const [includeGlobs, setIncludeGlobs] = useState('')
  const [excludeGlobs, setExcludeGlobs] = useState('')
  const [contextLines, setContextLines] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [changes, setChanges] = useState<ChangeSummary[]>([])
  const [changeCursor, setChangeCursor] = useState<string | null>(null)
  const [history, setHistory] = useState<DocumentDiff | null>(null)
  const [compareCurrent, setCompareCurrent] = useState(false)
  const [operation, setOperation] = useState<DocumentOperationParams['operation'] | ''>('')
  const [operationPath, setOperationPath] = useState('')
  const [destination, setDestination] = useState('')
  const [recursive, setRecursive] = useState(false)
  const [line, setLine] = useState('1')
  const [codeContext, setCodeContext] = useState<{ projectId: string; projectRoot: string } | null>(
    null
  )
  const [codeEditor, setCodeEditor] = useState<monaco.editor.IStandaloneCodeEditor | null>(null)
  const [codeResult, setCodeResult] = useState<LanguageResult | null>(null)
  const [codeError, setCodeError] = useState('')
  const [newName, setNewName] = useState('')
  const [selectedRenames, setSelectedRenames] = useState<string[]>([])
  const [renamePreview, setRenamePreview] = useState<string | null>(null)
  const codeBinding = useRef<EditorLanguageBinding | null>(null)
  const codeGeneration = useRef(0)
  const navigation = useRef<(path: string, line: number, column: number) => Promise<void>>(
    async () => {}
  )
  const pendingPosition = useRef<{ path: string; line: number; column: number } | null>(null)
  const queryRef = useRef(query)
  queryRef.current = query
  const stateRef = useRef(state)
  const mounted = useRef(true)
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const listGeneration = useRef(0)
  const openGeneration = useRef(0)
  const draftQueues = useRef(new Map<string, Promise<void>>())
  const actionRef = useRef(false)
  const active = state.buffers.find((buffer) => buffer.path === state.active)

  /** 所有异步更新仍写回原会话缓存；卸载后不更新 React。 Cache updates by original session and avoid updating unmounted React. */
  const update = useCallback(
    (change: (old: WorkbenchState) => WorkbenchState) => {
      const next = change(stateRef.current)
      stateRef.current = next
      cached.set(sessionId, next)
      if (mounted.current) setState(next)
    },
    [sessionId]
  )

  /** 同文件草稿依次落盘，早发请求不会覆盖后发编辑。 Persist each file's drafts sequentially so older writes never replace newer edits. */
  const persist = useCallback(
    (buffer: Buffer) => {
      const previous = draftQueues.current.get(buffer.path) ?? Promise.resolve()
      const next = previous
        .then(async () => {
          const result = await window.agent.documentsDraft({
            session_id: sessionId,
            path: buffer.path,
            base_content: buffer.base,
            content: buffer.content
          })
          if (!result.ok && mounted.current) setError(`草稿保存失败：${result.error.message}`)
        })
        .catch(() => {
          if (mounted.current) setError('草稿连接中断；当前窗口缓冲仍保留。')
        })
      draftQueues.current.set(buffer.path, next)
      return next
    },
    [sessionId]
  )

  /** 刷新文件发现，保留未保存缓冲。 Refresh file discovery while retaining unsaved buffers. */
  const refresh = useCallback(
    async (directory = stateRef.current.directory, filter = queryRef.current) => {
      const ticket = ++listGeneration.current
      try {
        const result = await window.agent.documentsList({
          session_id: sessionId,
          directory,
          query: filter,
          limit: 1000
        })
        if (!mounted.current || ticket !== listGeneration.current) return
        if (result.ok) {
          setListing(result.data)
          update((old) => ({ ...old, directory }))
        } else setError(result.error.message)
      } catch {
        if (mounted.current) setError('文件树读取失败。')
      }
    },
    [sessionId, update]
  )

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (!searchModeRef.current) void refresh()
    }, 250)
    return () => clearTimeout(timeout)
  }, [query, searchMode, refresh])

  useEffect(() => {
    let disposed = false
    void Promise.all([
      window.agent.getSession({ session_id: sessionId, before_seq: null }),
      window.agent.listProjects()
    ])
      .then(([session, projects]) => {
        if (disposed) return
        if (!session.ok || !projects.ok) {
          setCodeError('语言服务项目资料暂不可用；文件保存仍可使用。')
          return
        }
        const project =
          projects.data.recent_projects.find(
            (item) => item.project_id === session.data.summary.project_id
          ) ??
          (projects.data.active_project?.project_id === session.data.summary.project_id
            ? projects.data.active_project
            : null)
        if (project)
          setCodeContext({ projectId: project.project_id, projectRoot: project.canonical_path })
      })
      .catch(() => {
        if (!disposed) setCodeError('语言服务项目连接中断；文件保存仍可使用。')
      })
    return () => {
      disposed = true
    }
  }, [sessionId])

  useEffect(() => {
    if (!codeEditor || !codeContext || history) return
    const binding = bindEditorIntelligence({
      editor: codeEditor,
      sessionId,
      ...codeContext,
      onError: (message) => {
        if (mounted.current) setCodeError(message)
      },
      onRename: (result) => {
        if (mounted.current) {
          setCodeResult(result)
          setSelectedRenames([])
          setRenamePreview(null)
        }
      },
      onNavigate: (path, targetLine, column) => navigation.current(path, targetLine, column)
    })
    codeBinding.current = binding
    return () => {
      ++codeGeneration.current
      binding.dispose()
      if (codeBinding.current === binding) codeBinding.current = null
    }
  }, [codeEditor, codeContext, sessionId, history])

  /** 分页历史修改，运行身份保留在记录中。 Page historical changes with their original run identities. */
  const loadChanges = useCallback(
    async (cursor: string | null = null) => {
      try {
        const result = await window.agent.listChanges({ session_id: sessionId, cursor, limit: 100 })
        if (!mounted.current) return
        if (result.ok) {
          setChanges((old) => (cursor ? [...old, ...result.data.changes] : result.data.changes))
          setChangeCursor(result.data.next_cursor)
          if (result.data.unavailable_count)
            setNotice(`${result.data.unavailable_count} 条历史记录不可读，文件编辑仍可继续。`)
        } else setError(result.error.message)
      } catch {
        if (mounted.current) setError('历史修改读取失败。')
      }
    },
    [sessionId]
  )

  useEffect(() => {
    mounted.current = true
    void refresh()
    void loadChanges()
    void window.agent
      .documentsDrafts({ session_id: sessionId })
      .then(async (result) => {
        if (!mounted.current) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        for (const draft of result.data.drafts) {
          if (!mounted.current) return
          // 不覆盖本窗口已经编辑的缓冲；恢复只发生在尚未打开的文件。
          // Never overwrite this window's newer buffer while restoring unopened drafts.
          if (stateRef.current.buffers.some((buffer) => buffer.path === draft.path)) continue
          const disk = await window.agent.documentsRead({ session_id: sessionId, path: draft.path })
          if (!mounted.current) return
          const buffer: Buffer = {
            path: draft.path,
            content: editorText(draft.content),
            base: editorText(draft.base_content),
            encoding: disk.ok ? disk.data.encoding : '未知',
            newline: disk.ok ? disk.data.newline : '未知',
            read_at: disk.ok ? disk.data.read_at : (draft.updated_at ?? ''),
            disk:
              disk.ok && editorText(disk.data.content) !== editorText(draft.base_content)
                ? editorText(disk.data.content)
                : undefined,
            missing: !disk.ok
          }
          update((old) => ({
            ...old,
            buffers: [...old.buffers, buffer],
            active: old.active || buffer.path
          }))
        }
      })
      .catch(() => {
        if (mounted.current) setError('草稿恢复失败，已保存记录仍保留。')
      })
    return () => {
      mounted.current = false
      ++listGeneration.current
      ++openGeneration.current
    }
  }, [sessionId, refresh, loadChanges, update])

  /** 打开指定文件，快速连续选择时只激活最新请求。 Open selected files and activate only the latest rapid selection. */
  const open = async (path: string, targetLine = 1, column = 1) => {
    const ticket = ++openGeneration.current
    setHistory(null)
    if (!stateRef.current.buffers.some((buffer) => buffer.path === path)) {
      try {
        const result = await window.agent.documentsRead({ session_id: sessionId, path })
        if (!mounted.current) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        const draftResult = await window.agent.documentsDrafts({ session_id: sessionId })
        if (!mounted.current) return
        const draft = draftResult.ok
          ? draftResult.data.drafts.find((item) => item.path === path)
          : undefined
        if (!draftResult.ok) setError(draftResult.error.message)
        const buffer: Buffer = draft
          ? {
              ...result.data,
              base: editorText(draft.base_content),
              content: editorText(draft.content),
              disk:
                editorText(draft.base_content) !== editorText(result.data.content)
                  ? editorText(result.data.content)
                  : undefined
            }
          : {
              ...result.data,
              content: editorText(result.data.content),
              base: editorText(result.data.content)
            }
        update((old) =>
          old.buffers.some((item) => item.path === path)
            ? old
            : { ...old, buffers: [...old.buffers, buffer] }
        )
      } catch {
        if (mounted.current) setError('无法打开文件。')
        return
      }
    }
    if (!mounted.current || ticket !== openGeneration.current) return
    update((old) => ({ ...old, active: path }))
    pendingPosition.current = { path, line: targetLine, column }
    setLine(String(targetLine))
    requestAnimationFrame(() => {
      if (editor.current?.getModel()?.uri.toString() === codeModelUri(sessionId, path).toString()) {
        editor.current.revealLineInCenter(targetLine)
        editor.current.setPosition({ lineNumber: targetLine, column })
        editor.current.focus()
      }
    })
  }
  navigation.current = open

  /** 查询结果绑定实际模型，文件切换后不展示迟到结果。 Associate query responses with the actual model and reject late results. */
  const queryCode = async (action: LanguageQuery['action']) => {
    const ticket = ++codeGeneration.current
    const model = editor.current?.getModel()
    const result = await codeBinding.current?.query(
      action,
      action === 'rename' ? newName : undefined
    )
    if (
      !mounted.current ||
      ticket !== codeGeneration.current ||
      editor.current?.getModel() !== model
    )
      return
    if (result) {
      setCodeResult(result)
      setSelectedRenames([])
      setRenamePreview(null)
    }
  }

  /** 安装编辑器并在模型变化后恢复精确导航位置。 Attach the editor and restore exact navigation after model changes. */
  const attachEditor = (instance: monaco.editor.IStandaloneCodeEditor) => {
    editor.current = instance
    setCodeEditor(instance)
    const position = () => {
      const pending = pendingPosition.current
      if (
        pending &&
        instance.getModel()?.uri.toString() === codeModelUri(sessionId, pending.path).toString()
      ) {
        instance.revealLineInCenter(pending.line)
        instance.setPosition({ lineNumber: pending.line, column: pending.column })
        instance.focus()
        pendingPosition.current = null
      }
    }
    position()
    const listener = instance.onDidChangeModel(() => {
      ++codeGeneration.current
      setCodeResult(null)
      requestAnimationFrame(position)
    })
    instance.onDidDispose(() => {
      listener.dispose()
      if (editor.current === instance) editor.current = null
    })
  }

  const renameTargets =
    codeResult?.action === 'rename' && codeContext
      ? codeRenameTargets(codeResult, codeContext.projectRoot)
      : []

  /** 明确选择后应用快照建议；草稿只改缓冲，磁盘写入仍用原始快照。 Apply explicitly selected snapshots; drafts stay local and disk writes use captured baselines. */
  const applyRenames = async (saveDisk: boolean) => {
    if (actionRef.current) return
    actionRef.current = true
    setBusy(true)
    const targets = renameTargets.filter((target) => selectedRenames.includes(target.path))
    let completed = 0
    const failures: string[] = []
    try {
      for (const target of targets) {
        if (target.base === null || target.content === null || target.error) {
          failures.push(`${target.path}：${target.error ?? '缺少快照'}`)
          continue
        }
        if (saveDisk && target.source === 'draft') {
          failures.push(`${target.path}：这是草稿建议，请先应用到缓冲，再点击文件保存。`)
          continue
        }
        let buffer = stateRef.current.buffers.find((item) => item.path === target.path)
        if (
          buffer &&
          ((target.source === 'disk' && buffer.content !== buffer.base) ||
            editorText(target.base) !== buffer.content)
        ) {
          failures.push(`${target.path}：缓冲已变化，保留当前编辑，请重新查询。`)
          continue
        }
        if (target.source === 'draft' && !buffer) {
          failures.push(`${target.path}：原草稿已关闭，请重新查询。`)
          continue
        }
        if (saveDisk) {
          // 使用查询时捕获正文；不把此时重新读取的磁盘内容当作保存基线。
          // Use the query-time snapshot rather than rereading a new save baseline.
          const result = await window.agent.documentsSave({
            session_id: sessionId,
            path: target.path,
            base_content: target.base,
            content: target.content
          })
          if (!result.ok) {
            failures.push(`${target.path}：${result.error.message}`)
            continue
          }
          const saved = editorText(result.data.content)
          update((old) => ({
            ...old,
            buffers: old.buffers.map((item) =>
              item.path === target.path
                ? {
                    ...result.data,
                    content: item.content === editorText(target.base!) ? saved : item.content,
                    base: saved
                  }
                : item
            )
          }))
          buffer = stateRef.current.buffers.find((item) => item.path === target.path)
          if (buffer) await persist(buffer)
        } else {
          if (!buffer) {
            const result = await window.agent.documentsRead({
              session_id: sessionId,
              path: target.path
            })
            if (!result.ok || editorText(result.data.content) !== editorText(target.base)) {
              failures.push(`${target.path}：磁盘已变化或不可读，请重新查询。`)
              continue
            }
            // 读取仅提供显示元数据，编辑建议仍使用查询时的正文。
            // Read only display metadata; edits retain their query-time text.
            buffer = {
              ...result.data,
              base: editorText(target.base),
              content: editorText(target.base)
            }
          }
          const latest = stateRef.current.buffers.find((item) => item.path === target.path)
          if (latest && latest.content !== buffer.content) {
            failures.push(`${target.path}：缓冲已变化，未覆盖。`)
            continue
          }
          const next = { ...buffer, content: editorText(target.content) }
          update((old) => ({
            ...old,
            buffers: [...old.buffers.filter((item) => item.path !== target.path), next],
            active: old.active || target.path
          }))
          await persist(next)
        }
        ++completed
      }
      if (mounted.current) {
        setNotice(
          `已${saveDisk ? '保存到磁盘' : '应用到缓冲'} ${completed} 个文件${saveDisk ? '' : '；检查后点击文件保存。'}`
        )
        setCodeError(failures.join('；'))
        setSelectedRenames([])
        if (saveDisk) void loadChanges()
      }
    } catch {
      if (mounted.current) setCodeError('重命名应用连接中断；已保存的文件保留，请核对后继续。')
    } finally {
      actionRef.current = false
      if (mounted.current) setBusy(false)
    }
  }

  /** 修改内存缓冲并立即排队保存草稿，不隐式写入项目。 Update buffers and queue drafts without implicit project saves. */
  const edit = (content: string | undefined) => {
    const current = stateRef.current.buffers.find(
      (buffer) => buffer.path === stateRef.current.active
    )
    if (!current || content === undefined) return
    const next = { ...current, content }
    update((old) => ({
      ...old,
      buffers: old.buffers.map((buffer) => (buffer.path === next.path ? next : buffer))
    }))
    void persist(next)
  }

  /** 保存时沿后端原文基线检查；冲突读取磁盘并保留草稿。 Save through backend base checks and preserve drafts on conflict. */
  const save = async () => {
    if (!active || actionRef.current) return
    const snapshot = active
    actionRef.current = true
    setBusy(true)
    setError('')
    try {
      await persist(snapshot)
      const result = await window.agent.documentsSave({
        session_id: sessionId,
        path: snapshot.path,
        base_content: snapshot.base,
        content: snapshot.content
      })
      if (!result.ok) {
        if (mounted.current) setError(result.error.message)
        const disk = await window.agent.documentsRead({
          session_id: sessionId,
          path: snapshot.path
        })
        if (disk.ok)
          update((old) => ({
            ...old,
            buffers: old.buffers.map((buffer) =>
              buffer.path === snapshot.path
                ? { ...buffer, disk: editorText(disk.data.content) }
                : buffer
            )
          }))
        return
      }
      const latest = stateRef.current.buffers.find((buffer) => buffer.path === snapshot.path)
      if (latest) {
        const next = {
          ...latest,
          base: editorText(result.data.content),
          disk: undefined,
          missing: false
        }
        update((old) => ({
          ...old,
          buffers: old.buffers.map((buffer) => (buffer.path === snapshot.path ? next : buffer))
        }))
        await persist(next)
      }
      if (mounted.current) {
        setNotice('已保存到原项目并记录人工修改。')
        void loadChanges()
      }
    } catch {
      if (mounted.current) setError('保存连接中断，请核对磁盘后继续；草稿保留。')
    } finally {
      actionRef.current = false
      if (mounted.current) setBusy(false)
    }
  }

  /** 重读磁盘；脏缓冲保留双方，干净缓冲直接更新。 Reload disk, retaining both sides of a dirty buffer. */
  const reload = async () => {
    if (!active) return
    const result = await window.agent.documentsRead({ session_id: sessionId, path: active.path })
    if (!mounted.current) return
    if (!result.ok) {
      setError(result.error.message)
      return
    }
    update((old) => ({
      ...old,
      buffers: old.buffers.map((buffer) =>
        buffer.path !== active.path
          ? buffer
          : buffer.content !== buffer.base
            ? { ...buffer, disk: editorText(result.data.content) }
            : {
                ...result.data,
                content: editorText(result.data.content),
                base: editorText(result.data.content)
              }
      )
    }))
  }

  /** 显式接受比较过的磁盘基线，右侧合并内容仍待人工保存。 Accept the compared disk baseline; the merged right side still needs saving. */
  const acceptMerge = () => {
    if (!active || active.disk === undefined) return
    const next = { ...active, base: active.disk, disk: undefined }
    update((old) => ({
      ...old,
      buffers: old.buffers.map((buffer) => (buffer.path === next.path ? next : buffer))
    }))
    void persist(next)
    setNotice('已采用比较中的磁盘基线；检查合并内容后点击保存。')
  }

  /** 保留草稿后关闭标签；再次打开仍恢复此窗口缓冲。 Close tabs after keeping their draft contents. */
  const close = (path: string) => {
    const buffer = stateRef.current.buffers.find((item) => item.path === path)
    if (buffer) void persist(buffer)
    update((old) => ({
      ...old,
      buffers: old.buffers.filter((item) => item.path !== path),
      active:
        old.active === path
          ? (old.buffers.find((item) => item.path !== path)?.path ?? '')
          : old.active
    }))
  }

  /** 内容搜索独立于文件名过滤。 Search contents independently from filename filtering. */
  const search = async () => {
    if (!query.trim()) return
    setSearchMode(true)
    setMatches([])
    setError('')
    const ticket = ++listGeneration.current
    const result = await window.agent.documentsSearch({
      session_id: sessionId,
      query,
      limit: 100,
      regex,
      before: contextLines,
      after: contextLines,
      include_globs: includeGlobs
        .split(';')
        .map((value) => value.trim())
        .filter(Boolean),
      exclude_globs: excludeGlobs
        .split(';')
        .map((value) => value.trim())
        .filter(Boolean)
    })
    if (!mounted.current || ticket !== listGeneration.current) return
    if (result.ok) {
      setMatches(result.data.matches)
      setSearchMode(true)
      setNotice(
        result.data.truncated
          ? '搜索已截断，请缩小查询。'
          : `命中 ${result.data.matches.length} 处，跳过 ${result.data.skipped} 个不可读文件。`
      )
    } else setError(result.error.message)
  }

  /** 按真实逐项结果显示部分成功。 Display partial success from actual per-file outcomes. */
  const showOperation = (result: OperationResult) => {
    const failures = result.items.filter((item) => item.status === 'failed')
    const successes = result.items.length - failures.length
    setNotice(`完成 ${successes} 项${result.partial ? '（部分成功）' : ''}。`)
    if (failures.length)
      setError(failures.map((item) => `${item.path}：${item.message ?? item.code}`).join('；'))
  }

  /** 文件操作通过后端，删除范围由表单显式选定。 Route file operations through the backend with explicit deletion scope. */
  const performOperation = async () => {
    if (!operation || !operationPath || actionRef.current) return
    actionRef.current = true
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.documentsOperate({
        session_id: sessionId,
        path: operationPath,
        operation,
        destination: destination || null,
        recursive,
        content: ''
      })
      if (!mounted.current) return
      if (result.ok) {
        showOperation(result.data)
        setOperation('')
        void refresh()
        void loadChanges()
      } else setError(result.error.message)
    } catch {
      if (mounted.current) setError('文件操作连接中断，请检查磁盘后继续。')
    } finally {
      actionRef.current = false
      if (mounted.current) setBusy(false)
    }
  }

  /** 读取历史与当前磁盘三方事实。 Load historical snapshots and independent current disk facts. */
  const compare = async (changeId: string) => {
    const result = await window.agent.documentsDiff({ session_id: sessionId, change_id: changeId })
    if (!mounted.current) return
    if (result.ok) {
      setHistory(result.data)
      setCompareCurrent(false)
    } else setError(result.error.message)
  }

  /** 恢复明确选定的记录，后端保留不重叠后续编辑。 Restore one selected record while backend preserves unrelated later edits. */
  const restore = async () => {
    if (!history || actionRef.current) return
    actionRef.current = true
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.documentsRestore({
        session_id: sessionId,
        change_id: history.summary.change_id
      })
      if (!mounted.current) return
      if (result.ok) {
        showOperation(result.data)
        await compare(history.summary.change_id)
        void loadChanges()
        void refresh()
      } else setError(result.error.message)
    } catch {
      if (mounted.current) setError('恢复连接中断，请核对磁盘；没有自动重放。')
    } finally {
      actionRef.current = false
      if (mounted.current) setBusy(false)
    }
  }

  /** 把编辑器选区作为实际材料交给输入区，草稿不自动保存。 Send actual selected material to chat without saving drafts to project. */
  const reference = () => {
    if (!active || !onReference) return
    const selection = editor.current?.getSelection()
    const model = editor.current?.getModel()
    const selected =
      selection && !selection.isEmpty() && model ? model.getValueInRange(selection) : active.content
    onReference({
      path: active.path,
      content: selected,
      start_line: selection && !selection.isEmpty() ? selection.startLineNumber : 1,
      end_line:
        selection && !selection.isEmpty()
          ? selection.endLineNumber
          : active.content.split(/\r\n|\r|\n/).length,
      draft: active.content !== active.base
    })
  }

  const files = (listing?.files ?? []).filter((path) =>
    path.toLocaleLowerCase().includes(query.toLocaleLowerCase())
  )
  const directDirectories = (listing?.directories ?? []).filter((path) => {
    const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '.'
    return parent === state.directory
  })

  return (
    <section className="workspace-editor" aria-label="文件工作台">
      <aside className="workspace-files">
        <div className="workspace-file-toolbar">
          <strong>文件</strong>
          <button onClick={() => void refresh()}>刷新</button>
        </div>
        <input
          aria-label="快速打开文件"
          placeholder="快速打开 · 文件路径"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setSearchMode(false)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void search()
          }}
        />
        <button disabled={!query.trim()} onClick={() => void search()}>
          搜索文件内容
        </button>
        <details className="workspace-search-options">
          <summary>搜索选项</summary>
          <label>
            <input
              type="checkbox"
              checked={regex}
              onChange={(event) => setRegex(event.target.checked)}
            />
            正则表达式（rg）
          </label>
          <label>
            包含路径
            <input
              placeholder="**/*.py; **/*.ts"
              value={includeGlobs}
              onChange={(event) => setIncludeGlobs(event.target.value)}
            />
          </label>
          <label>
            排除路径
            <input
              placeholder="tests/**; vendor/**"
              value={excludeGlobs}
              onChange={(event) => setExcludeGlobs(event.target.value)}
            />
          </label>
          <label>
            前后文行数
            <input
              type="number"
              min={0}
              value={contextLines}
              onChange={(event) =>
                setContextLines(Math.max(0, Math.trunc(Number(event.target.value) || 0)))
              }
            />
          </label>
          <small>多个模式用分号分隔；沿用项目忽略规则。</small>
        </details>
        <button
          onClick={() => {
            setSearchMode(false)
            void refresh('.')
          }}
        >
          项目根
        </button>
        <small>{state.directory}</small>
        <nav aria-label="项目文件树">
          {state.directory !== '.' && (
            <button
              onClick={() =>
                void refresh(
                  state.directory.includes('/')
                    ? state.directory.slice(0, state.directory.lastIndexOf('/'))
                    : '.'
                )
              }
            >
              ↰ 上一级
            </button>
          )}
          {searchMode ? (
            matches.map((match, index) => (
              <button
                key={`${match.path}:${match.line}:${index}`}
                onClick={() => void open(match.path, match.line)}
              >
                <span>
                  {match.path}:{match.line}
                </span>
                {(match.context_before ?? []).map((line) => (
                  <small key={`b${line.line}`}>
                    {line.line}: {line.text}
                  </small>
                ))}
                <small>
                  <strong>
                    {match.line}: {match.text}
                  </strong>
                </small>
                {(match.context_after ?? []).map((line) => (
                  <small key={`a${line.line}`}>
                    {line.line}: {line.text}
                  </small>
                ))}
              </button>
            ))
          ) : (
            <>
              {directDirectories.map((path) => (
                <button key={`dir:${path}`} onClick={() => void refresh(path)}>
                  ▸ {path.split('/').pop()}/
                </button>
              ))}
              {files.map((path) => (
                <button
                  key={path}
                  onClick={() => void open(path)}
                  title={path}
                  style={{ paddingLeft: `${Math.min(path.split('/').length, 6) * 7}px` }}
                >
                  {path}
                </button>
              ))}
            </>
          )}
          {!searchMode && listing && !listing.files.length && !listing.directories.length && (
            <p>没有符合路径筛选的文件。</p>
          )}
          {listing?.truncated && <p>发现结果已截断，可打开子目录继续查看。</p>}
        </nav>
        <details>
          <summary>创建、移动与删除</summary>
          <select
            aria-label="文件操作"
            value={operation}
            onChange={(event) => {
              const value = event.target.value
              setOperation(
                value === 'create_file' ||
                  value === 'create_directory' ||
                  value === 'move' ||
                  value === 'delete'
                  ? value
                  : ''
              )
              setOperationPath(state.active)
            }}
          >
            <option value="">选择操作</option>
            <option value="create_file">新建文件</option>
            <option value="create_directory">新建目录</option>
            <option value="move">移动 / 重命名</option>
            <option value="delete">删除</option>
          </select>
          {operation && (
            <>
              <input
                aria-label="操作路径"
                placeholder="项目相对路径"
                value={operationPath}
                onChange={(event) => setOperationPath(event.target.value)}
              />
              {operation === 'move' && (
                <input
                  aria-label="移动目的地"
                  placeholder="目的地相对路径"
                  value={destination}
                  onChange={(event) => setDestination(event.target.value)}
                />
              )}
              {operation === 'delete' && (
                <label>
                  <input
                    type="checkbox"
                    checked={recursive}
                    onChange={(event) => setRecursive(event.target.checked)}
                  />
                  包含目录全部内容（递归删除）
                </label>
              )}
              <button disabled={busy || !operationPath} onClick={() => void performOperation()}>
                {operation === 'delete' ? '删除指定路径' : '执行操作'}
              </button>
            </>
          )}
        </details>
        <details>
          <summary>历史修改（{changes.length}）</summary>
          <button onClick={() => void loadChanges()}>刷新记录</button>
          {changes.map((change) => (
            <button
              key={change.change_id}
              onClick={() => void compare(change.change_id)}
              title={`Run ${change.run_id}`}
            >
              <span>{change.path}</span>
              <small>
                {change.operation} · {change.source ?? 'agent'} · {change.status} ·{' '}
                {change.run_id.slice(0, 8)}
              </small>
            </button>
          ))}
          {changeCursor && <button onClick={() => void loadChanges(changeCursor)}>更多记录</button>}
        </details>
      </aside>
      <main className="workspace-code">
        <div className="workspace-tabs" role="tablist" aria-label="打开文件">
          {state.buffers.map((buffer) => (
            <div key={buffer.path} className={state.active === buffer.path ? 'active' : ''}>
              <button
                role="tab"
                aria-selected={state.active === buffer.path}
                onClick={() => {
                  setHistory(null)
                  update((old) => ({ ...old, active: buffer.path }))
                }}
              >
                {buffer.path.split('/').pop()}
                {buffer.content !== buffer.base ? ' ●' : ''}
              </button>
              <button aria-label={`关闭 ${buffer.path}`} onClick={() => close(buffer.path)}>
                ×
              </button>
            </div>
          ))}
        </div>
        {error && (
          <p role="alert" className="workspace-notice">
            {error}
          </p>
        )}
        {notice && <p className="workspace-notice">{notice}</p>}
        {history ? (
          <>
            <div className="workspace-code-toolbar">
              <strong>{history.summary.path}</strong>
              <button onClick={() => setCompareCurrent(!compareCurrent)}>
                {compareCurrent ? '查看历史修改' : '比较历史之后与当前磁盘'}
              </button>
              <button disabled={busy || !history.restorable} onClick={() => void restore()}>
                恢复这次选定修改
              </button>
              <button onClick={() => setHistory(null)}>关闭比较</button>
            </div>
            <p className="workspace-notice">
              {compareCurrent ? '左：历史之后；右：当前磁盘。' : '左：历史之前；右：历史之后。'}{' '}
              {history.message}
            </p>
            <DiffEditor
              original={compareCurrent ? history.after : history.before}
              modified={compareCurrent ? history.current : history.after}
              language={language(history.summary.path)}
              theme="vs-dark"
              options={{
                readOnly: true,
                renderSideBySide: true,
                automaticLayout: true,
                minimap: { enabled: false }
              }}
            />
          </>
        ) : active ? (
          <>
            <div className="workspace-code-toolbar">
              <span title={active.path}>{active.path}</span>
              <button disabled={busy || active.content === active.base} onClick={() => void save()}>
                保存
              </button>
              <button onClick={() => void reload()}>比较磁盘 / 刷新</button>
              <button disabled={!onReference} onClick={reference}>
                引用选区 / 文件
              </button>
              <button
                onClick={() =>
                  void window.agent
                    .openExternalEditor({ session_id: sessionId, path: active.path })
                    .then((result) => {
                      if (!result.ok && mounted.current) setError(result.error.message)
                    })
                    .catch(() => {
                      if (mounted.current) setError('外部编辑器打开失败。')
                    })
                }
              >
                外部编辑器
              </button>
              <input
                aria-label="跳转行号"
                type="number"
                min="1"
                value={line}
                onChange={(event) => setLine(event.target.value)}
              />
              <button
                onClick={() => {
                  const number = Number(line)
                  if (Number.isInteger(number) && number > 0) {
                    editor.current?.revealLineInCenter(number)
                    editor.current?.setPosition({ lineNumber: number, column: 1 })
                    editor.current?.focus()
                  }
                }}
              >
                跳转
              </button>
            </div>
            {active.missing && (
              <p className="workspace-notice">
                草稿仍保留；当前磁盘文件不可读或不存在。可检查路径并通过新建文件入口恢复。
              </p>
            )}
            <div
              className="workspace-code-toolbar workspace-language-toolbar"
              aria-label="代码理解操作"
            >
              {(
                [
                  'definition',
                  'references',
                  'symbols',
                  'hover',
                  'completion',
                  'diagnostics'
                ] as const
              ).map((action, index) => (
                <button key={action} disabled={!codeContext} onClick={() => void queryCode(action)}>
                  {['定义', '引用', '符号', '说明', '补全', '诊断'][index]}
                </button>
              ))}
              <input
                aria-label="新符号名称"
                placeholder="新符号名称"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
              <button
                disabled={!codeContext || !newName.trim()}
                onClick={() => void queryCode('rename')}
              >
                预览重命名
              </button>
              <small>F12 定义 · Shift+F12 引用 · Ctrl+空格补全 · F2 重命名；诊断不阻断保存</small>
            </div>
            {codeError && (
              <p role="status" className="workspace-notice">
                {codeError}
              </p>
            )}
            {codeResult && codeContext && (
              <div className="workspace-language-panel">
                <button
                  onClick={() => {
                    ++codeGeneration.current
                    setCodeResult(null)
                  }}
                >
                  关闭语言结果
                </button>
                <EditorIntelligenceView
                  result={codeResult}
                  projectRoot={codeContext.projectRoot}
                  onNavigate={(path, row, column) => void open(path, row, column)}
                />
                {codeResult.action === 'rename' && (
                  <>
                    <p>草稿建议只修改缓冲；磁盘建议可明确保存，变化的缓冲与磁盘不会被覆盖。</p>
                    {renameTargets.map((target) => (
                      <div key={target.path}>
                        <label>
                          <input
                            type="checkbox"
                            checked={selectedRenames.includes(target.path)}
                            disabled={!!target.error}
                            onChange={(event) =>
                              setSelectedRenames((old) =>
                                event.target.checked
                                  ? [...old, target.path]
                                  : old.filter((path) => path !== target.path)
                              )
                            }
                          />
                          {target.path} · {target.count} 处 ·{' '}
                          {target.source === 'draft' ? '草稿' : '磁盘快照'}
                        </label>
                        <button
                          onClick={() =>
                            setRenamePreview(renamePreview === target.path ? null : target.path)
                          }
                        >
                          比较建议
                        </button>
                        {target.error && <p role="status">{target.error}</p>}
                        {renamePreview === target.path &&
                          target.base !== null &&
                          target.content !== null && (
                            <div className="workspace-rename-diff">
                              <DiffEditor
                                original={target.base}
                                modified={target.content}
                                language={language(target.path)}
                                theme="vs-dark"
                                options={{
                                  readOnly: true,
                                  automaticLayout: true,
                                  minimap: { enabled: false }
                                }}
                              />
                            </div>
                          )}
                      </div>
                    ))}
                    {!renameTargets.length && <p>没有可应用的项目文件文本建议。</p>}
                    <button
                      disabled={busy || !selectedRenames.length}
                      onClick={() => void applyRenames(false)}
                    >
                      应用选中建议到缓冲
                    </button>
                    <button
                      disabled={
                        busy ||
                        !selectedRenames.length ||
                        renameTargets.some(
                          (target) =>
                            selectedRenames.includes(target.path) && target.source === 'draft'
                        )
                      }
                      onClick={() => void applyRenames(true)}
                    >
                      保存选中的磁盘建议
                    </button>
                  </>
                )}
              </div>
            )}
            {active.disk !== undefined ? (
              <>
                <div className="workspace-code-toolbar">
                  <span>左：当前磁盘；右：未保存缓冲（可编辑）。</span>
                  <button onClick={acceptMerge}>采用此磁盘基线并保留合并内容</button>
                </div>
                <DiffEditor
                  key={`merge:${active.path}`}
                  original={active.disk}
                  modified={active.content}
                  modifiedModelPath={codeModelUri(sessionId, active.path).toString()}
                  originalModelPath={monaco.Uri.from({
                    scheme: 'inmemory',
                    authority: 'baseline',
                    path: `/${sessionId}/${active.path}`
                  }).toString()}
                  language={language(active.path)}
                  theme="vs-dark"
                  options={{
                    renderSideBySide: true,
                    automaticLayout: true,
                    originalEditable: false,
                    minimap: { enabled: false }
                  }}
                  onMount={(instance) => {
                    attachEditor(instance.getModifiedEditor())
                    const listener = instance
                      .getModifiedEditor()
                      .onDidChangeModelContent(() => edit(instance.getModifiedEditor().getValue()))
                    instance.onDidDispose(() => listener.dispose())
                  }}
                />
              </>
            ) : (
              <Editor
                path={codeModelUri(sessionId, active.path).toString()}
                language={language(active.path)}
                value={active.content}
                theme="vs-dark"
                saveViewState
                options={{
                  automaticLayout: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false
                }}
                onMount={(instance) => {
                  attachEditor(instance)
                }}
                onChange={edit}
              />
            )}
            <footer>
              {active.encoding} · {active.newline} ·{' '}
              {active.content !== active.base
                ? '未保存到项目 · 草稿持续保存到应用数据根'
                : '已与保存基线一致'}
            </footer>
          </>
        ) : (
          <p className="workspace-empty">从文件树打开文件，或使用快速打开与内容搜索。</p>
        )}
      </main>
    </section>
  )
}
