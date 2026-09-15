/**
 * 终止本应用拥有的进程；Windows 额外处理启动器产生的后代。
 * Stop owned processes, including launcher descendants on Windows.
 */

import { spawn, type ChildProcess } from 'node:child_process'
import path from 'node:path'

/**
 * Windows 尝试终止自有进程树，其余平台发送终止信号；调用方仍须等待退出。
 * Stop the owned Windows tree or signal the child elsewhere; callers must still await exit.
 */
export function terminateProcessTree(
  child: ChildProcess,
  log: (code: string) => void
): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null || !child.pid) return Promise.resolve()
  if (process.platform !== 'win32') {
    child.kill('SIGKILL')
    return Promise.resolve()
  }
  // Windows venv 与 npm.cmd 可能产生后代，仅终止启动器会遗留工作进程。
  // Windows venv and npm.cmd launchers can leave descendants alive when only their PID is killed.
  const systemRoot = process.env.SystemRoot ?? process.env.SYSTEMROOT
  if (!systemRoot) {
    log('PROCESS_TREE_TERMINATION_UNAVAILABLE')
    child.kill()
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    const killer = spawn(
      path.join(systemRoot, 'System32/taskkill.exe'),
      ['/PID', String(child.pid), '/T', '/F'],
      {
        stdio: 'ignore',
        windowsHide: true,
        env: { SystemRoot: systemRoot }
      }
    )
    const timer = setTimeout(() => {
      log('PROCESS_TREE_TERMINATION_TIMEOUT')
      killer.kill()
      child.kill()
    }, 2000)
    /**
     * 结束终止辅助进程的等待并清除它的超时句柄。
     * Finish waiting for the termination helper and clear its timeout handle.
     */
    const finish = () => {
      clearTimeout(timer)
      resolve()
    }
    killer.once('error', () => {
      log('PROCESS_TREE_TERMINATION_FAILED')
      child.kill()
      finish()
    })
    killer.once('exit', (code) => {
      if (code !== 0 && child.exitCode === null && child.signalCode === null) {
        log('PROCESS_TREE_TERMINATION_FAILED')
        child.kill()
      }
      finish()
    })
  })
}
