'use client';

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchNotificationPreferences, updateNotificationPreferences, type NotificationPreferences } from '@/lib/monitoring-api';

const QUERY_KEY = ['notification-preferences'];

export default function EmailNotificationPreferences() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: QUERY_KEY, queryFn: fetchNotificationPreferences });
  const [emailOptIn, setEmailOptIn] = useState(false);
  const [emailFrequency, setEmailFrequency] = useState<'daily' | 'weekly'>('daily');
  const [timezone, setTimezone] = useState('');
  const [optOutSaved, setOptOutSaved] = useState(false);

  useEffect(() => {
    if (!preferences.data) return;
    setEmailOptIn(preferences.data.email_opt_in);
    setEmailFrequency(preferences.data.email_frequency);
    setTimezone(preferences.data.timezone);
  }, [preferences.data]);

  const save = useMutation({
    mutationFn: (input: Pick<NotificationPreferences, 'email_opt_in' | 'email_frequency' | 'timezone'>) => updateNotificationPreferences(input),
    onSuccess: (updated) => {
      queryClient.setQueryData(QUERY_KEY, updated);
      setOptOutSaved(!updated.email_opt_in);
    },
  });

  if (preferences.isLoading) return null;

  if (preferences.isError || !preferences.data) {
    return (
      <section aria-labelledby="email-preferences-heading" className="border-t border-zenith-border/60 pt-6">
        <h2 id="email-preferences-heading" className="mb-2 font-serif text-[18px] font-normal text-ink-900">Email notifications</h2>
        <p role="status" className="text-[13px] text-zenith-muted">Email notification preferences are unavailable right now.</p>
      </section>
    );
  }

  if (!preferences.data.available) {
    if (!preferences.data.email_opt_in && !optOutSaved) return null;

    return (
      <section aria-labelledby="email-preferences-heading" className="border-t border-zenith-border/60 pt-6">
        <h2 id="email-preferences-heading" className="mb-2 font-serif text-[18px] font-normal text-ink-900">Email notifications</h2>
        {optOutSaved ? (
          <p role="status" className="text-[13px] text-emerald-800">Email opt-in turned off.</p>
        ) : (
          <>
            <p className="mb-4 max-w-2xl text-[13px] leading-6 text-zenith-muted">Email delivery is unavailable, so no email will be sent. You can remove your saved email opt-in here.</p>
            {save.isError && <p role="alert" className="mb-4 text-[13px] text-red-800">Could not turn off email notifications. Please try again.</p>}
            <button
              type="button"
              onClick={() => save.mutate({
                email_opt_in: false,
                email_frequency: preferences.data.email_frequency,
                timezone: preferences.data.timezone,
              })}
              disabled={save.isPending}
              className="rounded-xl border border-zenith-border px-4 py-2.5 text-[13px] font-semibold text-ink-900 transition hover:bg-white disabled:cursor-wait disabled:opacity-50"
            >
              {save.isPending ? 'Turning off…' : 'Turn off email opt-in'}
            </button>
          </>
        )}
      </section>
    );
  }

  return (
    <section aria-labelledby="email-preferences-heading" className="border-t border-zenith-border/60 pt-6">
      <h2 id="email-preferences-heading" className="mb-2 font-serif text-[18px] font-normal text-ink-900">Email notifications</h2>
      <p id="email-notification-disclosure" className="mb-4 max-w-2xl text-[13px] leading-6 text-zenith-muted">
        If you opt in, Zenith emails a generic digest with counts of new watchlist matches and a link to your in-app notifications. Email does not include paper details or private project or watchlist text. Choose a schedule and time zone; in-app notifications remain available, and you can turn email off here at any time. A verified email address is required for delivery.
      </p>

      {preferences.data.suppressed && (
        <p role="status" className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[13px] leading-5 text-amber-900">
          Email delivery is currently paused. In-app notifications remain available.
        </p>
      )}

      {save.isSuccess && <p role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-[13px] text-emerald-800">Email preferences saved.</p>}
      {save.isError && <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[13px] leading-5 text-red-800">Could not save email preferences. Check that your email address is verified, then try again.</p>}

      <form onSubmit={(event) => { event.preventDefault(); setOptOutSaved(false); save.mutate({ email_opt_in: emailOptIn, email_frequency: emailFrequency, timezone: timezone.trim() }); }} className="space-y-4">
        <div>
          <label htmlFor="email-notifications-opt-in" className="flex items-start gap-3 text-sm font-medium text-ink-900">
            <input
              id="email-notifications-opt-in"
              type="checkbox"
              checked={emailOptIn}
              onChange={(event) => { setEmailOptIn(event.target.checked); save.reset(); }}
              aria-describedby="email-notification-disclosure"
              className="mt-0.5 h-4 w-4 rounded border-zenith-border text-zenith-secondary focus:ring-zenith-secondary"
            />
            <span>Email me watchlist updates</span>
          </label>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="email-notification-frequency" className="mb-1.5 block text-sm font-medium text-ink-900">Email frequency</label>
            <select
              id="email-notification-frequency"
              value={emailFrequency}
              onChange={(event) => { setEmailFrequency(event.target.value as 'daily' | 'weekly'); save.reset(); }}
              className="w-full rounded-xl border border-zenith-border bg-white px-3 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none"
            >
              <option value="daily">Daily digest</option>
              <option value="weekly">Weekly digest</option>
            </select>
          </div>
          <div>
            <label htmlFor="email-notification-timezone" className="mb-1.5 block text-sm font-medium text-ink-900">Time zone</label>
            <input
              id="email-notification-timezone"
              value={timezone}
              onChange={(event) => { setTimezone(event.target.value); save.reset(); }}
              maxLength={80}
              required
              placeholder="e.g. Asia/Kolkata"
              aria-describedby="email-notification-timezone-help"
              className="w-full rounded-xl border border-zenith-border bg-white px-3 py-3 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none"
            />
            <p id="email-notification-timezone-help" className="mt-1 text-xs leading-5 text-zenith-muted">Use an IANA time zone such as Asia/Kolkata or America/New_York.</p>
          </div>
        </div>

        <button type="submit" disabled={save.isPending || !timezone.trim()} className="rounded-xl bg-ink-900 px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">
          {save.isPending ? 'Saving…' : 'Save email preferences'}
        </button>
      </form>
    </section>
  );
}
