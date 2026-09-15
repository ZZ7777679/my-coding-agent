/**
 * 启动目录的隔离行为用例；迁移入口测试仅替换 UI 子进程。
 * Isolated launch-path checks; relocated-entry tests replace only the UI child process.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { execFileSync } from 'node:child_process'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  writeFileSync
} from 'node:fs'
import path from 'node:path'
import {
  LaunchConfigError,
  resolveLaunchPaths,
  saveLocalPaths
} from '../../scripts/launch-config.mjs'
import { root, artifacts } from '../support/runtime.mjs'

const defaults = JSON.parse(readFileSync(path.join(root, 'src/my_agent/defaults.json'), 'utf8'))
mkdirSync(artifacts, { recursive: true })

/**
 * 创建独立测试目录，并按需要写入本机路径样本。
 * Create a dedicated test directory and optionally write a local-path fixture.
 */
function fixture(content) {
  const folder = mkdtempSync(path.join(artifacts, '启动 路径-'))
  if (content !== undefined) {
    writeFileSync(path.join(folder, 'agent.paths.local.json'), JSON.stringify(content))
  }
  return folder
}

/**
 * 验证缺失本机文件时使用集中默认值且不初始化数据。
 * Verify missing local files use centralized defaults without initializing data.
 */
test('missing local file retains the E drive development defaults without writing data', () => {
  const folder = fixture()
  assert.deepEqual(resolveLaunchPaths(folder, defaults, [], {}), {
    dataDir: path.join(defaults.data_dir, 'dev'),
    projectDir: path.normalize(defaults.development_project_dir)
  })
  assert.equal(existsSync(path.join(folder, 'agent.paths.local.json')), false)
})

/**
 * 从不同 cwd 解析相对路径，确认基准始终是配置文件位置。
 * Resolve paths from another cwd and confirm the configuration file remains the base.
 */
test('relative paths follow the local file, independent of the shell working directory', () => {
  const folder = fixture({ data_dir: '../独立数据', project_dir: './中文 项目' })
  const previous = process.cwd()
  try {
    process.chdir(artifacts)
    assert.deepEqual(resolveLaunchPaths(folder, defaults, [], {}), {
      dataDir: path.resolve(folder, '../独立数据'),
      projectDir: path.join(folder, '中文 项目')
    })
    assert.equal(existsSync(path.join(folder, '中文 项目')), false)
  } finally {
    process.chdir(previous)
  }
})

/**
 * 覆盖 CLI、环境、本机文件与缺省字段的组合优先级。
 * Check priority across CLI, environment, local files and absent fields.
 */
test('data CLI overrides environment, environment overrides file, absent fields use defaults', () => {
  const folder = fixture({ data_dir: './local-data', project_dir: './local-project' })
  const env = {
    MY_AGENT_DATA_DIR: path.join(folder, 'env-data'),
    MY_AGENT_PROJECT_DIR: path.join(folder, 'env-project')
  }
  assert.deepEqual(resolveLaunchPaths(folder, defaults, [], env), {
    dataDir: env.MY_AGENT_DATA_DIR,
    projectDir: env.MY_AGENT_PROJECT_DIR
  })
  assert.equal(
    resolveLaunchPaths(folder, defaults, ['--data-dir', path.join(folder, 'cli-data')], env)
      .dataDir,
    path.join(folder, 'cli-data')
  )
  assert.equal(
    resolveLaunchPaths(folder, defaults, [], {}).dataDir,
    path.join(folder, 'local-data')
  )
  assert.equal(
    resolveLaunchPaths(fixture({}), defaults, [], {}).projectDir,
    path.normalize(defaults.development_project_dir)
  )
})

/**
 * 注入类型、编码、大小与路径错误，确认不泄露或重置文件内容。
 * Inject type, encoding, size and path errors without leaking or resetting file content.
 */
test('bad local files fail without echoing their contents or resetting them', () => {
  const privateMarker = 'launch-test-private-content'
  const cases = [
    JSON.stringify({ api_key: privateMarker }),
    JSON.stringify({ data_dir: null }),
    JSON.stringify({ data_dir: 123 }),
    JSON.stringify({ project_dir: ' ' }),
    JSON.stringify({ data_dir: '\0' }),
    JSON.stringify([privateMarker]),
    'null',
    privateMarker,
    Buffer.from([0xc3, 0x28]),
    ' '.repeat(16 * 1024 + 1)
  ]
  if (process.platform === 'win32') {
    cases.push(JSON.stringify({ data_dir: 'E:ambiguous' }))
    cases.push(JSON.stringify({ project_dir: '\\ambiguous' }))
  }
  for (const content of cases) {
    const folder = fixture()
    const target = path.join(folder, 'agent.paths.local.json')
    writeFileSync(target, content)
    assert.throws(
      () => resolveLaunchPaths(folder, defaults, [], {}),
      (cause) => cause instanceof LaunchConfigError && !cause.message.includes(privateMarker)
    )
    assert.deepEqual(readFileSync(target), Buffer.from(content))
  }
  const folder = fixture()
  mkdirSync(path.join(folder, 'agent.paths.local.json'))
  assert.throws(() => resolveLaunchPaths(folder, defaults, [], {}), LaunchConfigError)
})

