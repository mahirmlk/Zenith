'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getJWT } from '@/lib/auth';
import { fetchProjectSources } from '@/lib/project-api';
import { buildProjectExport, type ExportFormat, type ProjectExportNote, type ProjectExportPaper, type ProjectExportSource } from '@/lib/project-export';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface Project {
  id: string;
  title: string;
  description?: string | null;
  owner_id: string;
  current_role: 'owner' | 'editor' | 'viewer';
  created_at?: string;
}

type ProjectNote = ProjectExportNote & { created_by?: string };
type ProjectSource = Pick<ProjectExportSource, 'id' | 'paper_id'>;
type ProjectSourceWithPaper = ProjectExportSource;
type SourcePaper = ProjectExportPaper;

interface EvidenceItem {
  paper_id: string;
  title: string;
  sentence: string;
  start_offset: number;
  end_offset: number;
}

interface EvidenceResponse {
  evidence: EvidenceItem[];
  abstained: boolean;
  explanation: string;
}

interface AnswerResponse {
  summary: string;
  claims?: string[];
  citation_ids?: string[];
  abstained: boolean;
  confidence_explanation: string;
}

interface ComparisonRow {
  paper_id: string;
  problem: string;
  methods: string;
  datasets: string;
  metrics: string;
  limitations: string;
  code_status: string;
}

interface ComparisonResponse {
  rows: ComparisonRow[];
}

interface ProjectSearchResult {
  id: string;
  title: string;
  abstract?: string;
  score?: number;
}

interface ProjectSearchResponse {
  results: ProjectSearchResult[];
}

type ResearchMode = 'search' | 'evidence' | 'answer' | 'compare';
type ResearchResponse = EvidenceResponse | AnswerResponse | ComparisonResponse | ProjectSearchResponse;

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getJWT();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based error when the server does not return JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function isEvidenceResponse(value: ResearchResponse): value is EvidenceResponse {
  return 'evidence' in value;
}

function isAnswerResponse(value: ResearchResponse): value is AnswerResponse {
  return 'claims' in value;
}

function isComparisonResponse(value: ResearchResponse): value is ComparisonResponse {
  return 'rows' in value;
}

function isProjectSearchResponse(value: ResearchResponse): value is ProjectSearchResponse {
  return 'results' in value;
}

function downloadProjectExport(
  format: ExportFormat,
  project: Project,
  sources: ProjectSourceWithPaper[],
  notes: ProjectNote[],
) {
  const content = buildProjectExport(format, project, sources, notes);
  const mime = format === 'csv' ? 'text/csv;charset=utf-8' : 'text/plain;charset=utf-8';
  const extension = format === 'bib' ? 'bib' : format;
  const fileName = project.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'project';
  const blobUrl = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = `${fileName}.${extension}`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
}

