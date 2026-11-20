import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PaperDetailPage from '@/app/paper/[id]/page';
import { ApiError, fetchPaper, fetchPaperCode } from '@/lib/api';

const mocks = vi.hoisted(() => ({
  fetchPaper: vi.fn(),
  fetchPaperCode: vi.fn(),
  fetchPaperStatusWatch: vi.fn(),
  setPaperStatusWatch: vi.fn(),
  fetchResearchCapabilities: vi.fn(),
  fetchPublicPaperEvidence: vi.fn(),
}));

vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'paper-123' }) }));
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, ...mocks };
});

const paper = {
  id: 'paper-123',
  title: 'A Test Paper',
  authors: ['A. Researcher'],
  abstract: 'A short abstract.',
  publishedAt: '2026-01-02T00:00:00Z',
  url: 'https://example.org/paper.pdf',
  preprintId: '2601.01234',
  sourceVersion: 2,
  summaryStatus: 'unknown' as const,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false },
    },
  });
  return render(<QueryClientProvider client={client}><PaperDetailPage /></QueryClientProvider>);
}

describe('PaperDetailPage fetch states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPaperCode).mockResolvedValue({ repos: [] });
    vi.mocked(mocks.fetchPaperStatusWatch).mockResolvedValue(false);
    vi.mocked(mocks.setPaperStatusWatch).mockResolvedValue(true);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: false,
    });
    vi.mocked(mocks.fetchPublicPaperEvidence).mockResolvedValue({
      paper_id: 'paper-123',
      preprint_id: 'arxiv:2601.01234',
      version: 2,
      title: 'A Test Paper',
      source_url: 'https://arxiv.org/abs/2601.01234',
      license_url: 'https://creativecommons.org/licenses/by/4.0/',
      license_name: 'CC BY 4.0',
      attribution: 'Authors of A Test Paper',
      evidence: [{
        page_number: 3,
        citation_id: 'arxiv:2601.01234v2:page:3',
        sentence: 'The experiments use the ExampleBench dataset.',
        start_offset: 108,
        end_offset: 159,
      }],
    });
  });

  it('shows not-found only for an HTTP 404', async () => {
    vi.mocked(fetchPaper).mockRejectedValue(new ApiError('Not found', 404));
    renderPage();

    expect(await screen.findByText('Paper not found.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to feed' })).toHaveAttribute('href', '/feed');
  });

  it('shows a retry action for network errors and renders the paper after retry', async () => {
    vi.mocked(fetchPaper)
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(paper as never);
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this paper.');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('heading', { name: 'A Test Paper' })).toBeInTheDocument();
    await waitFor(() => expect(fetchPaper).toHaveBeenCalledTimes(2));
  });

  it('shows a sign-in action for authentication failures', async () => {
    vi.mocked(fetchPaper).mockRejectedValue(new ApiError('Unauthorized', 401));
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Your session may have expired');
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('shows a retry action for server errors', async () => {
    vi.mocked(fetchPaper).mockRejectedValue(new ApiError('Service unavailable', 503));
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this paper.');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('shows Crossref update provenance and lets the reader opt into alerts', async () => {
    vi.mocked(fetchPaper).mockResolvedValue({
      ...paper,
      doi: '10.1234/original-work',
      publicationUpdateType: 'retraction',
      publicationUpdateDoi: '10.9999/retraction-notice',
      publicationUpdateLabel: 'Retraction',
      publicationUpdateDate: '2026-03-04',
      publicationUpdateSource: 'crossref',
      publicationUpdateDepositSource: 'retraction-watch',
    } as never);
    renderPage();

    expect(await screen.findByRole('status', { name: 'Publication status update' }))
      .toHaveTextContent('Crossref update: Retraction');
    expect(screen.getByRole('status', { name: 'Publication status update' }))
      .toHaveTextContent('Notice deposit source reported by Crossref: Retraction Watch.');
    expect(screen.getByRole('link', { name: /View update notice/ }))
      .toHaveAttribute('href', 'https://doi.org/10.9999/retraction-notice');
    fireEvent.click(await screen.findByRole('button', { name: 'Get update alerts' }));
    await waitFor(() => expect(mocks.setPaperStatusWatch).toHaveBeenCalledWith('paper-123', true));
    expect(await screen.findByRole('button', { name: 'Stop monitoring' })).toBeInTheDocument();
  });

  it('hides public evidence controls when the capability is disabled', async () => {
    vi.mocked(fetchPaper).mockResolvedValue(paper as never);
    renderPage();

    expect(await screen.findByRole('heading', { name: 'A Test Paper' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Find passages in this preprint' })).not.toBeInTheDocument();
    expect(mocks.fetchPublicPaperEvidence).not.toHaveBeenCalled();
  });

  it('shows unsupported guidance without a search form when preprint metadata is missing', async () => {
    vi.mocked(fetchPaper).mockResolvedValue({ ...paper, preprintId: null, sourceVersion: null } as never);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: true,
    });
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Page evidence unavailable' })).toBeInTheDocument();
    expect(screen.getByText(/verified arXiv preprint identifier and version are required/)).toBeInTheDocument();
    expect(screen.queryByRole('searchbox', { name: 'What evidence are you looking for?' })).not.toBeInTheDocument();
    expect(mocks.fetchPublicPaperEvidence).not.toHaveBeenCalled();
  });

  it('searches and renders exact page evidence with source and license attribution', async () => {
    vi.mocked(fetchPaper).mockResolvedValue(paper as never);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: true,
    });
    renderPage();

    const input = await screen.findByRole('searchbox', { name: 'What evidence are you looking for?' });
    fireEvent.change(input, { target: { value: 'Which dataset was used?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Find evidence' }));

    expect(await screen.findByText('The experiments use the ExampleBench dataset.')).toBeInTheDocument();
    expect(screen.getByText('Page 3 · arxiv:2601.01234v2:page:3')).toBeInTheDocument();
    expect(screen.getByText('Text offsets 108–159')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View source' })).toHaveAttribute('href', 'https://arxiv.org/abs/2601.01234');
    expect(screen.getByRole('link', { name: 'CC BY 4.0 license' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by/4.0/');
    expect(screen.getByText('Authors of A Test Paper')).toBeInTheDocument();
    expect(screen.getByText(/not a scientific correctness assessment/)).toBeInTheDocument();
    await waitFor(() => expect(mocks.fetchPublicPaperEvidence).toHaveBeenCalledWith('paper-123', 'Which dataset was used?', expect.anything()));
  });

  it('rejects one-character public evidence queries accessibly', async () => {
    vi.mocked(fetchPaper).mockResolvedValue(paper as never);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: true,
    });
    renderPage();

    const input = await screen.findByRole('searchbox', { name: 'What evidence are you looking for?' });
    fireEvent.change(input, { target: { value: 'x' } });
    expect(input).toHaveAttribute('minlength', '2');
    expect(input).toHaveAttribute('aria-describedby', 'public-evidence-query-help');
    expect(screen.getByText('Enter at least 2 characters to search.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Find evidence' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('search', { name: 'Search public paper evidence' }));
    expect(mocks.fetchPublicPaperEvidence).not.toHaveBeenCalled();
  });

  it('shows an empty state and retries failed public evidence requests', async () => {
    vi.mocked(fetchPaper).mockResolvedValue(paper as never);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: true,
    });
    vi.mocked(mocks.fetchPublicPaperEvidence)
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce({
        paper_id: 'paper-123',
        preprint_id: 'arxiv:2601.01234',
        version: 2,
        title: 'A Test Paper',
        source_url: 'https://arxiv.org/abs/2601.01234',
        license_url: 'https://creativecommons.org/licenses/by/4.0/',
        license_name: 'CC BY 4.0',
        attribution: 'Authors of A Test Paper',
        evidence: [],
      });
    renderPage();

    fireEvent.change(await screen.findByRole('searchbox', { name: 'What evidence are you looking for?' }), { target: { value: 'missing claim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Find evidence' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('We could not load public paper evidence.');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('status')).toHaveTextContent('No matching page excerpts were found.');
  });

  it.each([
    [451, 'This source’s license does not permit reuse of its text here.', 'No excerpts are available.'],
    [409, 'The saved arXiv metadata is out of date or unsupported.', 'until the paper metadata is refreshed.'],
    [422, 'This paper’s source is not supported for page evidence.', 'supported arXiv preprints.'],
  ])('shows non-retry guidance for public evidence HTTP %i', async (status, guidance, detail) => {
    vi.mocked(fetchPaper).mockResolvedValue(paper as never);
    vi.mocked(mocks.fetchResearchCapabilities).mockResolvedValue({
      research_synthesis_enabled: false,
      research_plan_execution_enabled: false,
      public_paper_evidence_enabled: true,
    });
    vi.mocked(mocks.fetchPublicPaperEvidence).mockRejectedValue(new ApiError('Unavailable', status));
    renderPage();

    fireEvent.change(await screen.findByRole('searchbox', { name: 'What evidence are you looking for?' }), { target: { value: 'dataset' } });
    fireEvent.click(screen.getByRole('button', { name: 'Find evidence' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(guidance);
    expect(alert).toHaveTextContent(detail);
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });
});
