/**
 * 为三个桌面入口构建资源；sandbox preload 内联依赖，开发页面仅绑定回环地址。
 * Build three desktop entries; bundle sandbox preload dependencies and bind dev to loopback.
 */

import { defineConfig } from 'electron-vite'

export default defineConfig({
  main: {},
  preload: { build: { externalizeDeps: false } },
  renderer: {
    esbuild: { jsx: 'automatic' },
    server: { host: '127.0.0.1' }
  }
})
