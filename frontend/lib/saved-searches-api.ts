import { getJWT } from '@/lib/auth';
import type { SavedSearch } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getJWT();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') window.location.href = '/login';
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based message when an error response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export interface SavedSearchCreate {
  name: string;
  query: string;
  model?: string | null;
  project_id: string;
}

export interface SavedSearchUpdate {
  name: string;
  query: string;
  model: string | null;
}

export function fetchSavedSearches(): Promise<SavedSearch[]> {
  return request<SavedSearch[]>('/api/saved-searches');
}

export function createSavedSearch(input: SavedSearchCreate): Promise<SavedSearch> {
  return request<SavedSearch>('/api/saved-searches', { method: 'POST', body: JSON.stringify(input) });
}

export function updateSavedSearch(id: string, input: SavedSearchUpdate): Promise<SavedSearch> {
  return request<SavedSearch>(`/api/saved-searches/${encodeURIComponent(id)}`, {
    method: 'PATCH', body: JSON.stringify(input),
  });
}

export function deleteSavedSearch(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/saved-searches/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function runSavedSearch(id: string): Promise<{ run_id: string }> {
  return request<{ run_id: string }>(`/api/saved-searches/${encodeURIComponent(id)}/run`, { method: 'POST' });
}
