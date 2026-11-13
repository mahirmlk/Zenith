export interface Paper {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  url: string;
  publishedAt: string;
  summaryTldr?: string;
  summaryContributions?: string[];
  relevanceScore?: number;
  difficulty?: 'introductory' | 'intermediate' | 'expert';
  papersWithCode?: { repos: { url: string; stars: number }[] };
}

export type PlanFactCategory =
  | 'architecture'
  | 'dependency'
  | 'dataset'
  | 'metric'
  | 'training'
  | 'evaluation'
  | 'limitation'
  | 'compute';

export interface EvidenceSpan {
  paper_id: string;
  paper_url: string;
  start: number;
  end: number;
  quote: string;
}

export interface PlanFact {
  category: PlanFactCategory;
  text: string;
  evidence: EvidenceSpan;
}

export interface ModelDataCard {
  model_or_method: string | null;
  datasets: string[];
  dataset_license: string | null;
  intended_use: string | null;
  limitations: string[];
  status: 'partial' | 'not available';
}

export interface CandidateRepository {
  url: string;
  stars: number;
  verified: boolean;
  verification_status: string;
  source: string;
}

export interface ImplementationPlan {
  paper_id: string;
  title: string;
  architecture: string;
  dependencies: string[];
  datasets: string[];
  metrics: string[];
  training_steps: string[];
  evaluation_steps: string[];
  compute_requirements: string[];
  facts: PlanFact[];
  checklist: string[];
  suggested_structure: string[];
  compatibility_notes: string[];
  model_data_card: ModelDataCard;
  candidate_repos: CandidateRepository[];
  repository_lookup_status: 'available' | 'no_results' | 'unavailable';
  reproducibility_gaps: string[];
  citations: string[];
  status: 'plan generated';
}

export interface PaperSearchResult {
  papers: Paper[];
  runId: string;
}

export interface UserPrefs {
  preferredModel: string;
  interests: string[];
}

export interface AgentStep {
  agent: string;
  status: string;
  count?: number;
  paperId?: string;
  message?: string;
}

export interface StreamEvent {
  event: 'agent_step' | 'result' | 'error' | 'cancelled';
  data: AgentStep | PaperSearchResult | ResearchPlanExecutionResult | { message: string } | ResearchRunCancelledEvent;
}

export interface ResearchRunCancelledEvent {
  run_id: string;
  status: 'cancelled';
}

export interface ResearchPlanExecutionStep {
  step_id: ResearchPlanStepId;
  status: string;
  count?: number;
}

export interface ResearchPlanExecutionEvidence {
  citation_id: string;
  paper_id?: string;
  document_id?: string;
  page_number?: number;
  title?: string;
  sentence: string;
  start_offset: number;
  end_offset: number;
}

export interface ResearchPlanExecutionComparisonRow {
  paper_id: string;
  problem?: string | null;
  methods?: string | null;
  datasets?: string | null;
  metrics?: string | null;
  limitations?: string | null;
  code_status?: string;
}

export interface ResearchPlanExecutionSynthesisClaim {
  text: string;
  status: 'supported' | 'conflicting' | 'uncertain';
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  cited_evidence_ids: string[];
  explanation: string;
}

export interface ResearchPlanExecutionResult {
  kind: 'research_plan_execution';
  run_id: string;
  task_type: ResearchTaskType;
  source_scope: ResearchPlanScope;
  steps: ResearchPlanExecutionStep[];
  sources: { paper_id: string; title: string }[];
  evidence: ResearchPlanExecutionEvidence[];
  gaps: string[];
  comparison?: ResearchPlanExecutionComparisonRow[];
  synthesis?: ResearchPlanExecutionSynthesisClaim[];
  cost_tracking_available: false;
  estimated_cost_usd: null;
}

export type ResearchTaskType = 'feed' | 'explain' | 'compare' | 'deep_research';
export type ResearchPlanScope = 'public_corpus' | 'project';
export type ResearchPlanStepId =
  | 'retrieve_sources'
  | 'extract_evidence'
  | 'compare_sources'
  | 'identify_gaps'
  | 'draft_synthesis'
  | 'review_claims'
  | 'synthesis_unavailable';

export interface ResearchPlanStep {
  step_id: ResearchPlanStepId;
  title: string;
  description: string;
  execution_state: 'proposed';
}

export interface ResearchPlanPreview {
  query: string;
  task_type: ResearchTaskType;
  max_tool_calls: number;
  max_sources: number;
  source_scope: ResearchPlanScope;
  steps: ResearchPlanStep[];
  max_depth: number;
  max_wall_clock_seconds: number;
  max_model_calls: number;
  max_output_tokens: number;
  synthesis_available: boolean;
  estimated_cost_usd: null;
  cost_tracking_available: false;
  execution_available: boolean;
  limits_are_preview_only: boolean;
}

export type LLMModel =
  | 'anthropic/claude-opus-4'
  | 'anthropic/claude-sonnet-4-5'
  | 'openai/gpt-4o'
  | 'openai/gpt-4o-mini'
  | 'google/gemini-2.5-pro'
  | 'google/gemini-2.0-flash'
  | 'mistralai/mistral-large'
  | 'meta-llama/llama-3.3-70b-instruct'
  | 'deepseek/deepseek-r1';
