'use client';

import { useEffect, useState } from 'react';
import { cancelRun, streamSearch } from '@/lib/api';
import type { AgentStep, PaperSearchResult, ResearchPlanExecutionResult, ResearchRunCancelledEvent } from '@/types';

interface ResearchPlanExecutionPanelProps {
  runId: string;
}

export default function ResearchPlanExecutionPanel({ runId }: ResearchPlanExecutionPanelProps) {
  const [events, setEvents] = useState<AgentStep[]>([]);
  const [result, setResult] = useState<ResearchPlanExecutionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelPending, setCancelPending] = useState(false);
  const [runStatus, setRunStatus] = useState<'running' | 'complete' | 'failed' | 'cancelled'>('running');

  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;

    setEvents([]);
    setResult(null);
    setError(null);
    setRunStatus('running');

    void streamSearch(runId, (event) => {
      if (!active) return;
      if (isExecutionResult(event)) {
        setResult(event);
        setRunStatus('complete');
      } else if (isRunCancelled(event)) {
        setRunStatus('cancelled');
      } else if (isAgentStep(event)) {
        setEvents((current) => [...current, event]);
      }
    }, (streamError) => {
      if (active) {
        setError(streamError.message);
        setRunStatus('failed');
      }
    }).then((stop) => {
      if (active) unsubscribe = stop;
      else stop();
    }).catch((streamError: unknown) => {
      if (active) {
        setError(streamError instanceof Error ? streamError.message : 'Could not connect to research progress.');
        setRunStatus('failed');
      }
    });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [runId]);

  async function handleCancel() {
    setCancelPending(true);
    try {
      const response = await cancelRun(runId);
      if (response.status === 'complete' || response.status === 'failed' || response.status === 'cancelled') {
        setRunStatus(response.status);
      } else {
        setRunStatus('cancelled');
      }
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : 'Could not cancel this run.');
    } finally {
      setCancelPending(false);
    }
  }

  const finished = runStatus !== 'running';

  return (
    <section className="space-y-4 rounded-xl border border-zenith-secondary/30 bg-white p-4" aria-labelledby="plan-execution-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 id="plan-execution-heading" className="font-semibold text-ink-900">Plan execution</h4>
          <p className="mt-1 font-mono text-[10px] text-zenith-muted">Run {runId}</p>
        </div>
        {!finished && (
          <button type="button" onClick={handleCancel} disabled={cancelPending} className="rounded-lg border border-red-300 px-3 py-2 text-xs font-semibold text-red-800 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60" aria-label="Cancel research plan execution">
            {cancelPending ? 'Cancelling…' : 'Cancel run'}
          </button>
        )}
      </div>

      {!finished && <p role="status" aria-live="polite" className="text-sm text-zenith-body">Research is running. Progress updates will appear here.</p>}
      {runStatus === 'cancelled' && <p role="status" className="rounded-lg bg-zenith-surface p-3 text-sm text-zenith-body">Run cancelled.</p>}
      {runStatus === 'complete' && !result && <p role="status" className="rounded-lg bg-zenith-surface p-3 text-sm text-zenith-body">Run completed.</p>}
      {runStatus === 'failed' && !error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Run failed.</p>}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}

      {events.length > 0 && (
        <ol className="space-y-2" aria-label="Research execution progress" aria-live="polite">
          {events.map((event, index) => (
            <li key={`${event.agent}:${event.status}:${index}`} className="rounded-lg border border-zenith-border bg-zenith-surface/50 px-3 py-2 text-sm">
              <span className="font-semibold text-ink-900">{event.agent.replaceAll('_', ' ')}</span>
              <span className="text-zenith-body"> · {event.message || event.status.replaceAll('_', ' ')}</span>
              {event.count !== undefined && <span className="ml-2 font-mono text-xs text-zenith-muted">{event.count}</span>}
            </li>
          ))}
        </ol>
      )}

      {result && <ExecutionResult result={result} />}
    </section>
  );
}