export default function ProjectWorkspacePage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const queryClient = useQueryClient();
  const [noteDraft, setNoteDraft] = useState('');
  const [paperToAttach, setPaperToAttach] = useState('');
  const [paperSearch, setPaperSearch] = useState('');
  const [debouncedPaperSearch, setDebouncedPaperSearch] = useState('');
  const [researchQuery, setResearchQuery] = useState('');
  const [researchMode, setResearchMode] = useState<ResearchMode>('evidence');
  const [researchResults, setResearchResults] = useState<ResearchResponse | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedPaperSearch(paperSearch.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [paperSearch]);

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => apiRequest<Project>(`/api/projects/${encodeURIComponent(projectId)}`),
    enabled: !!projectId,
  });

  const notesQuery = useQuery({
    queryKey: ['project-notes', projectId],
    queryFn: () => apiRequest<ProjectNote[]>(`/api/projects/${encodeURIComponent(projectId)}/notes`),
    enabled: !!projectId,
  });

  const sourceQuery = useQuery({
    queryKey: ['project-sources', projectId],
    queryFn: () => fetchProjectSources(projectId),
    enabled: !!projectId,
  });

  const paperChoicesQuery = useQuery({
    queryKey: ['project-source-candidates', debouncedPaperSearch],
    queryFn: () => {
      const search = new URLSearchParams({ limit: '50', offset: '0' });
      if (debouncedPaperSearch) search.set('q', debouncedPaperSearch);
      return apiRequest<SourcePaper[]>(`/api/papers?${search.toString()}`);
    },
  });

  const attachSource = useMutation({
    mutationFn: (paperId: string) => apiRequest<ProjectSource[]>(
      `/api/projects/${encodeURIComponent(projectId)}/sources`,
      { method: 'POST', body: JSON.stringify({ paper_id: paperId }) },
    ),
    onSuccess: async () => {
      setPaperToAttach('');
      setResearchResults(null);
      await queryClient.invalidateQueries({ queryKey: ['project-sources', projectId] });
    },
  });

  const removeSource = useMutation({
    mutationFn: (sourceId: string) => apiRequest<{ status: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(sourceId)}`,
      { method: 'DELETE' },
    ),
    onSuccess: async () => {
      setResearchResults(null);
      await queryClient.invalidateQueries({ queryKey: ['project-sources', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['project-research', projectId] });
    },
  });

  const createNote = useMutation({
    mutationFn: (content: string) => apiRequest<ProjectNote[]>(
      `/api/projects/${encodeURIComponent(projectId)}/notes`,
      { method: 'POST', body: JSON.stringify({ content }) },
    ),
    onSuccess: async () => {
      setNoteDraft('');
      await queryClient.invalidateQueries({ queryKey: ['project-notes', projectId] });
    },
  });

  const research = useMutation({
    mutationFn: ({ query, mode }: { query: string; mode: ResearchMode }) => {
      const path = mode === 'search' ? '/api/retrieval/search' : `/api/research/${mode === 'evidence' ? 'evidence-map' : mode}`;
      const body = mode === 'search'
        ? { query, project_id: projectId, limit: 10 }
        : { query, project_id: projectId };
      return apiRequest<ResearchResponse>(path, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    onSuccess: setResearchResults,
  });

  function handleNoteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = noteDraft.trim();
    if (content) createNote.mutate(content);
  }

  function handleResearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = researchQuery.trim();
    if (query) research.mutate({ query, mode: researchMode });
  }

  if (projectQuery.isLoading) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10 pt-28 sm:px-6">
        <p role="status" className="text-sm text-zenith-muted">Loading project…</p>
      </main>
    );
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10 pt-28 sm:px-6">
        <Link href="/projects" className="text-sm font-medium text-zenith-secondary hover:underline">← Projects</Link>
        <section className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5" role="alert">
          <h1 className="font-serif text-xl text-ink-900">Project unavailable</h1>
          <p className="mt-2 text-sm text-red-800">{projectQuery.error instanceof Error ? projectQuery.error.message : 'This project could not be loaded.'}</p>
        </section>
      </main>
    );
  }

  const project = projectQuery.data;
  const canWrite = project.current_role === 'owner' || project.current_role === 'editor';
  const notes = notesQuery.data ?? [];
  const result = researchResults;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 pt-28 sm:px-6">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/projects" className="mb-4 inline-flex text-sm font-medium text-zenith-muted hover:text-ink-900">← All projects</Link>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-zenith-secondary">Research workspace</p>
          <h1 className="mt-2 font-serif text-3xl font-normal text-ink-900">{project.title}</h1>
          {project.description && <p className="mt-2 max-w-2xl text-sm leading-6 text-zenith-body">{project.description}</p>}
        </div>
        {project.created_at && (
          <p className="pt-7 text-xs text-zenith-muted">Created {new Date(project.created_at).toLocaleDateString()}</p>
        )}
      </div>

      {!canWrite && (
        <p className="mb-5 rounded-xl border border-zenith-border bg-zenith-surface/60 px-4 py-3 text-sm text-zenith-muted" role="status">
          You have read-only access to this project. An owner or editor can add papers and notes.
        </p>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-2" aria-label="Export project">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-zenith-muted">Export</span>
        {([['md', 'Markdown'], ['csv', 'CSV'], ['bib', 'BibTeX']] as const).map(([format, label]) => (
          <button key={format} type="button" onClick={() => downloadProjectExport(format, project, sourceQuery.data ?? [], notesQuery.data ?? [])} disabled={sourceQuery.isLoading || notesQuery.isLoading} className="rounded-full border border-zenith-border bg-white px-3 py-1.5 text-xs font-medium text-ink-900 hover:border-ink-900 disabled:cursor-not-allowed disabled:opacity-50" aria-label={`Export project as ${label}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)]">
        <section className="surface-card p-5 sm:p-6" aria-labelledby="research-heading">
          <div className="mb-5 flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Project research</p>
              <h2 id="research-heading" className="mt-1 font-serif text-xl text-ink-900">Explore attached papers</h2>
            </div>
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 font-mono text-[9px] uppercase tracking-wide text-amber-900">Abstract evidence</span>
          </div>

          <div className="mb-4 rounded-xl border border-zenith-border bg-zenith-surface/60 p-4 text-sm leading-6 text-zenith-body">
            Answers quote abstracts from attached papers. Uploading documents and page-level citations are not available yet.
          </div>

          <form onSubmit={handleResearchSubmit} className="space-y-4">
            <fieldset>
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-zenith-muted">Research mode</legend>
              <div className="flex flex-wrap gap-2">
                {([
                  ['search', 'Search in project'],
                  ['evidence', 'Evidence map'],
                  ['answer', 'Answer'],
                  ['compare', 'Compare'],
                ] as const).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={researchMode === mode}
                    onClick={() => setResearchMode(mode)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${researchMode === mode ? 'border-ink-900 bg-ink-900 text-white' : 'border-zenith-border bg-white text-zenith-body hover:border-ink-900'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </fieldset>
            <label htmlFor="project-research-query" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Question or comparison</label>
            <textarea
              id="project-research-query"
              value={researchQuery}
              onChange={(event) => setResearchQuery(event.target.value)}
              maxLength={500}
              rows={3}
              placeholder="e.g. Which datasets are used to evaluate retrieval quality?"
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-3 text-sm text-ink-900 placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20"
              required
            />
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-zenith-muted">Results quote abstracts; they are not scientific synthesis.</p>
              <button type="submit" disabled={research.isPending || !researchQuery.trim()} className="rounded-xl bg-ink-900 px-4 py-2.5 text-xs font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">
                {research.isPending ? 'Searching…' : 'Run research'}
              </button>
            </div>
          </form>

          {research.isError && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{research.error instanceof Error ? research.error.message : 'Research request failed.'}</p>}

          {result && (
            <div className="mt-6 border-t border-zenith-border pt-5" aria-live="polite">
              <h3 className="mb-3 font-serif text-lg text-ink-900">Results</h3>
              {isEvidenceResponse(result) && (
                <div className="space-y-3">
                  <p className="text-sm text-zenith-body">{result.explanation}</p>
                  {result.evidence.map((item) => (
                    <article key={`${item.paper_id}:${item.start_offset}:${item.end_offset}`} className="rounded-xl border border-zenith-border bg-white p-4">
                      <h4 className="text-sm font-semibold text-ink-900">{item.title || item.paper_id}</h4>
                      <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                      <p className="mt-2 font-mono text-[10px] text-zenith-muted">{item.paper_id} · abstract offsets {item.start_offset}–{item.end_offset}</p>
                    </article>
                  ))}
                  {result.abstained && <p className="rounded-lg bg-zenith-surface p-3 text-sm text-zenith-muted">No matching abstract evidence was found. Attach papers to this project or try a more specific query.</p>}
                </div>
              )}
              {isAnswerResponse(result) && (
                <div className="space-y-3">
                  <p className="text-sm leading-6 text-zenith-body">{result.summary}</p>
                  {result.claims?.map((claim, index) => <p key={`${index}:${claim}`} className="rounded-xl border border-zenith-border bg-white p-4 text-sm leading-6 text-ink-800">{claim}</p>)}
                  {result.abstained && <p className="text-sm text-amber-900">{result.confidence_explanation}</p>}
                  {!result.abstained && <p className="text-xs text-zenith-muted">Extracted from abstracts. Citation IDs: {result.citation_ids?.join(', ') || 'none'}.</p>}
                </div>
              )}
              {isComparisonResponse(result) && (
                result.rows.length ? (
                  <div className="overflow-x-auto rounded-xl border border-zenith-border">
                    <table className="min-w-full text-left text-xs">
                      <caption className="sr-only">Extracted metadata comparison of attached papers</caption>
                      <thead className="bg-zenith-surface text-zenith-muted"><tr>{['Paper', 'Problem / abstract', 'Method', 'Datasets', 'Metrics', 'Limitations', 'Code'].map((heading) => <th key={heading} scope="col" className="px-3 py-2 font-semibold">{heading}</th>)}</tr></thead>
                      <tbody>{result.rows.map((row) => <tr key={row.paper_id} className="border-t border-zenith-border align-top"><th scope="row" className="px-3 py-2 font-mono text-zenith-secondary">{row.paper_id}</th><td className="max-w-xs px-3 py-2 text-zenith-body">{row.problem || 'Not available'}</td><td className="px-3 py-2 text-zenith-body">{row.methods || 'Not available'}</td><td className="px-3 py-2 text-zenith-muted">{row.datasets || 'Not reported'}</td><td className="px-3 py-2 text-zenith-muted">{row.metrics || 'Not reported'}</td><td className="px-3 py-2 text-zenith-muted">{row.limitations || 'Not reported'}</td><td className="px-3 py-2 text-zenith-muted">{row.code_status}</td></tr>)}</tbody>
                    </table>
                  </div>
                ) : <p className="text-sm text-zenith-muted">No papers are attached to this project yet.</p>
              )}
              {isProjectSearchResponse(result) && (
                result.results.length ? (
                  <ul className="space-y-3">
                    {result.results.map((paper) => (
                      <li key={paper.id} className="rounded-xl border border-zenith-border bg-white p-4">
                        <h4 className="text-sm font-semibold text-ink-900">{paper.title}</h4>
                        <p className="mt-1 font-mono text-[10px] text-zenith-muted">{paper.id}{typeof paper.score === 'number' ? ` · score ${paper.score.toFixed(2)}` : ''}</p>
                        {paper.abstract && <p className="mt-2 line-clamp-4 text-sm leading-6 text-zenith-body">{paper.abstract}</p>}
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-zenith-muted">No papers in this project matched the search. Attach a paper or try different terms.</p>
              )}
            </div>
          )}
        </section>

        <div className="space-y-5">
        <section className="surface-card p-5 sm:p-6" aria-labelledby="sources-heading">
          <div className="mb-5">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Project library</p>
            <h2 id="sources-heading" className="mt-1 font-serif text-xl text-ink-900">Attached papers</h2>
          </div>
          {canWrite ? <form onSubmit={(event) => { event.preventDefault(); if (paperToAttach) attachSource.mutate(paperToAttach); }} className="space-y-3">
            <label htmlFor="paper-search" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Find a paper by title</label>
            <input id="paper-search" type="search" value={paperSearch} onChange={(event) => setPaperSearch(event.target.value)} maxLength={200} placeholder="Search your paper feed…" className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900 placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20" />
            <label htmlFor="paper-to-attach" className="sr-only">Choose a paper to add</label>
            <select id="paper-to-attach" value={paperToAttach} onChange={(event) => setPaperToAttach(event.target.value)} className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20">
              <option value="">{paperChoicesQuery.isLoading ? 'Searching…' : 'Choose a paper…'}</option>
              {(paperChoicesQuery.data ?? []).filter((paper) => !(sourceQuery.data ?? []).some((source) => source.paper_id === paper.id)).map((paper) => <option key={paper.id} value={paper.id}>{paper.title}</option>)}
            </select>
            <p className="text-xs text-zenith-muted">Search covers paper titles and shows up to 50 matches. PDF upload is not available yet.</p>
            {paperChoicesQuery.isError && <p role="alert" className="text-xs text-red-700">Could not load paper choices.</p>}
            {attachSource.isError && <p role="alert" className="text-xs text-red-700">{attachSource.error instanceof Error ? attachSource.error.message : 'Could not attach paper.'}</p>}
            <button type="submit" disabled={!paperToAttach || attachSource.isPending} className="w-full rounded-xl border border-ink-900 px-4 py-2.5 text-xs font-semibold text-ink-900 hover:bg-ink-900 hover:text-white disabled:cursor-not-allowed disabled:opacity-50">
              {attachSource.isPending ? 'Adding…' : 'Add paper'}
            </button>
          </form> : <p className="text-sm text-zenith-muted">Only project owners and editors can attach papers.</p>}
          <div className="mt-5 border-t border-zenith-border pt-4">
            {sourceQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading papers…</p>}
            {sourceQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load attached papers.</p>}
            {!sourceQuery.isLoading && !sourceQuery.isError && (sourceQuery.data ?? []).length === 0 && <p className="text-sm leading-6 text-zenith-muted">No papers attached yet. Add one from your feed to use project-scoped research.</p>}
            {removeSource.isError && <p role="alert" className="mb-3 text-xs text-red-700">{removeSource.error instanceof Error ? removeSource.error.message : 'Could not remove paper.'}</p>}
            <ul className="space-y-3">
              {(sourceQuery.data ?? []).map((source) => (
                <li key={source.id} className="rounded-xl border border-zenith-border bg-white p-3">
                  <p className="text-sm font-medium leading-5 text-ink-900">{source.paper?.title ?? source.paper_id}</p>
                  <p className="mt-1 font-mono text-[10px] text-zenith-muted">{source.paper_id}</p>
                  {canWrite && (
                    <button type="button" onClick={() => removeSource.mutate(source.id)} disabled={removeSource.isPending} className="mt-2 text-xs font-medium text-red-700 underline decoration-red-300 underline-offset-2 hover:text-red-900 disabled:opacity-50" aria-label={`Remove ${source.paper?.title ?? source.paper_id} from project`}>
                      Remove paper
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="surface-card p-5 sm:p-6" aria-labelledby="notes-heading">
          <div className="mb-5">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Project notebook</p>
            <h2 id="notes-heading" className="mt-1 font-serif text-xl text-ink-900">Notes</h2>
          </div>
          {canWrite ? <form onSubmit={handleNoteSubmit} className="space-y-3">
            <label htmlFor="project-note" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Add a note</label>
            <textarea
              id="project-note"
              value={noteDraft}
              onChange={(event) => setNoteDraft(event.target.value)}
              maxLength={20000}
              rows={4}
              placeholder="Capture an idea or a question for later…"
              className="w-full rounded-xl border border-zenith-border bg-white px-4 py-3 text-sm text-ink-900 placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20"
              required
            />
            {createNote.isError && <p role="alert" className="text-sm text-red-700">{createNote.error instanceof Error ? createNote.error.message : 'Could not save note.'}</p>}
            <button type="submit" disabled={createNote.isPending || !noteDraft.trim()} className="w-full rounded-xl border border-ink-900 px-4 py-2.5 text-xs font-semibold text-ink-900 hover:bg-ink-900 hover:text-white disabled:cursor-not-allowed disabled:opacity-50">
              {createNote.isPending ? 'Saving…' : 'Save note'}
            </button>
          </form> : <p className="text-sm text-zenith-muted">Only project owners and editors can add notes.</p>}

          <div className="mt-6 border-t border-zenith-border pt-5">
            <h3 className="sr-only">Saved project notes</h3>
            {notesQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading notes…</p>}
            {notesQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load notes.</p>}
            {!notesQuery.isLoading && !notesQuery.isError && notes.length === 0 && <p className="text-sm leading-6 text-zenith-muted">No notes yet. Add the first observation or next step for this project.</p>}
            <ul className="space-y-3">
              {notes.map((note) => (
                <li key={note.id} className="rounded-xl border border-zenith-border bg-white p-4">
                  <p className="whitespace-pre-wrap text-sm leading-6 text-zenith-body">{note.content}</p>
                  {note.created_at && <time className="mt-3 block font-mono text-[10px] text-zenith-muted" dateTime={note.created_at}>{new Date(note.created_at).toLocaleString()}</time>}
                </li>
              ))}
            </ul>
          </div>
        </section>
        </div>
      </div>
    </main>
  );
}
