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
    const child = original(
      command,
      ['-u', '-X', 'utf8', path.join(__dirname, 'agent_peer.py'), data],
      options
    )
    // 只记录方法名与时间；不记录 bootstrap 凭据或参数。 Record names/times, never credentials/arguments.
    if (process.env.MY_AGENT_TEST_RPC_METRICS) {
      const { appendFileSync } = require('node:fs')
      const write = child.stdin.write.bind(child.stdin)
      child.stdin.write = (chunk, ...rest) => {
        for (const line of String(chunk).split('\n').filter(Boolean)) {
          const value = JSON.parse(line)
          if (typeof value.method === 'string')
            appendFileSync(
              process.env.MY_AGENT_TEST_RPC_METRICS,
              JSON.stringify({ at: Date.now(), method: value.method }) + '\n'
            )
        }
        return write(chunk, ...rest)
      }
    }
    return child
  }
  return original(command, args, options)
}
require('../../apps/desktop/out/main/index.js')
