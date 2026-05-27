import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="text-center">
        <h1 className="mb-2 text-6xl font-bold text-gray-900">404</h1>
        <p className="mb-6 text-lg text-gray-600">This page does not exist.</p>
        <Link href="/feed" className="rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700">
          Go to Feed
        </Link>
      </div>
    </main>
  );
}
