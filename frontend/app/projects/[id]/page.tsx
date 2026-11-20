'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { useParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getJWT } from '@/lib/auth';
import { executeResearchPlan } from '@/lib/api';
import { fetchProjectSources } from '@/lib/project-api';
import { createProjectAnnotation, deleteProjectAnnotation, fetchProjectAnnotations, updateProjectAnnotation } from '@/lib/project-annotations-api';
import { createSavedSearch, deleteSavedSearch, fetchSavedSearches, runSavedSearch, updateSavedSearch } from '@/lib/saved-searches-api';
import ResearchPlanExecutionPanel from '@/components/ResearchPlanExecutionPanel';
import ProjectBriefsPanel from '@/components/ProjectBriefsPanel';
import { StreamingResponse } from '@/components/StreamingResponse';
import { buildProjectExport, type ExportFormat, type ProjectExportNote, type ProjectExportPaper, type ProjectExportSource } from '@/lib/project-export';
import type { PaperSearchResult, ProjectAnnotation, ProjectAnnotationAnchor, ProjectBriefSourceLocator, ResearchPlanPreview, SavedSearch } from '@/types';

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
  pdf_comparisons?: PdfComparisonRow[];
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

interface PdfComparisonEvidence {
  sentence: string;
  citation_id: string;
  page_number: number;
  start_offset: number;
  end_offset: number;
}

interface PdfComparisonRow {
  document_id: string;
  filename: string;
  problem?: PdfComparisonEvidence | null;
  methods?: PdfComparisonEvidence | null;
  datasets?: PdfComparisonEvidence | null;
  metrics?: PdfComparisonEvidence | null;
  limitations?: PdfComparisonEvidence | null;
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

type ResearchPlanResponse = ResearchPlanPreview;

interface ProjectDocument {
  id: string;
  filename: string;
  page_count: number;
  created_at?: string;
}

type ExtractionMethod = 'native' | 'ocr' | 'empty' | 'ocr_limit';

interface ProjectDocumentPage {
  page_number: number;
  text: string;
  citation_id: string;
  extraction_method: ExtractionMethod;
}

interface ProjectDocumentPages {
  id: string;
  filename: string;
  page_count: number;
  pages: ProjectDocumentPage[];
}

type ResearchMode = 'search' | 'plan' | 'evidence' | 'answer' | 'compare' | 'synthesize';
type ResearchResponse = ResearchPlanResponse | EvidenceResponse | AnswerResponse | ComparisonResponse | ProjectSearchResponse | SynthesisResponse;

type AnnotationAnchorDraft = ProjectAnnotationAnchor & { label: string };

function getTokenSubject(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(payload.length / 4) * 4, '=');
    const claims = JSON.parse(window.atob(base64)) as { sub?: unknown };
    return typeof claims.sub === 'string' ? claims.sub : null;
  } catch {
    return null;
  }
}

function extractionMethodLabel(method: ExtractionMethod): string {
  switch (method) {
    case 'native': return 'Native text';
    case 'ocr': return 'OCR text';
    case 'empty': return 'No text found';
    case 'ocr_limit': return 'OCR page limit reached';
  }
}

function emptyPageMessage(method: ExtractionMethod): string {
  if (method === 'ocr') return 'OCR found no readable text on this page.';
  if (method === 'ocr_limit') return 'This scanned page was not processed because the OCR page limit was reached.';
  return 'No text found on this page.';
}

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

