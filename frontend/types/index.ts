export interface Paper {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  url: string;
  publishedAt: string;
  doi?: string | null;
  preprintId?: string | null;
  sourceVersion?: number | null;
  publicationUpdateType?: PaperPublicationUpdateType | null;
  publicationUpdateDoi?: string | null;
  publicationUpdateLabel?: string | null;
  publicationUpdateDate?: string | null;
  publicationUpdateSource?: 'crossref' | null;
  publicationUpdateDepositSource?: 'publisher' | 'retraction-watch' | null;
  publicationUpdateCheckedAt?: string | null;
  summaryTldr?: string;
  summaryContributions?: string[];
  summaryStatus?: PaperSummaryStatus;
  summaryFallbackReason?: PaperSummaryFallbackReason | null;
  relevanceScore?: number;
  difficulty?: 'introductory' | 'intermediate' | 'expert';
  papersWithCode?: { repos: { url: string; stars: number }[] };
}

export interface ResearchCapabilities {
  research_synthesis_enabled: boolean;
  research_plan_execution_enabled: boolean;
  public_paper_evidence_enabled: boolean;
}

export interface PublicPaperEvidenceItem {
  page_number: number;
  citation_id: string;
  sentence: string;
  start_offset: number;
  end_offset: number;
}

export interface PublicPaperEvidenceResponse {
  paper_id: string;
  preprint_id: string;
  version: number;
  title: string;
  source_url: string;
  license_url: string;
  license_name: string;
  attribution: string;
  evidence: PublicPaperEvidenceItem[];
}

export type PaperPublicationUpdateType =
  | 'retraction'
  | 'partial_retraction'
  | 'withdrawal'
  | 'removal'
  | 'expression_of_concern';

export type PaperSummaryStatus = 'generated' | 'abstract_preview' | 'unknown';

export type PaperSummaryFallbackReason =
  | 'per_run_cap'
  | 'spend_limit'
  | 'billing_unavailable'
  | 'provider_unavailable'
  | 'invalid_output';

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

export interface ResearchPlanExecutionPdfComparisonEvidence {
  sentence: string;
  citation_id: string;
  page_number: number;
  start_offset: number;
  end_offset: number;
}

export interface ResearchPlanExecutionPdfComparisonRow {
  document_id: string;
  filename: string;
  problem?: ResearchPlanExecutionPdfComparisonEvidence | null;
  methods?: ResearchPlanExecutionPdfComparisonEvidence | null;
  datasets?: ResearchPlanExecutionPdfComparisonEvidence | null;
  metrics?: ResearchPlanExecutionPdfComparisonEvidence | null;
  limitations?: ResearchPlanExecutionPdfComparisonEvidence | null;
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
  pdf_comparisons?: ResearchPlanExecutionPdfComparisonRow[];
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
  | 'anthropic/claude-opus-5.5'
  | 'anthropic/claude-sonnet-5.5'
  | 'openai/gpt-4o'
  | 'openai/gpt-4o-mini'
  | 'google/gemini-3.6-flash'
  | 'meta-llama/llama-3.3-70b-instruct';

export interface ProjectAnnotation {
  id: string;
  project_id: string;
  source_type: 'paper_abstract' | 'pdf_page';
  source_label: string | null;
  paper_source_id: string | null;
  document_id: string | null;
  page_number: number | null;
  start_offset: number;
  end_offset: number;
  quote: string;
  quote_sha256: string;
  content: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
}

export type ProjectAnnotationAnchor =
  | {
    source_type: 'paper_abstract';
    paper_source_id: string;
    start_offset: number;
    end_offset: number;
    quote: string;
  }
  | {
    source_type: 'pdf_page';
    document_id: string;
    page_number: number;
    start_offset: number;
    end_offset: number;
    quote: string;
  };

export interface SavedSearch {
  id: string;
  name: string;
  query: string;
  model: LLMModel | null;
  project_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type ProjectBriefSourceLocator =
  | {
    source_type: 'paper_abstract';
    paper_source_id: string;
    start_offset: number;
    end_offset: number;
    quote: string;
  }
  | {
    source_type: 'pdf_page';
    document_id: string;
    page_number: number;
    start_offset: number;
    end_offset: number;
    quote: string;
  };

export interface ProjectBriefSourceSnapshot {
  source_type: 'paper_abstract' | 'pdf_page';
  source_id: string;
  paper_id?: string | null;
  document_id?: string | null;
  page_number?: number | null;
  start_offset: number;
  end_offset: number;
  quote: string;
  quote_sha256: string;
  source_sha256: string;
  source_label: string;
}

export interface ProjectBrief {
  id: string;
  project_id: string;
  title: string;
  created_by: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectBriefVersion {
  id: string;
  brief_id: string;
  version: number;
  content: string;
  source_snapshot: ProjectBriefSourceSnapshot[];
  created_by: string;
  created_at: string;
  content_sha256: string;
  origin: 'user_authored';
}

export interface ProjectBriefCreateResponse {
  brief: ProjectBrief;
  version: ProjectBriefVersion;
}
