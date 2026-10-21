/** 页面卸载期间由工作台保留的草稿。 Drafts retained by the workspace while the page is unmounted. */
import type { EvolutionCandidate, EvolutionTarget, EvolutionScope } from '../../generated/protocol'
import type { SelectedEvidence } from './EvolutionEvidence'

export interface CandidateDraft {
  text: string
  base: string
  comparison: string
  checkScript: string
}

export interface EvolutionDraft {
  origin?: EvolutionScope | null
  target: EvolutionTarget
  feedback: string
  selected: string[]
  instruction: string
  references: SelectedEvidence[]
  candidate: EvolutionCandidate | null
  drafts: Map<string, CandidateDraft>
  sourceProjectId: string
  directed: boolean
  generation: { key: string; jobId: string } | null
  proposalJobs: Record<string, string>
  findingSelections: Record<string, string[]>
}

export type EvolutionDraftCache = Map<string, EvolutionDraft>
