/**
 * 集中桌面验收配置；单 worker 避免窗口互扰，每次输出进入独立产物目录。
 * Central desktop test config; one worker avoids window conflicts and each run gets its own output.
 */

import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

export default defineConfig({
  testDir: '../../tests/desktop',
  outputDir: path.join('../../.artifacts/tests/desktop-results', randomUUID()),
  workers: 1,
  timeout: 45000,
  expect: { timeout: 15000 },
  reporter: [['list']],
  use: { trace: 'retain-on-failure' },
  metadata: { projectRoot: path.resolve(__dirname, '../..') }
})
