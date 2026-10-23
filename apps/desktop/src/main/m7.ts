/** 自进化 IPC 复用来源校验。 Evolution IPC reuses sender validation. */
import type { Protocol as P } from '../generated/schema'
import type { Backend } from './backend'
import { validate } from '../shared/validation'

const routes: ReadonlyArray<readonly [string, keyof P, keyof P]> = [
  ['diagnostic', 'DiagnosticQuery', 'DiagnosticEvent'],
  ['list', 'EvolutionQuery', 'EvolutionPage'],
  ['catalog', 'EvolutionQuery', 'EvolutionCatalog'],
  ['configure', 'EvolutionSettings', 'EvolutionSettings'],
  ['feedback', 'SaveEvolutionFeedback', 'EvolutionFeedback'],
  ['resource', 'EvolutionResourceQuery', 'EvolutionResource'],
  ['generate', 'GenerateEvolutionCandidate', 'EvolutionJob'],
  ['preview', 'GenerateEvolutionCandidate', 'EvolutionInput'],
  ['runs', 'EvolutionRunsQuery', 'EvolutionRunsPage'],
  ['candidate', 'EvolutionCandidateParams', 'EvolutionCandidate'],
  ['create', 'CreateEvolutionCandidate', 'EvolutionCandidate'],
  ['edit', 'SaveEvolutionCandidate', 'EvolutionCandidate'],
  ['compare', 'CompareEvolutionCandidate', 'EvolutionCandidate'],
  ['control', 'EvolutionControl', 'EvolutionCandidate'],
  ['stop', 'EvolutionJobControl', 'EvolutionJob'],
  ['job', 'EvolutionJobControl', 'EvolutionJob'],
  ['experiment', 'EvolutionExperimentParams', 'EvolutionJob']
]

/** 仅登记明确方法；长请求由后端生命周期管理。 Register explicit methods with backend-owned lifecycle. */
export function registerM7Ipc(
  register: (
    channel: string,
    count: number,
    action: (...args: unknown[]) => Promise<unknown>
  ) => void,
  ready: () => Promise<Backend>
): void {
  for (const [method, input, output] of routes) {
    register('agent:m7-' + method, 1, async (value) => {
      const service = await ready()
      return service.call('evolution.' + method, validate(input, value), output, null)
    })
  }
}
