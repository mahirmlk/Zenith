import { getJWT } from './auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class AccountApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'AccountApiError';
  }
}

async function request(path: '/api/account/export' | '/api/account', method: 'GET' | 'DELETE'): Promise<Response> {
  const token = await getJWT();
  if (!token) {
    throw new AccountApiError('Your session has expired. Sign in again and retry.', 401);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json() as { detail?: string; message?: string };
      message = body.detail ?? body.message ?? message;
    } catch {
      // Keep the useful status based message when the server returns no JSON.
    }
    throw new AccountApiError(message, response.status);
  }
  return response;
}

export async function exportAccountData(): Promise<Record<string, unknown>> {
  const response = await request('/api/account/export', 'GET');
  return response.json() as Promise<Record<string, unknown>>;
}

export async function deleteAccount(): Promise<void> {
  await request('/api/account', 'DELETE');
}
