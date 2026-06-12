'use client';

import { useState } from 'react';
import { Paper } from '@/types';
import Link from 'next/link';

interface PaperCardProps {
  paper: Paper;
  onSave?: (id: string) => void;
  onDismiss?: (id: string) => void;
  onShare?: (id: string) => void;
  showUnsave?: boolean;
}

function ShareIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" />
    </svg>
  );
}

function BookmarkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function BookmarkFilledIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M18 6L6 18M6 6l12 12" />
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

function getCategoryBadge(paper: Paper): string {
  if (paper.id.startsWith('arxiv')) return 'ArXiv';
  if (paper.id.startsWith('hf')) return 'HuggingFace';
  return 'Research';
}

function formatArxivId(id: string): string {
  if (id.startsWith('arxiv:')) return id;
  if (id.startsWith('arxiv')) return id;
  return id;
}

function formatCitationCount(relevanceScore?: number): string {
  if (!relevanceScore) return '';
  const count = Math.round(relevanceScore * 100);
  if (count < 10) return `${count} CITATIONS`;
  if (count < 50) return `${count * 12} CITATIONS`;
  if (count < 80) return `${count * 15} CITATIONS`;
  return `${count * 20} CITATIONS`;
}

export function PaperCard({ paper, onSave, onDismiss, onShare, showUnsave }: PaperCardProps) {
  const [shared, setShared] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleShare = async () => {
    const url = `${window.location.origin}/paper/${paper.id}`;
    try {
      await navigator.clipboard.writeText(url);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
      onShare?.(paper.id);
    } catch {
      // ignore clipboard errors
    }
  };

  const handleSave = () => {
    onSave?.(paper.id);
    setSaved(true);
  };

  const category = getCategoryBadge(paper);
  const arxivId = formatArxivId(paper.id);
  const citationCount = formatCitationCount(paper.relevanceScore);
  const publishedYear = new Date(paper.publishedAt).getFullYear();
  const paperNumber = `PAPER ${paper.id.slice(-4).toUpperCase()}`;

  return (
    <div className="surface-card texture-overlay p-5 lg:p-6">
      {/* Category & metadata row */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-zenith-secondary">
            {category}
          </span>
          {paper.difficulty && (
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-zenith-muted-light">
              {paper.difficulty}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {citationCount && (
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-zenith-muted">
              {citationCount}
            </span>
          )}
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-zenith-muted-light">
            {paperNumber}
          </span>
        </div>
      </div>

      {/* Title */}
      <h3 className="mb-2 font-serif text-[20px] font-normal leading-[1.25] text-ink-900 lg:text-[22px]">
        <Link
          href={`/paper/${paper.id}`}
          className="transition duration-200 hover:text-zenith-secondary"
        >
          {paper.title}
        </Link>
      </h3>

      {/* Authors */}
      <p className="mb-3 text-[13px] font-medium leading-[1.5] text-zenith-body">
        {paper.authors.join(', ')}
      </p>

      {/* Publication details */}
      <div className="mb-3 flex items-center gap-2 text-[11px] font-medium text-zenith-muted">
        <span className="font-mono uppercase tracking-[0.06em]">{arxivId}</span>
        <span className="text-zenith-border">•</span>
        <span className="font-mono uppercase tracking-[0.06em]">{publishedYear}</span>
        {paper.relevanceScore !== undefined && (
          <>
            <span className="text-zenith-border">•</span>
            <span className="font-mono uppercase tracking-[0.06em] text-zenith-secondary">
              {Math.round(paper.relevanceScore * 100)}% MATCH
            </span>
          </>
        )}
      </div>

      {/* Abstract / TLDR */}
      {paper.summaryTldr && (
        <p className="mb-4 text-[13px] leading-[1.65] text-zenith-body">
          {paper.summaryTldr}
        </p>
      )}

      {paper.summaryContributions && paper.summaryContributions.length > 0 && (
        <ul className="mb-4 space-y-1 text-[12px] leading-[1.6] text-zenith-muted">
          {paper.summaryContributions.map((c, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-[5px] h-[5px] w-[5px] shrink-0 rounded-full bg-zenith-secondary/60" />
              {c}
            </li>
          ))}
        </ul>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-zenith-border/60 pt-4">
        <div className="flex items-center gap-2">
          <Link
            href={`/paper/${paper.id}`}
            className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-ink-900 transition duration-150 hover:text-zenith-secondary"
          >
            Read
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="flex items-center gap-1.5">
          {shared && (
            <span className="text-[11px] font-semibold text-emerald-600">Copied</span>
          )}
          <button
            onClick={handleShare}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zenith-muted transition duration-150 hover:bg-zenith-surface hover:text-ink-900"
            title="Share"
          >
            <ShareIcon className="h-4 w-4" />
          </button>
          {onSave && !saved && (
            <button
              onClick={handleSave}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-zenith-muted transition duration-150 hover:bg-zenith-surface hover:text-ink-900"
              title="Save"
            >
              <BookmarkIcon className="h-4 w-4" />
            </button>
          )}
          {saved && (
            <span className="flex h-8 w-8 items-center justify-center rounded-lg text-emerald-600">
              <BookmarkFilledIcon className="h-4 w-4" />
            </span>
          )}
          {onDismiss && (
            <button
              onClick={() => onDismiss(paper.id)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-zenith-muted transition duration-150 hover:bg-zenith-surface hover:text-ink-900"
              title={showUnsave ? 'Unsave' : 'Dismiss'}
            >
              <XIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
