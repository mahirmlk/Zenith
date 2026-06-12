'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchSavedPapers, unsavePaper } from '@/lib/api';

import { PaperCard } from '@/components/PaperCard';
import { SkeletonCard } from '@/components/SkeletonCard';
import Link from 'next/link';

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

export default function SavedPage() {
  const queryClient = useQueryClient();

  const { data: papers, isLoading, error } = useQuery({
    queryKey: ['savedPapers'],
    queryFn: fetchSavedPapers,
  });

  const unsaveMutation = useMutation({
    mutationFn: unsavePaper,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedPapers'] });
    },
  });

  const handleUnsave = (id: string) => {
    unsaveMutation.mutate(id);
  };

  if (isLoading) {
    return (
      <main className="relative mx-auto max-w-4xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <div className="relative mb-8">
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">
            Reading List
          </p>
          <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">
            Saved Papers
          </h1>
        </div>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="relative mx-auto max-w-4xl px-4 py-8 pt-28">
        <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />
        <div className="relative mb-8">
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">
            Reading List
          </p>
          <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">
            Saved Papers
          </h1>
        </div>
        <div className="rounded-xl border border-red-200 bg-red-50/80 p-4 text-[13px] font-medium text-red-700">
          Failed to load saved papers. Please try again.
        </div>
      </main>
    );
  }

  const savedPapers = papers ?? [];

  return (
    <main className="relative mx-auto max-w-4xl px-4 py-8 pt-28">
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />

      <div className="relative z-10">
        <div className="mb-8">
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">
            Reading List
          </p>
          <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">
            Saved Papers
          </h1>
        </div>

        {savedPapers.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-zenith-border bg-white py-16 text-center shadow-soft">
            <p className="font-serif text-[18px] font-normal text-zenith-muted">
              No saved papers yet.
            </p>
            <p className="mt-1 text-[13px] text-zenith-muted-light">
              Start exploring to build your reading list.
            </p>
            <Link
              href="/feed"
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-ink-900 px-5 py-2.5 text-[13px] font-semibold text-white shadow-button transition duration-200 hover:bg-ink-800"
            >
              Explore Papers
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {savedPapers.map((paper) => (
              <PaperCard
                key={paper.id}
                paper={paper}
                onDismiss={handleUnsave}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
