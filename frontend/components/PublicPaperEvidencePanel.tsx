'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, fetchPublicPaperEvidence } from '@/lib/api';

function safeHttpsUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.toString() : null;
  } catch {
    return null;
  }
}

interface PublicPaperEvidencePanelProps {
  paperId: string;
  enabled: boolean;
  supported: boolean;
}

export function PublicPaperEvidencePanel({ paperId, enabled, supported }: PublicPaperEvidencePanelProps) {
  const [draftQuery, setDraftQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const evidenceQuery = useQuery({
    queryKey: ['public-paper-evidence', paperId, submittedQuery],
    queryFn: ({ signal }) => fetchPublicPaperEvidence(paperId, submittedQuery, signal),
    enabled: enabled && supported && Boolean(submittedQuery),
    retry: false,
  });

  if (!enabled) return null;

  if (!supported) {
    return (
      <section className="mb-6 rounded-xl border border-zenith-border bg-zenith-surface/60 p-4" aria-labelledby="public-evidence-unavailable-heading">
        <h2 id="public-evidence-unavailable-heading" className="text-sm font-semibold text-ink-900">Page evidence unavailable</h2>
        <p className="mt-1 text-xs leading-5 text-zenith-muted">A verified arXiv preprint identifier and version are required to search page evidence for this paper. This record does not provide both.</p>
      </section>
    );
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = draftQuery.trim();
    if (query.length >= 2) setSubmittedQuery(query);
  };

  const evidence = evidenceQuery.data;
  const sourceUrl = safeHttpsUrl(evidence?.source_url);
  const licenseUrl = safeHttpsUrl(evidence?.license_url);
  const errorStatus = evidenceQuery.error instanceof ApiError ? evidenceQuery.error.status : null;
  const permanentDenial = errorStatus === 451;
  const staleSource = errorStatus === 409;
  const unsupportedSource = errorStatus === 422;

  return (
    <section className="mb-6 rounded-xl border border-zenith-border bg-white p-5" aria-labelledby="public-evidence-heading">
      <div className="mb-4">
        <p className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">Source evidence</p>
        <h2 id="public-evidence-heading" className="mt-1 font-serif text-xl text-ink-900">Find passages in this preprint</h2>
        <p className="mt-2 text-xs leading-5 text-zenith-muted">Search for relevant page excerpts from the versioned public preprint. Excerpts provide source context and are not a scientific correctness assessment.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row" role="search" aria-label="Search public paper evidence">
        <label htmlFor="public-evidence-query" className="sr-only">What evidence are you looking for?</label>
        <input
          id="public-evidence-query"
          type="search"
          value={draftQuery}
          onChange={(event) => setDraftQuery(event.target.value)}
          minLength={2}
          maxLength={256}
          required
          aria-describedby="public-evidence-query-help"
          placeholder="e.g. What dataset did the authors evaluate?"
          className="min-h-10 flex-1 rounded-lg border border-zenith-border px-3 py-2 text-sm text-ink-900 placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-2 focus:ring-zenith-secondary/20"
        />
        <button type="submit" disabled={draftQuery.trim().length < 2 || evidenceQuery.isFetching} className="min-h-10 rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50">
          {evidenceQuery.isFetching ? 'Searching…' : 'Find evidence'}
        </button>
      </form>
      <p id="public-evidence-query-help" className="mt-2 text-xs text-zenith-muted">
        {draftQuery.trim().length === 1 ? 'Enter at least 2 characters to search.' : 'Search queries need at least 2 characters.'}
      </p>

      {evidenceQuery.isFetching && <p role="status" className="mt-4 text-sm text-zenith-muted">Searching page text…</p>}

      {evidenceQuery.isError && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3" role="alert">
          {permanentDenial ? (
            <p className="text-sm text-red-800">This source’s license does not permit reuse of its text here. No excerpts are available.</p>
          ) : staleSource ? (
            <p className="text-sm text-red-800">The saved arXiv metadata is out of date or unsupported. Evidence is unavailable until the paper metadata is refreshed.</p>
          ) : unsupportedSource ? (
            <p className="text-sm text-red-800">This paper’s source is not supported for page evidence. Search is available only for supported arXiv preprints.</p>
          ) : (
            <>
              <p className="text-sm text-red-800">We could not load public paper evidence. Try again.</p>
              <button type="button" onClick={() => void evidenceQuery.refetch()} disabled={evidenceQuery.isFetching} className="mt-2 text-sm font-semibold text-red-900 underline disabled:opacity-50">Retry</button>
            </>
          )}
        </div>
      )}

      {evidence && (
        <div className="mt-5">
          <div className="border-b border-zenith-border pb-3">
            <h3 className="text-sm font-semibold text-ink-900">{evidence.title}</h3>
            <p className="mt-1 text-xs text-zenith-muted">Preprint {evidence.preprint_id}, version {evidence.version}</p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="font-medium text-zenith-secondary underline">View source</a>}
              {evidence.license_name && (
                licenseUrl
                  ? <a href={licenseUrl} target="_blank" rel="noopener noreferrer" className="font-medium text-zenith-secondary underline">{evidence.license_name} license</a>
                  : <span className="text-zenith-muted">{evidence.license_name} license</span>
              )}
            </div>
            {evidence.attribution && <p className="mt-2 text-xs leading-5 text-zenith-muted">{evidence.attribution}</p>}
          </div>

          {evidence.evidence.length === 0 ? (
            <p className="mt-4 text-sm text-zenith-muted" role="status">No matching page excerpts were found. Try a different query.</p>
          ) : (
            <ol className="mt-4 space-y-3" aria-label="Matching page excerpts">
              {evidence.evidence.map((item, index) => (
                <li key={`${item.citation_id}-${index}`} className="rounded-lg border border-zenith-border bg-zenith-surface/50 p-3">
                  <p className="font-mono text-[11px] font-medium text-zenith-secondary">Page {item.page_number} · {item.citation_id}</p>
                  <blockquote className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink-800">{item.sentence}</blockquote>
                  <p className="mt-2 font-mono text-[10px] text-zenith-muted">Text offsets {item.start_offset}–{item.end_offset}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
