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
  event: 'agent_step' | 'result' | 'error';
  data: AgentStep | PaperSearchResult | { message: string };
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
