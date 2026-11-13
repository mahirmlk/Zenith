'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import type { Session } from '@supabase/supabase-js';
import { getJWT, getSession } from '@/lib/auth';
import { supabase } from '@/lib/supabase';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const authCallbackPromises = new Map<string, Promise<Session | null>>();

interface Acceptance {
  project_id: string;
  project_title: string;
  role: 'editor' | 'viewer';
  status: 'accepted';
}

function resolveAuthSession(tokenHash?: string, authType?: string, code?: string): Promise<Session | null> {
  const callbackKey = tokenHash ? `invite:${tokenHash}` : code ? `code:${code}` : null;
  if (!callbackKey) return getSession();

  const existing = authCallbackPromises.get(callbackKey);
  if (existing) return existing;

  const callbackPromise = (async () => {
    if (tokenHash) {
      if (authType !== 'invite') throw new Error('This invitation link has an invalid authentication type.');
      const { data, error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type: 'invite' });
      if (error) throw error;
      return data.session ?? getSession();
    }
    if (code) {
      const { data, error } = await supabase.auth.exchangeCodeForSession(code);
      if (error) throw error;
      return data.session ?? getSession();
    }
    return getSession();
  })();
  authCallbackPromises.set(callbackKey, callbackPromise);
  return callbackPromise;
}

export default function InvitationAcceptance({
  invitationId,
  tokenHash,
  authType,
  code,
}: { invitationId: string; tokenHash?: string; authType?: string; code?: string }) {
  const router = useRouter();
  const [sessionState, setSessionState] = useState<'loading' | 'authenticated' | 'missing' | 'error'>('loading');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const validInvitation = UUID_PATTERN.test(invitationId);

  useEffect(() => {
    let active = true;
    resolveAuthSession(tokenHash, authType, code).then((session) => {
      if (!active) return;
      if (!session?.access_token) setSessionState('missing');
      else {
        setEmail(session.user.email ?? '');
        setSessionState('authenticated');
      }
    }).catch(() => { if (active) setSessionState('error'); });
    return () => { active = false; };
  }, [authType, code, tokenHash]);

  async function handleAccept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (!validInvitation) {
      setMessage('This invitation link is invalid. Ask the project owner to send a new one.');
      return;
    }
    if (password && password.length < 8) {
      setMessage('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setMessage('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      if (password) {
        const { error } = await supabase.auth.updateUser({ password });
        if (error) throw error;
      }
      const token = await getJWT();
      if (!token) {
        setSessionState('missing');
        return;
      }
      const response = await fetch(`${API_BASE}/api/project-invitations/${encodeURIComponent(invitationId)}/accept`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        let detail = `Could not accept invitation (${response.status}).`;
        try {
          const body = await response.json() as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch { /* retain status-based message */ }
        throw new Error(detail);
      }
      const result = await response.json() as Acceptance;
      if (!UUID_PATTERN.test(result.project_id)) throw new Error('The server returned an invalid project link.');
      if (result.status !== 'accepted') throw new Error('The invitation was not accepted. Refresh and try again.');
      router.replace(`/projects/${encodeURIComponent(result.project_id)}` as Route);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not accept invitation.');
    } finally {
      setBusy(false);
    }
  }

  const loginHref: Route = (validInvitation ? `/login?invite=${encodeURIComponent(invitationId)}` : '/login') as Route;

  return (
    <main className="mx-auto flex min-h-screen max-w-xl items-center px-4 py-12">
      <section className="surface-card w-full p-6 sm:p-8" aria-labelledby="invitation-heading">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Project invitation</p>
        <h1 id="invitation-heading" className="mt-2 font-serif text-2xl text-ink-900">Join a research project</h1>
        {!validInvitation ? (
          <p className="mt-4 text-sm text-red-700" role="alert">This invitation link is invalid. Ask the project owner to send a new one.</p>
        ) : sessionState === 'loading' ? (
          <p role="status" className="mt-4 text-sm text-zenith-muted">Checking your invitation session…</p>
        ) : sessionState === 'error' ? (
          <p role="alert" className="mt-4 text-sm text-red-700">Could not verify your sign-in session. Refresh this page or sign in again.</p>
        ) : sessionState === 'missing' ? (
          <div className="mt-4 space-y-3 text-sm text-zenith-body">
            <p>Sign in with the email address that received the invitation to continue.</p>
            <Link href={loginHref} className="inline-flex rounded-xl bg-ink-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink-800">Sign in to continue</Link>
          </div>
        ) : (
          <form onSubmit={handleAccept} className="mt-4 space-y-4">
            <p className="text-sm text-zenith-body">Signed in as <strong>{email || 'your account'}</strong>. Set a password if this is a new account, then accept the invitation.</p>
            <div>
              <label htmlFor="invite-password" className="mb-1.5 block text-sm font-semibold text-ink-900">Set password (optional)</label>
              <input id="invite-password" type="password" autoComplete="new-password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-sm text-ink-900" />
              <p className="mt-1 text-xs text-zenith-muted">Use at least 8 characters. Leave blank if your account already has a password.</p>
            </div>
            {password && <div>
              <label htmlFor="invite-confirm-password" className="mb-1.5 block text-sm font-semibold text-ink-900">Confirm password</label>
              <input id="invite-confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="w-full rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-sm text-ink-900" />
            </div>}
            {message && <p role="alert" className="text-sm text-red-700">{message}</p>}
            <button type="submit" disabled={busy} className="w-full rounded-xl bg-ink-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink-800 disabled:opacity-50">{busy ? 'Accepting…' : 'Accept invitation'}</button>
          </form>
        )}
        {sessionState === 'authenticated' && message && !validInvitation && <p role="alert" className="mt-3 text-sm text-red-700">{message}</p>}
      </section>
    </main>
  );
}
