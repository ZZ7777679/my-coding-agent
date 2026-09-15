/**
 * 故障注入用 JSONL peer，故意发送非法响应或延迟，不用于业务运行。
 * Fault-injection JSONL peer sending invalid or delayed replies, never used in production.
 */

import { createInterface } from 'node:readline'
import { readFileSync } from 'node:fs'
const fixtures = JSON.parse(
  readFileSync(new URL('../fixtures/contracts.json', import.meta.url), 'utf8')
)
const ready = fixtures.find((sample) => sample.name === 'ready-state').data
const diagnostic = fixtures.find((sample) => sample.name === 'diagnostic-report').data
const mode = process.argv[2]
const input = createInterface({ input: process.stdin })
let first = true
/**
 * 跳过私有引导帧后按模式响应，保持请求关联用于网关边界验证。
 * Skip the private bootstrap, then respond by mode with request IDs for gateway checks.
 */
input.on('line', (line) => {
  if (first) {
    first = false
    return
  }
  const request = JSON.parse(line)
  if (mode === 'timeout') return
  if (mode === 'exit') {
    process.exit(2)
  }
  if (mode === 'invalid-utf8') {
    process.stdout.write(Buffer.from([255, 10]))
    return
  }
  if (mode === 'oversize') {
    process.stdout.write('x'.repeat(1024 * 1024 + 20))
    return
  }
  if (request.method === 'diagnostics.get') {
    const reply = JSON.stringify({ jsonrpc: '2.0', id: request.id, result: diagnostic }) + '\n'
    setTimeout(() => process.stdout.write(reply), mode === 'slow-diagnostic' ? 9000 : 0)
    return
  }
  const reply = {
    jsonrpc: '2.0',
    id: mode === 'unmatched' ? 'wrong-id' : request.id,
    result:
      request.method === 'initialize'
        ? ready
        : request.method === 'config.get'
          ? ready.config
          : ready.projects
  }
  if (mode === 'split') {
    const raw = Buffer.from(JSON.stringify(reply) + '\n')
    const chinese = raw.indexOf(Buffer.from('中'))
    const split = chinese >= 0 ? chinese + 1 : 15
    process.stdout.write(raw.subarray(0, split))
    setTimeout(() => process.stdout.write(raw.subarray(split)), 15)
  } else process.stdout.write(JSON.stringify(reply) + '\n')
})
