/**
 * 共用桌面锁定的 Playwright 依赖，避免维护另一套测试运行时。
 * Reuse the desktop-locked Playwright dependency instead of maintaining another runtime.
 */

export {
  _electron as electron,
  expect,
  test,
  type ElectronApplication
} from '../../apps/desktop/node_modules/@playwright/test'
