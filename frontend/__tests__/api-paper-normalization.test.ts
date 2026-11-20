/// <reference types="vitest/globals" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchPublicPaperEvidence, fetchResearchCapabilities, normalizePaper, normalizePaperSearchResult, streamSearch } from '@/lib/api';
import { getJWT } from '@/lib/auth';

vi.mock('@/lib/auth', () => ({ getJWT: vi.fn().mockResolvedValue(null) }));

const snakePaper = {
  id: 'arxiv:2401.12345',
  title: 'A useful paper',
  abstract: 'Paper abstract',
  authors: ['A. Author'],
  url: 'https://example.test/paper',
  published_at: '2024-01-01T00:00:00Z',
  doi: '10.1234/paper',
  preprint_id: '2401.12345',
  source_version: 2,
  publication_update_type: 'retraction',
  publication_update_doi: '10.9999/notice',
  publication_update_label: 'Retraction',
  publication_update_date: '2026-03-04',
  publication_update_source: 'crossref',
  publication_update_deposit_source: 'retraction-watch',
  publication_update_checked_at: '2026-11-13T00:00:00Z',
  summary_tldr: 'Concise generated summary',
  summary_contributions: ['Contribution one'],
  summary_status: 'abstract_preview',
  summary_fallback_reason: 'per_run_cap',
  relevance_score: 0.8,
  papers_with_code: { repos: [{ url: 'https://github.com/example/repo', stars: 12 }] },
};

