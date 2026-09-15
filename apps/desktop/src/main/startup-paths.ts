/**
 * 受信的开发启动目录设置；业务配置和项目记录仍由 Python 管理。
 * Trusted development path settings; Python still owns business config and project records.
 */

import { app } from 'electron'
import { existsSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'
import defaults from '../../../../src/my_agent/defaults.json'
import { readLocalPaths, saveLocalPaths } from '../../../../scripts/launch-config.mjs'
import type { StartupPaths, StartupPathsParams } from '../generated/protocol'
import { BackendError } from './backend'

/**
 * 从 Electron 应用入口定位仓库，不依赖终端当前目录。
 * Locate the repository from the Electron app entry, independent of the shell directory.
 */
export function workspaceRoot(): string {
  return path.resolve(app.getAppPath(), '../..')
}

/**
 * 读取下次启动的文件配置，并单独返回本次实际数据根。
 * Read saved next-launch paths and separately return the current effective data root.
 */
export function startupPaths(currentDataDir: string): StartupPaths {
  try {
    const root = workspaceRoot()
    const local = readLocalPaths(root)
    return {
      config_path: path.join(root, 'agent.paths.local.json'),
      current_data_dir: currentDataDir,
      data_dir: local.data_dir ?? path.join(defaults.data_dir, 'dev'),
      project_dir: local.project_dir ?? defaults.development_project_dir
    }
  } catch {
    throw new BackendError({
      code: 'STARTUP_CONFIG_INVALID',
      message: '无法读取启动目录配置。',
      remediation: '请检查仓库根目录 agent.paths.local.json；原文件已保留。'
    })
  }
}

/**
 * 解析真实目录及 junction；允许新数据目录使用已存在父级的规范路径。
 * Resolve directories and junctions, using an existing parent for a new data directory.
 */
export function canonicalDirectory(value: string, mustExist: boolean): string {
  if (
    !value.trim() ||
    value.includes('\0') ||
    !path.isAbsolute(value) ||
    (process.platform === 'win32' && path.parse(value).root.length <= 1)
  )
    throw new Error('A complete absolute path is required')
  const resolved = path.resolve(value)
  if (!existsSync(path.parse(resolved).root)) throw new Error('Drive unavailable')
  if (existsSync(resolved)) {
    if (!statSync(resolved).isDirectory()) throw new Error('Not a directory')
    return realpathSync.native(resolved)
  }
  if (mustExist) throw new Error('Directory unavailable')
  const parent = canonicalDirectory(path.dirname(resolved), false)
  return path.join(parent, path.basename(resolved))
}

/**
 * 验证目录边界后原子保存开发配置；不迁移数据或切换当前运行根。
 * Validate path boundaries and atomically save dev settings without moving active data.
 */
export function saveStartupPaths(params: StartupPathsParams, currentDataDir: string): StartupPaths {
  if (app.isPackaged) throw new Error('Packaged startup settings are not available in M0')
  try {
    const dataDir = canonicalDirectory(params.data_dir, false)
    const projectDir = canonicalDirectory(params.project_dir, true)
    /**
     * 按路径组件判断包含关系，避免相同字符串前缀造成误判。
     * Check containment by path components rather than shared string prefixes.
     */
    const inside = (parent: string, child: string): boolean => {
      const relative = path.relative(parent, child)
      return (
        relative === '' ||
        (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative))
      )
    }
    if (inside(dataDir, projectDir) || inside(projectDir, dataDir)) {
      throw new Error('Project and data directories overlap')
    }
    saveLocalPaths(workspaceRoot(), { data_dir: dataDir, project_dir: projectDir })
    return startupPaths(currentDataDir)
  } catch {
    throw new BackendError({
      code: 'STARTUP_PATHS_INVALID',
      message: '启动目录保存失败，原配置已保留。',
      remediation:
        '请使用可访问磁盘上的完整路径；项目目录须已存在，且与数据目录不能相同或互相包含。'
    })
  }
}
