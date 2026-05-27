import Link from 'next/link';

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="max-w-2xl text-center">
        <h1 className="mb-4 text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
          AI Paper Research Agent
        </h1>
        <p className="mb-8 text-lg text-gray-600">
          Zero effort from &quot;paper exists&quot; to &quot;here&apos;s why it matters to you.&quot;
          Discover, summarise, and personalise academic papers from ArXiv and HuggingFace.
        </p>
        <div className="flex justify-center gap-4">
          <Link
            href="/feed"
            className="rounded-lg bg-primary-600 px-6 py-3 text-base font-medium text-white hover:bg-primary-700"
          >
            Explore Papers
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-gray-300 bg-white px-6 py-3 text-base font-medium text-gray-700 hover:bg-gray-50"
          >
            Sign In
          </Link>
        </div>
      </div>
    </main>
  );
}
