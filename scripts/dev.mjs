/**
 * 从脚本位置装配开发或预览启动，向子进程传递已解析的本机目录。
 * Launch dev or preview from the script location, passing resolved local paths to the child.
 */

import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { LaunchConfigError, resolveLaunchPaths } from './launch-config.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const defaults = JSON.parse(readFileSync(path.join(root, 'src/my_agent/defaults.json'), 'utf8'))
const args = process.argv.slice(2)
const preview = args[0] === '--preview'
if (preview) args.shift()
let paths
try {
  paths = resolveLaunchPaths(root, defaults, args)
} catch (cause) {
  console.error(cause instanceof LaunchConfigError ? cause.message : 'Cannot load launch paths.')
  process.exit(1)
}
const child = spawn(
  process.execPath,
  [
    path.join(root, 'apps/desktop/node_modules/electron-vite/bin/electron-vite.js'),
    preview ? 'preview' : 'dev'
  ],
  {
    cwd: path.join(root, 'apps/desktop'),
    stdio: 'inherit',
    env: {
      ...process.env,
      [defaults.data_dir_env]: paths.dataDir,
      [defaults.project_dir_env]: paths.projectDir
    },
    windowsHide: true
  }
)
child.on('error', () => {
  process.exitCode = 1
})
child.on('exit', (code) => {
  process.exitCode = code ?? 1
})
