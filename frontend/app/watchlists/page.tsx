'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createWatchlist,
  deleteWatchlist,
  fetchWatchedProjects,
  fetchWatchlists,
  updateWatchlist,
  type Watchlist,
} from '@/lib/monitoring-api';

function formatDate(value: string | null): string {
  if (!value) return 'Not checked yet';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not checked yet' : `Last checked ${date.toLocaleString()}`;
}

export default function WatchlistsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [targetType, setTargetType] = useState<'topic' | 'author' | 'citation'>('topic');
  const [projectId, setProjectId] = useState('');
  const [cadence, setCadence] = useState<'daily' | 'weekly'>('daily');
  const [formError, setFormError] = useState<string | null>(null);

  const watches = useQuery({ queryKey: ['watchlists'], queryFn: fetchWatchlists });
  const projects = useQuery({ queryKey: ['projects'], queryFn: fetchWatchedProjects });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['watchlists'] });

  const create = useMutation({
    mutationFn: () => createWatchlist({
      target_type: targetType,
      ...(targetType === 'topic' ? { query: query.trim() } : { target_id: query.trim() }),
      cadence,
      ...(projectId ? { project_id: projectId } : {}),
    }),
    onSuccess: async () => {
      setQuery('');
      setProjectId('');
      setFormError(null);
      await invalidate();
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : 'Could not create this watchlist.'),
  });

  const update = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateWatchlist(id, { enabled }),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteWatchlist, onSuccess: invalidate });

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      setFormError(targetType === 'topic' ? 'Enter a topic to watch.' : 'Enter a Semantic Scholar ID.');
      return;
    }
    create.mutate();
  }

  const watchesError = watches.error instanceof Error ? watches.error.message : null;
  const projectError = projects.error instanceof Error ? projects.error.message : null;

  return (
    <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
      <div className="relative z-10">
        <header className="mb-8">
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">Monitoring</p>
          <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">Watchlists</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-zenith-body">
            Track a topic, an author, or papers citing a research paper. Updates arrive in the in-app notifications list when ingestion runs.
          </p>
        </header>

        <form onSubmit={submit} className="mb-8 space-y-4 surface-card p-5 lg:p-6" aria-label="Create a watchlist">
          <h2 className="font-serif text-xl text-ink-900">New watchlist</h2>
          <div>
            <label htmlFor="watch-type" className="mb-1.5 block text-sm font-medium text-ink-900">What to monitor</label>
            <select id="watch-type" value={targetType} onChange={(event) => setTargetType(event.target.value as typeof targetType)} className="w-full rounded-xl border border-zenith-border bg-white px-3 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none">
              <option value="topic">Topic</option>
              <option value="author">Author (Semantic Scholar)</option>
              <option value="citation">Papers citing a paper (Semantic Scholar)</option>
            </select>
          </div>
          <div>
            <label htmlFor="watch-query" className="mb-1.5 block text-sm font-medium text-ink-900">{targetType === 'topic' ? 'Topic or search phrase' : targetType === 'author' ? 'Semantic Scholar author ID' : 'Semantic Scholar paper ID'}</label>
            <input
              id="watch-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={targetType === 'topic' ? 500 : 200}
              required
              placeholder={targetType === 'topic' ? 'e.g. protein language models' : targetType === 'author' ? 'Paste the author ID from a Semantic Scholar profile URL' : 'Paste the paper ID from a Semantic Scholar paper URL'}
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="watch-project" className="mb-1.5 block text-sm font-medium text-ink-900">Linked project (optional)</label>
              <select
                id="watch-project"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                className="w-full rounded-xl border border-zenith-border bg-white px-3 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none"
              >
                <option value="">All papers</option>
                {(projects.data ?? []).map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
              </select>
              {projectError && <p className="mt-1 text-xs text-amber-700">Project list unavailable; this watchlist will cover all papers.</p>}
              {!projectError && <p className="mt-1 text-xs leading-5 text-zenith-muted">Project context is added to alerts. Monitoring results are global papers from the selected source.</p>}
            </div>
            <div>
              <label htmlFor="watch-cadence" className="mb-1.5 block text-sm font-medium text-ink-900">Check frequency</label>
              <select
                id="watch-cadence"
                value={cadence}
                onChange={(event) => setCadence(event.target.value as 'daily' | 'weekly')}
                className="w-full rounded-xl border border-zenith-border bg-white px-3 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
          </div>
          {formError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{formError}</p>}
          <button type="submit" disabled={create.isPending} className="rounded-xl bg-ink-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:opacity-50">
            {create.isPending ? 'Creating…' : 'Create watchlist'}
          </button>
        </form>

        <section aria-labelledby="active-watchlists-heading">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="active-watchlists-heading" className="font-serif text-xl text-ink-900">Your watchlists</h2>
            <button type="button" onClick={() => void watches.refetch()} className="text-xs font-semibold text-zenith-body underline underline-offset-4 hover:text-ink-900">Refresh</button>
          </div>
          {watches.isLoading && <p role="status" className="py-6 text-sm text-zenith-muted">Loading watchlists…</p>}
          {watchesError && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Could not load watchlists: {watchesError}</p>}
          {!watches.isLoading && !watchesError && (watches.data?.length ?? 0) === 0 && (
              <div className="surface-card p-6 text-sm text-zenith-muted">No watchlists yet. Add a target above to receive in-app updates as matching papers are found.</div>
          )}
          <ul className="space-y-3">
            {(watches.data ?? []).map((watch: Watchlist) => (
              <li key={watch.id} className="surface-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <h3 className="break-words font-medium text-ink-900">{watch.target_type === 'citation' ? `Citing: ${watch.query}` : watch.query}</h3>
                  <p className="mt-1 text-xs text-zenith-muted">
                    {watch.target_type === 'topic' ? 'Topic' : watch.target_type === 'author' ? 'Author' : 'Citation neighborhood'} · {watch.cadence === 'weekly' ? 'Weekly' : 'Daily'} · {watch.project_id ? (
                      <>Linked project: <Link href={`/projects/${encodeURIComponent(watch.project_id)}` as Route} className="font-medium underline underline-offset-2">{(projects.data ?? []).find((project) => project.id === watch.project_id)?.title ?? 'Project'}</Link></>
                    ) : 'All papers'} · {formatDate(watch.last_checked_at)}
                  </p>
                  {!watch.enabled && <span className="mt-2 inline-block rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800">Paused</span>}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    disabled={update.isPending}
                    onClick={() => update.mutate({ id: watch.id, enabled: !watch.enabled })}
                    className="rounded-lg border border-zenith-border px-3 py-2 text-xs font-semibold text-ink-900 hover:bg-neutral-50 disabled:opacity-50"
                    aria-label={`${watch.enabled ? 'Pause' : 'Resume'} ${watch.query} watchlist`}
                  >{watch.enabled ? 'Pause' : 'Resume'}</button>
                  <button
                    type="button"
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(watch.id)}
                    className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                    aria-label={`Delete ${watch.query} watchlist`}
                  >Delete</button>
                </div>
              </li>
            ))}
          </ul>
          {(update.error || remove.error) && <p role="alert" className="mt-3 text-sm text-red-700">{(update.error ?? remove.error)?.message ?? 'The watchlist could not be updated.'}</p>}
        </section>
        <p className="mt-6 text-xs leading-5 text-zenith-muted">Topic monitoring checks ingested papers. Author and citation monitoring uses Semantic Scholar stable IDs and runs when ingestion executes; provider outages pause that watch’s cursor for retry. New matches appear in your in-app notifications. You can optionally enable email digests in <Link href="/settings" className="font-medium underline underline-offset-2">Settings</Link>.</p>
      </div>
    </main>
  );
}
