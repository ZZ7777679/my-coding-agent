/** 自进化的有限桌面接口。 Restricted evolution desktop API. */
import type { ProtocolV13 as P } from '../generated/protocol'
import type { Result } from './api'

export interface M7DesktopAPI {
  evolutionList(params: P['EvolutionQuery']): Promise<Result<P['EvolutionPage']>>
  evolutionCatalog(params: P['EvolutionQuery']): Promise<Result<P['EvolutionCatalog']>>
  evolutionConfigure(params: P['EvolutionSettings']): Promise<Result<P['EvolutionSettings']>>
  evolutionFeedback(params: P['SaveEvolutionFeedback']): Promise<Result<P['EvolutionFeedback']>>
  evolutionResource(params: P['EvolutionResourceQuery']): Promise<Result<P['EvolutionResource']>>
  evolutionGenerate(params: P['GenerateEvolutionCandidate']): Promise<Result<P['EvolutionJob']>>
  evolutionPreview(params: P['GenerateEvolutionCandidate']): Promise<Result<P['EvolutionInput']>>
  evolutionRuns(params: P['EvolutionRunsQuery']): Promise<Result<P['EvolutionRunsPage']>>
  evolutionCandidate(
    params: P['EvolutionCandidateParams']
  ): Promise<Result<P['EvolutionCandidate']>>
  evolutionCreate(params: P['CreateEvolutionCandidate']): Promise<Result<P['EvolutionCandidate']>>
  evolutionEdit(params: P['SaveEvolutionCandidate']): Promise<Result<P['EvolutionCandidate']>>
  evolutionCompare(params: P['CompareEvolutionCandidate']): Promise<Result<P['EvolutionCandidate']>>
  evolutionControl(params: P['EvolutionControl']): Promise<Result<P['EvolutionCandidate']>>
  evolutionStop(params: P['EvolutionJobControl']): Promise<Result<P['EvolutionJob']>>
  evolutionJob(params: P['EvolutionJobControl']): Promise<Result<P['EvolutionJob']>>
  evolutionExperiment(params: P['EvolutionExperimentParams']): Promise<Result<P['EvolutionJob']>>
}
