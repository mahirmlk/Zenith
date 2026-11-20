import { PaperSummaryFallbackReason, PaperSummaryStatus } from '@/types';

const STATUS_LABELS: Record<PaperSummaryStatus, string> = {
  generated: 'AI-generated summary',
  abstract_preview: 'Abstract preview',
  unknown: 'Summary source unknown',
};

const FALLBACK_REASON_COPY: Record<PaperSummaryFallbackReason, string> = {
  per_run_cap: 'The per-run summary limit was reached.',
  spend_limit: 'The spend limit prevented a generated summary.',
  billing_unavailable: 'Billing controls were unavailable.',
  provider_unavailable: 'The model provider was unavailable.',
  invalid_output: 'The generated output could not be validated.',
};

interface SummaryProvenanceProps {
  status?: PaperSummaryStatus;
  fallbackReason?: PaperSummaryFallbackReason | null;
}

export function SummaryProvenance({ status = 'unknown', fallbackReason }: SummaryProvenanceProps) {
  const reason = fallbackReason ? FALLBACK_REASON_COPY[fallbackReason] : null;

  return (
    <div className="mb-2">
      <p className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-zenith-muted">
        {STATUS_LABELS[status]}
      </p>
      {reason && <p className="mt-1 text-[12px] leading-[1.5] text-zenith-muted">{reason}</p>}
    </div>
  );
}
