'use client';

import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { fetchPaper, fetchPaperCode } from '@/lib/api';
import Link from 'next/link';

export default function PaperDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data: paper, isLoading } = useQuery({
    queryKey: ['paper', id],
    queryFn: () => fetchPaper(id),
    enabled: !!id,
  });

  const { data: codeData } = useQuery({
    queryKey: ['paperCode', id],
    queryFn: () => fetchPaperCode(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="py-12 text-center text-gray-500">Loading paper...</div>
      </main>
    );
  }

  if (!paper) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="py-12 text-center text-gray-500">Paper not found.</div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/feed" className="mb-4 inline-block text-sm text-primary-600 hover:underline">
        Back to feed
      </Link>

      <article className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="mb-3 text-2xl font-bold text-gray-900">{paper.title}</h1>
        <p className="mb-4 text-sm text-gray-600">{paper.authors.join(', ')}</p>

        {paper.summaryTldr && (
          <div className="mb-6 rounded-lg bg-primary-50 p-4">
            <h2 className="mb-1 text-sm font-semibold text-primary-800">TL;DR</h2>
            <p className="text-sm text-primary-900">{paper.summaryTldr}</p>
          </div>
        )}

        {paper.summaryContributions && paper.summaryContributions.length > 0 && (
          <div className="mb-6">
            <h2 className="mb-2 text-lg font-semibold text-gray-900">Key Contributions</h2>
            <ul className="list-inside list-disc space-y-1 text-gray-700">
              {paper.summaryContributions.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mb-6">
          <h2 className="mb-2 text-lg font-semibold text-gray-900">Abstract</h2>
          <p className="leading-relaxed text-gray-700">{paper.abstract}</p>
        </div>

        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>Published: {new Date(paper.publishedAt).toLocaleDateString()}</span>
          {paper.difficulty && (
            <span className="rounded bg-gray-100 px-2 py-0.5 capitalize">{paper.difficulty}</span>
          )}
        </div>

        {codeData && codeData.repos && codeData.repos.length > 0 && (
          <div className="mb-6">
            <h2 className="mb-2 text-lg font-semibold text-gray-900">Code & Repositories</h2>
            <ul className="space-y-2">
              {codeData.repos.map((repo, i) => (
                <li key={i}>
                  <a
                    href={repo.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:underline"
                  >
                    {repo.url} {repo.stars > 0 && <span className="text-gray-500">({repo.stars} stars)</span>}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {paper.url && (
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 inline-block rounded-lg bg-primary-600 px-5 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            View PDF
          </a>
        )}
      </article>
    </main>
  );
}
