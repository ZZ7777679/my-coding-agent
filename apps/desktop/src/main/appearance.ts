import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync
} from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import type { AppearanceSettings } from '../generated/protocol'
import { defaultAppearance } from '../shared/themes'
import { validate } from '../shared/validation'
import { BackendError } from './backend'

/** 外观仅归 Electron 数据目录；损坏时保留原文件并报告。 Read without silently resetting corrupt preferences. */
export function readAppearance(dataDir: string): AppearanceSettings {
  const file = path.join(dataDir, 'electron', 'appearance.json')
  if (!existsSync(file)) return defaultAppearance
  try {
    return validate('AppearanceSettings', JSON.parse(readFileSync(file, 'utf8')))
  } catch {
    throw new BackendError({
      code: 'APPEARANCE_READ_FAILED',
      message: '外观设置无法读取，原文件已保留。',
      remediation: '本次先使用默认外观；可在设置中重新保存。'
    })
  }
}

/** 同目录临时写入并同步后原子替换，失败不假称保存。 Persist validated appearance atomically. */
export function saveAppearance(dataDir: string, input: unknown): AppearanceSettings {
  const value = validate('AppearanceSettings', input)
  const directory = path.join(dataDir, 'electron')
  const temporary = path.join(directory, `.appearance-${randomUUID()}.tmp`)
  try {
    mkdirSync(directory, { recursive: true })
    const fd = openSync(temporary, 'wx')
    try {
      writeFileSync(fd, JSON.stringify(value, null, 2) + '\n', 'utf8')
      fsyncSync(fd)
    } finally {
      closeSync(fd)
    }
    renameSync(temporary, path.join(directory, 'appearance.json'))
    return value
  } catch {
    throw new BackendError({
      code: 'APPEARANCE_SAVE_FAILED',
      message: '外观设置未保存。',
      remediation: '请检查应用数据目录是否可写，原设置保持不变。'
    })
  } finally {
    if (existsSync(temporary)) {
      try {
        unlinkSync(temporary)
      } catch {
        /* 临时文件不影响原偏好，保留供诊断。 Preserve cleanup residue for diagnosis. */
      }
    }
  }
}
