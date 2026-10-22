/**
 * 将真实网关连接到测试 peer，验证传输与清理而不调用模型服务。
 * Connect the real gateway to test peers to verify transport and cleanup without model calls.
 */

import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import childProcess from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, mkdtemp, readFile, writeFile, stat, rm } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
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

/** 单次只读等待超时不杀后端，迟到响应不会误配或使后续读取失败。
 * A read timeout neither kills the backend nor mispairs its late reply. */
test('M8 read timeout preserves backend and consumes late responses', async () => {
  const peers = []
  childProcess.spawn = (command, args, options) => {
    if (path.basename(command).toLowerCase() === 'taskkill.exe') return realSpawn(command, args, options)
    const peer = realSpawn(process.execPath, [fileURLToPath(new URL('peer.mjs', import.meta.url)), 'delayed-read'], options)
    peers.push(peer)
    return peer
  }
  const backend = new Backend(root, artifacts, '0.0.0', () => {})
  try {
    await backend.start()
    await assert.rejects(backend.call('projects.list', {}, 'ProjectsView', 20), e => e.detail.code === 'BACKEND_TIMEOUT')
    assert.equal(peers[0].exitCode, null)
    const result = await backend.call('projects.list', {}, 'ProjectsView', 1000)
    assert.equal(result.active_project, null)
    assert.equal(peers.length, 1)
    await backend.info()
  } finally { await backend.stop() }
})

/** 真正退出后恢复同一后端对象和订阅，不在第一次失败时悄悄重发原操作。
 * Recover only after actual exit, retaining the backend object without replaying failed work. */
test('M8 read reconnect is single flight after actual process closure', async () => {
  const peers = []
  childProcess.spawn = (command, args, options) => {
    if (path.basename(command).toLowerCase() === 'taskkill.exe') return realSpawn(command, args, options)
    const mode = peers.length ? 'normal' : 'crash-on-read'
    const peer = realSpawn(process.execPath, [fileURLToPath(new URL('peer.mjs', import.meta.url)), mode], options)
    peers.push(peer)
    return peer
  }
  const backend = new Backend(root, artifacts, '0.0.0', () => {})
  try {
    await backend.start()
    const closed = new Promise(resolve => peers[0].once('close', resolve))
    await assert.rejects(backend.call('projects.list', {}, 'ProjectsView'), e => e.detail.code === 'BACKEND_EXITED')
    assert.equal(peers.length, 1)
    await closed
    await Promise.all(Array.from({length: 8}, () => backend.reconnectForRead()))
    assert.equal(peers.length, 2)
    assert.equal((await backend.info()).projects.active_project, null)
  } finally { await backend.stop() }
})

/** 长查询与元数据移动使用真实 Python / RPC，只有耗时为夹具注入。
 * Real Python/RPC for long queries and moves; only delays are injected.
 */
test(
  'search and Git waits leave controls responsive and moves survive normal exit',
  { timeout: 35000 },
  async () => {
    const isolated = await mkdtemp(path.join(artifacts, 'search-git-'))
    const project = path.join(isolated, 'project')
    await mkdir(path.join(project, '.git'), { recursive: true })
    await writeFile(path.join(project, '.git/HEAD'), 'ref: refs/heads/main\n')
    await writeFile(path.join(project, 'main.py'), 'def hello():\n    pass\n')
    const peers = []
    childProcess.spawn = (command, args, options) => {
      if (path.basename(command).toLowerCase() === 'taskkill.exe')
        return realSpawn(command, args, options)
      const peer = realSpawn(
        command,
        args.map((value) => (value === 'my_agent' ? 'tests.support.search_git_backend' : value)),
        options
      )
      peers.push(peer)
      return peer
    }
    /** 等待夹具边界，不靠固定延迟猜测是否开始。 Observe fixture boundaries instead of guessing. */
    async function entered(name) {
      const end = performance.now() + 5000
      while (performance.now() < end) {
        if (
          await stat(path.join(project, name)).then(
            () => true,
            () => false
          )
        )
          return
        await new Promise((resolve) => setTimeout(resolve, 20))
      }
      assert.fail(`Fixture did not enter ${name}`)
    }
    const backend = new Backend(root, path.join(isolated, 'data'), '0.0.0', () => {})
    try {
      await backend.start()
      const opened = await backend.call('projects.open', { path: project }, 'ProjectsView')
      const project_id = opened.active_project.project_id
      const created = await backend.call(
        'tasks.create',
        {
          operation_id: randomUUID(),
          project_id,
          model_id: 'glm-5.3-flash',
          fields: { title: 'Lifecycle fixture', goal: 'No model calls' }
        },
        'CreateTaskResult'
      )
      const session_id = created.session.session_id
      const slow = () =>
        backend.call(
          'documents.search',
          { session_id, query: '__slow_fixture__' },
          'DocumentSearchResult',
          null
        )
      const superseded = assert.rejects(slow(), (error) => error.detail.code === 'CANCELLED')
      await entered('search-entered')
      const ordinary = await backend.call('projects.list', {}, 'ProjectsView', 2000)
      assert.equal(ordinary.active_project.project_id, project_id)
      const result = await backend.call(
        'documents.search',
        { session_id, query: '^def', regex: true },
        'DocumentSearchResult',
        null
      )
      assert.equal(result.matches[0].path, 'main.py')
      await superseded
      await rm(path.join(project, 'search-entered'))
      const cancelledAtExit = assert.rejects(slow(), (error) =>
        ['BACKEND_EXITED', 'CANCELLED'].includes(error.detail.code)
      )
      await entered('search-entered')
      const move = backend.call(
        'git.configure',
        { project_id, enabled: false },
        'GitSettings',
        null
      )
      await entered('move-entered')
      const status = backend.call('git.status', { project_id }, 'GitStatus', null)
      assert.equal(
        (await backend.call('projects.list', {}, 'ProjectsView', 2000)).active_project.project_id,
        project_id
      )
      const stopped = backend.stop()
      const saved = await move
      assert.equal(saved.enabled, false)
      assert.equal((await status).code, 'GIT_DISABLED')
      await Promise.all([stopped, cancelledAtExit])
      assert.equal(peers[0].exitCode, 0)
      assert.equal(
        await readFile(path.join(saved.backup_path, 'HEAD'), 'utf8'),
        'ref: refs/heads/main\n'
      )
      assert.equal(
        await stat(path.join(project, '.git')).then(
          () => true,
          () => false
        ),
        false
      )
      assert.equal(
        (await readFile(path.join(project, 'search-cleaned'), 'utf8')).trim().split('\n').length,
        2
      )
      const reopened = new Backend(root, path.join(isolated, 'data'), '0.0.0', () => {})
      try {
        await reopened.start()
        const restored = await reopened.call(
          'git.configure',
          { project_id, enabled: true },
          'GitSettings',
          null
        )
        assert.equal(restored.enabled, true)
        assert.equal(
          await readFile(path.join(project, '.git/HEAD'), 'utf8'),
          'ref: refs/heads/main\n'
        )
      } finally {
        await reopened.stop()
      }
    } finally {
      await backend.stop()
    }
  }
)

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
