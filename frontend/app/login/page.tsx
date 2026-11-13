'use client';

import { useState } from 'react';
import { signInWithEmail, signUpWithEmail } from '@/lib/auth';
import { supabase } from '@/lib/supabase';
import Link from 'next/link';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function invitationDestination(): string | null {
  const invitationId = new URLSearchParams(window.location.search).get('invite');
  return invitationId && UUID_PATTERN.test(invitationId)
    ? `/projects/invitations/accept?invitation_id=${encodeURIComponent(invitationId)}`
    : null;
}

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const validatePassword = (value: string): string | null => {
    if (value.length < 6) return 'Password must be at least 6 characters.';
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (isSignUp) {
      const passwordError = validatePassword(password);
      if (passwordError) {
        setError(passwordError);
        return;
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        return;
      }
    }

    setLoading(true);
    try {
      if (isSignUp) {
        const data = await signUpWithEmail(email, password);
        if (data.user?.identities?.length === 0) {
          setError('An account with this email already exists.');
        } else {
          setSuccess('Account created! Please check your email to verify your account before signing in.');
        }
      } else {
        await signInWithEmail(email, password);
        window.location.href = invitationDestination() ?? '/feed';
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Authentication failed';
      if (message.includes('Email not confirmed')) {
        setError('Please verify your email address before signing in. Check your inbox for the confirmation link.');
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = (mode: boolean) => {
    setIsSignUp(mode);
    setError(null);
    setSuccess(null);
    setPassword('');
    setConfirmPassword('');
  };

  const handleOAuth = async (provider: 'google' | 'github') => {
    try {
      const destination = invitationDestination() ?? '/feed';
      await supabase.auth.signInWithOAuth({
        provider,
        options: { redirectTo: `${window.location.origin}${destination}` },
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'OAuth sign in failed');
    }
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center px-4">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
      <div className="relative z-10 w-full max-w-md surface-card p-8 lg:p-10">
        <h1 className="mb-6 font-serif text-[26px] font-normal text-ink-900">
          {isSignUp ? 'Create Account' : 'Sign In'}
        </h1>

        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50/80 p-3 text-[13px] font-medium text-red-700">{error}</div>
        )}

        {success && (
          <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50/80 p-3 text-[13px] font-medium text-emerald-700">{success}</div>
        )}

        <div className="mb-4 space-y-2">
          <button
            type="button"
            onClick={() => handleOAuth('google')}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-[13px] font-semibold text-ink-900 shadow-soft transition duration-200 hover:bg-zenith-surface"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </button>
          <button
            type="button"
            onClick={() => handleOAuth('github')}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-[13px] font-semibold text-ink-900 shadow-soft transition duration-200 hover:bg-zenith-surface"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 1C5.925 1 1 5.925 1 12c0 4.86 3.152 8.983 7.523 10.437.55.101.75-.238.75-.53 0-.262-.009-.955-.014-1.872-3.06.665-3.705-1.475-3.705-1.475-.5-1.27-1.221-1.61-1.221-1.61-.998-.682.076-.668.076-.668 1.104.078 1.684 1.133 1.684 1.133.98 1.68 2.57 1.195 3.198.914.1-.71.384-1.195.698-1.47-2.442-.278-5.01-1.222-5.01-5.437 0-1.2.428-2.183 1.132-2.95-.113-.278-.49-1.397.108-2.91 0 0 .923-.296 3.025 1.127A10.51 10.51 0 0112 5.8c.935.005 1.874.126 2.756.37 2.1-1.423 3.022-1.127 3.022-1.127.6 1.513.222 2.632.11 2.91.705.767 1.13 1.75 1.13 2.95 0 4.226-2.572 5.156-5.022 5.428.395.34.747 1.01.747 2.037 0 1.47-.014 2.657-.014 3.017 0 .295.2.637.757.53C19.85 20.98 23 16.858 23 12c0-6.075-4.925-11-11-11z" />
            </svg>
            Sign in with GitHub
          </button>
        </div>

        <div className="mb-4 flex items-center gap-2">
          <div className="h-px flex-1 bg-zenith-border" />
          <span className="text-[11px] text-zenith-muted-light">or</span>
          <div className="h-px flex-1 bg-zenith-border" />
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-[13px] font-semibold text-ink-900">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-[14px] text-ink-900 shadow-soft placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-[13px] font-semibold text-ink-900">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-[14px] text-ink-900 shadow-soft placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
            />
            {isSignUp && (
              <p className="mt-1 text-[12px] text-zenith-muted">Must be at least 6 characters.</p>
            )}
          </div>
          {isSignUp && (
            <div>
              <label htmlFor="confirmPassword" className="mb-1.5 block text-[13px] font-semibold text-ink-900">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-xl border border-zenith-border bg-white px-4 py-2.5 text-[14px] text-ink-900 shadow-soft placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
              />
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-ink-900 py-2.5 font-semibold text-white shadow-button transition duration-200 hover:bg-ink-800 disabled:opacity-50"
          >
            {loading ? 'Please wait...' : isSignUp ? 'Sign Up' : 'Sign In'}
          </button>
        </form>

        <div className="mt-6 text-center text-[13px] text-zenith-body">
          {isSignUp ? (
            <>
              Already have an account?{' '}
              <button onClick={() => toggleMode(false)} className="font-semibold text-zenith-secondary transition duration-150 hover:text-zenith-accent">
                Sign in
              </button>
            </>
          ) : (
            <>
              Don&apos;t have an account?{' '}
              <button onClick={() => toggleMode(true)} className="font-semibold text-zenith-secondary transition duration-150 hover:text-zenith-accent">
                Sign up
              </button>
            </>
          )}
        </div>

        <div className="mt-4 text-center">
          <Link href="/" className="text-[13px] text-zenith-muted transition duration-150 hover:text-ink-900">
            Back to home
          </Link>
        </div>
      </div>
    </main>
  );
}
