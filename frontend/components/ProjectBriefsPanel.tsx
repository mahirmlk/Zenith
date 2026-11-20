'use client';

import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  appendProjectBriefVersion,
  createProjectBrief,
  fetchProjectBriefVersions,
  fetchProjectBriefs,
  ProjectBriefApiError,
} from '@/lib/project-briefs-api';
import type {
  ProjectBrief,
  ProjectBriefSourceLocator,
  ProjectBriefSourceSnapshot,
  ProjectBriefVersion,
} from '@/types';

interface ProjectBriefsPanelProps {
  projectId: string;
  canWrite: boolean;
  sources: ProjectBriefSourceLocator[];
  onRemoveSource: (index: number) => void;
  onClearSources: () => void;
  onSetSources: (sources: ProjectBriefSourceLocator[]) => void;
}

function toLocator(source: ProjectBriefSourceSnapshot): ProjectBriefSourceLocator | null {
  if (source.source_type === 'paper_abstract' && source.source_id) {
    return {
      source_type: 'paper_abstract',
      paper_source_id: source.source_id,
      start_offset: source.start_offset,
      end_offset: source.end_offset,
      quote: source.quote,
    };
  }
  if (source.source_type === 'pdf_page' && source.document_id && source.page_number) {
    return {
      source_type: 'pdf_page',
      document_id: source.document_id,
      page_number: source.page_number,
      start_offset: source.start_offset,
      end_offset: source.end_offset,
      quote: source.quote,
    };
  }
  return null;
}

function versionSources(version: ProjectBriefVersion): ProjectBriefSourceLocator[] {
  return (version.source_snapshot ?? []).map(toLocator).filter(
    (source): source is ProjectBriefSourceLocator => source !== null,
  );
}

function labelForSource(source: ProjectBriefSourceLocator): string {
  return source.source_type === 'pdf_page'
    ? `PDF page ${source.page_number}`
    : `Paper abstract ${source.paper_source_id}`;
}

