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

interface ProjectMember {
  project_id: string;
  user_id: string;
  role: 'viewer' | 'editor';
}

interface ProjectInvitation {
  id: string;
  project_id: string;
  email: string;
  role: 'viewer' | 'editor';
  status: string;
  created_at: string;
  expires_at: string;
  email_sent_at: string | null;
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
  pdf_evidence?: {
    document_id: string;
    filename: string;
    page_number: number;
    citation_id: string;
    sentence: string;
    start_offset: number;
    end_offset: number;
  }[];
  abstained: boolean;
  explanation: string;
}

interface AnswerResponse {
  summary: string;
  claims?: string[];
  citation_ids?: string[];
  pdf_evidence?: {
    document_id: string;
    filename: string;
    page_number: number;
    citation_id: string;
    sentence: string;
    start_offset: number;
    end_offset: number;
  }[];
  abstained: boolean;
  confidence_explanation: string;
}

interface ComparisonRow {
  paper_id: string;
  problem: string | null;
  methods: string | null;
  datasets: string | null;
  metrics: string | null;
  limitations: string | null;
  code_status: string;
}

interface ComparisonResponse {
  rows: ComparisonRow[];
  pdf_evidence: {
    document_id: string;
    filename: string;
    page_number: number;
    citation_id: string;
    sentence: string;
    start_offset: number;
    end_offset: number;
  }[];
}

interface ProjectSearchResult {
  id: string;
  source_type: 'paper' | 'pdf_page';
  title: string;
  abstract?: string;
  snippet?: string;
  score?: number;
  citation_id?: string;
  filename?: string;
  page_number?: number;
  start_offset?: number;
  end_offset?: number;
}

interface ProjectSearchResponse {
  results: ProjectSearchResult[];
}

interface SynthesisResponse {
  query: string;
  claims: {
    text: string;
    status: 'supported' | 'conflicting' | 'uncertain';
    supporting_evidence_ids: string[];
    contradicting_evidence_ids: string[];
    cited_evidence_ids: string[];
    explanation: string;
  }[];
  evidence: {
    evidence_id: string;
    paper_id: string;
    title: string;
    sentence: string;
    start_offset: number;
    end_offset: number;
  }[];
  abstained: boolean;
  explanation: string;
}

interface ResearchCapabilities {
  research_synthesis_enabled: boolean;
}

interface ProjectDocument {
  id: string;
  filename: string;
  page_count: number;
  created_at?: string;
}

interface ProjectDocumentPage {
  page_number: number;
  text: string;
  citation_id: string;
}

interface ProjectDocumentPages {
  id: string;
  filename: string;
  page_count: number;
  pages: ProjectDocumentPage[];
}

type ResearchMode = 'search' | 'evidence' | 'answer' | 'compare' | 'synthesize';
type ResearchResponse = EvidenceResponse | AnswerResponse | ComparisonResponse | ProjectSearchResponse | SynthesisResponse;

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getJWT();
  const isMultipart = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(!isMultipart ? { 'Content-Type': 'application/json' } : {}),
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
  return 'evidence' in value && !('claims' in value);
}

function isAnswerResponse(value: ResearchResponse): value is AnswerResponse {
  return 'claims' in value && !('evidence' in value);
}

