/// <reference types="vitest/globals" />
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentStep } from '@/types';
import { cancelRun, streamSearch } from '@/lib/api';
import { StreamingResponse } from '@/components/StreamingResponse';

vi.mock('@/lib/api', () => ({
  cancelRun: vi.fn(),
  streamSearch: vi.fn(),
}));

describe('StreamingResponse', () => {
  let emitEvent: ((event: AgentStep, eventId?: string) => void) | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    emitEvent = undefined;
    vi.mocked(streamSearch).mockImplementation(async (_runId, onEvent) => {
      emitEvent = onEvent as (event: AgentStep, eventId?: string) => void;
      return () => {};
    });
  });

  it('deduplicates replayed progress events by their SSE id', () => {
    render(<StreamingResponse runId="run-1" />);
    const progress = { agent: 'research', status: 'started' } as AgentStep;

    act(() => {
      emitEvent?.(progress, '1');
      emitEvent?.(progress, '1');
    });

    expect(screen.getAllByText('research')).toHaveLength(1);
  });

  it('calls the run cancellation endpoint and shows the cancelled state', async () => {
    vi.mocked(cancelRun).mockResolvedValue({ status: 'cancelled' });
    render(<StreamingResponse runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel research run' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Run cancelled');
    expect(cancelRun).toHaveBeenCalledWith('run-1');
    expect(screen.queryByRole('button', { name: 'Cancel research run' })).toBeNull();
  });
});
