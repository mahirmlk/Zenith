import Link from 'next/link';

export default function SavedPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 bg-zenith-bg">
      <div className="max-w-md text-center">
        <h1 className="mb-3 text-2xl font-bold text-zenith-navy">Saved Papers</h1>
        <p className="mb-6 text-zenith-muted">
          Your saved papers will appear here. Start exploring to build your reading list.
        </p>
        <Link
          href="/feed"
          className="inline-flex items-center gap-2 rounded-full bg-zenith-navy px-6 py-2.5 text-sm font-medium text-white hover:bg-zenith-dark"
        >
          Explore Papers
        </Link>
      </div>
    </main>
  );
}