function isResearchPlanResponse(value: ResearchResponse): value is ResearchPlanResponse {
  return 'steps' in value && 'execution_available' in value;
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
  const [savedSearchName, setSavedSearchName] = useState('');
  const [savedSearchQueryDraft, setSavedSearchQueryDraft] = useState('');
  const [editingSavedSearchId, setEditingSavedSearchId] = useState<string | null>(null);
  const [editingSavedSearchName, setEditingSavedSearchName] = useState('');
  const [editingSavedSearchQuery, setEditingSavedSearchQuery] = useState('');
  const [editingSavedSearchModel, setEditingSavedSearchModel] = useState<string | null>(null);
  const [activeSavedSearchRunId, setActiveSavedSearchRunId] = useState<string | null>(null);
  const [savedSearchRunResult, setSavedSearchRunResult] = useState<PaperSearchResult | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [annotationAnchor, setAnnotationAnchor] = useState<AnnotationAnchorDraft | null>(null);
  const [annotationDraft, setAnnotationDraft] = useState('');
  const [editingAnnotationId, setEditingAnnotationId] = useState<string | null>(null);
  const [editingAnnotationDraft, setEditingAnnotationDraft] = useState('');
  const [briefSources, setBriefSources] = useState<ProjectBriefSourceLocator[]>([]);
  const [paperToAttach, setPaperToAttach] = useState('');
  const [paperSearch, setPaperSearch] = useState('');
  const [memberId, setMemberId] = useState('');
  const [memberRole, setMemberRole] = useState<'viewer' | 'editor'>('viewer');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'viewer' | 'editor'>('viewer');
  const [copiedInvitationId, setCopiedInvitationId] = useState<string | null>(null);
  const [invitationLinkError, setInvitationLinkError] = useState<string | null>(null);
  const [debouncedPaperSearch, setDebouncedPaperSearch] = useState('');
  const [researchQuery, setResearchQuery] = useState('');
  const [researchMode, setResearchMode] = useState<ResearchMode>('evidence');
  const [researchResults, setResearchResults] = useState<ResearchResponse | null>(null);
  const [executionRunId, setExecutionRunId] = useState<string | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedPaperSearch(paperSearch.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [paperSearch]);

  useEffect(() => {
    let active = true;
    void getJWT().then((token) => {
      if (active) setCurrentUserId(getTokenSubject(token));
    }).catch(() => {
      if (active) setCurrentUserId(null);
    });
    return () => { active = false; };
  }, []);

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

  const annotationsQuery = useQuery({
    queryKey: ['project-annotations', projectId],
    queryFn: () => fetchProjectAnnotations(projectId),
    enabled: !!projectId,
  });

  const savedSearchesQuery = useQuery({
    queryKey: ['saved-searches', projectId],
    queryFn: fetchSavedSearches,
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
      if (pdfInputRef.current) pdfInputRef.current.value = '';
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

  const createAnnotation = useMutation({
    mutationFn: ({ anchor, content }: { anchor: ProjectAnnotationAnchor; content: string }) =>
      createProjectAnnotation(projectId, anchor, content),
    onSuccess: async () => {
      setAnnotationAnchor(null);
      setAnnotationDraft('');
      await queryClient.invalidateQueries({ queryKey: ['project-annotations', projectId] });
    },
  });

  const updateAnnotation = useMutation({
    mutationFn: ({ annotationId, content }: { annotationId: string; content: string }) =>
      updateProjectAnnotation(projectId, annotationId, content),
    onSuccess: async () => {
      setEditingAnnotationId(null);
      setEditingAnnotationDraft('');
      await queryClient.invalidateQueries({ queryKey: ['project-annotations', projectId] });
    },
  });

  const removeAnnotation = useMutation({
    mutationFn: (annotationId: string) => deleteProjectAnnotation(projectId, annotationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-annotations', projectId] }),
  });

  const createSavedSearchMutation = useMutation({
    mutationFn: () => createSavedSearch({
      name: savedSearchName.trim(),
      query: savedSearchQueryDraft.trim(),
      project_id: projectId,
    }),
    onSuccess: async () => {
      setSavedSearchName('');
      setSavedSearchQueryDraft('');
      await queryClient.invalidateQueries({ queryKey: ['saved-searches', projectId] });
    },
  });

  const updateSavedSearchMutation = useMutation({
    mutationFn: ({ id, name, query, model }: { id: string; name: string; query: string; model: string | null }) =>
      updateSavedSearch(id, { name: name.trim(), query: query.trim(), model }),
    onSuccess: async () => {
      setEditingSavedSearchId(null);
      await queryClient.invalidateQueries({ queryKey: ['saved-searches', projectId] });
    },
  });

  const deleteSavedSearchMutation = useMutation({
    mutationFn: deleteSavedSearch,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-searches', projectId] }),
  });

  const runSavedSearchMutation = useMutation({
    mutationFn: runSavedSearch,
    onSuccess: ({ run_id }) => {
      setSavedSearchRunResult(null);
      setActiveSavedSearchRunId(run_id);
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

  async function copyInvitationLink(invitationId: string) {
    setInvitationLinkError(null);
    try {
      const url = new URL('/projects/invitations/accept', window.location.origin);
      url.searchParams.set('invitation_id', invitationId);
      await navigator.clipboard.writeText(url.toString());
      setCopiedInvitationId(invitationId);
    } catch {
      setInvitationLinkError('Could not copy the invitation link. Open the accept page below and copy its address instead.');
    }
  }

  const executePlan = useMutation({
    mutationFn: ({ query, projectId: scopedProjectId }: { query: string; projectId?: string }) => executeResearchPlan(query, scopedProjectId),
    onSuccess: ({ runId }) => setExecutionRunId(runId),
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
    onSuccess: (data) => {
      setResearchResults(data);
      setExecutionRunId(null);
      executePlan.reset();
    },
  });

  function handleNoteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = noteDraft.trim();
    if (content) createNote.mutate(content);
  }

  function beginAnnotation(anchor: ProjectAnnotationAnchor, label: string) {
    setAnnotationAnchor({ ...anchor, label });
    setAnnotationDraft('');
    createAnnotation.reset();
  }

  function addQuoteToBrief(source: ProjectBriefSourceLocator) {
    setBriefSources((current) => {
      if (current.length >= 50) return current;
      const alreadyAdded = current.some((item) => item.source_type === source.source_type
        && (item.source_type === 'paper_abstract'
          ? source.source_type === 'paper_abstract' && item.paper_source_id === source.paper_source_id
          : source.source_type === 'pdf_page' && item.document_id === source.document_id && item.page_number === source.page_number)
        && item.start_offset === source.start_offset
        && item.end_offset === source.end_offset);
      return alreadyAdded ? current : [...current, source];
    });
  }

  function handleAnnotationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = annotationDraft.trim();
    if (!annotationAnchor || !content) return;
    const anchor: ProjectAnnotationAnchor = annotationAnchor.source_type === 'paper_abstract'
      ? {
        source_type: 'paper_abstract',
        paper_source_id: annotationAnchor.paper_source_id,
        start_offset: annotationAnchor.start_offset,
        end_offset: annotationAnchor.end_offset,
        quote: annotationAnchor.quote,
      }
      : {
        source_type: 'pdf_page',
        document_id: annotationAnchor.document_id,
        page_number: annotationAnchor.page_number,
        start_offset: annotationAnchor.start_offset,
        end_offset: annotationAnchor.end_offset,
        quote: annotationAnchor.quote,
      };
    createAnnotation.mutate({ anchor, content });
  }

  function beginAnnotationEdit(annotation: ProjectAnnotation) {
    setEditingAnnotationId(annotation.id);
    setEditingAnnotationDraft(annotation.content);
    updateAnnotation.reset();
  }

  function handleAnnotationEdit(event: FormEvent<HTMLFormElement>, annotationId: string) {
    event.preventDefault();
    const content = editingAnnotationDraft.trim();
    if (content) updateAnnotation.mutate({ annotationId, content });
  }

  function handleResearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = researchQuery.trim();
    if (query) {
      setExecutionRunId(null);
      executePlan.reset();
      research.mutate({ query, mode: researchMode });
    }
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
                  ['plan', 'Plan'],
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
              <p className="text-xs text-zenith-muted">{researchMode === 'plan' ? 'Preview only. No sources, providers, or tools are accessed.' : researchMode === 'synthesize' ? 'Uses at most six public abstract sentences and two bounded model calls; PDF text is excluded.' : 'Results quote abstracts; they are not scientific synthesis.'}</p>
              <button type="submit" disabled={research.isPending || !researchQuery.trim()} className="rounded-xl bg-ink-900 px-4 py-2.5 text-xs font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">
                {research.isPending ? 'Working…' : researchMode === 'plan' ? 'Preview plan' : 'Run research'}
              </button>
            </div>
          </form>

          {research.isError && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{research.error instanceof Error ? research.error.message : 'Research request failed.'}</p>}

          {result && (
            <div className="mt-6 border-t border-zenith-border pt-5" aria-live="polite">
              <h3 className="mb-3 font-serif text-lg text-ink-900">Results</h3>
              {isResearchPlanResponse(result) && (
                <section aria-labelledby="research-plan-preview-heading" className="space-y-4">
                  <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
                    Preview only. This plan has not run; its limits do not constrain separate research requests.
                  </div>
                  <div>
                    <h4 id="research-plan-preview-heading" className="font-semibold text-ink-900">{result.task_type.replace('_', ' ')} · {result.source_scope === 'project' ? 'project sources' : 'public corpus'}</h4>
                    <p className="mt-1 text-sm text-zenith-body">{result.query}</p>
                  </div>
                  <ol className="space-y-2" aria-label="Proposed research steps">
                    {result.steps.map((step, index) => (
                      <li key={`${index}:${step.step_id}`} className="rounded-lg border border-zenith-border bg-white p-3">
                        <p className="text-sm font-semibold text-ink-900">{index + 1}. {step.title} <span className="font-mono text-[10px] uppercase text-zenith-muted">· proposed</span></p>
                        <p className="mt-1 text-xs leading-5 text-zenith-body">{step.description}</p>
                      </li>
                    ))}
                  </ol>
                  <dl className="grid grid-cols-2 gap-2 rounded-lg bg-zenith-surface p-3 text-xs">
                    <div><dt className="text-zenith-muted">Source cap</dt><dd className="font-semibold text-ink-900">{result.max_sources}</dd></div>
                    <div><dt className="text-zenith-muted">Tool calls</dt><dd className="font-semibold text-ink-900">{result.max_tool_calls}</dd></div>
                    <div><dt className="text-zenith-muted">Model calls</dt><dd className="font-semibold text-ink-900">{result.max_model_calls}</dd></div>
                    <div><dt className="text-zenith-muted">Time ceiling</dt><dd className="font-semibold text-ink-900">{result.max_wall_clock_seconds}s</dd></div>
                    <div><dt className="text-zenith-muted">Output token cap</dt><dd className="font-semibold text-ink-900">{result.max_output_tokens}</dd></div>
                    <div><dt className="text-zenith-muted">Dollar cost</dt><dd className="font-semibold text-ink-900">Not measured</dd></div>
                  </dl>
                  {result.execution_available && (
                    <div className="space-y-3">
                      <button type="button" onClick={() => executePlan.mutate({ query: result.query, projectId: result.source_scope === 'project' ? projectId : undefined })} disabled={executePlan.isPending || Boolean(executionRunId)} className="rounded-xl bg-ink-900 px-4 py-2.5 text-xs font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">
                        {executePlan.isPending ? 'Starting…' : executionRunId ? 'Plan started' : 'Execute plan'}
                      </button>
                      {executePlan.isError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{executePlan.error instanceof Error ? executePlan.error.message : 'Could not start plan execution.'}</p>}
                      {executionRunId && <ResearchPlanExecutionPanel runId={executionRunId} />}
                    </div>
                  )}
                </section>
              )}
              {isEvidenceResponse(result) && (
                <div className="space-y-3">
                  <p className="text-sm text-zenith-body">{result.explanation}</p>
                  {result.evidence.map((item) => {
                    const source = (sourceQuery.data ?? []).find((candidate) => candidate.paper_id === item.paper_id);
                    return (
                      <article key={`${item.paper_id}:${item.start_offset}:${item.end_offset}`} className="rounded-xl border border-zenith-border bg-white p-4">
                        <h4 className="text-sm font-semibold text-ink-900">{item.title || item.paper_id}</h4>
                        <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                        <p className="mt-2 font-mono text-[10px] text-zenith-muted">{item.paper_id} · abstract offsets {item.start_offset}–{item.end_offset}</p>
                        {canWrite && source && <button type="button" onClick={() => beginAnnotation({ source_type: 'paper_abstract', paper_source_id: source.id, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence }, `${item.title || item.paper_id} · abstract`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate evidence from ${item.title || item.paper_id}`}>Annotate quote</button>}
                        {canWrite && source && <button type="button" disabled={briefSources.length >= 50} onClick={() => addQuoteToBrief({ source_type: 'paper_abstract', paper_source_id: source.id, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence })} title={briefSources.length >= 50 ? 'A brief version supports at most 50 citations' : undefined} className="ml-2 mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary disabled:cursor-not-allowed disabled:opacity-50">Add quote to brief</button>}
                      </article>
                    );
                  })}
                  {result.pdf_evidence?.map((item) => (
                    <article key={`${item.citation_id}:${item.start_offset}`} className="rounded-xl border border-zenith-secondary/30 bg-zenith-surface/60 p-4">
                      <h4 className="text-sm font-semibold text-ink-900">{item.filename} · page {item.page_number}</h4>
                      <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
                      <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{item.citation_id}] · page offsets {item.start_offset}–{item.end_offset}</p>
                      {canWrite && <button type="button" onClick={() => beginAnnotation({ source_type: 'pdf_page', document_id: item.document_id, page_number: item.page_number, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence }, `${item.filename} · page ${item.page_number}`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate quote from ${item.filename} page ${item.page_number}`}>Annotate quote</button>}
                      {canWrite && <button type="button" disabled={briefSources.length >= 50} onClick={() => addQuoteToBrief({ source_type: 'pdf_page', document_id: item.document_id, page_number: item.page_number, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence })} title={briefSources.length >= 50 ? 'A brief version supports at most 50 citations' : undefined} className="ml-2 mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary disabled:cursor-not-allowed disabled:opacity-50">Add quote to brief</button>}
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
                          {cited.map((item) => {
                            const source = (sourceQuery.data ?? []).find((candidate) => candidate.paper_id === item.paper_id);
                            return (
                              <li key={item.evidence_id} className="border-l-2 border-zenith-secondary/60 pl-3">
                                <blockquote className="text-xs leading-5 text-zenith-body">“{item.sentence}”</blockquote>
                                <p className="mt-1 font-mono text-[10px] text-zenith-muted">{item.title || item.paper_id} · {item.paper_id} · abstract offsets {item.start_offset}–{item.end_offset}</p>
                                {canWrite && source && <button type="button" onClick={() => beginAnnotation({ source_type: 'paper_abstract', paper_source_id: source.id, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence }, `${item.title || item.paper_id} · abstract`)} className="mt-2 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate evidence from ${item.title || item.paper_id}`}>Annotate quote</button>}
                              </li>
                            );
                          })}
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
                      {canWrite && <button type="button" onClick={() => beginAnnotation({ source_type: 'pdf_page', document_id: item.document_id, page_number: item.page_number, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence }, `${item.filename} · page ${item.page_number}`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate quote from ${item.filename} page ${item.page_number}`}>Annotate quote</button>}
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
                  {(result.pdf_comparisons ?? []).length > 0 && (
                    <section aria-labelledby="comparison-pdf-fields-heading" className="space-y-3">
                      <div>
                        <h3 id="comparison-pdf-fields-heading" className="text-xs font-semibold uppercase tracking-wide text-zenith-muted">Project PDF comparison fields · separate source documents</h3>
                        <p className="mt-1 text-xs text-zenith-muted">Each field quotes an exact matching sentence. Uploaded PDFs are shown as their own sources and are not attributed to a paper.</p>
                      </div>
                      <div className="space-y-3">
                        {(result.pdf_comparisons ?? []).map((row) => {
                          const dimensions: [string, PdfComparisonEvidence | null | undefined][] = [
                            ['Research focus', row.problem],
                            ['Methods', row.methods],
                            ['Datasets', row.datasets],
                            ['Metrics', row.metrics],
                            ['Limitations', row.limitations],
                          ];
                          return (
                            <article key={row.document_id} className="rounded-xl border border-zenith-secondary/30 bg-white p-4">
                              <h4 className="text-sm font-semibold text-ink-900">{row.filename}</h4>
                              <dl className="mt-3 space-y-3">
                                {dimensions.map(([label, evidence]) => evidence && (
                                  <div key={label} className="border-t border-zenith-border pt-2">
                                    <dt className="text-[10px] font-semibold uppercase tracking-wide text-zenith-muted">{label} · page {evidence.page_number}</dt>
                                    <dd>
                                      <blockquote className="mt-1 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{evidence.sentence}”</blockquote>
                                      <p className="mt-1 font-mono text-[10px] text-zenith-muted">[{evidence.citation_id}] · page offsets {evidence.start_offset}–{evidence.end_offset}</p>
                                    </dd>
                                  </div>
                                ))}
                              </dl>
                            </article>
                          );
                        })}
                      </div>
                    </section>
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
                            {canWrite && <button type="button" onClick={() => beginAnnotation({ source_type: 'pdf_page', document_id: item.document_id, page_number: item.page_number, start_offset: item.start_offset, end_offset: item.end_offset, quote: item.sentence }, `${item.filename} · page ${item.page_number}`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate quote from ${item.filename} page ${item.page_number}`}>Annotate quote</button>}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {result.rows.length === 0 && !(result.pdf_comparisons ?? []).length && result.pdf_evidence.length === 0 && <p className="text-sm text-zenith-muted">No matching attached paper or PDF evidence was found for this comparison.</p>}
                </div>
              )}
              {isProjectSearchResponse(result) && (
                result.results.length ? (
                  <ul className="space-y-3">
                    {result.results.map((paper) => {
                      const paperSource = paper.source_type === 'paper' ? (sourceQuery.data ?? []).find((source) => source.paper_id === paper.id) : undefined;
                      const canAnchor = paper.snippet && typeof paper.start_offset === 'number' && typeof paper.end_offset === 'number';
                      return (
                      <li key={paper.id} className="rounded-xl border border-zenith-border bg-white p-4">
                        <h4 className="text-sm font-semibold text-ink-900">
                          {paper.source_type === 'pdf_page' ? `${paper.filename ?? paper.title} · page ${paper.page_number ?? '?'}` : paper.title}
                        </h4>
                        <p className="mt-1 font-mono text-[10px] text-zenith-muted">{paper.id}{typeof paper.score === 'number' ? ` · score ${paper.score.toFixed(2)}` : ''}</p>
                        {paper.snippet && <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{paper.snippet}”</blockquote>}
                        {paper.citation_id && <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{paper.citation_id}] · page offsets {paper.start_offset}–{paper.end_offset}</p>}
                        {paper.abstract && <p className="mt-2 line-clamp-4 text-sm leading-6 text-zenith-body">{paper.abstract}</p>}
                        {canWrite && canAnchor && paper.source_type === 'paper' && paperSource && <button type="button" onClick={() => beginAnnotation({ source_type: 'paper_abstract', paper_source_id: paperSource.id, start_offset: paper.start_offset!, end_offset: paper.end_offset!, quote: paper.snippet! }, `${paper.title} · abstract`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate evidence from ${paper.title}`}>Annotate quote</button>}
                        {canWrite && canAnchor && paper.source_type === 'pdf_page' && typeof paper.page_number === 'number' && <button type="button" onClick={() => beginAnnotation({ source_type: 'pdf_page', document_id: paper.id.split(':page:')[0], page_number: paper.page_number!, start_offset: paper.start_offset!, end_offset: paper.end_offset!, quote: paper.snippet! }, `${paper.filename ?? paper.title} · page ${paper.page_number}`)} className="mt-3 rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-secondary hover:border-zenith-secondary" aria-label={`Annotate quote from ${paper.filename ?? paper.title} page ${paper.page_number}`}>Annotate quote</button>}
                      </li>
                      );
                    })}
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
              <p className="mb-3 text-xs leading-5 text-zenith-muted">
                New accounts receive a secure sign-up link by email. For an existing account, share
                the pending invitation link below; acceptance is checked against the invited email.
              </p>
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
                {invitationLinkError && <p role="alert" className="text-sm text-red-700">{invitationLinkError}</p>}
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
                          {invitation.status === 'pending' && <>
                            <button type="button" onClick={() => copyInvitationLink(invitation.id)} className="text-xs font-medium text-zenith-secondary underline" aria-label={`Copy invitation link for ${invitation.email}`}>{copiedInvitationId === invitation.id ? 'Copied' : 'Copy link'}</button>
                            <Link href={`/projects/invitations/accept?invitation_id=${encodeURIComponent(invitation.id)}` as Route} target="_blank" rel="noreferrer" className="text-xs font-medium text-zenith-secondary underline" aria-label={`Open invitation link for ${invitation.email}`}>Open link</Link>
                          </>}
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
              <input ref={pdfInputRef} id="project-pdf" type="file" accept="application/pdf,.pdf" onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)} className="block w-full text-xs text-zenith-body file:mr-3 file:rounded-lg file:border file:border-zenith-border file:bg-white file:px-3 file:py-2 file:text-xs file:font-medium file:text-ink-900" />
              <p className="text-xs leading-5 text-zenith-muted">Maximum 20 MiB and 500 pages. The original PDF is not retained. Scanned pages are OCRed only when local OCR is enabled on the backend; OCR may be less accurate and is limited to five scanned pages per upload.</p>
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
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-zenith-border bg-zenith-surface px-2 py-1 text-[10px] font-medium text-zenith-muted">{extractionMethodLabel(page.extraction_method)}</span>
                      <code className="font-mono text-[10px] text-zenith-secondary">[{page.citation_id}]</code>
                    </div>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-zenith-body">{page.text || emptyPageMessage(page.extraction_method)}</p>
                </article>
              ))}
            </div>
          )}
        </section>

        <ProjectBriefsPanel
          projectId={projectId}
          canWrite={canWrite}
          sources={briefSources}
          onRemoveSource={(index) => setBriefSources((current) => current.filter((_, sourceIndex) => sourceIndex !== index))}
          onClearSources={() => setBriefSources([])}
          onSetSources={setBriefSources}
        />

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

          <div className="mt-6 border-t border-zenith-border pt-5" aria-labelledby="project-saved-searches-heading">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Repeatable queries</p>
            <h3 id="project-saved-searches-heading" className="mt-1 font-serif text-lg text-ink-900">Saved searches</h3>
            <p className="mt-1 text-xs leading-5 text-zenith-muted">Save a query with this project and run it again when you return. Each run starts a new research job.</p>

            {canWrite && <form onSubmit={(event) => { event.preventDefault(); if (savedSearchName.trim() && savedSearchQueryDraft.trim()) createSavedSearchMutation.mutate(); }} className="mt-4 space-y-2 rounded-xl border border-zenith-border bg-zenith-surface/40 p-3">
              <label htmlFor="saved-search-name" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Search name</label>
              <input id="saved-search-name" value={savedSearchName} onChange={(event) => setSavedSearchName(event.target.value)} maxLength={120} required placeholder="Weekly retrieval scan" className="w-full rounded-lg border border-zenith-border bg-white px-3 py-2 text-sm text-ink-900" />
              <label htmlFor="saved-search-query" className="block pt-1 text-xs font-semibold uppercase tracking-wide text-zenith-muted">Query</label>
              <textarea id="saved-search-query" value={savedSearchQueryDraft} onChange={(event) => setSavedSearchQueryDraft(event.target.value)} maxLength={500} rows={2} required placeholder="retrieval quality and benchmarks" className="w-full rounded-lg border border-zenith-border bg-white px-3 py-2 text-sm text-ink-900" />
              {createSavedSearchMutation.isError && <p role="alert" className="text-xs text-red-700">{createSavedSearchMutation.error instanceof Error ? createSavedSearchMutation.error.message : 'Could not save search.'}</p>}
              <button type="submit" disabled={createSavedSearchMutation.isPending || !savedSearchName.trim() || !savedSearchQueryDraft.trim()} className="rounded-lg bg-ink-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{createSavedSearchMutation.isPending ? 'Saving…' : 'Save search'}</button>
            </form>}
            {!canWrite && <p className="mt-3 text-xs text-zenith-muted">Only project owners and editors can save new searches.</p>}

            {savedSearchesQuery.isLoading && <p role="status" className="mt-4 text-sm text-zenith-muted">Loading saved searches…</p>}
            {savedSearchesQuery.isError && <p role="alert" className="mt-4 text-sm text-red-700">Could not load saved searches.</p>}
            {updateSavedSearchMutation.isError && <p role="alert" className="mt-3 text-xs text-red-700">{updateSavedSearchMutation.error instanceof Error ? updateSavedSearchMutation.error.message : 'Could not update saved search.'}</p>}
            {deleteSavedSearchMutation.isError && <p role="alert" className="mt-3 text-xs text-red-700">{deleteSavedSearchMutation.error instanceof Error ? deleteSavedSearchMutation.error.message : 'Could not delete saved search.'}</p>}
            {runSavedSearchMutation.isError && <p role="alert" className="mt-3 text-xs text-red-700">{runSavedSearchMutation.error instanceof Error ? runSavedSearchMutation.error.message : 'Could not run saved search.'}</p>}
            {activeSavedSearchRunId && <div className="mt-4">
              <p className="mb-2 text-xs text-zenith-muted">Research run: <code>{activeSavedSearchRunId}</code></p>
              <StreamingResponse key={activeSavedSearchRunId} runId={activeSavedSearchRunId} onResult={setSavedSearchRunResult} />
              {savedSearchRunResult && <div className="mt-3 rounded-lg border border-zenith-border bg-white p-3" aria-live="polite">
                <h4 className="text-sm font-semibold text-ink-900">Search results ({savedSearchRunResult.papers.length})</h4>
                <ul className="mt-2 space-y-2">{savedSearchRunResult.papers.slice(0, 10).map((paper) => <li key={paper.id}><Link href={`/paper/${encodeURIComponent(paper.id)}` as Route} className="text-sm font-medium text-zenith-secondary underline underline-offset-2">{paper.title}</Link></li>)}</ul>
              </div>}
            </div>}
            {!savedSearchesQuery.isLoading && !savedSearchesQuery.isError && (savedSearchesQuery.data ?? []).filter((search) => search.project_id === projectId).length === 0 && <p className="mt-4 text-sm text-zenith-muted">No saved searches for this project yet.</p>}
            <ul className="mt-4 space-y-3">
              {(savedSearchesQuery.data ?? []).filter((search) => search.project_id === projectId).map((search: SavedSearch) => {
                const canManage = canWrite || search.created_by === currentUserId;
                return <li key={search.id} className="rounded-xl border border-zenith-border bg-white p-3">
                  {editingSavedSearchId === search.id ? <form onSubmit={(event) => { event.preventDefault(); if (editingSavedSearchName.trim() && editingSavedSearchQuery.trim()) updateSavedSearchMutation.mutate({ id: search.id, name: editingSavedSearchName, query: editingSavedSearchQuery, model: editingSavedSearchModel }); }} className="space-y-2">
                    <label htmlFor={`saved-search-name-${search.id}`} className="sr-only">Edit saved search name</label>
                    <input id={`saved-search-name-${search.id}`} value={editingSavedSearchName} onChange={(event) => setEditingSavedSearchName(event.target.value)} maxLength={120} required className="w-full rounded-lg border border-zenith-border px-3 py-2 text-sm" />
                    <label htmlFor={`saved-search-query-${search.id}`} className="sr-only">Edit saved search query</label>
                    <textarea id={`saved-search-query-${search.id}`} value={editingSavedSearchQuery} onChange={(event) => setEditingSavedSearchQuery(event.target.value)} maxLength={500} rows={2} required className="w-full rounded-lg border border-zenith-border px-3 py-2 text-sm" />
                    <div className="flex justify-end gap-3"><button type="button" onClick={() => setEditingSavedSearchId(null)} className="text-xs text-zenith-muted underline">Cancel</button><button type="submit" disabled={updateSavedSearchMutation.isPending || !editingSavedSearchName.trim() || !editingSavedSearchQuery.trim()} className="text-xs font-semibold text-zenith-secondary underline disabled:opacity-50">Save changes</button></div>
                  </form> : <>
                    <div className="flex items-start justify-between gap-2"><p className="text-sm font-semibold text-ink-900">{search.name}</p><span className="shrink-0 rounded-full bg-zenith-surface px-2 py-1 text-[10px] text-zenith-muted">Project search</span></div>
                    <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-zenith-body">{search.query}</p>
                    {search.model && <p className="mt-1 font-mono text-[10px] text-zenith-muted">Model: {search.model}</p>}
                    <div className="mt-3 flex flex-wrap justify-end gap-3">
                      <button type="button" onClick={() => runSavedSearchMutation.mutate(search.id)} disabled={runSavedSearchMutation.isPending} className="text-xs font-semibold text-zenith-secondary underline disabled:opacity-50">{runSavedSearchMutation.isPending ? 'Starting…' : 'Run search'}</button>
                      {canManage && <><button type="button" onClick={() => { setEditingSavedSearchId(search.id); setEditingSavedSearchName(search.name); setEditingSavedSearchQuery(search.query); setEditingSavedSearchModel(search.model); updateSavedSearchMutation.reset(); }} className="text-xs text-zenith-muted underline">Edit</button><button type="button" onClick={() => deleteSavedSearchMutation.mutate(search.id)} disabled={deleteSavedSearchMutation.isPending} className="text-xs text-red-700 underline disabled:opacity-50">Delete</button></>}
                    </div>
                  </>}
                </li>;
              })}
            </ul>
          </div>

          <div className="mt-6 border-t border-zenith-border pt-5" aria-labelledby="project-annotations-heading">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Source-linked</p>
            <h3 id="project-annotations-heading" className="mt-1 font-serif text-lg text-ink-900">Annotations</h3>
            <p className="mt-1 text-xs leading-5 text-zenith-muted">Annotations keep the exact quote and character offsets from an attached paper abstract or extracted PDF page.</p>

            {annotationAnchor && canWrite && (
              <form id="annotation-composer" onSubmit={handleAnnotationSubmit} className="mt-4 space-y-3 rounded-xl border border-zenith-secondary/40 bg-zenith-surface/60 p-4" aria-label="Add source annotation">
                <div>
                  <p className="text-xs font-semibold text-ink-900">{annotationAnchor.label}</p>
                  <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{annotationAnchor.quote}”</blockquote>
                  <p className="mt-2 font-mono text-[10px] text-zenith-muted">Offsets {annotationAnchor.start_offset}–{annotationAnchor.end_offset}</p>
                </div>
                <label htmlFor="annotation-content" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Your annotation</label>
                <textarea id="annotation-content" value={annotationDraft} onChange={(event) => setAnnotationDraft(event.target.value)} maxLength={5000} rows={3} placeholder="Add a comment about this evidence…" required className="w-full rounded-xl border border-zenith-border bg-white px-3 py-2.5 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20" />
                {createAnnotation.isError && <p role="alert" className="text-sm text-red-700">{createAnnotation.error instanceof Error ? createAnnotation.error.message : 'Could not add annotation.'}</p>}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => { setAnnotationAnchor(null); setAnnotationDraft(''); createAnnotation.reset(); }} className="rounded-lg border border-zenith-border px-3 py-2 text-xs font-medium text-zenith-body hover:border-ink-900">Cancel</button>
                  <button type="submit" disabled={createAnnotation.isPending || !annotationDraft.trim()} className="rounded-lg bg-ink-900 px-3 py-2 text-xs font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">{createAnnotation.isPending ? 'Saving…' : 'Save annotation'}</button>
                </div>
              </form>
            )}

            {annotationsQuery.isLoading && <p role="status" className="mt-4 text-sm text-zenith-muted">Loading annotations…</p>}
            {annotationsQuery.isError && <p role="alert" className="mt-4 text-sm text-red-700">Could not load annotations.</p>}
            {!annotationsQuery.isLoading && !annotationsQuery.isError && (annotationsQuery.data ?? []).length === 0 && <p className="mt-4 text-sm text-zenith-muted">No source annotations yet. Annotate an evidence quote from your research results.</p>}
            <ul className="mt-4 space-y-3">
              {(annotationsQuery.data ?? []).map((annotation) => (
                <li key={annotation.id} className="rounded-xl border border-zenith-border bg-white p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-ink-900">{annotation.source_label ?? annotation.document_id ?? annotation.paper_source_id ?? 'Source'}{annotation.source_type === 'pdf_page' && annotation.page_number ? ` · page ${annotation.page_number}` : ' · abstract'}</p>
                    {annotation.is_stale && <span role="status" className="rounded-full border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-900">Source changed · quote may be stale</span>}
                  </div>
                  <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{annotation.quote}”</blockquote>
                  <p className="mt-1 font-mono text-[10px] text-zenith-muted">{annotation.source_type === 'pdf_page' ? `[${annotation.document_id}:page:${annotation.page_number}] · page` : 'Abstract'} offsets {annotation.start_offset}–{annotation.end_offset}</p>

                  {editingAnnotationId === annotation.id ? (
                    <form onSubmit={(event) => handleAnnotationEdit(event, annotation.id)} className="mt-3 space-y-2">
                      <label htmlFor={`annotation-edit-${annotation.id}`} className="sr-only">Edit annotation</label>
                      <textarea id={`annotation-edit-${annotation.id}`} value={editingAnnotationDraft} onChange={(event) => setEditingAnnotationDraft(event.target.value)} maxLength={5000} rows={3} required className="w-full rounded-lg border border-zenith-border bg-white px-3 py-2 text-sm text-ink-900 focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20" />
                      {updateAnnotation.isError && <p role="alert" className="text-xs text-red-700">{updateAnnotation.error instanceof Error ? updateAnnotation.error.message : 'Could not update annotation.'}</p>}
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => { setEditingAnnotationId(null); setEditingAnnotationDraft(''); }} className="rounded-lg border border-zenith-border px-3 py-1.5 text-xs font-medium text-zenith-body">Cancel</button>
                        <button type="submit" disabled={updateAnnotation.isPending || !editingAnnotationDraft.trim()} className="rounded-lg bg-ink-900 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{updateAnnotation.isPending ? 'Saving…' : 'Save changes'}</button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-800">{annotation.content}</p>
                      <time className="mt-2 block font-mono text-[10px] text-zenith-muted" dateTime={annotation.created_at}>{new Date(annotation.created_at).toLocaleString()}</time>
                      {canWrite && <div className="mt-3 flex justify-end gap-3">
                        <button type="button" onClick={() => beginAnnotationEdit(annotation)} className="text-xs font-medium text-zenith-secondary underline underline-offset-2" aria-label={`Edit annotation for ${annotation.source_label ?? annotation.document_id ?? annotation.paper_source_id ?? 'Source'}`}>Edit</button>
                        <button type="button" onClick={() => removeAnnotation.mutate(annotation.id)} disabled={removeAnnotation.isPending} className="text-xs font-medium text-red-700 underline underline-offset-2 disabled:opacity-50" aria-label={`Delete annotation for ${annotation.source_label ?? annotation.document_id ?? annotation.paper_source_id ?? 'Source'}`}>Delete</button>
                      </div>}
                    </>
                  )}
                </li>
              ))}
            </ul>
            {removeAnnotation.isError && <p role="alert" className="mt-3 text-sm text-red-700">{removeAnnotation.error instanceof Error ? removeAnnotation.error.message : 'Could not delete annotation.'}</p>}
          </div>
        </section>
        </div>
      </div>
    </main>
  );
}
