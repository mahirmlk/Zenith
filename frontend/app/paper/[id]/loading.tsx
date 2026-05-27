export default function PaperLoading() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-4 h-4 w-24 animate-pulse rounded bg-gray-200" />
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 h-8 w-3/4 animate-pulse rounded bg-gray-200" />
        <div className="mb-6 h-4 w-1/2 animate-pulse rounded bg-gray-200" />
        <div className="mb-6 h-20 w-full animate-pulse rounded bg-gray-200" />
        <div className="mb-4 h-32 w-full animate-pulse rounded bg-gray-200" />
        <div className="h-10 w-32 animate-pulse rounded bg-gray-200" />
      </div>
    </main>
  );
}
