export function SkeletonCard() {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-2 h-5 w-3/4 animate-pulse rounded bg-gray-200" />
      <div className="mb-3 h-3 w-1/2 animate-pulse rounded bg-gray-200" />
      <div className="mb-3 h-16 w-full animate-pulse rounded bg-gray-200" />
      <div className="flex justify-between">
        <div className="h-3 w-1/4 animate-pulse rounded bg-gray-200" />
        <div className="h-8 w-20 animate-pulse rounded bg-gray-200" />
      </div>
    </div>
  );
}
