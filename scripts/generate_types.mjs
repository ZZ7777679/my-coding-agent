/**
 * 从 Python schema 生成桌面类型；使用桌面已锁定的依赖并支持只读漂移检查。
 * Generate desktop types from Python schemas using locked dependencies and optional drift checks.
 */

import { createRequire } from 'node:module'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(path.join(root, 'apps/desktop/package.json'))
const { compile } = require('json-schema-to-typescript')
const schema = JSON.parse(
  await readFile(path.join(root, 'schemas/protocol-v12.schema.json'), 'utf8')
)
const generated = await compile(schema, 'ProtocolV12', {
  bannerComment: '/* Generated from Python DTOs. Do not edit by hand. */',
  unreachableDefinitions: true,
  additionalProperties: false
})
const target = path.join(root, 'apps/desktop/src/generated/protocol.ts')
if (process.argv.includes('--check')) {
  if ((await readFile(target, 'utf8')) !== generated) {
    throw new Error('Generated types drift: run npm run types:generate')
  }
} else {
  await mkdir(path.dirname(target), { recursive: true })
  await writeFile(target, generated, 'utf8')
}