export default function ProjectBriefsPanel({
  projectId,
  canWrite,
  sources,
  onRemoveSource,
  onClearSources,
  onSetSources,
}: ProjectBriefsPanelProps) {
  const queryClient = useQueryClient();
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [appendToBriefId, setAppendToBriefId] = useState<string | null>(null);

  const briefsQuery = useQuery({
    queryKey: ['project-briefs', projectId],
    queryFn: () => fetchProjectBriefs(projectId),
    enabled: !!projectId,
  });

  const versionsQuery = useQuery({
    queryKey: ['project-brief-versions', projectId, selectedBriefId],
    queryFn: () => fetchProjectBriefVersions(projectId, selectedBriefId!),
    enabled: !!projectId && !!selectedBriefId,
  });

  const createMutation = useMutation({
    mutationFn: () => createProjectBrief(projectId, {
      title: title.trim(),
      content: content.trim(),
      source_snapshot: sources,
    }),
    onSuccess: async (result) => {
      setDrafting(false);
      setTitle('');
      setContent('');
      onClearSources();
      setSelectedBriefId(result.brief.id);
      await queryClient.invalidateQueries({ queryKey: ['project-briefs', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['project-brief-versions', projectId] });
    },
  });

  const appendMutation = useMutation({
    mutationFn: (brief: ProjectBrief) => appendProjectBriefVersion(projectId, brief.id, {
      expected_current_version: brief.current_version,
      content: content.trim(),
      source_snapshot: sources,
    }),
    onSuccess: async () => {
      setDrafting(false);
      setAppendToBriefId(null);
      setContent('');
      onClearSources();
      await queryClient.invalidateQueries({ queryKey: ['project-briefs', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['project-brief-versions', projectId] });
    },
    onError: async (error) => {
      if (error instanceof ProjectBriefApiError && error.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ['project-briefs', projectId] });
        await queryClient.invalidateQueries({ queryKey: ['project-brief-versions', projectId] });
      }
    },
  });

  const briefs = briefsQuery.data ?? [];
  const selectedBrief = briefs.find((brief) => brief.id === selectedBriefId) ?? null;
  const versions = [...(versionsQuery.data ?? [])].sort((a, b) => b.version - a.version);
  const latestVersion = versions[0] ?? null;

  function beginNewBrief() {
    setSelectedBriefId(null);
    setAppendToBriefId(null);
    setTitle('');
    setContent('');
    setDrafting(true);
    createMutation.reset();
    appendMutation.reset();
  }

  function beginAppendVersion(brief: ProjectBrief, current: ProjectBriefVersion | null) {
    setAppendToBriefId(brief.id);
    setTitle(brief.title);
    setContent(current?.content ?? '');
    onSetSources(versionSources(current ?? ({} as ProjectBriefVersion)));
    setDrafting(true);
    createMutation.reset();
    appendMutation.reset();
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim()) return;
    if (appendToBriefId) {
      const brief = briefs.find((item) => item.id === appendToBriefId);
      if (brief) appendMutation.mutate(brief);
    } else if (title.trim()) {
      createMutation.mutate();
    }
  }

  const mutationError = createMutation.error ?? appendMutation.error;

  return (
    <section className="surface-card p-5 sm:p-6" aria-labelledby="project-briefs-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-zenith-secondary">Project synthesis</p>
          <h2 id="project-briefs-heading" className="mt-1 font-serif text-xl text-ink-900">Versioned briefs</h2>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-zenith-muted">Briefs are user-authored snapshots. Each revision keeps its cited source quotes and history; prior versions cannot be edited.</p>
        </div>
        {canWrite && <button type="button" onClick={beginNewBrief} className="rounded-lg bg-ink-900 px-3 py-2 text-xs font-semibold text-white hover:bg-ink-800">New brief</button>}
      </div>

      {briefsQuery.isError && <p role="alert" className="mt-4 text-sm text-red-700">Could not load project briefs.</p>}
      {briefsQuery.isLoading && <p role="status" className="mt-4 text-sm text-zenith-muted">Loading briefs…</p>}
      {!briefsQuery.isLoading && !briefsQuery.isError && briefs.length === 0 && <p className="mt-4 text-sm text-zenith-muted">No project briefs yet.</p>}

      {briefs.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2" aria-label="Project briefs">
          {briefs.map((brief) => (
            <li key={brief.id}>
              <button
                type="button"
                aria-pressed={selectedBriefId === brief.id}
                onClick={() => { setSelectedBriefId(brief.id); setDrafting(false); setAppendToBriefId(null); }}
                className={`rounded-lg border px-3 py-2 text-left text-xs ${selectedBriefId === brief.id ? 'border-ink-900 bg-ink-900 text-white' : 'border-zenith-border bg-white text-ink-900'}`}
              >
                {brief.title} <span className="opacity-70">· v{brief.current_version}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selectedBriefId && (
        <div className="mt-5 border-t border-zenith-border pt-4">
          {versionsQuery.isLoading && <p role="status" className="text-sm text-zenith-muted">Loading brief history…</p>}
          {versionsQuery.isError && <p role="alert" className="text-sm text-red-700">Could not load brief history.</p>}
          {selectedBrief && canWrite && latestVersion && !drafting && (
            <button type="button" onClick={() => beginAppendVersion(selectedBrief, latestVersion)} className="mb-4 rounded-lg border border-ink-900 px-3 py-2 text-xs font-semibold text-ink-900 hover:bg-ink-900 hover:text-white">Create next version</button>
          )}
          <ol className="space-y-4" aria-label="Immutable brief versions">
            {versions.map((version) => (
              <li key={version.id} className="rounded-xl border border-zenith-border bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-ink-900">Version {version.version}</h3>
                  <time className="font-mono text-[10px] text-zenith-muted" dateTime={version.created_at}>{new Date(version.created_at).toLocaleString()}</time>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zenith-body">{version.content}</p>
                <p className="mt-3 font-mono text-[10px] text-zenith-muted">Authored by {version.created_by} · {version.origin.replace('_', ' ')} · SHA-256 {version.content_sha256.slice(0, 12)}…</p>
                <div className="mt-3 space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-zenith-muted">Source snapshot ({version.source_snapshot.length})</h4>
                  {version.source_snapshot.length === 0 && <p className="text-xs text-zenith-muted">No citations were attached to this version.</p>}
                  {version.source_snapshot.map((source, index) => (
                    <figure key={`${source.source_id}:${source.start_offset}:${index}`} className="rounded-lg border border-zenith-border bg-zenith-surface/40 p-3">
                      <figcaption className="text-xs font-medium text-ink-900">{source.source_label}{source.source_type === 'pdf_page' && source.page_number ? ` · page ${source.page_number}` : ' · abstract'}</figcaption>
                      <blockquote className="mt-2 border-l-2 border-zenith-secondary pl-3 text-xs leading-5 text-zenith-body">“{source.quote}”</blockquote>
                      <p className="mt-2 font-mono text-[10px] text-zenith-muted">{source.start_offset}–{source.end_offset} · quote {source.quote_sha256.slice(0, 12)}… · source snapshot {source.source_sha256.slice(0, 12)}…</p>
                    </figure>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {drafting && canWrite && (
        <form onSubmit={handleSave} className="mt-5 space-y-3 border-t border-zenith-border pt-4" aria-label={appendToBriefId ? 'Create brief version' : 'Create project brief'}>
          {!appendToBriefId && <>
            <label htmlFor="project-brief-title" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Brief title</label>
            <input id="project-brief-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} required className="w-full rounded-lg border border-zenith-border bg-white px-3 py-2 text-sm text-ink-900" placeholder="Research direction and findings" />
          </>}
          <label htmlFor="project-brief-content" className="block text-xs font-semibold uppercase tracking-wide text-zenith-muted">Brief content</label>
          <textarea id="project-brief-content" value={content} onChange={(event) => setContent(event.target.value)} maxLength={50000} rows={8} required className="w-full rounded-lg border border-zenith-border bg-white px-3 py-2.5 text-sm leading-6 text-ink-900" placeholder="Summarize the current question, evidence, and next steps…" />
          <div className="rounded-lg border border-zenith-border bg-zenith-surface/40 p-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zenith-muted">Citations for this version · up to 50</h3>
              {sources.length > 0 && <button type="button" onClick={onClearSources} className="text-xs text-zenith-secondary underline">Clear all</button>}
            </div>
            {sources.length === 0 && <p className="mt-2 text-xs text-zenith-muted">Add exact quotes from the project evidence below while this editor is open.</p>}
            <ul className="mt-2 space-y-2">
              {sources.map((source, index) => (
                <li key={`${source.source_type}:${source.source_type === 'pdf_page' ? source.document_id : source.paper_source_id}:${source.start_offset}:${index}`} className="flex items-start justify-between gap-3 rounded-md bg-white p-2">
                  <div className="min-w-0">
                    <p className="text-[10px] font-medium text-ink-900">{labelForSource(source)}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-zenith-muted">“{source.quote}”</p>
                  </div>
                  <button type="button" onClick={() => onRemoveSource(index)} aria-label={`Remove ${labelForSource(source)} citation`} className="shrink-0 text-xs text-red-700 underline">Remove</button>
                </li>
              ))}
            </ul>
          </div>
          {mutationError && <p role="alert" className="text-sm text-red-700">{mutationError instanceof ProjectBriefApiError && mutationError.status === 409 ? 'Another collaborator saved a newer version. The latest history has been refreshed; review it before trying again.' : mutationError instanceof Error ? mutationError.message : 'Could not save the brief.'}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={createMutation.isPending || appendMutation.isPending || !content.trim() || (!appendToBriefId && !title.trim())} className="rounded-lg bg-ink-900 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
              {createMutation.isPending || appendMutation.isPending ? 'Saving…' : appendToBriefId ? 'Save new version' : 'Create brief'}
            </button>
            <button type="button" onClick={() => { setDrafting(false); setAppendToBriefId(null); }} className="rounded-lg border border-zenith-border px-3 py-2 text-xs font-semibold text-ink-900">Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
