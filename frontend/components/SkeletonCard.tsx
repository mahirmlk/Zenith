export function SkeletonCard() {
  return (
    <div className="surface-card p-5 lg:p-6">
      {/* Category row */}
      <div className="mb-3 flex items-center justify-between">
        <div className="h-3 w-16 animate-pulse rounded bg-zenith-border" />
        <div className="h-3 w-20 animate-pulse rounded bg-zenith-border" />
      </div>
      {/* Title */}
      <div className="mb-2 h-6 w-3/4 animate-pulse rounded bg-zenith-border" />
      <div className="mb-2 h-6 w-1/2 animate-pulse rounded bg-zenith-border" />
      {/* Authors */}
      <div className="mb-3 h-3 w-1/2 animate-pulse rounded bg-zenith-border" />
      {/* Metadata */}
      <div className="mb-3 h-3 w-40 animate-pulse rounded bg-zenith-border" />
      {/* Abstract */}
      <div className="mb-2 h-3 w-full animate-pulse rounded bg-zenith-border" />
      <div className="mb-2 h-3 w-full animate-pulse rounded bg-zenith-border" />
      <div className="mb-4 h-3 w-3/4 animate-pulse rounded bg-zenith-border" />
      {/* Actions */}
      <div className="flex justify-between border-t border-zenith-border/60 pt-4">
        <div className="h-4 w-16 animate-pulse rounded bg-zenith-border" />
        <div className="flex gap-2">
          <div className="h-8 w-8 animate-pulse rounded-lg bg-zenith-border" />
          <div className="h-8 w-8 animate-pulse rounded-lg bg-zenith-border" />
        </div>
      </div>
    </div>
  );
}
