/** 测试专用 Electron 入口，只替换 Python 模型装配。 Test-only entry replacing Python model composition. */
const childProcess = require('node:child_process')
const path = require('node:path')
const original = childProcess.spawn
childProcess.spawn = (command, args, options) => {
  if (args.includes('my_agent') && args.includes('serve')) {
    const data = args[args.indexOf('--data-dir') + 1]
    // 只在专用测试入口传入网站样本开关。 Forward the fixture flag only from this test entry.
    if (process.env.MY_AGENT_TEST_SKILL_CATALOG === '1') {
      options = { ...options, env: { ...options.env, MY_AGENT_TEST_SKILL_CATALOG: '1' } }
    }
    return original(
      command,
      ['-u', '-X', 'utf8', path.join(__dirname, 'agent_peer.py'), data],
      options
    )
  }
  return original(command, args, options)
}
require('../../apps/desktop/out/main/index.js')
