/**
 * 将真实网关连接到测试 peer，验证传输与清理而不调用模型服务。
 * Connect the real gateway to test peers to verify transport and cleanup without model calls.
 */

import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import childProcess from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, mkdtemp } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { requireDesktop, root, artifacts as artifactRoot } from '../support/runtime.mjs'

const { build } = requireDesktop('esbuild')
await mkdir(artifactRoot, { recursive: true })
const artifacts = await mkdtemp(path.join(artifactRoot, 'gateway-'))
const bundle = path.join(artifacts, 'backend.cjs')
await build({
  entryPoints: [path.join(root, 'apps/desktop/src/main/backend.ts')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  outfile: bundle
})
const { Backend } = createRequire(import.meta.url)(bundle)
const realSpawn = childProcess.spawn
after(() => {
  childProcess.spawn = realSpawn
})

/**
 * 通过不同故障 peer 检查稳定错误码和自有进程退出。
 * Check stable error codes and owned-process exit using several faulty peer modes.
 */
for (const [mode, expected] of [
  ['invalid-utf8', 'PROTOCOL_INVALID'],
  ['unmatched', 'PROTOCOL_INVALID'],
  ['oversize', 'FRAME_TOO_LARGE'],
  ['exit', 'BACKEND_EXITED'],
  ['timeout', 'BACKEND_TIMEOUT']
]) {
  test('bounded failure: ' + mode, { timeout: 12000 }, async () => {
    let peer
    childProcess.spawn = (command, args, options) => {
      if (path.basename(command).toLowerCase() === 'taskkill.exe')
        return realSpawn(command, args, options)
      peer = realSpawn(
        process.execPath,
        [fileURLToPath(new URL('peer.mjs', import.meta.url)), mode],
        options
      )
      return peer
    }
    const logs = []
    const backend = new Backend(root, artifacts, '0.0.0', (code) => logs.push(code))
    await assert.rejects(backend.start(), (error) => error.detail.code === expected)
    await backend.stop()
    assert.ok(peer.exitCode !== null || peer.signalCode !== null)
    assert.deepEqual(logs, [expected])
  })
}

/**
 * 特意拆开一个汉字的 UTF-8 字节，验证组帧后再解码。
 * Split a Chinese UTF-8 character deliberately to verify decoding after framing.
 */
test('UTF-8 bytes split across chunks are decoded after framing', async () => {
  childProcess.spawn = (command, args, options) => {
    if (path.basename(command).toLowerCase() === 'taskkill.exe')
      return realSpawn(command, args, options)
    return realSpawn(
      process.execPath,
      [fileURLToPath(new URL('peer.mjs', import.meta.url)), 'split'],
      options
    )
  }
  const backend = new Backend(root, artifacts, '0.0.0', () => {})
  const initial = await backend.start()
  assert.equal(initial.app.name, '中文工作台')
  assert.deepEqual((await backend.info()).projects, { active_project: null, recent_projects: [] })
  await backend.stop()
})

/**
 * 让诊断超过八秒，普通控制仍立即响应，重复探测被拒绝。
 * Keep ordinary control responsive during long diagnostics and reject duplicate probes.
 */
test(
  'slow diagnostics do not block control and reject duplicate probes',
  { timeout: 15000 },
  async () => {
    childProcess.spawn = (command, args, options) => {
      if (path.basename(command).toLowerCase() === 'taskkill.exe')
        return realSpawn(command, args, options)
      return realSpawn(
        process.execPath,
        [fileURLToPath(new URL('peer.mjs', import.meta.url)), 'slow-diagnostic'],
        options
      )
    }
    const logs = []
    const backend = new Backend(root, artifacts, '0.0.0', (code) => logs.push(code))
    try {
      await backend.start()
      const report = backend.diagnostics({ dev: true, network: false, write_probe: false })
      await assert.rejects(
        backend.diagnostics({ dev: false, network: false, write_probe: false }),
        (error) => error.detail.code === 'DIAGNOSTICS_BUSY'
      )
      const start = performance.now()
      const info = await backend.info()
      assert.ok(performance.now() - start < 2000)
      const diagnostic = await report
      assert.equal(diagnostic.authentication_verified, 'not_checked')
      assert.equal(info.config.model_id, 'glm-5.3-flash')
      assert.deepEqual(logs, [])
    } finally {
      await backend.stop()
    }
  }
)

/**
 * 在诊断中途关闭，确认待响应请求结束且仅终止自有 peer。
 * Close during diagnostics and verify pending work ends while only the owned peer is stopped.
 */
test(
  'closing during a diagnostic rejects pending work and terminates only its peer',
  { timeout: 6000 },
  async () => {
    let peer
    childProcess.spawn = (command, args, options) => {
      if (path.basename(command).toLowerCase() === 'taskkill.exe')
        return realSpawn(command, args, options)
      peer = realSpawn(
        process.execPath,
        [fileURLToPath(new URL('peer.mjs', import.meta.url)), 'slow-diagnostic'],
        options
      )
      return peer
    }
    const backend = new Backend(root, artifacts, '0.0.0', () => {})
    await backend.start()
    const report = backend.diagnostics({ dev: true, network: false, write_probe: false })
    const rejected = assert.rejects(report, (error) => error.detail.code === 'BACKEND_EXITED')
    await new Promise((resolve) => setImmediate(resolve))
    await Promise.all([backend.stop(), rejected])
    assert.ok(peer.exitCode !== null || peer.signalCode !== null)
  }
)
