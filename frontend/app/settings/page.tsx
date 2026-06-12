'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ModelSelector } from '@/components/ModelSelector';
import { useAppStore } from '@/store/useAppStore';
import { fetchPrefs, updatePrefs } from '@/lib/api';

export default function SettingsPage() {
  const { selectedModel, setUserPrefs } = useAppStore();
  const queryClient = useQueryClient();
  const [interests, setInterests] = useState('');

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
        </div>
      </div>
    </main>
  );
}
