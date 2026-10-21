/** 自进化的具名转发。 Named evolution forwarding. */
import type { ProtocolV12 as P } from '../generated/protocol'
import type { M7DesktopAPI } from '../shared/m7-api'
import type { Result } from '../shared/api'

type Invoke = <K extends keyof P>(
  channel: string,
  contract: K,
  args?: unknown[]
) => Promise<Result<P[K]>>

/** 不暴露通用 RPC 或文件访问。 Expose neither generic RPC nor filesystem access. */
export function m7Api(invoke: Invoke): M7DesktopAPI {
  return {
    evolutionList: (p) => invoke('agent:m7-list', 'EvolutionPage', [p]),
    evolutionCatalog: (p) => invoke('agent:m7-catalog', 'EvolutionCatalog', [p]),
    evolutionConfigure: (p) => invoke('agent:m7-configure', 'EvolutionSettings', [p]),
    evolutionFeedback: (p) => invoke('agent:m7-feedback', 'EvolutionFeedback', [p]),
    evolutionResource: (p) => invoke('agent:m7-resource', 'EvolutionResource', [p]),
    evolutionGenerate: (p) => invoke('agent:m7-generate', 'EvolutionJob', [p]),
    evolutionPreview: (p) => invoke('agent:m7-preview', 'EvolutionInput', [p]),
    evolutionRuns: (p) => invoke('agent:m7-runs', 'EvolutionRunsPage', [p]),
    evolutionCandidate: (p) => invoke('agent:m7-candidate', 'EvolutionCandidate', [p]),
    evolutionCreate: (p) => invoke('agent:m7-create', 'EvolutionCandidate', [p]),
    evolutionEdit: (p) => invoke('agent:m7-edit', 'EvolutionCandidate', [p]),
    evolutionCompare: (p) => invoke('agent:m7-compare', 'EvolutionCandidate', [p]),
    evolutionControl: (p) => invoke('agent:m7-control', 'EvolutionCandidate', [p]),
    evolutionStop: (p) => invoke('agent:m7-stop', 'EvolutionJob', [p]),
    evolutionJob: (p) => invoke('agent:m7-job', 'EvolutionJob', [p]),
    evolutionExperiment: (p) => invoke('agent:m7-experiment', 'EvolutionJob', [p])
  }
}