describe('paper API normalization', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('maps backend snake_case paper fields and summary provenance', () => {
    expect(normalizePaper(snakePaper)).toMatchObject({
      id: snakePaper.id,
      publishedAt: snakePaper.published_at,
      doi: snakePaper.doi,
      preprintId: snakePaper.preprint_id,
      sourceVersion: snakePaper.source_version,
      publicationUpdateType: 'retraction',
      publicationUpdateDoi: snakePaper.publication_update_doi,
      publicationUpdateLabel: snakePaper.publication_update_label,
      publicationUpdateDate: snakePaper.publication_update_date,
      publicationUpdateSource: 'crossref',
      publicationUpdateDepositSource: 'retraction-watch',
      summaryTldr: snakePaper.summary_tldr,
      summaryContributions: snakePaper.summary_contributions,
      summaryStatus: 'abstract_preview',
      summaryFallbackReason: 'per_run_cap',
      relevanceScore: 0.8,
      papersWithCode: snakePaper.papers_with_code,
    });
  });

  it('keeps missing provenance absent and maps invalid status and reason values to unknown', () => {
    expect(normalizePaper({ ...snakePaper, summary_status: 'unexpected', summary_fallback_reason: 'other' }))
      .toMatchObject({ summaryStatus: 'unknown', summaryFallbackReason: null });
    expect(normalizePaper({ id: 'p', title: 'P', abstract: '', authors: [], url: '' }))
      .toMatchObject({ summaryFallbackReason: null });
    expect(normalizePaper({ id: 'p', title: 'P', abstract: '', authors: [], url: '' }).summaryStatus).toBeUndefined();
  });

  it('fails closed on missing or invalid preprint identity and version metadata', () => {
    expect(normalizePaper({ id: '2401.12345v2', title: 'P', abstract: '', authors: [], url: '' }))
      .toMatchObject({ preprintId: null, sourceVersion: null });
    expect(normalizePaper({ ...snakePaper, source_version: 0 }))
      .toMatchObject({ sourceVersion: null });
    expect(normalizePaper({ ...snakePaper, source_version: 2.5 }))
      .toMatchObject({ sourceVersion: null });
  });

  it('does not surface unknown publication update types or sources', () => {
    expect(normalizePaper({
      ...snakePaper,
      publication_update_type: 'correction',
      publication_update_source: 'untrusted',
      publication_update_deposit_source: 'untrusted',
    })).toMatchObject({
      publicationUpdateType: null,
      publicationUpdateSource: null,
      publicationUpdateDepositSource: null,
    });
  });

  it('keeps missing or unsupported deposit sources unknown', () => {
    expect(normalizePaper({ ...snakePaper, publication_update_deposit_source: 'indexing-service' }))
      .toMatchObject({ publicationUpdateDepositSource: null });
    expect(normalizePaper({ id: 'p', title: 'P', abstract: '', authors: [], url: '' }))
      .toMatchObject({ publicationUpdateDepositSource: null });
  });

  it('normalizes paper search result fields', () => {
    expect(normalizePaperSearchResult({ run_id: 'run-123', papers: [snakePaper] })).toMatchObject({
      runId: 'run-123',
      papers: [{ summaryStatus: 'abstract_preview', summaryFallbackReason: 'per_run_cap' }],
    });
  });

  it('fetches public paper evidence with authenticated query parameters', async () => {
    vi.mocked(getJWT).mockResolvedValue('user-token');
    const payload = {
      paper_id: 'arxiv:2601.12345',
      preprint_id: '2601.12345',
      version: 2,
      title: 'A Test Paper',
      source_url: 'https://arxiv.org/abs/2601.12345',
      license_url: 'https://creativecommons.org/licenses/by/4.0/',
      license_name: 'CC BY 4.0',
      attribution: 'Authors of A Test Paper',
      evidence: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await fetchPublicPaperEvidence('arxiv:2601.12345', 'dataset & benchmark');

    const requestUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestUrl.pathname).toBe('/api/papers/arxiv%3A2601.12345/public-evidence');
    expect(requestUrl.searchParams.get('query')).toBe('dataset & benchmark');
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer user-token' });
    expect(response).toEqual(payload);
  });

  it('exposes the public-paper evidence capability as opt-in only', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      research_synthesis_enabled: true,
      research_plan_execution_enabled: true,
      public_paper_evidence_enabled: true,
    }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchResearchCapabilities()).resolves.toEqual({
      research_synthesis_enabled: true,
      research_plan_execution_enabled: true,
      public_paper_evidence_enabled: true,
    });
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
    }), { status: 200 }));
    await expect(fetchResearchCapabilities()).resolves.toEqual({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: false,
    });
  });

  it('uses authenticated fetch streaming and parses split CRLF, multiline data, and event ids', async () => {
    vi.mocked(getJWT).mockResolvedValue('user-jwt');
    const chunks = [
      'id: 41\r',
      '\nevent: agent_step\r\ndata: {"agent":"research",\r\n',
      'data: "status":"started"}\r\n\r\nid: 42\n',
      'event: result\ndata: ',
      `${JSON.stringify({ run_id: 'run-123', papers: [snakePaper] })}\n\n`,
    ];
    const encoder = new TextEncoder();
    const streamResponse = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }), { headers: { 'Content-Type': 'text/event-stream' } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ session_token: 'one-use-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(streamResponse);
    vi.stubGlobal('fetch', fetchMock);

    const receivedEvents: unknown[] = [];
    const eventIds: string[] = [];
    let resolveResult: (() => void) | undefined;
    const resultReceived = new Promise<void>((resolve) => { resolveResult = resolve; });
    const stop = streamSearch('run-123', {
      onEvent: (event, eventId) => {
        receivedEvents.push(event);
        if (eventId) eventIds.push(eventId);
        if ('papers' in event) resolveResult?.();
      },
      onLastEventId: (eventId) => { if (eventId) eventIds.push(`cursor:${eventId}`); },
    }, { lastEventId: '40' });

    await resultReceived;
    stop();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const sessionRequest = fetchMock.mock.calls[0];
    expect(sessionRequest?.[0]).toContain('/api/stream/session');
    expect((sessionRequest?.[1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer user-jwt' });
    const streamRequest = fetchMock.mock.calls[1];
    expect(streamRequest?.[0]).toContain('/api/stream/run-123');
    expect(streamRequest?.[0]).not.toContain('token=');
    expect((streamRequest?.[1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer one-use-token',
      'Last-Event-ID': '40',
      Accept: 'text/event-stream',
    });
    expect(receivedEvents[0]).toMatchObject({ agent: 'research', status: 'started' });
    expect(receivedEvents[1]).toMatchObject({ runId: 'run-123', papers: [{ id: snakePaper.id }] });
    expect(eventIds).toContain('cursor:41');
    expect(eventIds).toContain('cursor:42');
    expect(eventIds).toContain('41');
    expect(eventIds).toContain('42');
  });

  it('aborts session exchange when the stream is disposed before the response arrives', async () => {
    vi.mocked(getJWT).mockResolvedValue('user-jwt');
    let sessionSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      sessionSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((_resolve, reject) => {
        sessionSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const stop = streamSearch('run-123', { onEvent: vi.fn() });
    await Promise.resolve();
    stop();

    expect(sessionSignal?.aborted).toBe(true);
  });

  it('mints a new session token after a transport disconnect and resumes from the supplied cursor', async () => {
    vi.mocked(getJWT).mockResolvedValue('user-jwt');
    const emptyStream = () => new Response(new ReadableStream<Uint8Array>({ start(controller) { controller.close(); } }));
    const resultStream = () => new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(`event: result\nid: 52\ndata: ${JSON.stringify({ run_id: 'run-123', papers: [snakePaper] })}\n\n`));
        controller.close();
      },
    }));
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ session_token: 'session-token-1' }), { status: 200 }))
      .mockResolvedValueOnce(emptyStream())
      .mockResolvedValueOnce(new Response(JSON.stringify({ session_token: 'session-token-2' }), { status: 200 }))
      .mockResolvedValueOnce(resultStream());
    vi.stubGlobal('fetch', fetchMock);
    let resolveDisconnect: (() => void) | undefined;
    const disconnected = new Promise<void>((resolve) => { resolveDisconnect = resolve; });
    const onTransportError = vi.fn(() => resolveDisconnect?.());
    streamSearch('run-123', { onEvent: vi.fn(), onTransportError });
    await disconnected;

    let resolveResult: (() => void) | undefined;
    const resultReceived = new Promise<void>((resolve) => { resolveResult = resolve; });
    streamSearch('run-123', { onEvent: (event) => { if ('papers' in event) resolveResult?.(); } }, { lastEventId: '51' });
    await resultReceived;

    expect(onTransportError).toHaveBeenCalledWith(expect.objectContaining({ message: 'SSE connection ended before the run completed' }));
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer session-token-1' });
    expect((fetchMock.mock.calls[3]?.[1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer session-token-2',
      'Last-Event-ID': '51',
    });
  });

  it('keeps named terminal server errors separate from transport failures', async () => {
    vi.mocked(getJWT).mockResolvedValue('user-jwt');
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: error\ndata: {"message":"Worker failed"}\n\n'));
        controller.close();
      },
    }));
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ session_token: 'one-use-token' }), { status: 200 }))
      .mockResolvedValueOnce(response));
    const onTerminalError = vi.fn();
    const onTransportError = vi.fn();
    let resolveError: (() => void) | undefined;
    const errorReceived = new Promise<void>((resolve) => { resolveError = resolve; });

    streamSearch('run-123', {
      onEvent: vi.fn(),
      onTerminalError: (error) => { onTerminalError(error); resolveError?.(); },
      onTransportError,
    });
    await errorReceived;

    expect(onTerminalError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Worker failed' }));
    expect(onTransportError).not.toHaveBeenCalled();
  });
});
