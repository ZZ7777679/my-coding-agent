/** 将真实 LSP 结果适配到 Monaco，保存仍通过文件服务。 Adapt actual LSP results to Monaco while file services own saving. */
import * as monaco from 'monaco-editor'
import type { LanguageQuery, LanguageResult } from '../../generated/protocol'

type ObjectValue = Record<string, unknown>
type TextEdit = { range: monaco.IRange; text: string }
export type CodeLocation = { path: string; range: monaco.IRange; label?: string }
export type RenameTarget = {
  path: string
  base: string | null
  content: string | null
  source: 'disk' | 'draft'
  error: string | null
  count: number
}
type Options = {
  editor: monaco.editor.IStandaloneCodeEditor
  sessionId: string
  projectId: string
  projectRoot: string
  onError: (message: string) => void
  onRename: (result: LanguageResult) => void
  onNavigate: (path: string, line: number, column: number) => Promise<void>
}
export type EditorLanguageBinding = monaco.IDisposable & {
  query: (action: LanguageQuery['action'], newName?: string) => Promise<LanguageResult | null>
  diagnostics: () => Promise<void>
}

/** 将不受信的原生资料作为对象校验。 Validate untrusted native data as an object. */
function object(value: unknown): ObjectValue | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as ObjectValue)
    : null
}

/** 校验 LSP 零基位置并转换为 Monaco 一基范围。 Validate zero-based LSP positions and convert to Monaco ranges. */
export function codeRange(value: unknown): monaco.IRange | null {
  const data = object(value)
  const start = object(data?.start)
  const end = object(data?.end)
  if (!start || !end) return null
  const values = [start.line, start.character, end.line, end.character]
  if (!values.every((item) => typeof item === 'number' && Number.isInteger(item) && item >= 0))
    return null
  if (
    typeof start.line !== 'number' ||
    typeof start.character !== 'number' ||
    typeof end.line !== 'number' ||
    typeof end.character !== 'number'
  )
    return null
  return {
    startLineNumber: start.line + 1,
    startColumn: start.character + 1,
    endLineNumber: end.line + 1,
    endColumn: end.character + 1
  }
}

