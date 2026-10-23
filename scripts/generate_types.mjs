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
const { protocol_version: version } = JSON.parse(
  await readFile(path.join(root, 'src/my_agent/defaults.json'), 'utf8')
)
const schema = JSON.parse(
  await readFile(path.join(root, `schemas/protocol-v${version}.schema.json`), 'utf8')
)
const generated = await compile(schema, `ProtocolV${version}`, {
  bannerComment: '/* Generated from Python DTOs. Do not edit by hand. */',
  unreachableDefinitions: true,
  additionalProperties: false
})
const target = path.join(root, 'apps/desktop/src/generated/protocol.ts')
// 同一生成步骤选择 schema 与类型；业务校验器不再手填版本号。
// Generate schema and type selection together; validators do not hand-pick a version.
const schemaEntry = path.join(root, 'apps/desktop/src/generated/schema.ts')
const schemaSource = `/* Generated from defaults.json and Python DTOs. Do not edit by hand. */
export { default } from '../../../../schemas/protocol-v${version}.schema.json'
export type { ProtocolV${version} as Protocol } from './protocol'
`
if (process.argv.includes('--check')) {
  if ((await readFile(target, 'utf8')) !== generated) {
    throw new Error('Generated types drift: run npm run types:generate')
  }
  if ((await readFile(schemaEntry, 'utf8')) !== schemaSource) {
    throw new Error('Schema entry drift: run npm run types:generate')
  }
} else {
  await mkdir(path.dirname(target), { recursive: true })
  await writeFile(target, generated, 'utf8')
  await writeFile(schemaEntry, schemaSource, 'utf8')
}
