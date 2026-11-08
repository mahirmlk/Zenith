'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { fetchImplementationPlan } from '@/lib/api';
import type { ImplementationPlan, PlanFactCategory } from '@/types';

const FACT_LABELS: Record<PlanFactCategory, string> = {
  architecture: 'Architecture and method',
  dependency: 'Dependencies',
  dataset: 'Datasets',
  metric: 'Metrics',
  training: 'Training',
  evaluation: 'Evaluation',
  compute: 'Compute',
};

function safeGitHubUrl(value: string): string | null {
  try {
    const url = new URL(value);
    const pathParts = url.pathname.split('/').filter(Boolean);
    if (
      url.protocol !== 'https:'
      || url.hostname !== 'github.com'
      || url.username
      || url.password
      || url.search
      || url.hash
      || pathParts.length !== 2
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function ItemList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby={`section-${title.toLowerCase().replaceAll(' ', '-')}`}>
      <h2
        id={`section-${title.toLowerCase().replaceAll(' ', '-')}`}
        className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted"
      >
        {title}
      </h2>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={`${index}-${item}`} className="flex items-start gap-3 text-[13px] leading-[1.65] text-zenith-body">
            <span aria-hidden="true" className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-zenith-secondary/70" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EvidenceCard({ fact }: { fact: ImplementationPlan['facts'][number] }) {
  const { evidence } = fact;
  return (
    <article className="rounded-xl border border-zenith-border/80 bg-white p-4">
      <p className="mb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.13em] text-zenith-secondary">
        {FACT_LABELS[fact.category]}
      </p>
      <blockquote className="text-[13px] leading-[1.7] text-ink-800">“{evidence.quote}”</blockquote>
      <p className="mt-3 font-mono text-[10px] text-zenith-muted">
        Source {evidence.paper_id || 'identifier unavailable'} · abstract characters {evidence.start}–{evidence.end}
      </p>
    </article>
  );
}

function PlanContent({ plan }: { plan: ImplementationPlan }) {
  return (
    <>
      <div className="mb-7 rounded-xl border border-amber-300/70 bg-amber-50/70 p-4" role="status">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.13em] text-amber-900">
          Plan generated · not run
        </p>
        <p className="mt-1.5 text-[13px] leading-[1.6] text-amber-950/80">
          This brief extracts statements from the abstract and lists verification gaps. No repository was cloned, no code was executed, and no result was reproduced.
        </p>
      </div>

      <section className="mb-8" aria-labelledby="architecture-heading">
        <h2 id="architecture-heading" className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
          Architecture and method
        </h2>
        <p className="text-[14px] leading-[1.7] text-ink-800">{plan.architecture}</p>
        {plan.facts.length > 0 && (
          <p className="mt-2 font-mono text-[10px] text-zenith-muted">
            Extracted facts below include exact abstract spans and offsets.
          </p>
        )}
      </section>

      <section className="mb-8" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
          Evidence from the abstract
        </h2>
        {plan.facts.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {plan.facts.map((fact, index) => (
              <EvidenceCard key={`${fact.category}-${fact.evidence.start}-${index}`} fact={fact} />
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-zenith-border p-4 text-[13px] leading-[1.6] text-zenith-muted">
            No reproducibility facts were safely extractable from the abstract.
          </p>
        )}
      </section>

      <div className="mb-8 grid gap-7 md:grid-cols-2">
        <ItemList title="Dependencies" items={plan.dependencies} />
        <ItemList title="Datasets" items={plan.datasets} />
        <ItemList title="Metrics" items={plan.metrics} />
        <ItemList title="Training steps" items={plan.training_steps} />
        <ItemList title="Evaluation" items={plan.evaluation_steps} />
        <ItemList title="Compute requirements" items={plan.compute_requirements} />
      </div>

      <section className="mb-8" aria-labelledby="repositories-heading">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="repositories-heading" className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
            Candidate repositories
          </h2>
          <span className="rounded-full border border-zenith-border px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-zenith-muted">
            Association unverified
          </span>
        </div>
        {plan.candidate_repos.length > 0 ? (
          <ul className="space-y-2">
            {plan.candidate_repos.map((repo, index) => {
              const href = safeGitHubUrl(repo.url);
              return (
                <li key={`${repo.url}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zenith-border/80 bg-white px-4 py-3">
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="break-all text-[13px] font-semibold text-zenith-secondary underline decoration-zenith-secondary/30 underline-offset-4 hover:text-zenith-accent">
                      {repo.url}
                      <span className="sr-only"> (opens in a new tab; paper association not verified)</span>
                    </a>
                  ) : (
                    <span className="break-all text-[13px] text-zenith-muted">Untrusted repository URL omitted</span>
                  )}
                  <span className="font-mono text-[10px] text-zenith-muted">
                    {repo.stars.toLocaleString()} stars · {repo.verification_status}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-[13px] leading-[1.6] text-zenith-muted">
            {plan.repository_lookup_status === 'unavailable'
              ? 'Repository lookup was unavailable. This does not mean no implementation exists.'
              : 'No candidate repository was found. This does not mean no implementation exists.'}
          </p>
        )}
      </section>

      <div className="mb-8 grid gap-7 md:grid-cols-2">
        <ItemList title="Suggested project structure" items={plan.suggested_structure} />
        <ItemList title="Compatibility notes" items={plan.compatibility_notes} />
      </div>

      <section className="mb-8 rounded-xl border border-zenith-border/80 bg-zenith-surface/60 p-5" aria-labelledby="card-heading">
        <h2 id="card-heading" className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
          Model and data card · {plan.model_data_card.status}
        </h2>
        <dl className="grid gap-3 text-[12px] sm:grid-cols-2">
          <div>
            <dt className="font-semibold text-ink-800">Model or method</dt>
            <dd className="mt-1 text-zenith-muted">{plan.model_data_card.model_or_method ?? 'Not identified'}</dd>
          </div>
          <div>
            <dt className="font-semibold text-ink-800">Dataset license</dt>
            <dd className="mt-1 text-zenith-muted">{plan.model_data_card.dataset_license ?? 'Not verified'}</dd>
          </div>
          <div>
            <dt className="font-semibold text-ink-800">Intended use</dt>
            <dd className="mt-1 text-zenith-muted">{plan.model_data_card.intended_use ?? 'Not assessed'}</dd>
          </div>
          <div>
            <dt className="font-semibold text-ink-800">Limitations</dt>
            <dd className="mt-1 text-zenith-muted">
              {plan.model_data_card.limitations.length > 0 ? plan.model_data_card.limitations.join(' ') : 'Not identified from the available abstract.'}
            </dd>
          </div>
        </dl>
      </section>

      <section className="mb-8" aria-labelledby="checklist-heading">
        <h2 id="checklist-heading" className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
          Implementation checklist
        </h2>
        <ul className="space-y-2">
          {plan.checklist.map((item, index) => (
            <li key={`${index}-${item}`} className="flex items-start gap-3 text-[13px] leading-[1.6] text-zenith-body">
              <span aria-hidden="true" className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-zenith-border bg-white text-[10px] text-zenith-muted"> </span>
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="gaps-heading">
        <h2 id="gaps-heading" className="mb-3 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zenith-muted">
          Reproducibility gaps
        </h2>
        {plan.reproducibility_gaps.length > 0 ? (
          <ul className="space-y-2">
            {plan.reproducibility_gaps.map((gap, index) => (
              <li key={`${index}-${gap}`} className="rounded-lg border border-zenith-border/70 bg-white px-4 py-3 text-[12px] leading-[1.6] text-zenith-body">{gap}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-zenith-muted">No gaps were listed by the planner; verify details against the full paper before implementation.</p>
        )}
      </section>
    </>
  );
}

export default function ImplementationPlanPage() {
  const params = useParams<{ id: string }>();
  const paperId = params.id;
  const { data: plan, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['implementationPlan', paperId],
    queryFn: () => fetchImplementationPlan(paperId),
    enabled: Boolean(paperId),
    staleTime: 60_000,
    retry: 1,
  });

  return (
    <main className="relative mx-auto max-w-4xl px-4 py-8 pt-28">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
      <div className="relative z-10">
        <Link href={`/paper/${encodeURIComponent(paperId)}`} className="mb-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-zenith-muted transition hover:text-ink-900">
          <span aria-hidden="true">←</span> Back to paper
        </Link>

        <header className="mb-7">
          <p className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-zenith-secondary">Paper-to-code · planning only</p>
          <h1 className="font-serif text-[28px] font-normal leading-tight text-ink-900 sm:text-[34px]">Reproducibility brief</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-[1.65] text-zenith-muted">
            Extracted facts stay tied to exact abstract spans. Missing details remain unknown until checked against the full paper and its sources.
          </p>
        </header>

        {isPending ? (
          <section className="surface-card p-6" aria-busy="true" aria-label="Loading reproducibility plan">
            <div className="mb-4 h-5 w-2/3 animate-pulse rounded bg-zenith-border" />
            <div className="mb-3 h-4 w-full animate-pulse rounded bg-zenith-border" />
            <div className="h-4 w-4/5 animate-pulse rounded bg-zenith-border" />
          </section>
        ) : isError ? (
          <section className="surface-card p-6" role="alert" aria-live="assertive">
            <h2 className="font-semibold text-ink-900">Could not load this plan</h2>
            <p className="mt-2 text-[13px] leading-[1.6] text-zenith-muted">
              {error instanceof Error ? error.message : 'The request failed. Check your connection and try again.'}
            </p>
            <button
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="mt-4 rounded-lg bg-ink-900 px-4 py-2 text-[12px] font-semibold text-white transition hover:bg-ink-800 disabled:opacity-60"
            >
              {isFetching ? 'Retrying…' : 'Try again'}
            </button>
          </section>
        ) : plan ? (
          <>
            <div className="surface-card mb-5 p-5 sm:p-7">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-zenith-surface px-3 py-1 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-zenith-secondary">{plan.status}</span>
                <span className="font-mono text-[10px] text-zenith-muted">Source: {plan.paper_id}</span>
              </div>
              <h2 className="mb-6 font-serif text-[21px] leading-[1.35] text-ink-900 sm:text-[24px]">{plan.title || 'Untitled paper'}</h2>
              <PlanContent plan={plan} />
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
