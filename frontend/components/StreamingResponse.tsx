'use client';

import { useEffect, useState } from 'react';
import { AgentStep, PaperSearchResult } from '@/types';
import { streamSearch } from '@/lib/api';

interface StreamingResponseProps {
  runId: string;
  onResult?: (result: PaperSearchResult) => void;
}

export function StreamingResponse({ runId, onResult }: StreamingResponseProps) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    setSteps([]);
    setError(null);
    setDone(false);

    let unsubscribe: (() => void) | undefined;

    streamSearch(
      runId,
      (event) => {
        if ('papers' in event) {
          setDone(true);
          onResult?.(event as PaperSearchResult);
        } else {
          setSteps((prev) => [...prev, event as AgentStep]);
        }
      },
      (err) => setError(err.message)
    ).then((unsub) => {
      unsubscribe = unsub;
    });

    return () => {
      unsubscribe?.();
    };
  }, [runId, onResult]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h4 className="mb-3 text-sm font-semibold text-gray-900">Agent Progress</h4>

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
    </div>
  );
}
