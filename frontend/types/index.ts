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
