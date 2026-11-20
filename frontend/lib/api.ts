import { AgentStep, ImplementationPlan, Paper, PaperSearchResult, PaperSummaryFallbackReason, PaperSummaryStatus, PublicPaperEvidenceResponse, ResearchCapabilities, ResearchPlanExecutionResult, ResearchRunCancelledEvent, UserPrefs } from '@/types';
import { getJWT } from './auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function handleAuthRedirect(response: Response): void {
  if (response.status === 401 && typeof window !== 'undefined') {
    window.location.href = '/login';
  }
}

async function getHeaders(): Promise<Record<string, string>> {
  const token = await getJWT();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? body.message ?? `Request failed: ${res.status}`;
  } catch {
    return `Request failed: ${res.status}`;
  }
}

type JsonRecord = Record<string, unknown>;

function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function field(record: JsonRecord, snakeCase: string, camelCase: string): unknown {
  return record[camelCase] ?? record[snakeCase];
}

const SUMMARY_STATUSES: readonly PaperSummaryStatus[] = ['generated', 'abstract_preview', 'unknown'];
const SUMMARY_FALLBACK_REASONS: readonly PaperSummaryFallbackReason[] = [
  'per_run_cap',
  'spend_limit',
  'billing_unavailable',
  'provider_unavailable',
  'invalid_output',
];
const PUBLICATION_UPDATE_TYPES: readonly NonNullable<Paper['publicationUpdateType']>[] = [
  'retraction', 'partial_retraction', 'withdrawal', 'removal', 'expression_of_concern',
];

function isSummaryStatus(value: unknown): value is PaperSummaryStatus {
  return typeof value === 'string' && SUMMARY_STATUSES.includes(value as PaperSummaryStatus);
}

function isSummaryFallbackReason(value: unknown): value is PaperSummaryFallbackReason {
  return typeof value === 'string' && SUMMARY_FALLBACK_REASONS.includes(value as PaperSummaryFallbackReason);
}

/** Normalize a backend Paper payload (snake_case) at the API boundary. */
export function normalizePaper(payload: unknown): Paper {
  if (!isJsonRecord(payload)) throw new Error('Invalid paper response');

  const id = payload.id;
  const title = payload.title;
  const abstract = payload.abstract;
  const url = payload.url;
  const publishedAt = field(payload, 'published_at', 'publishedAt');
  const authors = payload.authors;
  const preprintId = field(payload, 'preprint_id', 'preprintId');
  const sourceVersion = field(payload, 'source_version', 'sourceVersion');
  const summaryTldr = field(payload, 'summary_tldr', 'summaryTldr');
  const summaryContributions = field(payload, 'summary_contributions', 'summaryContributions');
  const relevanceScore = field(payload, 'relevance_score', 'relevanceScore');
  const papersWithCode = field(payload, 'papers_with_code', 'papersWithCode');
  const rawStatus = field(payload, 'summary_status', 'summaryStatus');
  const rawReason = field(payload, 'summary_fallback_reason', 'summaryFallbackReason');
  const publicationUpdateType = field(payload, 'publication_update_type', 'publicationUpdateType');
  const publicationUpdateDoi = field(payload, 'publication_update_doi', 'publicationUpdateDoi');
  const publicationUpdateLabel = field(payload, 'publication_update_label', 'publicationUpdateLabel');
  const publicationUpdateDate = field(payload, 'publication_update_date', 'publicationUpdateDate');
  const publicationUpdateSource = field(payload, 'publication_update_source', 'publicationUpdateSource');
  const publicationUpdateDepositSource = field(payload, 'publication_update_deposit_source', 'publicationUpdateDepositSource');
  const publicationUpdateCheckedAt = field(payload, 'publication_update_checked_at', 'publicationUpdateCheckedAt');

  return {
    id: typeof id === 'string' ? id : '',
    title: typeof title === 'string' ? title : '',
    abstract: typeof abstract === 'string' ? abstract : '',
    authors: Array.isArray(authors) ? authors.filter((author): author is string => typeof author === 'string') : [],
    url: typeof url === 'string' ? url : '',
    publishedAt: typeof publishedAt === 'string' ? publishedAt : '',
    doi: typeof payload.doi === 'string' ? payload.doi : null,
    preprintId: typeof preprintId === 'string' && preprintId.trim() ? preprintId.trim() : null,
    sourceVersion: typeof sourceVersion === 'number' && Number.isSafeInteger(sourceVersion) && sourceVersion > 0
      ? sourceVersion
      : null,
    publicationUpdateType: typeof publicationUpdateType === 'string'
      && PUBLICATION_UPDATE_TYPES.includes(publicationUpdateType as NonNullable<Paper['publicationUpdateType']>)
      ? publicationUpdateType as NonNullable<Paper['publicationUpdateType']>
      : null,
    publicationUpdateDoi: typeof publicationUpdateDoi === 'string' ? publicationUpdateDoi : null,
    publicationUpdateLabel: typeof publicationUpdateLabel === 'string' ? publicationUpdateLabel : null,
    publicationUpdateDate: typeof publicationUpdateDate === 'string' ? publicationUpdateDate : null,
    publicationUpdateSource: publicationUpdateSource === 'crossref' ? 'crossref' : null,
    publicationUpdateDepositSource: publicationUpdateDepositSource === 'publisher' || publicationUpdateDepositSource === 'retraction-watch'
      ? publicationUpdateDepositSource
      : null,
    publicationUpdateCheckedAt: typeof publicationUpdateCheckedAt === 'string' ? publicationUpdateCheckedAt : null,
    summaryTldr: typeof summaryTldr === 'string' ? summaryTldr : undefined,
    summaryContributions: Array.isArray(summaryContributions)
      ? summaryContributions.filter((item): item is string => typeof item === 'string')
      : undefined,
    summaryStatus: rawStatus === undefined || rawStatus === null
      ? undefined
      : isSummaryStatus(rawStatus) ? rawStatus : 'unknown',
    summaryFallbackReason: isSummaryFallbackReason(rawReason) ? rawReason : null,
    relevanceScore: typeof relevanceScore === 'number' && Number.isFinite(relevanceScore)
      ? relevanceScore
      : undefined,
    difficulty: payload.difficulty === 'introductory' || payload.difficulty === 'intermediate' || payload.difficulty === 'expert'
      ? payload.difficulty
      : undefined,
    papersWithCode: isJsonRecord(papersWithCode)
      ? papersWithCode as Paper['papersWithCode']
      : undefined,
  };
}

