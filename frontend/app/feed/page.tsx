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
      setAllPapers((prev) => (offset === 0 ? feedPapers : [...prev, ...feedPapers]));
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
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Paper Feed</h1>
        <ModelSelector />
      </div>

      <form onSubmit={handleSearch} className="mb-6 flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search papers, e.g. diffusion models..."
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
        />
        <button
          type="submit"
          disabled={isSearchLoading}
          className="rounded-lg bg-primary-600 px-6 py-2 font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {isSearchLoading ? 'Searching...' : 'Search'}
        </button>
      </form>

      {displayError && (
        <div className="mb-6 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {displayError}
        </div>
      )}

      {runId && (
        <div className="mb-6">
          <StreamingResponse runId={runId} onResult={handleResult} />
        </div>
      )}

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
              <div className="py-12 text-center text-gray-500">No papers found.</div>
            )}
          </div>

          {!searchResults.length && hasMore && (
            <div className="mt-6 text-center">
              <button
                onClick={handleLoadMore}
                disabled={feedLoading}
                className="rounded-lg border border-gray-300 bg-white px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                {feedLoading ? 'Loading...' : 'Load More'}
              </button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
