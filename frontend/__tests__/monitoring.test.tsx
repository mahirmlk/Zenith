import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WatchlistsPage from '@/app/watchlists/page';
import NotificationsPage from '@/app/notifications/page';
import EmailNotificationPreferences from '@/components/EmailNotificationPreferences';
import {
  createWatchlist,
  deleteWatchlist,
  fetchNotifications,
  fetchNotificationPreferences,
  fetchWatchedProjects,
  fetchWatchlists,
  markNotificationRead,
  markNotificationsRead,
  updateWatchlist,
  updateNotificationPreferences,
} from '@/lib/monitoring-api';

vi.mock('@/lib/monitoring-api', () => ({
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  fetchNotifications: vi.fn(),
  fetchNotificationPreferences: vi.fn(),
  fetchWatchedProjects: vi.fn(),
  fetchWatchlists: vi.fn(),
  markNotificationRead: vi.fn(),
  markNotificationsRead: vi.fn(),
  updateWatchlist: vi.fn(),
  updateNotificationPreferences: vi.fn(),
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
      target_type: 'topic', query: 'protein models', cadence: 'weekly',
    }));
  });

  it('creates an author watchlist with a stable Semantic Scholar ID', async () => {
    vi.mocked(fetchWatchlists).mockResolvedValue([]);
    vi.mocked(fetchWatchedProjects).mockResolvedValue([]);
    vi.mocked(createWatchlist).mockResolvedValue([]);

    renderWithQuery(<WatchlistsPage />);
    fireEvent.change(screen.getByLabelText('What to monitor'), { target: { value: 'author' } });
    fireEvent.change(screen.getByLabelText('Semantic Scholar author ID'), { target: { value: '12345' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create watchlist' }));

    await waitFor(() => expect(createWatchlist).toHaveBeenCalledWith({
      target_type: 'author', target_id: '12345', cadence: 'daily',
    }));
  });

  it('lets a user pause an active watchlist', async () => {
    vi.mocked(fetchWatchlists).mockResolvedValue([{
      id: 'watch-1', query: 'protein models', project_id: 'project-1',
      target_type: 'topic', target_id: null,
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

  it('keeps email controls hidden when the backend reports the feature unavailable', async () => {
    vi.mocked(fetchNotificationPreferences).mockResolvedValue({
      available: false, email_opt_in: false, email_frequency: 'daily', timezone: 'UTC', suppressed: false,
    });
    renderWithQuery(<EmailNotificationPreferences />);

    await waitFor(() => expect(fetchNotificationPreferences).toHaveBeenCalledOnce());
    expect(screen.queryByRole('heading', { name: 'Email notifications' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Email me watchlist updates')).not.toBeInTheDocument();
  });

  it('lets an already opted-in user remove consent while email delivery is unavailable', async () => {
    vi.mocked(fetchNotificationPreferences).mockResolvedValue({
      available: false, email_opt_in: true, email_frequency: 'weekly', timezone: 'Asia/Kolkata', suppressed: false,
    });
    vi.mocked(updateNotificationPreferences).mockResolvedValue({
      available: false, email_opt_in: false, email_frequency: 'weekly', timezone: 'Asia/Kolkata', suppressed: false,
    });
    renderWithQuery(<EmailNotificationPreferences />);

    expect(await screen.findByText(/Email delivery is unavailable, so no email will be sent/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Email me watchlist updates')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Email frequency')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Turn off email opt-in' }));

    await waitFor(() => expect(updateNotificationPreferences).toHaveBeenCalledWith({
      email_opt_in: false, email_frequency: 'weekly', timezone: 'Asia/Kolkata',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Email opt-in turned off.');
  });

  it('saves explicit email opt-in, frequency, and time zone preferences', async () => {
    const initial = { available: true, email_opt_in: false, email_frequency: 'weekly' as const, timezone: 'UTC', suppressed: false };
    vi.mocked(fetchNotificationPreferences).mockResolvedValue(initial);
    vi.mocked(updateNotificationPreferences).mockImplementation(async (input) => ({ ...initial, ...input }));
    renderWithQuery(<EmailNotificationPreferences />);

    const optIn = await screen.findByRole('checkbox', { name: 'Email me watchlist updates' });
    expect(screen.getByText(/A verified email address is required for delivery/)).toBeInTheDocument();
    fireEvent.click(optIn);
    fireEvent.change(screen.getByLabelText('Email frequency'), { target: { value: 'daily' } });
    fireEvent.change(screen.getByLabelText('Time zone'), { target: { value: 'Asia/Kolkata' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save email preferences' }));

    await waitFor(() => expect(updateNotificationPreferences).toHaveBeenCalledWith({
      email_opt_in: true, email_frequency: 'daily', timezone: 'Asia/Kolkata',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Email preferences saved.');
  });

  it('discloses suppression without revealing suppression details', async () => {
    vi.mocked(fetchNotificationPreferences).mockResolvedValue({
      available: true, email_opt_in: true, email_frequency: 'daily', timezone: 'UTC', suppressed: true,
    });
    renderWithQuery(<EmailNotificationPreferences />);

    expect(await screen.findByRole('status')).toHaveTextContent('Email delivery is currently paused. In-app notifications remain available.');
    expect(screen.getByRole('checkbox', { name: 'Email me watchlist updates' })).toBeChecked();
  });

  it('marks notifications read and displays paper links', async () => {
    vi.mocked(fetchNotifications).mockResolvedValue([{
      id: 'notification-1', title: 'New paper found', body: 'Matches your watchlist.',
      reason_code: 'topic_term_overlap', reason_text: 'Matched 2/2 topic-watch terms in the paper title and abstract: transformer, language.',
      paper_id: 'paper-1', project_id: 'project-1', created_at: '2026-11-11T00:00:00Z', read_at: null,
    }]);
    vi.mocked(markNotificationsRead).mockResolvedValue({ status: 'ok' });

    renderWithQuery(<NotificationsPage />);
    await screen.findByText('New paper found');
    expect(screen.getByText(/Matched 2\/2 topic-watch terms/)).toBeInTheDocument();
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
