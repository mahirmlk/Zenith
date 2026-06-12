'use client';

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchFeed, searchPapers, savePaper } from '@/lib/api';
import { Paper, PaperSearchResult } from '@/types';
import { PaperCard } from '@/components/PaperCard';
import { StreamingResponse } from '@/components/StreamingResponse';
import { ModelSelector } from '@/components/ModelSelector';
import { SkeletonCard } from '@/components/SkeletonCard';
import { useAppStore } from '@/store/useAppStore';

const PAGE_SIZE = 10;

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

export default function FeedPage() {
  const [query, setQuery] = useState('');
  const [runId, setRunId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<Paper[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [allPapers, setAllPapers] = useState<Paper[]>([]);
  const { isSearchLoading, setIsSearchLoading, selectedModel } = useAppStore();

  const { data: feedPapers, isLoading: feedLoading, error: feedError } = useQuery({
    queryKey: ['feed', offset],
    queryFn: () => fetchFeed({ limit: PAGE_SIZE, offset }),
  });

  useEffect(() => {
    if (feedPapers) {
      setAllPapers((prev) => {
        if (offset === 0) return feedPapers;
        const existingIds = new Set(prev.map((p) => p.id));
        const newPapers = feedPapers.filter((p) => !existingIds.has(p.id));
        return [...prev, ...newPapers];
      });
    }
  }, [feedPapers, offset]);

  useEffect(() => {
    if (!query.trim()) {
      setSearchResults([]);
      setRunId(null);
      setSearchError(null);
    }
  }, [query]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setIsSearchLoading(true);
    setSearchResults([]);
    setSearchError(null);
    setRunId(null);
    try {
      const { runId: rid } = await searchPapers(query, selectedModel);
      setRunId(rid);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Search failed. Please try again.';
      setSearchError(message);
    } finally {
      setIsSearchLoading(false);
    }
  };

  const handleResult = (result: PaperSearchResult) => {
    setSearchResults(result.papers);
  };

  const handleSave = async (id: string) => {
    try {
      await savePaper(id);
    } catch (err) {
      console.error(err);
    }
  };

  const handleLoadMore = () => {
    setOffset((prev) => prev + PAGE_SIZE);
  };

  const displayError = searchError ?? (feedError instanceof Error ? feedError.message : null);
  const papers = searchResults.length > 0 ? searchResults : allPapers;
  const hasMore = feedPapers ? feedPapers.length === PAGE_SIZE : false;

  return (
    <main className="relative mx-auto max-w-4xl px-4 py-8 pt-28">
      {/* Subtle background texture */}
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" style={{ opacity: 0.02 }} />

      <div className="relative z-10">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-zenith-muted">
              Research Feed
            </p>
            <h1 className="font-serif text-[32px] font-normal leading-[1.1] text-ink-900 lg:text-[36px]">
              Paper Feed
            </h1>
          </div>
          <ModelSelector />
        </div>

        {/* Search form */}
        <form onSubmit={handleSearch} className="mb-8 flex gap-2">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-zenith-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search papers, e.g. diffusion models..."
              className="w-full rounded-xl border border-zenith-border bg-white py-3 pl-11 pr-4 text-[14px] text-ink-900 shadow-soft placeholder:text-zenith-muted-light focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
            />
          </div>
          <button
            type="submit"
            disabled={isSearchLoading}
            className="rounded-xl bg-ink-900 px-6 py-3 text-[13px] font-semibold text-white shadow-button transition duration-200 hover:bg-ink-800 disabled:opacity-50"
          >
            {isSearchLoading ? 'Searching...' : 'Search'}
          </button>
        </form>

        {/* Error */}
        {displayError && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50/80 p-4 text-[13px] font-medium text-red-700">
            {displayError}
          </div>
        )}

        {/* Streaming response */}
        {runId && (
          <div className="mb-6">
            <StreamingResponse runId={runId} onResult={handleResult} />
          </div>
        )}

        {/* Results count */}
        {searchResults.length > 0 && (
          <div className="mb-4 flex items-center gap-2">
            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-zenith-muted">
              {searchResults.length} Results
            </span>
            <button
              onClick={() => {
                setQuery('');
                setSearchResults([]);
                setRunId(null);
              }}
              className="text-[12px] font-medium text-zenith-secondary transition duration-150 hover:text-zenith-accent"
            >
              Clear
            </button>
          </div>
        )}

        {/* Paper list */}
        {feedLoading && allPapers.length === 0 ? (
          <div className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : (
          <>
            <div className="space-y-4">
              {papers.map((paper) => (
                <PaperCard key={paper.id} paper={paper} onSave={handleSave} />
              ))}
              {papers.length === 0 && (
                <div className="py-12 text-center">
                  <p className="font-serif text-[18px] font-normal text-zenith-muted">No papers found.</p>
                  <p className="mt-1 text-[13px] text-zenith-muted-light">Try a different search or explore the feed.</p>
                </div>
              )}
            </div>

            {/* Load more */}
            {!searchResults.length && hasMore && (
              <div className="mt-8 text-center">
                <button
                  onClick={handleLoadMore}
                  disabled={feedLoading}
                  className="inline-flex items-center gap-2 rounded-xl border border-zenith-border bg-white px-6 py-2.5 text-[13px] font-semibold text-ink-900 shadow-soft transition duration-200 hover:bg-zenith-surface hover:shadow-soft-lg disabled:opacity-50"
                >
                  {feedLoading ? 'Loading...' : 'Load More'}
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