function isSynthesisResponse(value: ResearchResponse): value is SynthesisResponse {
  return 'claims' in value && 'evidence' in value;
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
  const [memberId, setMemberId] = useState('');
  const [memberRole, setMemberRole] = useState<'viewer' | 'editor'>('viewer');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'viewer' | 'editor'>('viewer');
  const [debouncedPaperSearch, setDebouncedPaperSearch] = useState('');
  const [researchQuery, setResearchQuery] = useState('');
  const [researchMode, setResearchMode] = useState<ResearchMode>('evidence');
  const [researchResults, setResearchResults] = useState<ResearchResponse | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedPaperSearch(paperSearch.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [paperSearch]);

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => apiRequest<Project>(`/api/projects/${encodeURIComponent(projectId)}`),
    enabled: !!projectId,
  });

  const researchCapabilitiesQuery = useQuery({
    queryKey: ['research-capabilities'],
    queryFn: () => apiRequest<ResearchCapabilities>('/api/research/capabilities'),
    staleTime: 5 * 60 * 1000,
  });

  const membersQuery = useQuery({
    queryKey: ['project-members', projectId],
    queryFn: () => apiRequest<ProjectMember[]>(`/api/projects/${encodeURIComponent(projectId)}/members`),
    enabled: projectQuery.data?.current_role === 'owner',
  });

  const invitationsQuery = useQuery({
    queryKey: ['project-invitations', projectId],
    queryFn: () => apiRequest<ProjectInvitation[]>(`/api/projects/${encodeURIComponent(projectId)}/invitations`),
    enabled: projectQuery.data?.current_role === 'owner',
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

  const documentsQuery = useQuery({
    queryKey: ['project-documents', projectId],
    queryFn: () => apiRequest<ProjectDocument[]>(`/api/projects/${encodeURIComponent(projectId)}/documents`),
    enabled: !!projectId,
  });

  const documentPagesQuery = useQuery({
    queryKey: ['project-document-pages', projectId, selectedDocumentId],
    queryFn: () => apiRequest<ProjectDocumentPages>(
      `/api/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(selectedDocumentId!)}/pages`,
    ),
    enabled: !!projectId && !!selectedDocumentId,
  });

  const uploadDocument = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      return apiRequest<ProjectDocument>(
        `/api/projects/${encodeURIComponent(projectId)}/documents`,
        { method: 'POST', body: formData },
      );
    },
    onSuccess: async (document) => {
      setPdfFile(null);
      setSelectedDocumentId(document.id);
      await queryClient.invalidateQueries({ queryKey: ['project-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['project-document-pages', projectId] });
    },
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

  const addMember = useMutation({
    mutationFn: (input: { user_id: string; role: 'viewer' | 'editor' }) => apiRequest<ProjectMember[]>(
      `/api/projects/${encodeURIComponent(projectId)}/members`,
      { method: 'POST', body: JSON.stringify(input) },
    ),
    onSuccess: async () => {
      setMemberId('');
      await queryClient.invalidateQueries({ queryKey: ['project-members', projectId] });
    },
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) => apiRequest<{ status: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`,
      { method: 'DELETE' },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-members', projectId] }),
  });

  const createInvitation = useMutation({
    mutationFn: (input: { email: string; role: 'viewer' | 'editor' }) => apiRequest<ProjectInvitation>(
      `/api/projects/${encodeURIComponent(projectId)}/invitations`,
      { method: 'POST', body: JSON.stringify(input) },
    ),
    onSuccess: async () => {
      setInviteEmail('');
      await queryClient.invalidateQueries({ queryKey: ['project-invitations', projectId] });
    },
  });

  const resendInvitation = useMutation({
    mutationFn: (invitationId: string) => apiRequest<ProjectInvitation>(
      `/api/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(invitationId)}/resend`,
      { method: 'POST' },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-invitations', projectId] }),
  });

  const revokeInvitation = useMutation({
    mutationFn: (invitationId: string) => apiRequest<{ status: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(invitationId)}`,
      { method: 'DELETE' },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-invitations', projectId] }),
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
  const canManageMembers = project.current_role === 'owner';
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
              <h2 id="research-heading" className="mt-1 font-serif text-xl text-ink-900">Search project sources</h2>
            </div>
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 font-mono text-[9px] uppercase tracking-wide text-amber-900">Paper + PDF search</span>
          </div>

          <div className="mb-4 rounded-xl border border-zenith-border bg-zenith-surface/60 p-4 text-sm leading-6 text-zenith-body">
            Project search, answers, evidence maps, and comparisons can use exact sentences from up to 10 uploaded PDFs/500 pages. Synthesis uses attached papers&apos; public abstracts only; uploaded private PDF text is never sent to an LLM provider. Model-reviewed claims remain provisional and cite their exact source sentences.
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
                  ['synthesize', 'Synthesize'],
                ] as const).filter(([mode]) =>
                  mode !== 'synthesize' || researchCapabilitiesQuery.data?.research_synthesis_enabled === true,
                ).map(([mode, label]) => (
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
              <p className="text-xs text-zenith-muted">{researchMode === 'synthesize' ? 'Uses at most six public abstract sentences and two bounded model calls; PDF text is excluded.' : 'Results quote abstracts; they are not scientific synthesis.'}</p>
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
                  {result.pdf_evidence?.map((item) => (
                    <article key={`${item.citation_id}:${item.start_offset}`} className="rounded-xl border border-zenith-secondary/30 bg-zenith-surface/60 p-4">
                      <h4 className="text-sm font-semibold text-ink-900">{item.filename} · page {item.page_number}</h4>
                      <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                      <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{item.citation_id}] · page offsets {item.start_offset}–{item.end_offset}</p>
                    </article>
                  ))}
                  {result.abstained && <p className="rounded-lg bg-zenith-surface p-3 text-sm text-zenith-muted">No matching abstract or PDF page evidence was found. Attach papers or upload a text-based PDF, then try a more specific query.</p>}
                </div>
              )}
              {isSynthesisResponse(result) && (
                <div className="space-y-3">
                  <p className="text-sm leading-6 text-zenith-body">{result.explanation}</p>
                  {result.abstained && <p className="rounded-lg bg-zenith-surface p-3 text-sm text-zenith-muted">No cross-paper claim met the source and review requirements. {result.evidence.length < 2 ? 'Attach relevant papers with matching evidence.' : ''}</p>}
                  {result.claims.map((claim, index) => {
                    const statusLabel = claim.status === 'supported' ? 'Model-reviewed support' : claim.status === 'conflicting' ? 'Conflicting source findings' : 'Uncertain support';
                    const cited = result.evidence.filter((item) => claim.cited_evidence_ids.includes(item.evidence_id));
                    return (
                      <article key={`${index}:${claim.text}`} className="rounded-xl border border-zenith-border bg-white p-4">
                        <p className="font-mono text-[10px] uppercase tracking-wide text-zenith-secondary">{statusLabel}</p>
                        <p className="mt-2 text-sm leading-6 text-ink-900">{claim.text}</p>
                        {claim.explanation && <p className="mt-2 text-xs leading-5 text-zenith-muted">{claim.explanation}</p>}
                        <ul className="mt-3 space-y-2">
                          {cited.map((item) => (
                            <li key={item.evidence_id} className="border-l-2 border-zenith-secondary/60 pl-3">
                              <blockquote className="text-xs leading-5 text-zenith-body">“{item.sentence}”</blockquote>
                              <p className="mt-1 font-mono text-[10px] text-zenith-muted">{item.title || item.paper_id} · {item.paper_id} · abstract offsets {item.start_offset}–{item.end_offset}</p>
                            </li>
                          ))}
                        </ul>
                      </article>
                    );
                  })}
                  {!result.abstained && <p className="text-xs text-zenith-muted">Provider assessments are provisional and are not independent scientific verification.</p>}
                </div>
              )}
              {isAnswerResponse(result) && (
                <div className="space-y-3">
                  <p className="text-sm leading-6 text-zenith-body">{result.summary}</p>
                  {result.claims?.map((claim, index) => <p key={`${index}:${claim}`} className="rounded-xl border border-zenith-border bg-white p-4 text-sm leading-6 text-ink-800">{claim}</p>)}
                  {result.pdf_evidence?.map((item) => (
                    <article key={`${item.citation_id}:${item.start_offset}`} className="rounded-xl border border-zenith-secondary/30 bg-zenith-surface/60 p-4">
                      <h4 className="text-sm font-semibold text-ink-900">{item.filename} · page {item.page_number}</h4>
                      <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                      <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{item.citation_id}] · page offsets {item.start_offset}–{item.end_offset}</p>
                    </article>
                  ))}
                  {result.abstained && <p className="text-sm text-amber-900">{result.confidence_explanation}</p>}
                  {!result.abstained && <p className="text-xs text-zenith-muted">Extractive evidence only. Citation IDs: {result.citation_ids?.join(', ') || 'none'}.</p>}
                </div>
              )}
              {isComparisonResponse(result) && (
                <div className="space-y-4">
                  {result.rows.length > 0 && (
                    <div className="overflow-x-auto rounded-xl border border-zenith-border">
                      <table className="min-w-full text-left text-xs">
                        <caption className="sr-only">Heuristic comparison using exact abstract sentences from attached papers</caption>
                        <thead className="bg-zenith-surface text-zenith-muted"><tr>{['Paper', 'Research focus (abstract)', 'Methods (abstract)', 'Datasets (abstract)', 'Metrics (abstract)', 'Limitations (abstract)', 'Code status'].map((heading) => <th key={heading} scope="col" className="px-3 py-2 font-semibold">{heading}</th>)}</tr></thead>
                        <tbody>{result.rows.map((row) => <tr key={row.paper_id} className="border-t border-zenith-border align-top"><th scope="row" className="px-3 py-2 font-mono text-zenith-secondary">{row.paper_id}</th><td className="max-w-xs px-3 py-2 text-zenith-body">{row.problem ?? 'Not identified in abstract'}</td><td className="px-3 py-2 text-zenith-body">{row.methods ?? 'Not identified in abstract'}</td><td className="px-3 py-2 text-zenith-muted">{row.datasets ?? 'Not identified in abstract'}</td><td className="px-3 py-2 text-zenith-muted">{row.metrics ?? 'Not identified in abstract'}</td><td className="px-3 py-2 text-zenith-muted">{row.limitations ?? 'Not identified in abstract'}</td><td className="px-3 py-2 text-zenith-muted">Unverified</td></tr>)}</tbody>
                      </table>
                      <p className="border-t border-zenith-border bg-white px-3 py-2 text-xs text-zenith-muted">Heuristic keyword matches return exact abstract sentences. Empty fields mean no matching sentence was found; the extracted categories are not independently verified.</p>
                    </div>
                  )}
                  {result.pdf_evidence.length > 0 && (
                    <section aria-labelledby="comparison-pdf-evidence-heading" className="space-y-3">
                      <h3 id="comparison-pdf-evidence-heading" className="text-xs font-semibold uppercase tracking-wide text-zenith-muted">PDF source evidence · extractive, not synthesized</h3>
                      <ul className="space-y-3">
                        {result.pdf_evidence.map((item) => (
                          <li key={`${item.citation_id}:${item.start_offset}`} className="rounded-xl border border-zenith-border bg-white p-4">
                            <p className="text-xs font-semibold text-ink-900">{item.filename} · page {item.page_number}</p>
                            <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                            <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{item.citation_id}] · page offsets {item.start_offset}–{item.end_offset}</p>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {result.rows.length === 0 && result.pdf_evidence.length === 0 && <p className="text-sm text-zenith-muted">No matching attached paper or PDF evidence was found for this comparison.</p>}
                </div>
              )}
              {isProjectSearchResponse(result) && (
                result.results.length ? (
                  <ul className="space-y-3">
                    {result.results.map((paper) => (
                      <li key={paper.id} className="rounded-xl border border-zenith-border bg-white p-4">
                        <h4 className="text-sm font-semibold text-ink-900">
                          {paper.source_type === 'pdf_page' ? `${paper.filename ?? paper.title} · page ${paper.page_number ?? '?'}` : paper.title}
                        </h4>
                        <p className="mt-1 font-mono text-[10px] text-zenith-muted">{paper.id}{typeof paper.score === 'number' ? ` · score ${paper.score.toFixed(2)}` : ''}</p>
                        {paper.snippet && <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{paper.snippet}”</blockquote>}
                        {paper.citation_id && <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{paper.citation_id}] · page offsets {paper.start_offset}–{paper.end_offset}</p>}
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
        {canManageMembers && (
          <section className="surface-card p-5 sm:p-6" aria-labelledby="members-heading">
            <div className="mb-4">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Collaboration</p>
              <h2 id="members-heading" className="mt-1 font-serif text-xl text-ink-900">Project members</h2>
            </div>
            <form onSubmit={(event) => { event.preventDefault(); const id = memberId.trim(); if (id) addMember.mutate({ user_id: id, role: memberRole }); }} className="space-y-3">
              <label htmlFor="member-id" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Existing account user ID</label>
              <input id="member-id" value={memberId} onChange={(event) => setMemberId(event.target.value)} maxLength={36} pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" title="Enter a valid user UUID" required placeholder="00000000-0000-4000-8000-000000000000" className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 font-mono text-xs text-ink-900 placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20" />
              <label htmlFor="member-role" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Project role</label>
              <select id="member-role" value={memberRole} onChange={(event) => setMemberRole(event.target.value as 'viewer' | 'editor')} className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900">
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <p className="text-xs text-zenith-muted">Adds an existing Zenith account by its user UUID.</p>
              {addMember.isError && <p role="alert" className="text-xs text-red-700">{addMember.error instanceof Error ? addMember.error.message : 'Could not add member.'}</p>}
              <button type="submit" disabled={!memberId.trim() || addMember.isPending} className="w-full rounded-xl border border-ink-900 px-4 py-2.5 text-xs font-semibold text-ink-900 hover:bg-ink-900 hover:text-white disabled:cursor-not-allowed disabled:opacity-50">
                {addMember.isPending ? 'Adding…' : 'Add or update member'}
              </button>
            </form>
            <div className="mt-5 border-t border-zenith-border pt-4">
              {membersQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading members…</p>}
              {membersQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load project members.</p>}
              {removeMember.isError && <p role="alert" className="text-sm text-red-700">Could not remove this member.</p>}
              {!membersQuery.isLoading && !membersQuery.isError && (membersQuery.data ?? []).length === 0 && <p className="text-sm text-zenith-muted">No members have been added yet.</p>}
              <ul className="space-y-2">
                {(membersQuery.data ?? []).map((member) => (
                  <li key={member.user_id} className="flex items-center justify-between gap-3 rounded-lg border border-zenith-border bg-white p-3">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-ink-900">{member.user_id}</p>
                      <p className="mt-1 text-xs capitalize text-zenith-muted">{member.role}</p>
                    </div>
                    <button type="button" onClick={() => removeMember.mutate(member.user_id)} disabled={removeMember.isPending} className="shrink-0 text-xs font-medium text-red-700 underline decoration-red-300 underline-offset-2 disabled:opacity-50" aria-label={`Remove member ${member.user_id}`}>Remove</button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-5 border-t border-zenith-border pt-4">
              <h3 className="mb-3 text-sm font-semibold text-ink-900">Invite by email</h3>
              <form onSubmit={(event) => { event.preventDefault(); const email = inviteEmail.trim(); if (email) createInvitation.mutate({ email, role: inviteRole }); }} className="space-y-3">
                <label htmlFor="invite-email" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Email address</label>
                <input id="invite-email" type="email" autoComplete="email" required maxLength={320} value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900" />
                <label htmlFor="invite-role" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Invitation role</label>
                <select id="invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value as 'viewer' | 'editor')} className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900">
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                {createInvitation.isError && <p role="alert" className="text-xs text-red-700">{createInvitation.error instanceof Error ? createInvitation.error.message : 'Could not send invitation.'}</p>}
                <button type="submit" disabled={!inviteEmail.trim() || createInvitation.isPending} className="w-full rounded-xl bg-ink-900 px-4 py-2.5 text-xs font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">{createInvitation.isPending ? 'Sending…' : 'Send invitation'}</button>
              </form>
              <div className="mt-4 border-t border-zenith-border pt-4">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zenith-muted">Invitations</h4>
                {invitationsQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading invitations…</p>}
                {invitationsQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load invitations.</p>}
                {resendInvitation.isError && <p role="alert" className="text-sm text-red-700">Could not resend invitation.</p>}
                {revokeInvitation.isError && <p role="alert" className="text-sm text-red-700">Could not revoke invitation.</p>}
                {!invitationsQuery.isLoading && !invitationsQuery.isError && (invitationsQuery.data ?? []).length === 0 && <p className="text-sm text-zenith-muted">No email invitations yet.</p>}
                <ul className="space-y-2">
                  {(invitationsQuery.data ?? []).map((invitation) => (
                    <li key={invitation.id} className="rounded-lg border border-zenith-border bg-white p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="break-all text-sm font-medium text-ink-900">{invitation.email}</p>
                          <p className="mt-1 text-xs capitalize text-zenith-muted">{invitation.role} · {invitation.status}</p>
                          <p className="mt-1 text-[11px] text-zenith-muted">Expires {new Date(invitation.expires_at).toLocaleDateString()}</p>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <button type="button" onClick={() => resendInvitation.mutate(invitation.id)} disabled={resendInvitation.isPending || invitation.status === 'accepted' || invitation.status === 'revoked'} className="text-xs font-medium text-zenith-secondary underline disabled:opacity-50" aria-label={`Resend invitation to ${invitation.email}`}>Resend</button>
                          <button type="button" onClick={() => revokeInvitation.mutate(invitation.id)} disabled={revokeInvitation.isPending || invitation.status === 'accepted' || invitation.status === 'revoked'} className="text-xs font-medium text-red-700 underline disabled:opacity-50" aria-label={`Revoke invitation to ${invitation.email}`}>Revoke</button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        )}
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
            <p className="text-xs text-zenith-muted">Search covers paper titles and shows up to 50 matches.</p>
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

        <section className="surface-card p-5 sm:p-6" aria-labelledby="documents-heading">
          <div className="mb-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Primary sources</p>
            <h2 id="documents-heading" className="mt-1 font-serif text-xl text-ink-900">PDF documents</h2>
          </div>
          {canWrite ? (
            <form onSubmit={(event) => { event.preventDefault(); if (pdfFile) uploadDocument.mutate(pdfFile); }} className="space-y-3">
              <label htmlFor="project-pdf" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Upload a PDF you have permission to use</label>
              <input id="project-pdf" type="file" accept="application/pdf,.pdf" onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)} className="block w-full text-xs text-zenith-body file:mr-3 file:rounded-lg file:border file:border-zenith-border file:bg-white file:px-3 file:py-2 file:text-xs file:font-medium file:text-ink-900" />
              <p className="text-xs leading-5 text-zenith-muted">Maximum 20 MiB and 500 pages. Text is extracted per page; the original PDF is not retained. Scanned pages need OCR, which is not available.</p>
              {uploadDocument.isError && <p role="alert" className="text-sm text-red-700">{uploadDocument.error instanceof Error ? uploadDocument.error.message : 'Could not process this PDF.'}</p>}
              <button type="submit" disabled={!pdfFile || uploadDocument.isPending} className="w-full rounded-xl border border-ink-900 px-4 py-2.5 text-xs font-semibold text-ink-900 hover:bg-ink-900 hover:text-white disabled:cursor-not-allowed disabled:opacity-50">
                {uploadDocument.isPending ? 'Extracting pages…' : 'Upload and extract pages'}
              </button>
            </form>
          ) : <p className="text-sm text-zenith-muted">Only project owners and editors can upload documents.</p>}
          <div className="mt-5 border-t border-zenith-border pt-4">
            {documentsQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading documents…</p>}
            {documentsQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load project documents.</p>}
            {!documentsQuery.isLoading && !documentsQuery.isError && (documentsQuery.data ?? []).length === 0 && <p className="text-sm text-zenith-muted">No PDF documents uploaded yet.</p>}
            <ul className="space-y-2">
              {(documentsQuery.data ?? []).map((document) => (
                <li key={document.id} className="flex items-center justify-between gap-3 rounded-lg border border-zenith-border bg-white p-3">
                  <div className="min-w-0">
                    <p className="break-all text-sm font-medium text-ink-900">{document.filename}</p>
                    <p className="mt-1 font-mono text-[10px] text-zenith-muted">{document.page_count} {document.page_count === 1 ? 'page' : 'pages'}</p>
                  </div>
                  <button type="button" onClick={() => setSelectedDocumentId(document.id)} className="shrink-0 text-xs font-medium text-zenith-secondary underline underline-offset-2" aria-label={`View pages in ${document.filename}`}>View pages</button>
                </li>
              ))}
            </ul>
          </div>
          {documentPagesQuery.isLoading && <p role="status" className="mt-4 text-sm text-zenith-muted">Loading extracted pages…</p>}
          {documentPagesQuery.isError && <p role="alert" className="mt-4 text-sm text-red-700">Could not load extracted pages.</p>}
          {documentPagesQuery.data && (
            <div className="mt-5 space-y-3 border-t border-zenith-border pt-4" aria-label={`Extracted pages from ${documentPagesQuery.data.filename}`}>
              {documentPagesQuery.data.pages.map((page) => (
                <article key={page.page_number} className="rounded-xl border border-zenith-border bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-ink-900">Page {page.page_number}</h3>
                    <code className="font-mono text-[10px] text-zenith-secondary">[{page.citation_id}]</code>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-zenith-body">{page.text || 'No selectable text found on this page.'}</p>
                </article>
              ))}
            </div>
          )}
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