function ExecutionResult({ result }: { result: ResearchPlanExecutionResult }) {
  const evidenceById = new Map(result.evidence.map((item) => [item.citation_id, item]));
  return (
    <div className="space-y-4 border-t border-zenith-border pt-4">
      <div role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-950">
        Plan completed · {result.task_type.replaceAll('_', ' ')} · {result.source_scope === 'project' ? 'project sources' : 'public corpus'}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-ink-900">Completed steps</h5>
        <ul className="mt-2 space-y-1 text-sm text-zenith-body">
          {result.steps.map((step) => <li key={step.step_id}>{step.step_id.replaceAll('_', ' ')}: {step.status}{step.count === undefined ? '' : ` · ${step.count} found`}</li>)}
        </ul>
      </div>

      <div>
        <h5 className="text-sm font-semibold text-ink-900">Sources ({result.sources.length})</h5>
        {result.sources.length ? <ul className="mt-2 list-inside list-disc text-sm text-zenith-body">{result.sources.map((source) => <li key={source.paper_id}>{source.title} <span className="font-mono text-xs text-zenith-muted">{source.paper_id}</span></li>)}</ul> : <p className="mt-1 text-sm text-zenith-muted">No sources found.</p>}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-ink-900">Evidence ({result.evidence.length})</h5>
        {result.evidence.length ? <ul className="mt-2 space-y-3">{result.evidence.map((item) => (
          <li key={`${item.citation_id}:${item.start_offset}`} className="rounded-lg border border-zenith-border bg-zenith-surface/50 p-3">
            <blockquote className="border-l-2 border-zenith-secondary pl-3 text-sm leading-6 text-zenith-body">“{item.sentence}”</blockquote>
            <p className="mt-2 font-mono text-[10px] text-zenith-muted">[{item.citation_id}]{item.title ? ` · ${item.title}` : ''}{item.paper_id ? ` · ${item.paper_id}` : ''}{item.document_id ? ` · document ${item.document_id}` : ''}{item.page_number ? ` · page ${item.page_number}` : ''} · offsets {item.start_offset}–{item.end_offset}</p>
          </li>
        ))}</ul> : <p className="mt-1 text-sm text-zenith-muted">No evidence was returned.</p>}
      </div>

      {result.comparison && <div>
        <h5 className="text-sm font-semibold text-ink-900">Comparison</h5>
        <div className="mt-2 overflow-x-auto"><table className="min-w-full border-collapse text-left text-xs"><thead><tr>{['Paper', 'Problem', 'Methods', 'Datasets', 'Metrics', 'Limitations', 'Code'].map((heading) => <th key={heading} className="border-b border-zenith-border p-2 font-semibold text-zenith-muted">{heading}</th>)}</tr></thead><tbody>{result.comparison.map((row) => <tr key={row.paper_id}>{[row.paper_id, row.problem, row.methods, row.datasets, row.metrics, row.limitations, row.code_status].map((cell, index) => <td key={index} className="border-b border-zenith-border p-2 align-top text-zenith-body">{cell || '—'}</td>)}</tr>)}</tbody></table></div>
      </div>}

      {result.synthesis && result.synthesis.length > 0 && <section aria-labelledby="provisional-synthesis-heading" className="rounded-lg border border-amber-300 bg-amber-50 p-3">
        <h5 id="provisional-synthesis-heading" className="font-semibold text-amber-950">Provisional synthesis · model reviewed</h5>
        <p className="mt-1 text-xs leading-5 text-amber-900">These claims are provisional and should be checked against the cited source evidence.</p>
        <ul className="mt-3 space-y-3">{result.synthesis.map((claim, index) => (
          <li key={`${claim.text}:${index}`} className="border-t border-amber-300/70 pt-2">
            <p className="text-sm font-medium text-ink-900">{claim.text}</p>
            <p className="mt-1 font-mono text-[10px] uppercase text-amber-900">{claim.status}</p>
            {claim.explanation && <p className="mt-1 text-xs text-amber-900">{claim.explanation}</p>}
            <ul className="mt-2 space-y-2">{claim.cited_evidence_ids.map((citationId) => {
              const evidence = evidenceById.get(citationId);
              return <li key={citationId} className="text-xs text-amber-950">[{citationId}] {evidence ? `“${evidence.sentence}”` : 'Citation is included in the evidence list above.'}</li>;
            })}</ul>
          </li>
        ))}</ul>
      </section>}

      {result.gaps.length > 0 && <div>
        <h5 className="text-sm font-semibold text-ink-900">Research gaps</h5>
        <ul className="mt-2 list-inside list-disc text-sm text-zenith-body">{result.gaps.map((gap, index) => <li key={`${index}:${gap}`}>{gap}</li>)}</ul>
      </div>}

      <p className="text-xs text-zenith-muted">Cost tracking is unavailable; estimated cost was not measured.</p>
    </div>
  );
}

function isExecutionResult(event: AgentStep | ResearchPlanExecutionResult | ResearchRunCancelledEvent | PaperSearchResult | object): event is ResearchPlanExecutionResult {
  return 'kind' in event && event.kind === 'research_plan_execution';
}

function isRunCancelled(event: AgentStep | ResearchPlanExecutionResult | ResearchRunCancelledEvent | PaperSearchResult | object): event is ResearchRunCancelledEvent {
  return 'status' in event && event.status === 'cancelled' && 'run_id' in event;
}

function isAgentStep(event: AgentStep | ResearchPlanExecutionResult | ResearchRunCancelledEvent | PaperSearchResult | object): event is AgentStep {
  return 'agent' in event && 'status' in event;
}