/**
 * 确认非法显式路径直接失败，不悄悄采用低优先级值。
 * Confirm invalid explicit paths fail instead of silently using lower-priority values.
 */
test('invalid CLI and environment paths cannot silently fall back to defaults', () => {
  const folder = fixture()
  for (const [args, env] of [
    [['--data-dir'], {}],
    [['--data-dir', 'relative'], {}],
    [['--unknown'], {}],
    [[], { MY_AGENT_DATA_DIR: '' }],
    [[], { MY_AGENT_DATA_DIR: 'relative' }],
    [[], { MY_AGENT_PROJECT_DIR: '' }],
    [[], { MY_AGENT_PROJECT_DIR: 'relative' }]
  ]) {
    assert.throws(() => resolveLaunchPaths(folder, defaults, args, env), LaunchConfigError)
  }
})

/**
 * 保存路径后检查启动解析复用结果，不创建或搬迁业务目录。
 * Check saved paths are reused without creating or moving business directories.
 */
test('saved paths are reused by the launcher without creating or moving data', () => {
  const folder = fixture({ data_dir: './old-data', project_dir: './old-project' })
  const paths = {
    data_dir: path.join(folder, 'new-data'),
    project_dir: path.join(folder, 'project')
  }
  saveLocalPaths(folder, paths)
  assert.deepEqual(resolveLaunchPaths(folder, defaults, [], {}), {
    dataDir: paths.data_dir,
    projectDir: paths.project_dir
  })
  assert.deepEqual(readdirSync(folder), ['agent.paths.local.json'])
  const before = readFileSync(path.join(folder, 'agent.paths.local.json'))
  assert.throws(() => saveLocalPaths(folder, { ...paths, data_dir: 'relative' }), LaunchConfigError)
  assert.deepEqual(readFileSync(path.join(folder, 'agent.paths.local.json')), before)
})

/**
 * 确认保存操作不会覆盖需要修复的损坏文件。
 * Confirm saving cannot overwrite a corrupt file that needs repair.
 */
test('saving refuses to replace malformed startup configuration', () => {
  const folder = fixture()
  const file = path.join(folder, 'agent.paths.local.json')
  writeFileSync(file, '{broken')
  assert.throws(
    () =>
      saveLocalPaths(folder, {
        data_dir: path.join(folder, 'data'),
        project_dir: path.join(folder, 'project')
      }),
    LaunchConfigError
  )
  assert.equal(readFileSync(file, 'utf8'), '{broken')
  assert.deepEqual(readdirSync(folder), ['agent.paths.local.json'])
})

/**
 * 在搬迁的测试仓库从其他 cwd 执行真实 dev / preview 入口。
 * Run real dev/preview entrypoints from another cwd in a relocated fixture repository.
 */
test('relocated dev and preview entrypoints pass the file settings to their child process', () => {
  const folder = fixture({ data_dir: '../启动数据', project_dir: './测试项目' })
  for (const directory of [
    'scripts',
    'src/my_agent',
    'apps/desktop/node_modules/electron-vite/bin'
  ]) {
    mkdirSync(path.join(folder, directory), { recursive: true })
  }
  for (const name of ['dev.mjs', 'launch-config.mjs']) {
    copyFileSync(path.join(root, 'scripts', name), path.join(folder, 'scripts', name))
  }
  writeFileSync(path.join(folder, 'src/my_agent/defaults.json'), JSON.stringify(defaults))
  // 执行搬迁后的真实启动入口，仅用输出参数的替身替换 UI 子进程。
  // Run the real relocated entrypoint; only replace the UI child with an argument-reporting stub.
  writeFileSync(
    path.join(folder, 'apps/desktop/node_modules/electron-vite/bin/electron-vite.js'),
    'console.log(JSON.stringify({mode:process.argv[2],cwd:process.cwd(),dataDir:process.env.MY_AGENT_DATA_DIR,projectDir:process.env.MY_AGENT_PROJECT_DIR}))'
  )
  const env = { ...process.env }
  delete env.MY_AGENT_DATA_DIR
  delete env.MY_AGENT_PROJECT_DIR
  for (const mode of ['dev', 'preview']) {
    const output = execFileSync(
      process.execPath,
      [path.join(folder, 'scripts/dev.mjs'), ...(mode === 'preview' ? ['--preview'] : [])],
      { cwd: artifacts, env, encoding: 'utf8', windowsHide: true, timeout: 10000 }
    )
    assert.deepEqual(JSON.parse(output), {
      mode,
      cwd: path.join(folder, 'apps/desktop'),
      dataDir: path.resolve(folder, '../启动数据'),
      projectDir: path.join(folder, '测试项目')
    })
  }
})