function normalizePaperList(payload: unknown): Paper[] {
  if (!Array.isArray(payload)) throw new Error('Invalid paper list response');
  return payload.map(normalizePaper);
}

export function normalizePaperSearchResult(payload: unknown): PaperSearchResult {
  if (!isJsonRecord(payload)) throw new Error('Invalid paper search result');
  const runId = field(payload, 'run_id', 'runId');
  return {
    papers: normalizePaperList(payload.papers),
    runId: typeof runId === 'string' ? runId : '',
  };
}

function normalizeAgentStep(payload: unknown): AgentStep {
  if (!isJsonRecord(payload)) throw new Error('Invalid progress event');
  const paperId = field(payload, 'paper_id', 'paperId');
  return {
    agent: typeof payload.agent === 'string' ? payload.agent : 'research',
    status: typeof payload.status === 'string' ? payload.status : 'unknown',
    count: typeof payload.count === 'number' ? payload.count : undefined,
    paperId: typeof paperId === 'string' ? paperId : undefined,
    message: typeof payload.message === 'string' ? payload.message : undefined,
  };
}

function normalizeResultEvent(payload: unknown): PaperSearchResult | ResearchPlanExecutionResult {
  if (isJsonRecord(payload) && Array.isArray(payload.papers)) {
    return normalizePaperSearchResult(payload);
  }
  return payload as ResearchPlanExecutionResult;
}

export async function searchPapers(query: string, model?: string): Promise<{ runId: string }> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify({ query, model }),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  // Backend returns snake_case { run_id }; expose camelCase to callers.
  const data = await res.json();
  return { runId: data.run_id ?? data.runId };
}

