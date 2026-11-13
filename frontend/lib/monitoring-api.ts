import { getJWT } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface Watchlist {
  id: string;
  query: string;
  target_type: 'topic' | 'author' | 'citation';
  target_id: string | null;
  project_id: string | null;
  cadence: 'daily' | 'weekly';
  enabled: boolean;
  last_checked_at: string | null;
}

export interface WatchedProject {
  id: string;
  title: string;
}

export interface AppNotification {
  id: string;
  title: string;
  body: string | null;
  reason_code?: 'topic_term_overlap' | 'author_relation' | 'citation_relation' | null;
  reason_text?: string | null;
  paper_id: string | null;
  project_id?: string | null;
  created_at: string;
  read_at: string | null;
}

export interface NotificationPreferences {
  available: boolean;
  email_opt_in: boolean;
  email_frequency: 'daily' | 'weekly';
  timezone: string;
  suppressed: boolean;
}

export class MonitoringApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'MonitoringApiError';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getJWT();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json() as { detail?: string; message?: string };
      message = body.detail ?? body.message ?? message;
    } catch {
      // Keep a useful status message when the server did not return JSON.
    }
    throw new MonitoringApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function fetchWatchlists(): Promise<Watchlist[]> {
  return request('/api/watchlists');
}

export function createWatchlist(input: {
  query?: string;
  target_type: 'topic' | 'author' | 'citation';
  target_id?: string;
  project_id?: string;
  cadence: 'daily' | 'weekly';
}): Promise<Watchlist[]> {
  return request('/api/watchlists', { method: 'POST', body: JSON.stringify(input) });
}

export function updateWatchlist(
  id: string,
  patch: { enabled?: boolean; cadence?: 'daily' | 'weekly' },
): Promise<Watchlist[]> {
  return request(`/api/watchlists/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export function deleteWatchlist(id: string): Promise<{ status: string }> {
  return request(`/api/watchlists/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function fetchWatchedProjects(): Promise<WatchedProject[]> {
  return request('/api/projects');
}

export function fetchNotifications(): Promise<AppNotification[]> {
  return request('/api/notifications');
}

export function markNotificationsRead(): Promise<{ status: string }> {
  return request('/api/notifications/read', { method: 'POST' });
}

export function markNotificationRead(id: string): Promise<{ status: string }> {
  return request(`/api/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' });
}

export function fetchNotificationPreferences(): Promise<NotificationPreferences> {
  return request('/api/notifications/preferences');
}

export function updateNotificationPreferences(input: Pick<NotificationPreferences, 'email_opt_in' | 'email_frequency' | 'timezone'>): Promise<NotificationPreferences> {
  return request('/api/notifications/preferences', { method: 'PUT', body: JSON.stringify(input) });
}
