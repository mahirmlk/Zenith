'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ModelSelector } from '@/components/ModelSelector';
import EmailNotificationPreferences from '@/components/EmailNotificationPreferences';
import { useAppStore } from '@/store/useAppStore';
import { fetchPrefs, updatePrefs } from '@/lib/api';
import { AccountApiError, deleteAccount, exportAccountData } from '@/lib/account-api';
import { clearLocalSession } from '@/lib/auth';

export default function SettingsPage() {
  const { selectedModel, setUserPrefs } = useAppStore();
  const queryClient = useQueryClient();
  const [interests, setInterests] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  const [accountMessage, setAccountMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null);

  const { data: prefs } = useQuery({
    queryKey: ['prefs'],
    queryFn: fetchPrefs,
  });

  useEffect(() => {
    if (prefs) {
      setUserPrefs(prefs);
      if (prefs.interests) setInterests(prefs.interests.join(', '));
    }
  }, [prefs, setUserPrefs]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updatePrefs({
        preferredModel: selectedModel,
        interests: interests.split(',').map((s) => s.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prefs'] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: exportAccountData,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `zenith-account-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setAccountMessage({ kind: 'success', text: 'Your account export has downloaded.' });
    },
    onError: (error) => setAccountMessage({ kind: 'error', text: error.message }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: async () => {
      try {
        await clearLocalSession();
      } catch {
        // The account has already been deleted server-side; still leave the
        // authenticated settings page and prevent a stale local session.
      } finally {
        window.location.replace('/login?accountDeletionAccepted=1');
      }
    },
    onError: (error) => {
      const text = error instanceof AccountApiError && error.status === 409
        ? 'A research run is still shutting down. Wait briefly, then retry account deletion.'
        : error.message;
      setAccountMessage({ kind: 'error', text });
    },
  });

  const confirmDelete = () => {
    if (deleteConfirmation === 'DELETE') {
      setAccountMessage(null);
      deleteMutation.mutate();
    }
  };

  return (
    <main className="relative mx-auto max-w-2xl px-4 py-8 pt-28">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />

      <div className="relative z-10">
        <div className="mb-8">
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">
            Preferences
          </p>
          <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">
            Settings
          </h1>
        </div>

        <div className="space-y-6 surface-card p-6 lg:p-8">
          <div>
            <h2 className="mb-3 font-serif text-[18px] font-normal text-ink-900">Model</h2>
            <ModelSelector />
          </div>

          <div className="border-t border-zenith-border/60 pt-6">
            <h2 className="mb-3 font-serif text-[18px] font-normal text-ink-900">Research Interests</h2>
            <p className="mb-3 text-[13px] text-zenith-muted">
              Comma-separated topics you are interested in.
            </p>
            <textarea
              value={interests}
              onChange={(e) => setInterests(e.target.value)}
              placeholder="e.g. diffusion models, NLP, reinforcement learning"
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-3 text-[14px] text-ink-900 shadow-soft placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
              rows={3}
            />
          </div>

          {saveMutation.isError && (
            <div className="rounded-xl border border-red-200 bg-red-50/80 p-3 text-[13px] font-medium text-red-700">
              Failed to save preferences. Please try again.
            </div>
          )}

          {saveMutation.isSuccess && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-3 text-[13px] font-medium text-emerald-700">
              Preferences saved.
            </div>
          )}

          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="rounded-xl bg-ink-900 px-5 py-2.5 text-[13px] font-semibold text-white shadow-button transition duration-200 hover:bg-ink-800 disabled:opacity-50"
          >
            {saveMutation.isPending ? 'Saving...' : 'Save Preferences'}
          </button>

          <EmailNotificationPreferences />
        </div>

        <section aria-labelledby="account-data-heading" className="mt-6 surface-card p-6 lg:p-8">
          <h2 id="account-data-heading" className="mb-2 font-serif text-[20px] font-normal text-ink-900">
            Account data
          </h2>
          <p className="mb-5 text-[13px] leading-6 text-zenith-muted">
            Download a JSON copy of your account data, or request permanent deletion. Once accepted, you will be signed out while cleanup continues and retries safely in the background.
          </p>

          {accountMessage && (
            <div
              role={accountMessage.kind === 'error' ? 'alert' : 'status'}
              className={`mb-4 rounded-xl border p-3 text-[13px] font-medium ${
                accountMessage.kind === 'error'
                  ? 'border-red-200 bg-red-50/80 text-red-700'
                  : 'border-emerald-200 bg-emerald-50/80 text-emerald-700'
              }`}
            >
              {accountMessage.text}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => { setAccountMessage(null); exportMutation.mutate(); }}
              disabled={exportMutation.isPending || deleteMutation.isPending}
              className="rounded-xl border border-zenith-border px-4 py-2.5 text-[13px] font-semibold text-ink-900 transition hover:bg-white disabled:opacity-50"
            >
              {exportMutation.isPending ? 'Preparing export…' : 'Download account data'}
            </button>
            <button
              type="button"
              onClick={() => { setDeleteConfirmation(''); setShowDeleteConfirmation(true); setAccountMessage(null); }}
              aria-expanded={showDeleteConfirmation}
              className="rounded-xl border border-red-200 px-4 py-2.5 text-[13px] font-semibold text-red-700 transition hover:bg-red-50"
            >
              Delete account…
            </button>
          </div>

          {showDeleteConfirmation && (
            <div className="mt-5 rounded-xl border border-red-200 bg-red-50/60 p-4">
              <p className="mb-3 text-[13px] leading-6 text-red-900">
                This permanently removes your account and stored account data. Type <strong>DELETE</strong> to continue.
              </p>
              <label htmlFor="delete-account-confirmation" className="mb-2 block text-[12px] font-semibold text-red-900">
                Confirmation
              </label>
              <input
                id="delete-account-confirmation"
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                autoComplete="off"
                className="mb-3 w-full rounded-lg border border-red-200 bg-white px-3 py-2 text-[14px] text-ink-900 focus:outline-none focus:ring-2 focus:ring-red-400"
              />
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={confirmDelete}
                  disabled={deleteConfirmation !== 'DELETE' || deleteMutation.isPending || exportMutation.isPending}
                  className="rounded-xl bg-red-700 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-red-800 disabled:opacity-50"
                >
                  {deleteMutation.isPending ? 'Deleting account…' : 'Permanently delete account'}
                </button>
                <button
                  type="button"
                  onClick={() => { setDeleteConfirmation(''); setShowDeleteConfirmation(false); }}
                  disabled={deleteMutation.isPending}
                  className="rounded-xl border border-zenith-border px-4 py-2.5 text-[13px] font-semibold text-ink-900 transition hover:bg-white disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
