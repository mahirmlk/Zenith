import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WatchlistsPage from '@/app/watchlists/page';
import NotificationsPage from '@/app/notifications/page';
import {
  createWatchlist,
  deleteWatchlist,
  fetchNotifications,
  fetchWatchedProjects,
  fetchWatchlists,
  markNotificationRead,
  markNotificationsRead,
  updateWatchlist,
} from '@/lib/monitoring-api';

vi.mock('@/lib/monitoring-api', () => ({
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  fetchNotifications: vi.fn(),
  fetchWatchedProjects: vi.fn(),
  fetchWatchlists: vi.fn(),
  markNotificationRead: vi.fn(),
  markNotificationsRead: vi.fn(),
  updateWatchlist: vi.fn(),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('monitoring pages', () => {
  beforeEach(() => vi.clearAllMocks());

  it('creates a topic watchlist with its selected cadence', async () => {
    vi.mocked(fetchWatchlists).mockResolvedValue([]);
    vi.mocked(fetchWatchedProjects).mockResolvedValue([]);
    vi.mocked(createWatchlist).mockResolvedValue([]);

    renderWithQuery(<WatchlistsPage />);
    fireEvent.change(screen.getByLabelText('Topic or search phrase'), { target: { value: 'protein models' } });
    fireEvent.change(screen.getByLabelText('Check frequency'), { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create watchlist' }));

    await waitFor(() => expect(createWatchlist).toHaveBeenCalledWith({
      query: 'protein models', cadence: 'weekly',
    }));
  });

  it('lets a user pause an active watchlist', async () => {
    vi.mocked(fetchWatchlists).mockResolvedValue([{
      id: 'watch-1', query: 'protein models', project_id: 'project-1',
      cadence: 'daily', enabled: true, last_checked_at: null,
    }]);
    vi.mocked(fetchWatchedProjects).mockResolvedValue([{ id: 'project-1', title: 'Protein project' }]);
    vi.mocked(updateWatchlist).mockResolvedValue([]);

    renderWithQuery(<WatchlistsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Pause protein models watchlist' }));

    await waitFor(() => expect(updateWatchlist).toHaveBeenCalledWith('watch-1', { enabled: false }));
    expect(screen.getByRole('link', { name: 'Protein project' })).toHaveAttribute('href', '/projects/project-1');
    expect(deleteWatchlist).not.toHaveBeenCalled();
  });

  it('marks notifications read and displays paper links', async () => {
    vi.mocked(fetchNotifications).mockResolvedValue([{
      id: 'notification-1', title: 'New paper found', body: 'Matches your watchlist.',
      paper_id: 'paper-1', project_id: 'project-1', created_at: '2026-11-11T00:00:00Z', read_at: null,
    }]);
    vi.mocked(markNotificationsRead).mockResolvedValue({ status: 'ok' });

    renderWithQuery(<NotificationsPage />);
    await screen.findByText('New paper found');
    fireEvent.click(await screen.findByRole('button', { name: 'Mark all as read' }));

    await waitFor(() => expect(markNotificationsRead).toHaveBeenCalledOnce());
    expect(screen.getByRole('link', { name: 'Open paper' })).toHaveAttribute('href', '/paper/paper-1');
    expect(screen.getByRole('link', { name: 'Open linked project' })).toHaveAttribute('href', '/projects/project-1');
  });

  it('marks one unread notification read without marking all', async () => {
    vi.mocked(fetchNotifications).mockResolvedValue([{
      id: 'notification-2', title: 'Another paper', body: null,
      paper_id: 'paper-2', project_id: null, created_at: '2026-11-11T00:00:00Z', read_at: null,
    }]);
    vi.mocked(markNotificationRead).mockResolvedValue({ status: 'ok' });

    renderWithQuery(<NotificationsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Mark Another paper as read' }));

    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledOnce());
    expect(vi.mocked(markNotificationRead).mock.calls[0]?.[0]).toBe('notification-2');
    expect(markNotificationsRead).not.toHaveBeenCalled();
  });
});
