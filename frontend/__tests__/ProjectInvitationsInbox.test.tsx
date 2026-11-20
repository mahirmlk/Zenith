import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProjectsPage from '@/app/projects/page';

const mocks = vi.hoisted(() => ({ push: vi.fn(), getJWT: vi.fn(async () => 'test-token') }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth', () => ({ getJWT: mocks.getJWT }));

describe('ProjectsPage invitation inbox', () => {
  afterEach(() => vi.unstubAllGlobals());

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(mocks.getJWT).mockResolvedValue('test-token');
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === '/api/projects') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.pathname === '/api/project-invitations/received') {
        return new Response(JSON.stringify([{
          id: 'invite-1',
          project_id: 'project-1',
          project_title: 'Methods review',
          role: 'editor',
          expires_at: '2026-12-01T00:00:00Z',
        }]), { status: 200 });
      }
      if (url.pathname === '/api/project-invitations/invite-1/accept' && init?.method === 'POST') {
        return new Response(JSON.stringify({ status: 'accepted', project_id: 'project-1' }), { status: 200 });
      }
      return new Response('{}', { status: 404 });
    }));
  });

  it('shows a pending invite and accepts it using the existing verified-email flow', async () => {
    render(<ProjectsPage />);

    expect(await screen.findByText('Methods review')).toBeInTheDocument();
    expect(screen.getByText(/Invited as editor/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Accept invitation to Methods review' }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/projects/project-1'));
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/project-invitations/invite-1/accept',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
