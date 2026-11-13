import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchPlanExecutionPanel from '@/components/ResearchPlanExecutionPanel';
import { cancelRun, streamSearch } from '@/lib/api';
import type { ResearchPlanExecutionResult } from '@/types';

vi.mock('@/lib/api', () => ({
  cancelRun: vi.fn(),
  streamSearch: vi.fn(),
}));

const finalResult: ResearchPlanExecutionResult = {
  kind: 'research_plan_execution',
  run_id: 'run-1',
  task_type: 'deep_research',
  source_scope: 'project',
  steps: [{ step_id: 'extract_evidence', status: 'complete', count: 1 }],
  sources: [{ paper_id: 'paper-1', title: 'Reliable Retrieval' }],
  evidence: [{ citation_id: 'paper-1:abstract:12-45', paper_id: 'paper-1', sentence: 'Retrieval improved on the benchmark.', start_offset: 12, end_offset: 45 }],
  gaps: ['No replication study was found.'],
  synthesis: [{ text: 'Retrieval improved in this study.', status: 'supported', supporting_evidence_ids: ['paper-1:abstract:12-45'], contradicting_evidence_ids: [], cited_evidence_ids: ['paper-1:abstract:12-45'], explanation: '' }],
  cost_tracking_available: false,
  estimated_cost_usd: null,
};

function renderPanel() {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}><ResearchPlanExecutionPanel runId="run-1" /></QueryClientProvider>);
}

describe('ResearchPlanExecutionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(streamSearch).mockImplementation(async (_runId, onEvent) => {
      onEvent({ agent: 'evidence_agent', status: 'complete', count: 1 });
      onEvent(finalResult);
      return () => {};
    });
  });

  it('renders streamed progress, final citations, provisional synthesis, and gaps', async () => {
    renderPanel();

    expect(await screen.findByRole('status')).toHaveTextContent('Plan completed');
    expect(screen.getByRole('list', { name: 'Research execution progress' })).toHaveTextContent('evidence agent');
    expect(screen.getByText('Reliable Retrieval')).toBeInTheDocument();
    expect(screen.getByText('“Retrieval improved on the benchmark.”')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === 'P' && element.textContent?.includes('[paper-1:abstract:12-45]') === true)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Provisional synthesis · model reviewed' })).toBeInTheDocument();
    expect(screen.getByText('No replication study was found.')).toBeInTheDocument();
  });

  it('shows the terminal status returned when cancellation races with completion', async () => {
    vi.mocked(streamSearch).mockImplementation(async () => new Promise(() => {}));
    vi.mocked(cancelRun).mockResolvedValue({ status: 'complete' });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel research plan execution' }));
    expect(await screen.findByText('Run completed.')).toBeInTheDocument();
    expect(screen.queryByText('Run cancelled.')).not.toBeInTheDocument();
    expect(cancelRun).toHaveBeenCalledWith('run-1');
  });

  it('shows cancellation received from the SSE stream', async () => {
    vi.mocked(streamSearch).mockImplementation(async (_runId, onEvent) => {
      onEvent({ run_id: 'run-1', status: 'cancelled' });
      return () => {};
    });
    renderPanel();

    expect(await screen.findByText('Run cancelled.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel research plan execution' })).not.toBeInTheDocument();
  });
});
