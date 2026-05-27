import { SkeletonCard } from '@/components/SkeletonCard';

export default function FeedLoading() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 h-8 w-48 animate-pulse rounded bg-gray-200" />
      <div className="mb-6 h-10 w-full animate-pulse rounded bg-gray-200" />
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </main>
  );
}
