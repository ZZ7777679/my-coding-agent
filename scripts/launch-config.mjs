/**
 * 开发入口共用的本机路径解析和原子保存，不处理项目业务记录。
 * Shared dev-launch path resolution and atomic saving, independent of project business records.
 */

import {
  closeSync,
  fstatSync,
  openSync,
  readSync,
  fsyncSync,
  writeFileSync,
  renameSync,
  unlinkSync
} from 'node:fs'
import { randomUUID } from 'node:crypto'
import path from 'node:path'

const localFile = 'agent.paths.local.json'
const maxBytes = 16 * 1024

/**
 * 仅携带可公开的启动错误，不暴露配置原文。
 * Carry public launch errors without exposing raw configuration content.
 */
export class LaunchConfigError extends Error {}

/**
 * 区分完整绝对路径与依赖当前盘符的 Windows 路径。
 * Distinguish fully absolute paths from Windows paths tied to the current drive.
 */
function isFullyAbsolute(value) {
  // Windows 的根相对路径仍依赖当前盘符，不能仅依赖 node:path 的 absolute 判断。
  // Windows root-relative paths depend on the current drive despite node:path calling them absolute.
  return (
    path.isAbsolute(value) && (process.platform !== 'win32' || path.parse(value).root.length > 1)
  )
}

/**
 * 有界读取本机 JSON；相对路径以文件所在目录解析，坏文件保持原样。
 * Read bounded local JSON; resolve relative paths from its directory and preserve bad files.
 */
export function readLocalPaths(root) {
  let descriptor
  try {
    descriptor = openSync(path.join(root, localFile), 'r')
  } catch (cause) {
    if (cause.code === 'ENOENT') return {}
    throw new LaunchConfigError(`Cannot read ${localFile}; check file permissions.`)
  }
  let content
  try {
    const stat = fstatSync(descriptor)
    if (!stat.isFile() || stat.size > maxBytes) throw new Error('Invalid file')
    const buffer = Buffer.alloc(maxBytes + 1)
    let count = 0
    while (count < buffer.length) {
      const size = readSync(descriptor, buffer, count, buffer.length - count, null)
      if (size === 0) break
      count += size
    }
    if (count > maxBytes) throw new Error('Oversized file')
    content = JSON.parse(
      new TextDecoder('utf-8', { fatal: true }).decode(buffer.subarray(0, count))
    )
  } catch {
    // JSON 解析错误可能包含配置原文，改为固定公开说明。
    // JSON parse errors may contain raw input; replace them with a fixed public message.
    throw new LaunchConfigError(`${localFile} must be a UTF-8 JSON file of at most 16 KiB.`)
  } finally {
    closeSync(descriptor)
  }
  if (
    content === null ||
    typeof content !== 'object' ||
    Array.isArray(content) ||
    Object.keys(content).some((key) => !['data_dir', 'project_dir'].includes(key))
  ) {
    throw new LaunchConfigError(`${localFile} supports only data_dir and project_dir.`)
  }
  const result = {}
  for (const [key, value] of Object.entries(content)) {
    if (
      typeof value !== 'string' ||
      !value.trim() ||
      value.includes('\0') ||
      (!isFullyAbsolute(value) && path.parse(value).root !== '')
    ) {
      throw new LaunchConfigError(`${localFile}: ${key} must be a nonempty, unambiguous path.`)
    }
    // 相对值以本机文件目录为基准，不随终端 cwd 变化。
    // Relative values follow the local file's directory, never the shell's cwd.
    result[key] = path.resolve(root, value)
  }
  return result
}

/**
 * 校验并原子保存目录；只写本机文件，不创建或搬迁业务数据。
 * Validate and atomically save paths without creating or moving application data.
 */
export function saveLocalPaths(root, paths) {
  // 先检查旧文件；损坏内容需要保留供用户修复。
  // Check the old file first and preserve malformed content for user repair.
  readLocalPaths(root)
  const value = {
    data_dir: absolutePath(paths.data_dir, 'data_dir'),
    project_dir: absolutePath(paths.project_dir, 'project_dir')
  }
  const target = path.join(root, localFile)
  const temporary = path.join(root, `.${localFile}-${randomUUID()}.tmp`)
  let descriptor
  try {
    descriptor = openSync(temporary, 'wx')
    writeFileSync(descriptor, JSON.stringify(value, null, 2) + '\n', 'utf8')
    fsyncSync(descriptor)
    closeSync(descriptor)
    descriptor = undefined
    renameSync(temporary, target)
  } catch {
    throw new LaunchConfigError('Cannot save startup paths; the existing file was preserved.')
  } finally {
    if (descriptor !== undefined) closeSync(descriptor)
    try {
      unlinkSync(temporary)
    } catch (cause) {
      if (cause.code !== 'ENOENT') console.error('STARTUP_PATH_TEMP_CLEANUP_FAILED')
    }
  }
}

/**
 * 校验显式输入必须完整绝对，然后按平台规范化路径。
 * Require fully absolute explicit input, then normalize the path for the platform.
 */
function absolutePath(value, name) {
  if (
    typeof value !== 'string' ||
    !value.trim() ||
    value.includes('\0') ||
    !isFullyAbsolute(value)
  ) {
    throw new LaunchConfigError(`${name} must be a complete absolute path.`)
  }
  return path.normalize(value)
}

/**
 * 按 CLI、环境、本机文件和集中默认值解析启动路径，失效输入不降级。
 * Resolve CLI, environment, local file and defaults in order, without masking invalid input.
 */
export function resolveLaunchPaths(root, defaults, args, env = process.env) {
  if (args.length && (args.length !== 2 || args[0] !== '--data-dir')) {
    throw new LaunchConfigError('Usage: npm run dev -- [--data-dir ABSOLUTE_PATH]')
  }
  const local = readLocalPaths(root)
  return {
    dataDir: absolutePath(
      args[1] ??
        env[defaults.data_dir_env] ??
        local.data_dir ??
        path.join(defaults.data_dir, 'dev'),
      '--data-dir / MY_AGENT_DATA_DIR'
    ),
    projectDir: absolutePath(
      env[defaults.project_dir_env] ?? local.project_dir ?? defaults.development_project_dir,
      'MY_AGENT_PROJECT_DIR'
    )
  }
}