export async function executeResearchPlan(
  query: string,
  projectId?: string,
): Promise<{ runId: string }> {
  const idempotencyKey = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const res = await fetch(`${API_BASE}/api/research/execute`, {
    method: 'POST',
    headers: { ...(await getHeaders()), 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ query, ...(projectId ? { project_id: projectId } : {}) }),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  const data = await res.json();
  return { runId: data.run_id ?? data.runId };
}

export async function cancelRun(runId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function fetchFeed(params?: { limit?: number; offset?: number; q?: string }): Promise<Paper[]> {
  const url = new URL(`${API_BASE}/api/papers`);
  if (params?.limit !== undefined) url.searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined) url.searchParams.set('offset', String(params.offset));
  if (params?.q) url.searchParams.set('q', params.q);

  const res = await fetch(url.toString(), {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return normalizePaperList(await res.json());
}

export async function fetchPaper(id: string): Promise<Paper> {
  const res = await fetch(`${API_BASE}/api/papers/${id}`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return normalizePaper(await res.json());
}

export async function fetchResearchCapabilities(): Promise<ResearchCapabilities> {
  const res = await fetch(`${API_BASE}/api/research/capabilities`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  const data = await res.json();
  return {
    research_synthesis_enabled: data.research_synthesis_enabled === true,
    research_plan_execution_enabled: data.research_plan_execution_enabled === true,
    public_paper_evidence_enabled: data.public_paper_evidence_enabled === true,
  };
}

export async function fetchPublicPaperEvidence(
  paperId: string,
  query: string,
  signal?: AbortSignal,
): Promise<PublicPaperEvidenceResponse> {
  const url = new URL(`${API_BASE}/api/papers/${encodeURIComponent(paperId)}/public-evidence`);
  url.searchParams.set('query', query);
  const res = await fetch(url.toString(), {
    headers: await getHeaders(),
    signal,
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function fetchPaperStatusWatch(id: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/papers/${encodeURIComponent(id)}/status-watch`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  const data = await res.json();
  return data.watching === true;
}

export async function setPaperStatusWatch(id: string, watching: boolean): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/papers/${encodeURIComponent(id)}/status-watch`, {
    method: watching ? 'POST' : 'DELETE',
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  const data = await res.json();
  return data.watching === true;
}

export async function fetchImplementationPlan(paperId: string): Promise<ImplementationPlan> {
  const res = await fetch(
    `${API_BASE}/api/implementations/${encodeURIComponent(paperId)}/plan`,
    { headers: await getHeaders() },
  );
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function fetchImplementationExport(paperId: string): Promise<string> {
  const res = await fetch(
    `${API_BASE}/api/implementations/${encodeURIComponent(paperId)}/export`,
    { headers: await getHeaders() },
  );
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.text();
}

export async function fetchPaperCode(id: string): Promise<{ repos: { url: string; stars: number }[] }> {
  const res = await fetch(`${API_BASE}/api/papers/${id}/code`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function savePaper(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/papers/${id}/save`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify({ dismissed: false }),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
}

export async function unsavePaper(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/papers/${id}/save`, {
    method: 'DELETE',
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
}

export async function dismissPaper(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/papers/${id}/save`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify({ dismissed: true }),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
}

export async function fetchSavedPapers(): Promise<Paper[]> {
  const res = await fetch(`${API_BASE}/api/papers/saved`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return normalizePaperList(await res.json());
}

export async function fetchPrefs(): Promise<UserPrefs> {
  const res = await fetch(`${API_BASE}/api/prefs`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function updatePrefs(prefs: UserPrefs): Promise<UserPrefs> {
  const res = await fetch(`${API_BASE}/api/prefs`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify(prefs),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export async function fetchGraphData(id: string): Promise<{ nodes: unknown[]; edges: unknown[] }> {
  const res = await fetch(`${API_BASE}/api/graph/${id}`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export type StreamSearchEvent = AgentStep | PaperSearchResult | ResearchPlanExecutionResult | ResearchRunCancelledEvent;

export interface StreamSearchCallbacks {
  onEvent: (event: StreamSearchEvent, eventId?: string) => void;
  onLastEventId?: (eventId: string | undefined) => void;
  onTerminalError?: (err: Error) => void;
  onTransportError?: (err: Error) => void;
}

interface SseMessage {
  event: string;
  data: string;
  id?: string;
}

/** Incremental parser for UTF-8 SSE chunks, including split CRLF sequences. */
class SseParser {
  private buffer = '';
  private dataLines: string[] = [];
  private eventName = '';
  private lastEventId: string | undefined;

  constructor(
    private readonly onMessage: (message: SseMessage) => void,
    private readonly onLastEventId?: (eventId: string | undefined) => void,
  ) {}

  push(chunk: string, flush = false): void {
    this.buffer += chunk;
    let start = 0;
    while (start < this.buffer.length) {
      let end = start;
      while (end < this.buffer.length && this.buffer[end] !== '\r' && this.buffer[end] !== '\n') end += 1;
      if (end === this.buffer.length) break;

      const delimiter = this.buffer[end];
      if (delimiter === '\r' && end === this.buffer.length - 1 && !flush) break;
      this.processLine(this.buffer.slice(start, end));
      start = end + (delimiter === '\r' && this.buffer[end + 1] === '\n' ? 2 : 1);
    }
    this.buffer = this.buffer.slice(start);

    if (flush) {
      if (this.buffer.length > 0) this.processLine(this.buffer);
      this.buffer = '';
      this.dispatch();
    }
  }

  private processLine(line: string): void {
    if (line === '') {
      this.dispatch();
      return;
    }
    if (line.startsWith(':')) return;

    const colon = line.indexOf(':');
    const fieldName = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    if (fieldName === 'data') {
      this.dataLines.push(value);
    } else if (fieldName === 'event') {
      this.eventName = value;
    } else if (fieldName === 'id' && !value.includes('\0')) {
      if (value !== this.lastEventId) {
        this.lastEventId = value;
        this.onLastEventId?.(this.lastEventId || undefined);
      }
    }
  }

  private dispatch(): void {
    if (this.dataLines.length > 0) {
      this.onMessage({
        event: this.eventName || 'message',
        data: this.dataLines.join('\n'),
        id: this.lastEventId || undefined,
      });
    }
    this.dataLines = [];
    this.eventName = '';
  }
}

/**
 * Open one authenticated fetch-based SSE connection. The returned disposer is
 * synchronous so callers can abort both session creation and stream reading
 * during component cleanup. Reconnects should call this again to mint a fresh
 * short-lived session token and pass the latest `lastEventId` in options.
 */
export function streamSearch(
  runId: string,
  callbacks: StreamSearchCallbacks,
  options: { lastEventId?: string } = {},
): () => void {
  const controller = new AbortController();
  let disposed = false;
  let terminal = false;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let cursor = options.lastEventId;

  const dispose = () => {
    if (disposed) return;
    disposed = true;
    controller.abort();
    void reader?.cancel().catch(() => undefined);
  };

  const updateCursor = (eventId: string | undefined) => {
    cursor = eventId;
    callbacks.onLastEventId?.(eventId);
  };

  const failTerminal = (error: Error) => {
    if (disposed || terminal) return;
    terminal = true;
    callbacks.onTerminalError?.(error);
    dispose();
  };

  const handleMessage = (message: SseMessage) => {
    if (disposed || terminal) return;
    if (message.id !== undefined) updateCursor(message.id);
    try {
      if (message.event === 'agent_step') {
        callbacks.onEvent(normalizeAgentStep(JSON.parse(message.data)), message.id);
      } else if (message.event === 'result') {
        callbacks.onEvent(normalizeResultEvent(JSON.parse(message.data)), message.id);
        terminal = true;
        dispose();
      } else if (message.event === 'cancelled') {
        const payload = JSON.parse(message.data) as { run_id?: string };
        callbacks.onEvent({ run_id: payload.run_id ?? runId, status: 'cancelled' }, message.id);
        terminal = true;
        dispose();
      } else if (message.event === 'error') {
        let errorMessage = 'Research run failed';
        try {
          const payload = JSON.parse(message.data) as { message?: string };
          if (typeof payload.message === 'string' && payload.message) errorMessage = payload.message;
        } catch {
          // Keep the generic terminal message for malformed error payloads.
        }
        failTerminal(new Error(errorMessage));
      }
    } catch {
      failTerminal(new Error(`Invalid ${message.event || 'SSE'} event from the server`));
    }
  };

  const run = async () => {
    try {
      const userToken = await getJWT();
      if (disposed) return;
      if (!userToken) throw new Error('Your session may have expired. Please sign in again.');

      const sessionRes = await fetch(`${API_BASE}/api/stream/session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${userToken}`,
        },
        signal: controller.signal,
      });
      if (!sessionRes.ok) throw new Error(`Failed to create SSE session (${sessionRes.status})`);
      const sessionPayload = await sessionRes.json() as { session_token?: unknown };
      if (disposed) return;
      if (typeof sessionPayload.session_token !== 'string' || sessionPayload.session_token.length === 0) {
        throw new Error('SSE session response did not include a token');
      }

      const streamHeaders: Record<string, string> = {
        Accept: 'text/event-stream',
        Authorization: `Bearer ${sessionPayload.session_token}`,
      };
      if (cursor) streamHeaders['Last-Event-ID'] = cursor;
      const response = await fetch(`${API_BASE}/api/stream/${encodeURIComponent(runId)}`, {
        method: 'GET',
        headers: streamHeaders,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`SSE connection failed (${response.status})`);
      if (!response.body) throw new Error('SSE response did not include a readable stream');

      reader = response.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SseParser(handleMessage, updateCursor);
      while (!disposed) {
        const { done, value } = await reader.read();
        if (done) {
          parser.push(decoder.decode(), true);
          break;
        }
        parser.push(decoder.decode(value, { stream: true }));
      }
      if (!disposed && !terminal) throw new Error('SSE connection ended before the run completed');
    } catch (error) {
      if (!disposed && !terminal) {
        callbacks.onTransportError?.(error instanceof Error ? error : new Error('SSE transport failed'));
        dispose();
      }
    } finally {
      try {
        reader?.releaseLock();
      } catch {
        // Reader may already have been cancelled during cleanup.
      }
    }
  };

  void run();
  return dispose;
}
