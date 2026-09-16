/** 只在隔离诊断入口注入无网络计时模型。 Inject the offline timing model in this isolated entry only. */
const childProcess = require('node:child_process')
const path = require('node:path')
const original = childProcess.spawn
childProcess.spawn = (command, args, options) => {
  if (args.includes('my_agent') && args.includes('serve')) {
    const data = args[args.indexOf('--data-dir') + 1]
    return original(
      command,
      [
        '-u',
        '-X',
        'utf8',
        path.join(__dirname, 'latency_peer.py'),
        data,
        path.join(data, '..', 'backend.jsonl')
      ],
      options
    )
  }
  return original(command, args, options)
}
require('../../apps/desktop/out/main/index.js')
