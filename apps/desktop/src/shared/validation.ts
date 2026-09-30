/**
 * 使用 Python 生成的 schema 做运行时验证，禁止校验器改写输入。
 * Validate against Python-generated schemas without mutating input.
 */

import Ajv2020 from 'ajv/dist/2020.js'
import schema from '../../../../schemas/protocol-v6.schema.json'
import type { ProtocolV6 } from '../generated/protocol'

const ajv = new Ajv2020({
  strict: true,
  allErrors: true,
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false
})
ajv.addSchema(schema)

/**
 * 按命名契约校验 unknown 数据；失败仅返回固定错误标识。
 * Validate unknown data against a named contract, failing with a fixed public code.
 */
export function validate<K extends keyof ProtocolV6>(name: K, value: unknown): ProtocolV6[K] {
  const validator = ajv.getSchema<ProtocolV6[K]>(schema.$id + '#/$defs/' + name)
  if (!validator || '$async' in validator) throw new Error('PROTOCOL_INVALID')
  if (!validator(value)) throw new Error('PROTOCOL_INVALID')
  return value
}
