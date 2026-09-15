/**
 * 集中测试资源与产物位置，依赖从桌面锁定包解析。
 * Centralize test resources and output locations, resolving dependencies from the locked desktop package.
 */

import { createRequire } from 'node:module'
import path from 'node:path'

export const root = path.resolve(import.meta.dirname, '../..')
export const artifacts = path.join(root, '.artifacts/tests')
export const requireDesktop = createRequire(path.join(root, 'apps/desktop/package.json'))
