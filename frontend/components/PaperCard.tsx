'use client';

import { useState } from 'react';
import { Paper } from '@/types';
import Link from 'next/link';

interface PaperCardProps {
  paper: Paper;
  onSave?: (id: string) => void;
  onDismiss?: (id: string) => void;
  onShare?: (id: string) => void;
}

export function PaperCard({ paper, onSave, onDismiss, onShare }: PaperCardProps) {
  const [shared, setShared] = useState(false);

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

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <div className="mb-2 flex items-start justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          <Link href={`/paper/${paper.id}`} className="hover:text-primary-600">
            {paper.title}
          </Link>
        </h3>
        {paper.relevanceScore !== undefined && (
          <span className="ml-3 inline-flex items-center rounded-full bg-primary-100 px-2.5 py-0.5 text-xs font-medium text-primary-700">
            {Math.round(paper.relevanceScore * 100)}% match
          </span>
        )}
      </div>

      <p className="mb-3 text-sm text-gray-600">
        {paper.authors.join(', ')}
      </p>

      {paper.summaryTldr && (
        <p className="mb-3 text-sm leading-relaxed text-gray-700">
          {paper.summaryTldr}
        </p>
      )}

      {paper.summaryContributions && paper.summaryContributions.length > 0 && (
        <ul className="mb-3 list-inside list-disc space-y-0.5 text-xs text-gray-600">
          {paper.summaryContributions.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>{new Date(paper.publishedAt).toLocaleDateString()}</span>
          {paper.difficulty && (
            <span className="rounded bg-gray-100 px-2 py-0.5 capitalize">{paper.difficulty}</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {shared && (
            <span className="text-xs text-green-600">Link copied!</span>
          )}
          <button
            onClick={handleShare}
            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Share
          </button>
          {onSave && (
            <button
              onClick={() => onSave(paper.id)}
              className="rounded-md bg-primary-50 px-3 py-1.5 text-sm font-medium text-primary-700 hover:bg-primary-100"
            >
              Save
            </button>
          )}
          {onDismiss && (
            <button
              onClick={() => onDismiss(paper.id)}
              className="rounded-md bg-gray-50 px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100"
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
