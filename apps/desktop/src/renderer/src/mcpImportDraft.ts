import type { McpServer, McpConnectionValues } from '../../generated/protocol'

/** 仅用于导入预览的草稿；凭据不进入公开服务配置。 Import draft keeping credentials out of public config. */
export interface McpImportEntry {
  server: McpServer
  credential: string
  connectionValues: McpConnectionValues
  selected: boolean
  saved: boolean
  parsed: boolean
  error: string
}

/** 检查粘贴内容的对象形态。 Narrow pasted objects without coercing their fields. */
function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** 验证地址但保留原始路径和查询参数。 Validate a URL without rewriting its path or query. */
export function mcpImportUrl(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error('请填写远程服务 URL。')
  try {
    const url = new URL(value.trim())
    if (url.protocol === 'http:' || url.protocol === 'https:') return value.trim()
  } catch {
    // 不复述可能包含凭据的原始输入。 Do not echo potentially secret input in errors.
  }
  throw new Error('服务地址需要完整的 http:// 或 https:// URL。')
}

/** 将通用服务配置转换为保存协议，不建立另一套连接逻辑。 Adapt common configs to the existing save protocol. */
function importEntry(name: string, value: unknown): McpImportEntry {
  const server: McpServer = {
    server_id: crypto.randomUUID(),
    name,
    transport: 'http',
    all_projects: false,
    headers: {},
    header_refs: {},
    env_refs: {},
    auth: { source: 'none' }
  }
  let credential = ''
  const connectionValues: McpConnectionValues = { env: {}, headers: {} }
  try {
    if (!isObject(value)) throw new Error('服务配置必须是 JSON 对象。')
    const type = value.type ?? value.transport ?? (value.command !== undefined ? 'stdio' : 'http')
    if (typeof type !== 'string') throw new Error('连接类型必须是文本。')
    if (['http', 'streamableHttp', 'streamable-http', 'streamable_http'].includes(type))
      server.transport = 'http'
    else if (type === 'stdio' || type === 'sse') server.transport = type
    else throw new Error('暂不支持此连接类型；支持 stdio、Streamable HTTP 和 SSE。')
    const supported = new Set([
      'url',
      'type',
      'transport',
      'headers',
      'name',
      'description',
      'command',
      'args',
      'env',
      'cwd',
      'disabled',
      'timeout'
    ])
    if (Object.keys(value).some((key) => !supported.has(key))) {
      throw new Error('包含尚未支持的配置字段；请使用“新增服务”配置平台扩展，避免静默遗漏。')
    }
    if (value.name !== undefined && typeof value.name !== 'string')
      throw new Error('名称需要是文本。')
    if (value.description !== undefined && typeof value.description !== 'string')
      throw new Error('说明需要是文本。')
    server.name = typeof value.name === 'string' ? value.name : name
    server.description = typeof value.description === 'string' ? value.description : ''
    if (value.disabled !== undefined && typeof value.disabled !== 'boolean')
      throw new Error('disabled 必须为布尔值。')
    server.enabled = value.disabled !== true
    if (value.timeout !== undefined) {
      if (typeof value.timeout !== 'number' || value.timeout <= 0)
        throw new Error('timeout 需要为正数（毫秒）。')
      server.timeout_seconds = value.timeout / 1000
    }
    if (server.transport === 'stdio') {
      if (typeof value.command !== 'string' || !value.command.trim())
        throw new Error('本地服务需要 command 程序名或路径。')
      if (value.url !== undefined || value.headers !== undefined)
        throw new Error('stdio 使用 command／args／env；请移除远程 URL／headers 或选择远程类型。')
      server.command = value.command
      const args = value.args ?? []
      if (!Array.isArray(args) || !args.every((arg): arg is string => typeof arg === 'string'))
        throw new Error('args 必须是文本数组，每一项对应一个参数。')
      server.arguments = args
      if (value.cwd !== undefined && typeof value.cwd !== 'string')
        throw new Error('cwd 需要是文本路径。')
      server.cwd = typeof value.cwd === 'string' ? value.cwd : ''
      if (value.env !== undefined && !isObject(value.env))
        throw new Error('env 必须是名称与文本值组成的对象。')
      for (const [key, raw] of Object.entries(value.env ?? {})) {
        if (typeof raw !== 'string') throw new Error('env 的值必须是文本。')
        const ref = raw.match(/^\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}$/)
        if (ref) server.env_refs![key] = ref[1]
        else if (raw.includes('${'))
          throw new Error('环境变量仅支持完整的 ${NAME} 或 ${env:NAME} 引用。')
        else connectionValues.env![key] = raw
      }
    } else {
      if (['command', 'args', 'env', 'cwd'].some((key) => value[key] !== undefined))
        throw new Error('远程服务使用 URL／headers；本地启动配置请选择 stdio。')
      server.url = mcpImportUrl(value.url)
    }
    if (value.headers !== undefined && !isObject(value.headers))
      throw new Error('headers 必须是名称与文本值组成的对象。')
    const seen = new Set<string>()
    for (const [header, raw] of Object.entries(value.headers ?? {})) {
      if (typeof raw !== 'string') throw new Error('HTTP 请求头的值必须是文本。')
      const lower = header.toLowerCase()
      if (seen.has(lower)) throw new Error('HTTP 请求头存在大小写重复，请保留一项。')
      seen.add(lower)
      const ref = raw.match(/^\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}$/)
      if (ref) {
        server.header_refs![header] = ref[1]
        continue
      }
      if (lower === 'authorization') {
        const parts = lower === 'authorization' ? raw.trim().match(/^(\S+)\s+(.+)$/) : null
        const prefix = parts ? parts[1] : ''
        const token = parts ? parts[2] : raw
        const env = token.match(/^\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}$/)
        if (!env && token.includes('${'))
          throw new Error('认证头仅支持完整环境变量引用，或 Authorization 中的“Bearer ${变量名}”。')
        server.auth = env
          ? { source: 'environment', header, prefix, env_var: env[1] }
          : { source: 'saved', header, prefix }
        credential = env ? '' : token
      } else {
        if (raw.includes('${'))
          throw new Error('请求头仅支持完整环境变量引用，或 Authorization 中的“Bearer ${变量名}”。')
        connectionValues.headers![header] = raw
      }
    }
    server.stored_env = Object.keys(connectionValues.env ?? {})
    server.stored_headers = Object.keys(connectionValues.headers ?? {})
    return {
      server,
      credential,
      connectionValues,
      selected: true,
      saved: false,
      parsed: true,
      error: ''
    }
  } catch (error) {
    return {
      server,
      credential: '',
      connectionValues: {},
      selected: false,
      saved: false,
      parsed: false,
      error: error instanceof Error ? error.message : '无法识别此服务配置。'
    }
  }
}

/** 接受 URL、单服务对象或 mcpServers；只解析，不保存或访问网络。 Parse URL or JSON without storage or network access. */
export function parseMcpImport(text: string): McpImportEntry[] {
  const input = text.trim()
  if (/^https?:\/\//i.test(input)) {
    const url = mcpImportUrl(input)
    return [importEntry(new URL(url).hostname, { url })]
  }
  let value: unknown
  try {
    value = JSON.parse(input)
  } catch {
    throw new Error('请输入完整服务 URL，或有效 JSON（支持 mcpServers 配置）。')
  }
  if (!isObject(value)) throw new Error('JSON 需要是服务对象或包含 mcpServers 的对象。')
  const container = 'mcpServers' in value ? 'mcpServers' : 'servers' in value ? 'servers' : null
  if (container) {
    const servers = value[container]
    if (!isObject(servers) || !Object.keys(servers).length)
      throw new Error('配置中没有可导入的服务。')
    if (Object.keys(value).some((key) => key !== container))
      throw new Error('请只粘贴 mcpServers／servers 部分；应用的其他配置不会导入。')
    return Object.entries(servers).map(([name, config]) => importEntry(name, config))
  }
  return [importEntry('MCP 服务', value)]
}
