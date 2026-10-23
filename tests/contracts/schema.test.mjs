/**
 * 用共用正反样本验证 Ajv 结果，并检查校验过程不改写输入。
 * Verify Ajv outcomes with shared positive/negative fixtures and ensure input stays unchanged.
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { requireDesktop, root } from '../support/runtime.mjs'
import path from 'node:path'

const Ajv2020 = requireDesktop('ajv/dist/2020.js').default

const { protocol_version: version } = JSON.parse(
  readFileSync(path.join(root, 'src/my_agent/defaults.json'), 'utf8')
)
const schema = JSON.parse(
  readFileSync(path.join(root, `schemas/protocol-v${version}.schema.json`), 'utf8')
)
const cases = JSON.parse(readFileSync(path.join(root, 'tests/fixtures/contracts.json'), 'utf8'))
const ajv = new Ajv2020({
  strict: true,
  allErrors: true,
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false
})
ajv.addSchema(schema)
/**
 * 同一批样本也由 Python 读取，比较的是业务契约而非两套手写类型。
 * Python reads these same fixtures, checking the contract rather than two handwritten type sets.
 */
for (const fixture of cases) {
  test(fixture.name, () => {
    const original = structuredClone(fixture.data)
    const validate = ajv.getSchema(schema.$id + '#/$defs/' + fixture.type)
    assert.ok(validate)
    assert.equal(validate(fixture.data), fixture.valid, JSON.stringify(validate.errors))
    assert.deepEqual(fixture.data, original)
  })
}
