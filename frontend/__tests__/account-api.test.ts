import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccountApiError, deleteAccount, exportAccountData } from '@/lib/account-api';

vi.mock('@/lib/auth', () => ({ getJWT: vi.fn(async () => 'user-token') }));

describe('account API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('downloads the authenticated account export response as JSON data', async () => {
    const exportData = { user_id: 'u1', saved_papers: [] };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(exportData), { status: 200 })));

    await expect(exportAccountData()).resolves.toEqual(exportData);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/account\/export$/),
      expect.objectContaining({ method: 'GET', headers: { Authorization: 'Bearer user-token' } }),
    );
  });

  it('preserves a 409 response so the UI can explain active-run retries', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: 'Active research run.' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )));

    const error = await deleteAccount().catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(AccountApiError);
    expect(error).toMatchObject({ status: 409, message: 'Active research run.' });
  });

  it('does not call the API without an authenticated session', async () => {
    const { getJWT } = await import('@/lib/auth');
    vi.mocked(getJWT).mockResolvedValueOnce(null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(exportAccountData()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
