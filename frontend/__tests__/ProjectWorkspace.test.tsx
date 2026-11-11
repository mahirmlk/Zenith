import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProjectWorkspacePage from '@/app/projects/[id]/page';
import { fetchProjectSources } from '@/lib/project-api';
import { buildProjectExport } from '@/lib/project-export';

vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'project-1' }) }));
vi.mock('@/lib/auth', () => ({ getJWT: async () => 'test-token' }));

describe('ProjectWorkspacePage', () => {
  let sources: { id: string; paper_id: string; paper?: { id: string; title: string; authors: string[]; url: string } | null }[];
  let notes: { id: string; content: string; created_at: string }[];
  let request: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sources = [];
    notes = [];
    request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? 'GET';
      let body: unknown = {};

      if (url.pathname === '/api/projects/project-1' && method === 'GET') {
        body = { id: 'project-1', owner_id: 'user-1', title: 'Alpha Project', description: 'A research workspace' };
      } else if (url.pathname === '/api/projects/project-1/notes' && method === 'GET') {
        body = notes;
      } else if (url.pathname === '/api/projects/project-1/notes' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { content: string };
        notes = [{ id: 'note-1', content: payload.content, created_at: '2026-11-11T12:00:00Z' }];
        body = notes;
      } else if (url.pathname === '/api/projects/project-1/sources' && method === 'GET') {
        body = sources;
      } else if (url.pathname === '/api/projects/project-1/sources' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { paper_id: string };
        sources = [{
          id: 'source-1',
          paper_id: payload.paper_id,
          paper: { id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'], url: 'https://example.org/paper' },
        }];
        body = sources;
      } else if (url.pathname === '/api/projects/project-1/sources/source-1' && method === 'DELETE') {
        sources = [];
        body = { status: 'ok' };
      } else if (url.pathname === '/api/papers' && method === 'GET') {
        body = [{ id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'] }];
      } else if (url.pathname === '/api/papers/paper-1' && method === 'GET') {
        body = { id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'] };
      } else if (url.pathname === '/api/research/evidence-map' && method === 'POST') {
        body = {
          evidence: [{ paper_id: 'paper-1', title: 'Reliable Retrieval', sentence: 'Retrieval quality improved on the benchmark.', start_offset: 5, end_offset: 48 }],
          abstained: false,
          explanation: 'Exact abstract evidence from attached papers.',
        };
      } else if (url.pathname === '/api/retrieval/search' && method === 'POST') {
        body = { results: [{ id: 'paper-1', title: 'Reliable Retrieval', abstract: 'A useful project paper.', score: 0.9 }] };
      }

      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', request);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('attaches a paper, saves a note, and shows project-scoped abstract evidence', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);

    expect(await screen.findByRole('heading', { name: 'Alpha Project' })).toBeInTheDocument();

    await screen.findByLabelText('Find a paper by title');
    fireEvent.change(screen.getByLabelText('Choose a paper to add'), { target: { value: 'paper-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add paper' }));
    expect(await screen.findByRole('button', { name: 'Remove Reliable Retrieval from project' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Add a note'), { target: { value: 'Check the benchmark protocol.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));
    expect(await screen.findByText('Check the benchmark protocol.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Question or comparison'), { target: { value: 'retrieval quality benchmark' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run research' }));
    await waitFor(() => expect(request.mock.calls.some(([input]) => String(input).endsWith('/api/research/evidence-map'))).toBe(true));
    expect(await screen.findByText('“Retrieval quality improved on the benchmark.”')).toBeInTheDocument();

    await waitFor(() => {
      const researchRequest = request.mock.calls.find(([input, init]) =>
        String(input).endsWith('/api/research/evidence-map') && init?.method === 'POST',
      );
      expect(researchRequest).toBeDefined();
      expect(JSON.parse(String(researchRequest?.[1]?.body))).toEqual({
        query: 'retrieval quality benchmark',
        project_id: 'project-1',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Search in project' }));
    fireEvent.change(screen.getByLabelText('Question or comparison'), { target: { value: 'retrieval' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run research' }));
    expect(await screen.findByText('A useful project paper.')).toBeInTheDocument();
    await waitFor(() => {
      const searchRequest = request.mock.calls.find(([input, init]) =>
        String(input).endsWith('/api/retrieval/search') && init?.method === 'POST',
      );
      expect(searchRequest).toBeDefined();
      expect(JSON.parse(String(searchRequest?.[1]?.body))).toEqual({ query: 'retrieval', project_id: 'project-1', limit: 10 });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Remove Reliable Retrieval from project' }));
    expect(await screen.findByText('No papers attached yet. Add one from your feed to use project-scoped research.')).toBeInTheDocument();
  });
});

describe('buildProjectExport', () => {
  const project = { id: 'project-1', owner_id: 'user-1', title: 'A Project' };
  const sources = [{ id: 'source-1', paper_id: 'paper-1', paper: { id: 'paper-1', title: 'A Paper', authors: ['A. Author'], url: 'https://example.org/paper' } }];
  const notes = [{ id: 'note-1', content: 'Keep the quote: "result"', created_at: '2026-11-11T12:00:00Z' }];

  it('exports project sources and notes as Markdown, CSV, and BibTeX', () => {
    expect(buildProjectExport('md', project, sources, notes)).toContain('[A Paper](<https://example.org/paper>)');
    expect(buildProjectExport('md', project, sources, notes)).toContain('Keep the quote: "result"');
    expect(buildProjectExport('csv', project, sources, notes)).toContain('"Keep the quote: ""result"""');
    expect(buildProjectExport('bib', project, sources, notes)).toContain('@misc{zenith_paper-1');
    expect(buildProjectExport('bib', project, sources, notes)).toContain('author = {A. Author}');
  });

  it('neutralizes formula-like CSV cells and omits unsafe Markdown link schemes', () => {
    const unsafeSources = [{
      id: 'source-1',
      paper_id: 'paper-1',
      paper: { id: 'paper-1', title: '[Dangerous](title)', authors: [], url: 'javascript:alert(1)' },
    }];
    const formulaNotes = [{ id: 'note-1', content: ' \t=HYPERLINK("https://bad.example")', created_at: '2026-11-11T12:00:00Z' }];

    expect(buildProjectExport('md', project, unsafeSources, [])).toContain('\\[Dangerous\\](title)');
    expect(buildProjectExport('md', project, unsafeSources, [])).not.toContain('javascript:');
    expect(buildProjectExport('csv', project, [], formulaNotes)).toContain('"\' \t=HYPERLINK(""https://bad.example"")"');
  });
});

describe('fetchProjectSources', () => {
  it('paginates through the full project source collection', async () => {
    const firstPage = Array.from({ length: 200 }, (_, index) => ({ id: `source-${index}`, paper_id: `paper-${index}`, paper: null }));
    const lastPage = [{ id: 'source-200', paper_id: 'paper-200', paper: null }];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const offset = new URL(String(input)).searchParams.get('offset');
      const body = offset === '0' ? firstPage : lastPage;
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    const allSources = await fetchProjectSources('project-1');

    expect(allSources).toHaveLength(201);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toContain('limit=200&offset=0');
    expect(String(fetchMock.mock.calls[1][0])).toContain('limit=200&offset=200');
    vi.unstubAllGlobals();
  });
});
