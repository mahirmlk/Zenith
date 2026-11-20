'use client';

import { useParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, fetchPaper, fetchPaperCode, fetchPaperStatusWatch, fetchResearchCapabilities, setPaperStatusWatch } from '@/lib/api';
import Link from 'next/link';
import type { Route } from 'next';
import type { Paper } from '@/types';
import { SummaryProvenance } from '@/components/SummaryProvenance';
import { PublicPaperEvidencePanel } from '@/components/PublicPaperEvidencePanel';

function supportsVersionedArxivEvidence(paper: Paper): boolean {
  const preprintId = paper.preprintId;
  const isKnownArxivId = typeof preprintId === 'string'
    && (/^\d{4}\.\d{4,5}$/.test(preprintId) || /^[A-Za-z][A-Za-z0-9.-]*\/\d{7}$/.test(preprintId));
  return isKnownArxivId && Number.isSafeInteger(paper.sourceVersion) && (paper.sourceVersion ?? 0) > 0;
}

function ArrowLeft({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  );
}

function ArrowUpRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M4 12L12 4M12 4H6M12 4V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ExternalLink({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  );
}

export default function PaperDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const queryClient = useQueryClient();

  const { data: paper, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['paper', id],
    queryFn: () => fetchPaper(id),
    enabled: !!id,
  });

  const { data: codeData } = useQuery({
    queryKey: ['paperCode', id],
    queryFn: () => fetchPaperCode(id),
    enabled: !!id,
  });

  const capabilitiesQuery = useQuery({
    queryKey: ['research-capabilities'],
    queryFn: fetchResearchCapabilities,
    staleTime: 5 * 60 * 1000,
  });

  const statusWatchQuery = useQuery({
    queryKey: ['paper-status-watch', id],
    queryFn: () => fetchPaperStatusWatch(id),
    enabled: !!id && !!paper?.doi,
  });

  const statusWatchMutation = useMutation({
    mutationFn: (watching: boolean) => setPaperStatusWatch(id, watching),
    onSuccess: (watching) => queryClient.setQueryData(['paper-status-watch', id], watching),
  });

  if (isLoading) {
    return (
      <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <div className="relative py-12 text-center">
          <div className="mx-auto mb-3 h-6 w-32 animate-pulse rounded bg-zenith-border" />
          <div className="mx-auto h-4 w-48 animate-pulse rounded bg-zenith-border" />
        </div>
      </main>
    );
  }

  if (isError && error instanceof ApiError && error.status === 404) {
    return (
      <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <div className="relative py-12 text-center">
          <p className="font-serif text-[18px] font-normal text-zenith-muted">Paper not found.</p>
          <Link href="/feed" className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-zenith-secondary transition duration-150 hover:text-zenith-accent">
            <ArrowLeft className="h-4 w-4" />
            Back to feed
          </Link>
        </div>
      </main>
    );
  }

  if (isError) {
    const isUnauthorized = error instanceof ApiError && error.status === 401;
    const isForbidden = error instanceof ApiError && error.status === 403;
    const message = isUnauthorized
      ? 'Your session may have expired. Sign in to view this paper.'
      : isForbidden
        ? 'You do not have access to this paper.'
        : 'We could not load this paper. Check your connection and try again.';

    return (
      <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <section className="relative mx-auto max-w-xl py-12 text-center" aria-labelledby="paper-load-error-heading">
          <h1 id="paper-load-error-heading" className="font-serif text-[22px] font-normal text-ink-900">Paper unavailable</h1>
          <p role="alert" className="mt-3 text-sm leading-6 text-zenith-muted">{message}</p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="rounded-xl bg-ink-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink-800 disabled:opacity-50"
            >
              {isFetching ? 'Retrying…' : 'Try again'}
            </button>
            {isUnauthorized && <Link href="/login" className="rounded-xl border border-zenith-border px-4 py-2.5 text-sm font-semibold text-ink-900 hover:bg-white">Sign in</Link>}
            <Link href="/feed" className="rounded-xl border border-zenith-border px-4 py-2.5 text-sm font-semibold text-ink-900 hover:bg-white">Back to feed</Link>
          </div>
        </section>
      </main>
    );
  }

  if (!paper) {
    return (
      <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <div className="relative py-12 text-center">
          <p className="font-serif text-[18px] font-normal text-zenith-muted">Paper not found.</p>
          <Link href="/feed" className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-zenith-secondary transition duration-150 hover:text-zenith-accent">
            <ArrowLeft className="h-4 w-4" />
            Back to feed
          </Link>
        </div>
      </main>
    );
  }

  const publishedYear = new Date(paper.publishedAt).getFullYear();
  const paperNumber = `PAPER ${paper.id.slice(-4).toUpperCase()}`;

  return (
    <main className="relative mx-auto max-w-3xl px-4 py-8 pt-28">
      {/* Subtle background texture */}
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />

      <div className="relative z-10">
        <Link href="/feed" className="mb-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-zenith-muted transition duration-150 hover:text-ink-900">
          <ArrowLeft className="h-4 w-4" />
          Back to feed
        </Link>

        <article className="surface-card p-6 lg:p-8">
          {/* Header metadata */}
          <div className="mb-4 flex items-center gap-3">
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-zenith-secondary">
              {paper.id.startsWith('arxiv') ? 'ArXiv' : paper.id.startsWith('hf') ? 'HuggingFace' : 'Research'}
            </span>
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-zenith-muted-light">
              {paperNumber}
            </span>
          </div>

          {/* Title */}
          <h1 className="mb-3 font-serif text-[26px] font-normal leading-[1.2] text-ink-900 lg:text-[30px]">
            {paper.title}
          </h1>

          {/* Authors */}
          <p className="mb-4 text-[14px] font-medium leading-[1.5] text-zenith-body">
            {paper.authors.join(', ')}
          </p>

          {/* Publication details */}
          <div className="mb-6 flex items-center gap-2 text-[12px] font-medium text-zenith-muted">
            <span className="font-mono uppercase tracking-[0.06em]">{paper.id}</span>
            <span className="text-zenith-border">•</span>
            <span className="font-mono uppercase tracking-[0.06em]">{publishedYear}</span>
            {paper.difficulty && (
              <>
                <span className="text-zenith-border">•</span>
                <span className="font-mono uppercase tracking-[0.06em]">{paper.difficulty}</span>
              </>
            )}
          </div>

          {paper.publicationUpdateType && paper.publicationUpdateDoi && (
            <section role="status" aria-label="Publication status update" className="mb-6 rounded-xl border border-amber-300 bg-amber-50 p-4">
              <h2 className="text-sm font-semibold text-amber-950">
                Crossref update: {paper.publicationUpdateLabel ?? paper.publicationUpdateType.replaceAll('_', ' ')}
              </h2>
              <p className="mt-1 text-sm leading-6 text-amber-900">
                Crossref metadata links this work to an update{paper.publicationUpdateDate ? ` dated ${paper.publicationUpdateDate}` : ''}.
                Crossref records reflect deposited metadata and may not be complete.
              </p>
              {paper.publicationUpdateDepositSource && (
                <p className="mt-1 text-xs leading-5 text-amber-900">
                  Notice deposit source reported by Crossref: {paper.publicationUpdateDepositSource === 'publisher' ? 'Publisher' : 'Retraction Watch'}.
                </p>
              )}
              <a
                href={`https://doi.org/${paper.publicationUpdateDoi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex text-sm font-semibold text-amber-950 underline"
              >
                View update notice ({paper.publicationUpdateDoi})
              </a>
            </section>
          )}

          {paper.doi && (
            <section aria-label="Publication update monitoring" className="mb-6 rounded-xl border border-zenith-border bg-zenith-surface/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-zenith-muted">Publication updates</p>
                  <p className="mt-1 text-xs leading-5 text-zenith-muted">
                    Opt in to Crossref notices for this DOI. Missing Crossref metadata does not mean a paper has no updates.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => statusWatchMutation.mutate(!statusWatchQuery.data)}
                  disabled={statusWatchQuery.isLoading || statusWatchMutation.isPending}
                  className="rounded-xl border border-zenith-border bg-white px-3 py-2 text-xs font-semibold text-ink-900 hover:bg-zenith-surface disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {statusWatchMutation.isPending
                    ? 'Saving…'
                    : statusWatchQuery.data ? 'Stop monitoring' : 'Get update alerts'}
                </button>
              </div>
              {statusWatchQuery.isError && <p role="alert" className="mt-2 text-xs text-red-700">Could not load your monitoring preference.</p>}
              {statusWatchMutation.isError && <p role="alert" className="mt-2 text-xs text-red-700">Could not update your monitoring preference. Try again.</p>}
              <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex text-xs font-medium text-zenith-secondary underline">DOI: {paper.doi}</a>
            </section>
          )}

          {/* TL;DR */}
          {(paper.summaryTldr || paper.summaryFallbackReason || paper.summaryStatus !== undefined) && (
            <div className="mb-6 rounded-xl border border-zenith-border/80 bg-zenith-surface/60 p-5">
              <SummaryProvenance status={paper.summaryStatus} fallbackReason={paper.summaryFallbackReason} />
              {paper.summaryTldr && <p className="text-[14px] font-medium leading-[1.6] text-ink-800">{paper.summaryTldr}</p>}
            </div>
          )}

          {/* Key Contributions */}
          {paper.summaryContributions && paper.summaryContributions.length > 0 && (
            <div className="mb-6">
              <p className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
                Key Contributions
              </p>
              <ul className="space-y-2 text-[14px] leading-[1.6] text-zenith-body">
                {paper.summaryContributions.map((c, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-full bg-zenith-secondary/60" />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Abstract */}
          <div className="mb-6">
            <p className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
              Abstract
            </p>
            <p className="text-[14px] leading-[1.7] text-zenith-body">
              {paper.abstract}
            </p>
          </div>

          <PublicPaperEvidencePanel
            paperId={id}
            enabled={capabilitiesQuery.data?.public_paper_evidence_enabled === true}
            supported={supportsVersionedArxivEvidence(paper)}
          />

          {/* Code & Repositories */}
          {codeData && codeData.repos && codeData.repos.length > 0 && (
            <div className="mb-6">
              <p className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
                Code & Repositories
              </p>
              <ul className="space-y-2">
                {codeData.repos.map((repo, i) => (
                  <li key={i}>
                    <a
                      href={repo.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-zenith-secondary transition duration-150 hover:text-zenith-accent"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      {repo.url}
                      {repo.stars > 0 && (
                        <span className="font-mono text-[11px] font-medium text-zenith-muted">({repo.stars} stars)</span>
                      )}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3 border-t border-zenith-border/60 pt-6">
              <Link
                href={`/paper/${encodeURIComponent(id)}/implement` as Route}
                className="inline-flex items-center gap-2 rounded-lg border border-zenith-border bg-white px-5 py-2.5 text-[13px] font-semibold text-ink-900 transition duration-200 hover:border-zenith-secondary/50 hover:bg-zenith-surface"
              >
                Reproducibility plan
              </Link>
              {paper.url && (
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-ink-900 px-5 py-2.5 text-[13px] font-semibold text-white shadow-button transition duration-200 hover:bg-ink-800"
              >
                View PDF
                <ArrowUpRight className="h-3.5 w-3.5" />
              </a>
              )}
          </div>
        </article>
      </div>
    </main>
  );
}
