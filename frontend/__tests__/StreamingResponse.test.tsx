/// <reference types="vitest/globals" />
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentStep, ResearchRunCancelledEvent } from '@/types';
import { cancelRun, streamSearch } from '@/lib/api';
import { StreamingResponse } from '@/components/StreamingResponse';

vi.mock('@/lib/api', () => ({
  cancelRun: vi.fn(),
  streamSearch: vi.fn(),
}));

describe('StreamingResponse', () => {
  let emitEvent: ((event: AgentStep | ResearchRunCancelledEvent, eventId?: string) => void) | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    emitEvent = undefined;
    vi.mocked(streamSearch).mockImplementation((_runId, callbacks) => {
      emitEvent = callbacks.onEvent as (event: AgentStep | ResearchRunCancelledEvent, eventId?: string) => void;
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

  it('retries transport errors with the latest event id', async () => {
    vi.useFakeTimers();
    const connection = vi.fn((_runId, callbacks, _options) => {
      if (connection.mock.calls.length === 1) {
        callbacks.onLastEventId?.('event-17');
        callbacks.onTransportError?.(new Error('temporary disconnect'));
      } else {
        callbacks.onEvent({ agent: 'summary', status: 'resumed' } as AgentStep, 'event-18');
      }
      return () => {};
    });
    vi.mocked(streamSearch).mockImplementation(connection as typeof streamSearch);
    render(<StreamingResponse runId="run-retry" />);

    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(connection).toHaveBeenCalledTimes(2);
    expect(connection.mock.calls[1]?.[2]).toEqual({ lastEventId: 'event-17' });
    expect(screen.getByText('resumed')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('stops after three transport retries and shows the final disconnect', async () => {
    vi.useFakeTimers();
    const connection = vi.fn((_runId, callbacks, _options) => {
      const attempt = connection.mock.calls.length;
      callbacks.onLastEventId?.(`event-${attempt}`);
      callbacks.onTransportError?.(new Error(`disconnect ${attempt}`));
      return () => {};
    });
    vi.mocked(streamSearch).mockImplementation(connection as typeof streamSearch);
    render(<StreamingResponse runId="run-retry-limit" />);

    await act(async () => { await vi.runAllTimersAsync(); });

    expect(connection).toHaveBeenCalledTimes(4);
    expect(connection.mock.calls[1]?.[2]).toEqual({ lastEventId: 'event-1' });
    expect(connection.mock.calls[2]?.[2]).toEqual({ lastEventId: 'event-2' });
    expect(connection.mock.calls[3]?.[2]).toEqual({ lastEventId: 'event-3' });
    expect(screen.getByText('disconnect 4')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('treats named server errors as terminal and displays streamed cancellation', () => {
    vi.mocked(streamSearch).mockImplementationOnce((_runId, callbacks) => {
      callbacks.onTerminalError?.(new Error('Worker failed'));
      callbacks.onTransportError?.(new Error('should not retry'));
      return () => {};
    });
    const { rerender } = render(<StreamingResponse runId="run-error" />);
    expect(screen.getByText('Worker failed')).toBeInTheDocument();
    expect(streamSearch).toHaveBeenCalledTimes(1);

    vi.mocked(streamSearch).mockImplementationOnce((_runId, callbacks) => {
      callbacks.onEvent({ run_id: 'run-cancel', status: 'cancelled' });
      return () => {};
    });
    rerender(<StreamingResponse runId="run-cancel" />);
    expect(screen.getByRole('status')).toHaveTextContent('Run cancelled');
  });
});
