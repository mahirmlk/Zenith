'use client';

import { useEffect, useRef, useState } from 'react';
import { AgentStep, PaperSearchResult } from '@/types';
import { cancelRun, streamSearch } from '@/lib/api';

interface StreamingResponseProps {
  runId: string;
  onResult?: (result: PaperSearchResult) => void;
}

export function StreamingResponse({ runId, onResult }: StreamingResponseProps) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const unsubscribeRef = useRef<(() => void) | undefined>(undefined);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setSteps([]);
    setError(null);
    setDone(false);
    setCancelled(false);

    let disposed = false;
    let completed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let retries = 0;
    const seenEventIds = new Set<string>();
    const MAX_RETRIES = 3;

    const connect = () => {
      streamSearch(
        runId,
        (event, eventId) => {
          // The server replays its event log to a newly-created EventSource.
          // Keep a per-run cursor so reconnects don't duplicate progress rows.
          if (eventId) {
            if (seenEventIds.has(eventId)) return;
            seenEventIds.add(eventId);
          }
          if ('papers' in event) {
            completed = true;
            setDone(true);
            onResult?.(event as PaperSearchResult);
          } else {
            setSteps((prev) => [...prev, event as AgentStep]);
          }
        },
        (err) => {
          // Backend replays persisted events on reconnect (update.md
          // §7.1), so safe to re-subscribe. Retry with backoff.
          if (disposed || completed) return;
          if (retries < MAX_RETRIES) {
            retries += 1;
            retryTimer = setTimeout(connect, 1000 * retries);
            retryTimerRef.current = retryTimer;
          } else {
            setError(err.message);
          }
        }
      ).then((unsub) => {
        unsubscribeRef.current = unsub;
      });
    };
    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      unsubscribeRef.current?.();
      unsubscribeRef.current = undefined;
      retryTimerRef.current = undefined;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const handleCancel = async () => {
    if (done || cancelled || cancelling) return;
    setCancelling(true);
    setError(null);
    try {
      const response = await cancelRun(runId);
      if (response.status === 'cancelled') {
        setCancelled(true);
        setDone(false);
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
        retryTimerRef.current = undefined;
        unsubscribeRef.current?.();
        unsubscribeRef.current = undefined;
      } else if (response.status === 'complete') {
        setDone(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel research run');
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h4 className="mb-3 text-sm font-semibold text-gray-900">Agent Progress</h4>

      {!done && !cancelled && (
        <button
          type="button"
          onClick={handleCancel}
          disabled={cancelling}
          aria-label="Cancel research run"
          className="mb-3 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60"
        >
          {cancelling ? 'Cancelling…' : 'Cancel run'}
        </button>
      )}

      {error && (
        <div className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}

      <div className="space-y-2">
        {steps.map((step, idx) => (
          <div key={idx} className="flex items-center gap-2 text-sm text-gray-700">
            <span className="inline-block h-2 w-2 rounded-full bg-primary-500" />
            <span className="font-medium capitalize">{step.agent}</span>
            <span className="text-gray-500">{step.status.replace(/_/g, ' ')}</span>
            {step.count !== undefined && <span className="text-gray-400">({step.count})</span>}
          </div>
        ))}
      </div>

      {done && (
        <div className="mt-3 flex items-center gap-2 text-sm font-medium text-green-700">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
          Complete
        </div>
      )}
      {cancelled && (
        <div role="status" className="mt-3 text-sm font-medium text-gray-600">
          Run cancelled
        </div>
      )}
    </div>
  );
}
