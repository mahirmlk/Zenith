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
  let members: { project_id: string; user_id: string; role: 'viewer' | 'editor' }[];
  let invitations: { id: string; project_id: string; email: string; role: 'viewer' | 'editor'; status: string; created_at: string; expires_at: string; email_sent_at: string | null }[];
  let documents: { id: string; filename: string; page_count: number }[];
  let currentRole: 'owner' | 'editor' | 'viewer';
  let request: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sources = [];
    notes = [];
    members = [];
    invitations = [];
    documents = [];
    currentRole = 'owner';
    request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? 'GET';
      let body: unknown = {};

      if (url.pathname === '/api/projects/project-1' && method === 'GET') {
        body = { id: 'project-1', owner_id: 'user-1', title: 'Alpha Project', description: 'A research workspace', current_role: currentRole };
      } else if (url.pathname === '/api/projects/project-1/notes' && method === 'GET') {
        body = notes;
      } else if (url.pathname === '/api/projects/project-1/notes' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { content: string };
        notes = [{ id: 'note-1', content: payload.content, created_at: '2026-11-11T12:00:00Z' }];
        body = notes;
      } else if (url.pathname === '/api/projects/project-1/members' && method === 'GET') {
        body = members;
      } else if (url.pathname === '/api/projects/project-1/members' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { user_id: string; role: 'viewer' | 'editor' };
        members = [{ project_id: 'project-1', ...payload }];
        body = members;
      } else if (url.pathname === '/api/projects/project-1/invitations' && method === 'GET') {
        body = invitations;
      } else if (url.pathname === '/api/projects/project-1/invitations' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { email: string; role: 'viewer' | 'editor' };
        invitations = [{ id: 'invite-1', project_id: 'project-1', ...payload, status: 'pending', created_at: '2026-11-12T10:00:00Z', expires_at: '2026-11-19T10:00:00Z', email_sent_at: '2026-11-12T10:00:00Z' }];
        body = invitations[0];
      } else if (url.pathname === '/api/projects/project-1/invitations/invite-1/resend' && method === 'POST') {
        body = invitations[0];
      } else if (url.pathname === '/api/projects/project-1/invitations/invite-1' && method === 'DELETE') {
        invitations = invitations.map((invitation) => ({ ...invitation, status: 'revoked' }));
        body = { status: 'revoked' };
      } else if (url.pathname.startsWith('/api/projects/project-1/members/') && method === 'DELETE') {
        const userId = decodeURIComponent(url.pathname.split('/').at(-1) ?? '');
        members = members.filter((member) => member.user_id !== userId);
        body = { status: 'ok' };
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
      } else if (url.pathname === '/api/projects/project-1/documents' && method === 'GET') {
        body = documents;
      } else if (url.pathname === '/api/projects/project-1/documents' && method === 'POST') {
        const formData = init?.body as FormData;
        const file = formData.get('file') as File;
        documents = [{ id: 'document-1', filename: file.name, page_count: 1 }];
        body = documents[0];
      } else if (url.pathname === '/api/projects/project-1/documents/document-1/pages' && method === 'GET') {
        body = {
          id: 'document-1',
          filename: 'methods.pdf',
          page_count: 1,
          pages: [{ page_number: 1, text: 'The experiment used a held-out benchmark.', citation_id: 'document-1:page:1' }],
        };
      } else if (url.pathname === '/api/papers' && method === 'GET') {
        body = [{ id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'] }];
      } else if (url.pathname === '/api/papers/paper-1' && method === 'GET') {
        body = { id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'] };
      } else if (url.pathname === '/api/research/evidence-map' && method === 'POST') {
        body = {
          evidence: [{ paper_id: 'paper-1', title: 'Reliable Retrieval', sentence: 'Retrieval quality improved on the benchmark.', start_offset: 5, end_offset: 48 }],
          pdf_evidence: [{ document_id: 'document-1', filename: 'methods.pdf', page_number: 4, citation_id: 'document-1:page:4', sentence: 'The PDF reports the same benchmark.', start_offset: 0, end_offset: 35 }],
          abstained: false,
          explanation: 'Exact abstract evidence from attached papers.',
        };
      } else if (url.pathname === '/api/retrieval/search' && method === 'POST') {
        body = { results: [
          { id: 'paper-1', source_type: 'paper', title: 'Reliable Retrieval', abstract: 'A useful project paper.', score: 0.9 },
          { id: 'document-1:page:4', source_type: 'pdf_page', title: 'methods.pdf', filename: 'methods.pdf', page_number: 4, citation_id: 'document-1:page:4', snippet: 'The PDF reports retrieval quality.', start_offset: 5, end_offset: 39, score: 0.8 },
        ] };
      } else if (url.pathname === '/api/research/compare' && method === 'POST') {
        body = {
          rows: [{ paper_id: 'paper-1', problem: 'A useful project paper.', methods: null, datasets: null, metrics: null, limitations: null, code_status: 'unverified' }],
          pdf_evidence: [{ document_id: 'document-1', filename: 'methods.pdf', page_number: 4, citation_id: 'document-1:page:4', sentence: 'The PDF reports the comparison benchmark.', start_offset: 10, end_offset: 50 }],
        };
      } else if (url.pathname === '/api/research/answer' && method === 'POST') {
        body = {
          summary: 'Extractive evidence from a project PDF.',
          claims: ['Retrieval quality improved on the benchmark. [document-1:page:4]'],
          citation_ids: ['document-1:page:4'],
          pdf_evidence: [{ document_id: 'document-1', filename: 'methods.pdf', page_number: 4, citation_id: 'document-1:page:4', sentence: 'Retrieval quality improved on the benchmark.', start_offset: 12, end_offset: 57 }],
          abstained: false,
          confidence_explanation: 'Extractive evidence only.',
        };
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
    expect(await screen.findByText('“The PDF reports the same benchmark.”')).toBeInTheDocument();
    expect(screen.getByText('[document-1:page:4] · page offsets 0–35')).toBeInTheDocument();

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
    expect(await screen.findByText('“The PDF reports retrieval quality.”')).toBeInTheDocument();
    expect(screen.getByText('[document-1:page:4] · page offsets 5–39')).toBeInTheDocument();
    await waitFor(() => {
      const searchRequest = request.mock.calls.find(([input, init]) =>
        String(input).endsWith('/api/retrieval/search') && init?.method === 'POST',
      );
      expect(searchRequest).toBeDefined();
      expect(JSON.parse(String(searchRequest?.[1]?.body))).toEqual({ query: 'retrieval', project_id: 'project-1', limit: 10 });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Answer' }));
    fireEvent.change(screen.getByLabelText('Question or comparison'), { target: { value: 'retrieval quality benchmark' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run research' }));
    expect(await screen.findByText('[document-1:page:4] · page offsets 12–57')).toBeInTheDocument();
    expect(screen.getByText('“Retrieval quality improved on the benchmark.”')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
    fireEvent.change(screen.getByLabelText('Question or comparison'), { target: { value: 'compare retrieval benchmark' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run research' }));
    expect(await screen.findByText('“The PDF reports the comparison benchmark.”')).toBeInTheDocument();
    expect(screen.getByText('[document-1:page:4] · page offsets 10–50')).toBeInTheDocument();
    expect(screen.getByText('PDF source evidence · extractive, not synthesized')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove Reliable Retrieval from project' }));
    expect(await screen.findByText('No papers attached yet. Add one from your feed to use project-scoped research.')).toBeInTheDocument();
  });

  it('lets owners create, list, resend, and revoke email invitations', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);

    const email = await screen.findByLabelText('Email address');
    fireEvent.change(email, { target: { value: 'researcher@example.org' } });
    fireEvent.change(screen.getByLabelText('Invitation role'), { target: { value: 'editor' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
    expect(await screen.findByText('researcher@example.org')).toBeInTheDocument();
    await waitFor(() => {
      const call = request.mock.calls.find(([input, init]) => String(input).endsWith('/invitations') && init?.method === 'POST');
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ email: 'researcher@example.org', role: 'editor' });
    });
    fireEvent.click(screen.getByRole('button', { name: 'Resend invitation to researcher@example.org' }));
    fireEvent.click(screen.getByRole('button', { name: 'Revoke invitation to researcher@example.org' }));
    await waitFor(() => expect(request.mock.calls.some(([input, init]) => String(input).endsWith('/invitations/invite-1/resend') && init?.method === 'POST')).toBe(true));
    await waitFor(() => expect(request.mock.calls.some(([input, init]) => String(input).endsWith('/invitations/invite-1') && init?.method === 'DELETE')).toBe(true));
  });

  it('hides member and invitation controls from non-owners', async () => {
    currentRole = 'editor';
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Alpha Project' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Project members' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Email address')).not.toBeInTheDocument();
    expect(request.mock.calls.some(([input]) => String(input).endsWith('/invitations'))).toBe(false);
  });

  it('shows project content but hides mutation controls for viewer members', async () => {
    currentRole = 'viewer';
    sources = [{
      id: 'source-1',
      paper_id: 'paper-1',
      paper: { id: 'paper-1', title: 'Reliable Retrieval', authors: ['A. Researcher'], url: 'https://example.org/paper' },
    }];
    notes = [{ id: 'note-1', content: 'Shared reading note', created_at: '2026-11-11T12:00:00Z' }];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);

    expect(await screen.findByText(/read-only access to this project/i)).toBeInTheDocument();
    expect(await screen.findByText('Reliable Retrieval')).toBeInTheDocument();
    expect(await screen.findByText('Shared reading note')).toBeInTheDocument();
    expect(screen.queryByLabelText('Find a paper by title')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Add a note')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /remove reliable retrieval/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add paper' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save note' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Project members' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Upload a PDF you have permission to use')).not.toBeInTheDocument();
  });

  it('uploads a PDF, reloads its metadata, and renders page text with a citation ID', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);

    const file = new File(['pdf bytes'], 'methods.pdf', { type: 'application/pdf' });
    fireEvent.change(await screen.findByLabelText('Upload a PDF you have permission to use'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload and extract pages' }));

    expect(await screen.findByText('The experiment used a held-out benchmark.')).toBeInTheDocument();
    expect(screen.getByText('[document-1:page:1]')).toBeInTheDocument();
    expect(screen.getByText('methods.pdf')).toBeInTheDocument();
    expect(screen.getByText('1 page')).toBeInTheDocument();

    const uploadRequest = request.mock.calls.find(([input, init]) =>
      String(input).endsWith('/api/projects/project-1/documents') && init?.method === 'POST',
    );
    expect(uploadRequest).toBeDefined();
    expect(uploadRequest?.[1]?.body).toBeInstanceOf(FormData);
    expect(new Headers(uploadRequest?.[1]?.headers).has('Content-Type')).toBe(false);
    expect(request.mock.calls.some(([input]) => String(input).endsWith('/documents/document-1/pages'))).toBe(true);
  });

  it('lets the project owner add and remove an existing member', async () => {
    const memberId = '00000000-0000-4000-8000-000000000001';
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><ProjectWorkspacePage /></QueryClientProvider>);

    fireEvent.change(await screen.findByLabelText('Existing account user ID'), { target: { value: memberId } });
    fireEvent.change(screen.getByLabelText('Project role'), { target: { value: 'editor' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add or update member' }));
    expect(await screen.findByText(memberId)).toBeInTheDocument();
    expect(screen.getByText('editor')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: `Remove member ${memberId}` }));
    expect(await screen.findByText('No members have been added yet.')).toBeInTheDocument();
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