/** 按路径组件将 file URI 限定为项目文件，处理 Windows 驱动器编码。 Resolve file URIs to project-relative paths by components, including Windows drive encoding. */
export function relativeCodePath(uri: string, root: string): string | null {
  try {
    const url = new URL(uri)
    if (url.protocol !== 'file:') return null
    let path = decodeURIComponent(url.pathname).replace(/\\/g, '/')
    if (/^\/[a-z]:\//i.test(path)) path = path.slice(1)
    if (url.hostname) path = `//${url.hostname}/${path.replace(/^\/+/, '')}`
    const project = root.replace(/\\/g, '/').replace(/\/+$/, '')
    const windows = /^[a-z]:\//i.test(project) || project.startsWith('//')
    const components = path.split('/').filter(Boolean)
    const base = project.split('/').filter(Boolean)
    const same = (left: string, right: string): boolean =>
      windows ? left.toLowerCase() === right.toLowerCase() : left === right
    if (
      components.length <= base.length ||
      base.some((part, index) => !same(part, components[index]))
    )
      return null
    const relative = components.slice(base.length)
    if (relative.some((part) => part === '.' || part === '..')) return null
    return relative.join('/')
  } catch {
    return null
  }
}

/** 模型 URI 按组件编码，文件中的 # 和空格不成为 URL 标记。 Encode model URI components so filename hashes and spaces stay literal. */
export function codeModelUri(sessionId: string, path: string): monaco.Uri {
  return monaco.Uri.from({
    scheme: 'inmemory',
    authority: 'workbench',
    path: `/${sessionId}/${path}`
  })
}

/** 当前会话的编辑器模型映射到真实项目相对路径。 Map models owned by this session to real project-relative paths. */
function modelPath(model: monaco.editor.ITextModel, sessionId: string): string | null {
  const prefix = `/${sessionId}/`
  return model.uri.scheme === 'inmemory' &&
    model.uri.authority === 'workbench' &&
    model.uri.path.startsWith(prefix)
    ? model.uri.path.slice(prefix.length)
    : null
}

/** JSX 使用实际服务语言，Monaco 的着色语言仍保持原设置。 Use JSX service languages while retaining Monaco coloring language. */
function serviceLanguage(path: string, model: monaco.editor.ITextModel): string {
  if (path.endsWith('.tsx')) return 'typescriptreact'
  if (path.endsWith('.jsx')) return 'javascriptreact'
  return model.getLanguageId()
}

/** 解析 Location 与 LocationLink，项目外目标仍可在原生详情查看。 Parse Location and LocationLink; native details retain outside-project targets. */
export function codeLocations(value: unknown, root: string): CodeLocation[] {
  const items = Array.isArray(value) ? value : [value]
  return items.flatMap((item) => {
    const data = object(item)
    const uri = data?.uri ?? data?.targetUri
    const range = codeRange(data?.range ?? data?.targetSelectionRange ?? data?.targetRange)
    const path = typeof uri === 'string' ? relativeCodePath(uri, root) : null
    return path && range ? [{ path, range }] : []
  })
}

/** 文档符号可供编辑器大纲和列表导航共用。 Share document symbols between Monaco outlines and list navigation. */
export function codeSymbols(value: unknown): monaco.languages.DocumentSymbol[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const data = object(item)
    const range = codeRange(data?.range ?? object(data?.location)?.range)
    if (!data || typeof data.name !== 'string' || !range) return []
    const selectionRange = codeRange(data.selectionRange) ?? range
    const kind =
      typeof data.kind === 'number' && data.kind >= 1 && data.kind <= 26
        ? data.kind - 1
        : monaco.languages.SymbolKind.Variable
    return [
      {
        name: data.name,
        detail: typeof data.detail === 'string' ? data.detail : '',
        kind,
        tags: [],
        range,
        selectionRange,
        children: codeSymbols(data.children)
      }
    ]
  })
}

