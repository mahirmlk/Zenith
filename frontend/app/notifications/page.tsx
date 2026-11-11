'use client';

import Link from 'next/link';
import type { Route } from 'next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchNotifications, markNotificationsRead, type AppNotification } from '@/lib/monitoring-api';

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function NotificationsPage() {
  const client = useQueryClient();
  const notifications = useQuery({ queryKey: ['notifications'], queryFn: fetchNotifications });
  const markRead = useMutation({
    mutationFn: markNotificationsRead,
    onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }),
  });
  const unreadCount = (notifications.data ?? []).filter((item) => !item.read_at).length;
  const error = notifications.error instanceof Error ? notifications.error.message : null;

  return (
    <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
      <div className="relative z-10">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">Monitoring</p>
            <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">Notifications</h1>
            <p className="mt-3 text-sm text-zenith-body">In-app updates for papers matching your watchlists.</p>
          </div>
          <button
            type="button"
            disabled={unreadCount === 0 || markRead.isPending}
            onClick={() => markRead.mutate()}
            className="rounded-xl border border-zenith-border px-4 py-2.5 text-xs font-semibold text-ink-900 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
          >{markRead.isPending ? 'Marking read…' : 'Mark all as read'}</button>
        </header>

        {notifications.isLoading && <p role="status" className="py-6 text-sm text-zenith-muted">Loading notifications…</p>}
        {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Could not load notifications: {error}</p>}
        {markRead.error && <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Could not mark notifications as read. Please try again.</p>}
        {!notifications.isLoading && !error && (notifications.data?.length ?? 0) === 0 && (
          <div className="surface-card p-6 text-sm text-zenith-muted">No notifications yet. Create a watchlist to follow new matching papers.</div>
        )}
        <ul className="space-y-3">
          {(notifications.data ?? []).map((item: AppNotification) => (
            <li key={item.id} className={`surface-card flex gap-3 p-4 ${item.read_at ? '' : 'border-l-4 border-l-zenith-secondary'}`}>
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.read_at ? 'bg-transparent' : 'bg-zenith-secondary'}`} aria-hidden="true" />
              <article className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h2 className="font-medium text-ink-900">{item.title}</h2>
                  <time className="text-xs text-zenith-muted" dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                </div>
                {item.body && <p className="mt-1 text-sm leading-6 text-zenith-body">{item.body}</p>}
                {item.paper_id && <Link href={`/paper/${encodeURIComponent(item.paper_id)}`} className="mt-2 inline-block text-xs font-semibold text-ink-900 underline underline-offset-4">Open paper</Link>}
                {item.project_id && <Link href={`/projects/${encodeURIComponent(item.project_id)}` as Route} className="mt-2 inline-block text-xs font-semibold text-ink-900 underline underline-offset-4">Open linked project</Link>}
              </article>
            </li>
          ))}
        </ul>
        {!notifications.isLoading && !error && (notifications.data?.length ?? 0) === 50 && <p className="mt-4 text-center text-xs text-zenith-muted">Showing the 50 most recent notifications.</p>}
      </div>
    </main>
  );
}
