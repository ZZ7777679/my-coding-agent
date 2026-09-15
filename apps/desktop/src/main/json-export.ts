/**
 * 通过原生保存对话框导出公开数据，保护应用文件并原子写入。
 * Export public data through a native dialog, protecting app files with atomic writes.
 */

import { dialog, type BrowserWindow } from 'electron'
import { existsSync, realpathSync } from 'node:fs'
import { open, rename, unlink } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import type { ExportParams, ExportResult } from '../generated/protocol'
import { BackendError } from './backend'

/**
 * 由主进程提供可信内容和受保护路径；取消返回 null，失败保留原文件。
 * Use main-supplied content and protected paths; cancellation returns null and failure preserves files.
 */
export async function exportJson(
  window: BrowserWindow,
  kind: ExportParams['kind'],
  value: object,
  dataDir: string,
  protectedPaths: string[]
): Promise<ExportResult> {
  const selection = await dialog.showSaveDialog(window, {
    title: '导出 JSON',
    defaultPath: path.join(dataDir, `my-agent-${kind}.json`),
    filters: [{ name: 'JSON', extensions: ['json'] }]
  })
  if (selection.canceled || !selection.filePath) return { path: null }
  let temporary: string | undefined
  try {
    const target = selection.filePath
    /**
     * 将现有文件或其父目录解析为真实位置，识别路径别名。
     * Resolve the file or its parent to a real location to detect aliases.
     */
    const canonical = (file: string): string =>
      existsSync(file)
        ? realpathSync.native(file)
        : path.join(realpathSync.native(path.dirname(file)), path.basename(file))
    /**
     * 按当前平台处理路径大小写，供受保护目标比较使用。
     * Normalize path case for protected-target comparisons on the current platform.
     */
    const normalized = (file: string): string =>
      process.platform === 'win32' ? file.toLowerCase() : file
    const actual = normalized(canonical(target))
    if (
      path.extname(target).toLowerCase() !== '.json' ||
      protectedPaths.some((file) => normalized(canonical(file)) === actual)
    ) {
      throw new Error('Protected export target')
    }
    const content = JSON.stringify(value, null, 2) + '\n'
    if (Buffer.byteLength(content, 'utf8') > 1024 * 1024) throw new Error('Export too large')
    temporary = path.join(path.dirname(target), `.my-agent-export-${randomUUID()}.tmp`)
    const file = await open(temporary, 'wx')
    try {
      await file.writeFile(content, 'utf8')
      await file.sync()
    } finally {
      await file.close()
    }
    await rename(temporary, target)
    temporary = undefined
    return { path: target }
  } catch {
    throw new BackendError({
      code: 'EXPORT_FAILED',
      message: 'JSON 导出失败。',
      remediation: '请选择可写的 JSON 文件位置，不要覆盖应用配置或项目记录。'
    })
  } finally {
    if (temporary) {
      try {
        await unlink(temporary)
      } catch {
        console.error('EXPORT_TEMP_CLEANUP_FAILED')
      }
    }
  }
}
