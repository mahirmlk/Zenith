import { AgentStep, ImplementationPlan, Paper, PaperSearchResult, UserPrefs } from '@/types';
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
  return res.json();
}

export async function fetchPaper(id: string): Promise<Paper> {
  const res = await fetch(`${API_BASE}/api/papers/${id}`, {
    headers: await getHeaders(),
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
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
  return res.json();
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

export async function streamSearch(
  runId: string,
  onEvent: (event: AgentStep | PaperSearchResult, eventId?: string) => void,
  onError?: (err: Error) => void
) {
  const token = await getJWT();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const sessionRes = await fetch(`${API_BASE}/api/stream/session`, {
    method: 'POST',
    headers,
  });

  if (!sessionRes.ok) {
    if (onError) onError(new Error('Failed to create SSE session'));
    return () => {};
  }

  const { session_token } = await sessionRes.json();
  const evtSource = new EventSource(`${API_BASE}/api/stream/${runId}?token=${encodeURIComponent(session_token)}`);

  evtSource.addEventListener('agent_step', (e: MessageEvent<string>) => {
    try {
      onEvent(JSON.parse(e.data), e.lastEventId || undefined);
    } catch {
      // ignore parse errors
    }
  });

  evtSource.addEventListener('result', (e: MessageEvent<string>) => {
    try {
      onEvent(JSON.parse(e.data), e.lastEventId || undefined);
      evtSource.close();
    } catch {
      // ignore parse errors
    }
  });

  evtSource.addEventListener('error', (event: Event) => {
    const e = event as MessageEvent<string>;
    // The server uses an SSE `error` event for a terminal run failure; native
    // EventSource connection errors have no data. Handle both in one place so
    // a named server error cannot schedule two reconnects.
    if (!e.data) {
      onError?.(new Error('SSE connection error'));
      evtSource.close();
      return;
    }
    try {
      const payload = JSON.parse(e.data) as { message?: string };
      onError?.(new Error(payload.message ?? 'Research run failed'));
    } catch {
      onError?.(new Error('Research run failed'));
    }
    evtSource.close();
  });

  return () => evtSource.close();
}
