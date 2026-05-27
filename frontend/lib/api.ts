import { AgentStep, Paper, PaperSearchResult } from '@/types';
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
  return res.json();
}

export async function fetchFeed(params?: { limit?: number; offset?: number }): Promise<Paper[]> {
  const url = new URL(`${API_BASE}/api/papers`);
  if (params?.limit !== undefined) url.searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined) url.searchParams.set('offset', String(params.offset));

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
  });
  if (!res.ok) {
    handleAuthRedirect(res);
    throw new ApiError(await parseError(res), res.status);
  }
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

export function streamSearch(runId: string, onEvent: (event: AgentStep | PaperSearchResult) => void, onError?: (err: Error) => void) {
  const evtSource = new EventSource(`${API_BASE}/api/stream/${runId}`);

  evtSource.addEventListener('agent_step', (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      // ignore parse errors
    }
  });

  evtSource.addEventListener('result', (e) => {
    try {
      onEvent(JSON.parse(e.data));
      evtSource.close();
    } catch {
      // ignore parse errors
    }
  });

  evtSource.addEventListener('error', (_e) => {
    if (onError) onError(new Error('SSE error'));
    evtSource.close();
  });

  evtSource.onerror = () => {
    if (onError) onError(new Error('SSE connection error'));
    evtSource.close();
  };

  return () => evtSource.close();
}