/** Markdown 文案不启用 HTML、图片或受信命令链接。 Format Markdown without images, trusted command links or HTML. */
function markdown(value: unknown): monaco.IMarkdownString[] {
  if (Array.isArray(value)) return value.flatMap(markdown)
  if (typeof value === 'string')
    return [{ value: value.replace(/!\[/g, '['), isTrusted: false, supportHtml: false }]
  const data = object(value)
  if (typeof data?.value !== 'string') return []
  const text =
    typeof data.language === 'string' ? `\`\`\`${data.language}\n${data.value}\n\`\`\`` : data.value
  return [{ value: text.replace(/!\[/g, '['), isTrusted: false, supportHtml: false }]
}

/** 解析两种 WorkspaceEdit 文本编辑格式并使用捕获的基线。 Parse both WorkspaceEdit text formats against captured baselines. */
export function codeRenameTargets(result: LanguageResult, root: string): RenameTarget[] {
  const data = object(result.result)
  if (!data) return []
  const grouped = new Map<string, unknown[]>()
  /** 合并同一文件的编辑，避免重复保存。 Merge edits for one file to avoid duplicate saves. */
  const add = (uri: unknown, edits: unknown): void => {
    if (typeof uri !== 'string' || !Array.isArray(edits)) return
    const path = relativeCodePath(uri, root)
    if (path) grouped.set(path, [...(grouped.get(path) ?? []), ...edits])
  }
  const changes = object(data.changes)
  if (changes) for (const [uri, edits] of Object.entries(changes)) add(uri, edits)
  if (Array.isArray(data.documentChanges))
    for (const item of data.documentChanges) {
      const change = object(item)
      add(object(change?.textDocument)?.uri, change?.edits)
    }
  return [...grouped].map(([path, edits]) => {
    const snapshot = (result.rename_documents ?? []).find(
      (item) => item.path.replace(/\\/g, '/').toLowerCase() === path.toLowerCase()
    )
    const target: RenameTarget = {
      path,
      base: snapshot?.content ?? null,
      content: null,
      source: snapshot?.source ?? 'disk',
      error: snapshot?.error ?? null,
      count: edits.length
    }
    if (target.base === null)
      return { ...target, error: target.error ?? '未捕获该文件基线，无法应用。' }
    try {
      const parsed = edits.map((item) => {
        const edit = object(item)
        const range = codeRange(edit?.range)
        if (!range || typeof edit?.newText !== 'string')
          throw new Error('语言服务返回了无法解析的文本编辑。')
        return { range, text: edit.newText }
      })
      return { ...target, content: applyCodeEdits(target.base, parsed) }
    } catch (error) {
      return { ...target, error: error instanceof Error ? error.message : '无法应用编辑建议。' }
    }
  })
}

/** JavaScript 字符索引本身使用 UTF-16，计算原始换行上的准确偏移。 JavaScript indices use UTF-16; calculate exact offsets over original line endings. */
function applyCodeEdits(content: string, edits: TextEdit[]): string {
  const starts = [0]
  const newlines = /\r\n|\r|\n/g
  let match: RegExpExecArray | null
  while ((match = newlines.exec(content))) starts.push(match.index + match[0].length)
  /** 转换范围位置并拒绝超出快照的编辑。 Convert range positions and reject edits outside the snapshot. */
  const offset = (line: number, column: number): number => {
    const start = starts[line - 1]
    if (start === undefined) throw new Error('重命名范围超出捕获正文。')
    const end = starts[line] ?? content.length
    const lineText = content.slice(start, end).replace(/\r\n$|\r$|\n$/, '')
    if (column < 1 || column - 1 > lineText.length) throw new Error('重命名列位置超出捕获正文。')
    return start + column - 1
  }
  const spans = edits
    .map((edit) => ({
      start: offset(edit.range.startLineNumber, edit.range.startColumn),
      end: offset(edit.range.endLineNumber, edit.range.endColumn),
      text: edit.text
    }))
    .sort((left, right) => right.start - left.start)
  let previous = content.length
  let output = content
  for (const edit of spans) {
    if (edit.start > edit.end || edit.end > previous)
      throw new Error('重命名编辑范围重叠，未应用该文件。')
    output = output.slice(0, edit.start) + edit.text + output.slice(edit.end)
    previous = edit.start
  }
  return output
}

/** 只有编辑器发起实际查询才访问后端服务，卸载时移除所有提供器。 Query backend services only for actual editor requests and dispose every provider on unmount. */
export function bindEditorIntelligence(options: Options): EditorLanguageBinding {
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const subscriptions: monaco.IDisposable[] = []
  const owner = `project-lsp:${options.sessionId}`
  /** 捕获当前模型正文和版本，迟到结果不改写已变化的缓冲。 Capture model text and version without applying stale responses. */
  const queryModel = async (
    model: monaco.editor.ITextModel,
    action: LanguageQuery['action'],
    position: monaco.Position,
    token?: monaco.CancellationToken,
    newName?: string
  ): Promise<LanguageResult | null> => {
    const path = modelPath(model, options.sessionId)
    if (!path || disposed || token?.isCancellationRequested) return null
    const version = model.getVersionId()
    const content = model.getValue()
    let result
    try {
      result = await window.agent.queryLanguage({
        project_id: options.projectId,
        path,
        language: serviceLanguage(path, model),
        action,
        line: position.lineNumber - 1,
        character: position.column - 1,
        content,
        version,
        new_name: newName ?? null
      })
    } catch {
      if (!disposed && !token?.isCancellationRequested && options.editor.getModel() === model)
        options.onError('语言服务连接中断，文件保存仍可使用。')
      return null
    }
    if (
      disposed ||
      token?.isCancellationRequested ||
      model.isDisposed() ||
      version !== model.getVersionId()
    )
      return null
    if (!result.ok) {
      if (options.editor.getModel() === model)
        options.onError(`${result.error.code} · ${result.error.message}`)
      return null
    }
    if (options.editor.getModel() === model) options.onError('')
    return result.data
  }
  const selectors = ['python', 'typescript', 'javascript']
  for (const selector of selectors) {
    subscriptions.push(
      monaco.languages.registerDefinitionProvider(selector, {
        provideDefinition: async (model, position, token) => {
          const result = await queryModel(model, 'definition', position, token)
          return result
            ? codeLocations(result.result, options.projectRoot).map((item) => ({
                uri: codeModelUri(options.sessionId, item.path),
                range: item.range
              }))
            : null
        }
      })
    )
    subscriptions.push(
      monaco.languages.registerReferenceProvider(selector, {
        provideReferences: async (model, position, _context, token) => {
          const result = await queryModel(model, 'references', position, token)
          return result
            ? codeLocations(result.result, options.projectRoot).map((item) => ({
                uri: codeModelUri(options.sessionId, item.path),
                range: item.range
              }))
            : null
        }
      })
    )
    subscriptions.push(
      monaco.languages.registerHoverProvider(selector, {
        provideHover: async (model, position, token) => {
          const result = await queryModel(model, 'hover', position, token)
          const data = object(result?.result)
          if (!data) return null
          return { contents: markdown(data.contents), range: codeRange(data.range) ?? undefined }
        }
      })
    )
    subscriptions.push(
      monaco.languages.registerDocumentSymbolProvider(selector, {
        provideDocumentSymbols: async (model, token) => {
          const result = await queryModel(model, 'symbols', new monaco.Position(1, 1), token)
          return result ? codeSymbols(result.result) : []
        }
      })
    )
    subscriptions.push(
      monaco.languages.registerCompletionItemProvider(selector, {
        triggerCharacters: ['.', ':'],
        provideCompletionItems: async (model, position, _context, token) => {
          const result = await queryModel(model, 'completion', position, token)
          const data = object(result?.result)
          const items = Array.isArray(result?.result)
            ? result.result
            : Array.isArray(data?.items)
              ? data.items
              : []
          const word = model.getWordUntilPosition(position)
          const fallback = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn
          }
          const suggestions: monaco.languages.CompletionItem[] = items.flatMap((item) => {
            const entry = object(item)
            if (typeof entry?.label !== 'string') return []
            const edit = object(entry.textEdit)
            const range = codeRange(edit?.range ?? edit?.replace) ?? fallback
            const kinds: Record<number, monaco.languages.CompletionItemKind> = {
              2: monaco.languages.CompletionItemKind.Method,
              3: monaco.languages.CompletionItemKind.Function,
              5: monaco.languages.CompletionItemKind.Field,
              6: monaco.languages.CompletionItemKind.Variable,
              7: monaco.languages.CompletionItemKind.Class,
              9: monaco.languages.CompletionItemKind.Module,
              10: monaco.languages.CompletionItemKind.Property,
              14: monaco.languages.CompletionItemKind.Keyword,
              15: monaco.languages.CompletionItemKind.Snippet
            }
            const additional = Array.isArray(entry.additionalTextEdits)
              ? entry.additionalTextEdits.flatMap((value) => {
                  const other = object(value)
                  const otherRange = codeRange(other?.range)
                  return otherRange && typeof other?.newText === 'string'
                    ? [{ range: otherRange, text: other.newText }]
                    : []
                })
              : []
            return [
              {
                label: entry.label,
                kind:
                  typeof entry.kind === 'number'
                    ? (kinds[entry.kind] ?? monaco.languages.CompletionItemKind.Text)
                    : monaco.languages.CompletionItemKind.Text,
                insertText:
                  typeof edit?.newText === 'string'
                    ? edit.newText
                    : typeof entry.insertText === 'string'
                      ? entry.insertText
                      : entry.label,
                insertTextRules:
                  entry.insertTextFormat === 2
                    ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
                    : undefined,
                range,
                additionalTextEdits: additional,
                detail: typeof entry.detail === 'string' ? entry.detail : undefined,
                documentation: markdown(entry.documentation)[0],
                sortText: typeof entry.sortText === 'string' ? entry.sortText : undefined,
                filterText: typeof entry.filterText === 'string' ? entry.filterText : undefined
              }
            ]
          })
          return { suggestions, incomplete: data?.isIncomplete === true }
        }
      })
    )
    subscriptions.push(
      monaco.languages.registerRenameProvider(selector, {
        provideRenameEdits: async (model, position, newName, token) => {
          const result = await queryModel(model, 'rename', position, token, newName)
          if (result) options.onRename(result)
          return { edits: [] }
        }
      })
    )
  }
  subscriptions.push(
    monaco.editor.registerEditorOpener({
      openCodeEditor: async (_source, uri, selection) => {
        if (
          uri.scheme !== 'inmemory' ||
          uri.authority !== 'workbench' ||
          !uri.path.startsWith(`/${options.sessionId}/`)
        )
          return false
        const line =
          selection && 'startLineNumber' in selection
            ? selection.startLineNumber
            : (selection?.lineNumber ?? 1)
        const column =
          selection && 'startColumn' in selection ? selection.startColumn : (selection?.column ?? 1)
        await options.onNavigate(uri.path.slice(options.sessionId.length + 2), line, column)
        return true
      }
    })
  )

  /** 诊断标记只反映本次缓冲，缺失服务不阻止文件保存。 Mark diagnostics for this buffer without gating file saving. */
  const markDiagnostics = (model: monaco.editor.ITextModel, result: LanguageResult): void => {
    if (model.isDisposed() || options.editor.getModel() !== model) return
    const data = object(result.result)
    const items = Array.isArray(result.result)
      ? result.result
      : Array.isArray(data?.items)
        ? data.items
        : []
    const markers: monaco.editor.IMarkerData[] = items.flatMap((item) => {
      const entry = object(item)
      const range = codeRange(entry?.range)
      if (!range || typeof entry?.message !== 'string') return []
      const severity =
        entry.severity === 1
          ? monaco.MarkerSeverity.Error
          : entry.severity === 2
            ? monaco.MarkerSeverity.Warning
            : entry.severity === 4
              ? monaco.MarkerSeverity.Hint
              : monaco.MarkerSeverity.Info
      return [
        {
          ...range,
          severity,
          message: entry.message,
          source: typeof entry.source === 'string' ? entry.source : result.server_id,
          code:
            typeof entry.code === 'number' || typeof entry.code === 'string'
              ? String(entry.code)
              : undefined
        }
      ]
    })
    monaco.editor.setModelMarkers(model, owner, markers)
  }
  /** 自动诊断使用同一结果投影，不增加保存前置检查。 Project automatic diagnostics without adding save prerequisites. */
  const diagnostics = async (): Promise<void> => {
    const model = options.editor.getModel()
    if (!model || !selectors.includes(model.getLanguageId())) return
    const result = await queryModel(model, 'diagnostics', new monaco.Position(1, 1))
    if (result) markDiagnostics(model, result)
  }
  /** 编辑变化后等待输入停止再查询，不为每个字符启动请求。 Debounce editor changes instead of querying on every character. */
  const schedule = (): void => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      void diagnostics().catch(() => options.onError('语言服务连接中断，文件保存仍可使用。'))
    }, 650)
  }
  subscriptions.push(options.editor.onDidChangeModelContent(schedule))
  subscriptions.push(options.editor.onDidChangeModel(schedule))
  return {
    query: async (action, newName) => {
      const model = options.editor.getModel()
      const result = model
        ? await queryModel(
            model,
            action,
            options.editor.getPosition() ?? new monaco.Position(1, 1),
            undefined,
            newName
          )
        : null
      if (model && result && action === 'diagnostics') markDiagnostics(model, result)
      return result
    },
    diagnostics,
    dispose: () => {
      disposed = true
      if (timer) clearTimeout(timer)
      for (const subscription of subscriptions) subscription.dispose()
      for (const model of monaco.editor.getModels())
        if (modelPath(model, options.sessionId)) monaco.editor.setModelMarkers(model, owner, [])
    }
  }
}
