import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProjectBriefsPanel from '@/components/ProjectBriefsPanel';
import type { ProjectBriefSourceLocator } from '@/types';

vi.mock('@/lib/auth', () => ({ getJWT: async () => 'token' }));

const source: ProjectBriefSourceLocator = {
  source_type: 'paper_abstract',
  paper_source_id: 'paper-source-1',
  start_offset: 0,
  end_offset: 14,
  quote: 'Exact evidence',
};

describe('ProjectBriefsPanel', () => {
  let briefs: Record<string, unknown>[];
  let versions: Record<string, unknown>[];
  let request: ReturnType<typeof vi.fn>;
  let conflictOnAppend: boolean;

  beforeEach(() => {
    briefs = [];
    versions = [];
    conflictOnAppend = false;
    request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? 'GET';
      let status = 200;
      let body: unknown = {};
      if (url.pathname === '/api/projects/project-1/briefs' && method === 'GET') {
        body = briefs;
      } else if (url.pathname === '/api/projects/project-1/briefs' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { title: string; content: string; source_snapshot: ProjectBriefSourceLocator[] };
        const brief = { id: 'brief-1', project_id: 'project-1', title: payload.title, created_by: 'user-1', current_version: 1, created_at: '2026-11-15T10:00:00Z', updated_at: '2026-11-15T10:00:00Z' };
        const version = { id: 'version-1', brief_id: 'brief-1', version: 1, content: payload.content, source_snapshot: payload.source_snapshot.map((item) => ({ ...item, source_id: item.source_type === 'paper_abstract' ? item.paper_source_id : item.document_id, paper_id: item.source_type === 'paper_abstract' ? 'paper-1' : null, source_label: 'Quantum paper', quote_sha256: 'a'.repeat(64), source_sha256: 'b'.repeat(64) })), created_by: 'user-1', created_at: '2026-11-15T10:00:00Z', content_sha256: 'c'.repeat(64), origin: 'user_authored' };
        briefs = [brief];
        versions = [version];
        body = { brief, version };
      } else if (url.pathname === '/api/projects/project-1/briefs/brief-1/versions' && method === 'GET') {
        body = versions;
      } else if (url.pathname === '/api/projects/project-1/briefs/brief-1/versions' && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { expected_current_version: number; content: string; source_snapshot: ProjectBriefSourceLocator[] };
        if (conflictOnAppend) {
          status = 409;
          body = { detail: 'Brief version changed; refresh and retry' };
        } else {
          const version = { id: 'version-2', brief_id: 'brief-1', version: 2, content: payload.content, source_snapshot: payload.source_snapshot.map((item) => ({ ...item, source_id: item.source_type === 'paper_abstract' ? item.paper_source_id : item.document_id, paper_id: item.source_type === 'paper_abstract' ? 'paper-1' : null, source_label: 'Quantum paper', quote_sha256: 'a'.repeat(64), source_sha256: 'b'.repeat(64) })), created_by: 'user-1', created_at: '2026-11-15T11:00:00Z', content_sha256: 'd'.repeat(64), origin: 'user_authored' };
          versions = [...versions, version];
          briefs = briefs.map((item) => item.id === 'brief-1' ? { ...item, current_version: 2 } : item);
          body = version;
        }
      }
      return { ok: status < 400, status, json: async () => body } as Response;
    });
    vi.stubGlobal('fetch', request);
  });

  function renderPanel(canWrite = true, sources: ProjectBriefSourceLocator[] = [source]) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const onClearSources = vi.fn();
    const onRemoveSource = vi.fn();
    const onSetSources = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <ProjectBriefsPanel projectId="project-1" canWrite={canWrite} sources={sources} onRemoveSource={onRemoveSource} onClearSources={onClearSources} onSetSources={onSetSources} />
      </QueryClientProvider>,
    );
    return { onSetSources };
  }

  it('creates a brief with source citations and appends an immutable next version', async () => {
    const { onSetSources } = renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'New brief' }));
    fireEvent.change(screen.getByLabelText('Brief title'), { target: { value: 'Retrieval findings' } });
    fireEvent.change(screen.getByLabelText('Brief content'), { target: { value: 'Version one summary' } });
    expect(screen.getByText('“Exact evidence”')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create brief' }));
    await waitFor(() => expect(request.mock.calls.some(([input]) => String(input).includes('/brief-1/versions'))).toBe(true));

    expect(await screen.findByText('Version one summary')).toBeInTheDocument();
    await waitFor(() => {
      const call = request.mock.calls.find(([input, init]) => String(input).endsWith('/briefs') && init?.method === 'POST');
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ title: 'Retrieval findings', content: 'Version one summary', source_snapshot: [source] });
    });

    fireEvent.click(await screen.findByRole('button', { name: /Create next version/ }));
    expect(onSetSources).toHaveBeenCalledWith([source]);
    fireEvent.change(screen.getByLabelText('Brief content'), { target: { value: 'Version two summary' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save new version' }));
    await waitFor(() => expect(request.mock.calls.some(([input, init]) => String(input).endsWith('/brief-1/versions') && init?.method === 'POST')).toBe(true));
    expect(await screen.findByText('Version two summary')).toBeInTheDocument();
    await waitFor(() => {
      const call = request.mock.calls.find(([input, init]) => String(input).endsWith('/brief-1/versions') && init?.method === 'POST');
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ expected_current_version: 1, content: 'Version two summary', source_snapshot: [source] });
    });
    expect(await screen.findByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText('Version one summary')).toBeInTheDocument();
  });

  it('shows a conflict response and refreshes history without overwriting the current version', async () => {
    briefs = [{ id: 'brief-1', project_id: 'project-1', title: 'Existing brief', created_by: 'user-1', current_version: 1, created_at: '2026-11-15T10:00:00Z', updated_at: '2026-11-15T10:00:00Z' }];
    versions = [{ id: 'version-1', brief_id: 'brief-1', version: 1, content: 'Existing summary', source_snapshot: [], created_by: 'user-1', created_at: '2026-11-15T10:00:00Z', content_sha256: 'c'.repeat(64), origin: 'user_authored' }];
    conflictOnAppend = true;
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /Existing brief/ }));
    fireEvent.click(await screen.findByRole('button', { name: /Create next version/ }));
    fireEvent.change(screen.getByLabelText('Brief content'), { target: { value: 'Competing revision' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save new version' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Another collaborator saved a newer version');
    expect(screen.getByText('Existing summary')).toBeInTheDocument();
  });

  it('shows version history read only to project members', async () => {
    briefs = [{ id: 'brief-1', project_id: 'project-1', title: 'Shared brief', created_by: 'owner-1', current_version: 1, created_at: '2026-11-15T10:00:00Z', updated_at: '2026-11-15T10:00:00Z' }];
    versions = [{ id: 'version-1', brief_id: 'brief-1', version: 1, content: 'Member-visible version', source_snapshot: [], created_by: 'owner-1', created_at: '2026-11-15T10:00:00Z', content_sha256: 'c'.repeat(64), origin: 'user_authored' }];
    renderPanel(false, []);
    fireEvent.click(await screen.findByRole('button', { name: /Shared brief/ }));
    expect(await screen.findByText('Member-visible version')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New brief' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create next version' })).not.toBeInTheDocument();
  });
});
