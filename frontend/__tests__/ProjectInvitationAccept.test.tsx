import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InvitationAcceptance from '@/app/projects/invitations/accept/page.client';
import { getJWT, getSession } from '@/lib/auth';
import { supabase } from '@/lib/supabase';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));
vi.mock('@/lib/auth', () => ({ getJWT: vi.fn(), getSession: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser: vi.fn(), verifyOtp: vi.fn(), exchangeCodeForSession: vi.fn() } } }));

const invitationId = '123e4567-e89b-42d3-a456-426614174000';

describe('InvitationAcceptance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSession).mockResolvedValue({ access_token: 'jwt', user: { email: 'invitee@example.org' } } as never);
    vi.mocked(getJWT).mockResolvedValue('jwt');
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({ data: { user: null }, error: null } as never);
    vi.mocked(supabase.auth.verifyOtp).mockResolvedValue({ data: { session: { access_token: 'callback-jwt', user: { email: 'invitee@example.org' } } }, error: null } as never);
    vi.mocked(supabase.auth.exchangeCodeForSession).mockResolvedValue({ data: { session: { access_token: 'callback-jwt', user: { email: 'invitee@example.org' } } }, error: null } as never);
    vi.stubGlobal('fetch', vi.fn());
  });

  it('links to login with validated invitation context when there is no session', async () => {
    vi.mocked(getSession).mockResolvedValue(null as never);
    render(<InvitationAcceptance invitationId={invitationId} />);
    expect(await screen.findByRole('link', { name: 'Sign in to continue' })).toHaveAttribute('href', `/login?invite=${invitationId}`);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('sets a password, accepts with the session JWT, and routes to the project', async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ project_id: '123e4567-e89b-42d3-a456-426614174001', project_title: 'Alpha', role: 'editor', status: 'accepted' }), { status: 200 }));
    render(<InvitationAcceptance invitationId={invitationId} />);
    fireEvent.change(await screen.findByLabelText('Set password (optional)'), { target: { value: 'strong-pass-123' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'strong-pass-123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    await waitFor(() => expect(supabase.auth.updateUser).toHaveBeenCalledWith({ password: 'strong-pass-123' }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/project-invitations/${invitationId}/accept`),
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer jwt' }) }),
    ));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/projects/123e4567-e89b-42d3-a456-426614174001'));
  });

  it('verifies a Supabase invitation token hash before showing acceptance', async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ project_id: '123e4567-e89b-42d3-a456-426614174001', project_title: 'Alpha', role: 'viewer', status: 'accepted' }), { status: 200 }));
    render(<InvitationAcceptance invitationId={invitationId} tokenHash="one-time-token" authType="invite" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));
    await waitFor(() => expect(supabase.auth.verifyOtp).toHaveBeenCalledWith({ token_hash: 'one-time-token', type: 'invite' }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  });

  it('verifies a one-time invite token only once under React StrictMode', async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ project_id: '123e4567-e89b-42d3-a456-426614174001', project_title: 'Alpha', role: 'viewer', status: 'accepted' }), { status: 200 }));
    let finishVerification!: (result: unknown) => void;
    vi.mocked(supabase.auth.verifyOtp).mockImplementation(() => new Promise((resolve) => {
      finishVerification = resolve as (result: unknown) => void;
    }) as never);
    render(<StrictMode><InvitationAcceptance invitationId={invitationId} tokenHash="strictmode-one-time-token" authType="invite" /></StrictMode>);
    await waitFor(() => expect(supabase.auth.verifyOtp).toHaveBeenCalledTimes(1));
    finishVerification({ data: { session: { access_token: 'callback-jwt', user: { email: 'invitee@example.org' } } }, error: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(supabase.auth.verifyOtp).toHaveBeenCalledTimes(1);
  });

  it('shows acceptance API errors and does not navigate', async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Invitation expired.' }), { status: 410 }));
    render(<InvitationAcceptance invitationId={invitationId} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invitation expired.');
    expect(replace).not.toHaveBeenCalled();
  });

  it('rejects passwords shorter than eight characters', async () => {
    render(<InvitationAcceptance invitationId={invitationId} />);
    fireEvent.change(await screen.findByLabelText('Set password (optional)'), { target: { value: 'short' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Password must be at least 8 characters.');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
