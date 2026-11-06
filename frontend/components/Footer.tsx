import Link from 'next/link';

export function Footer() {
  return (
    <footer className="border-t border-neutral-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 text-sm text-neutral-500 sm:flex-row">
        <p>Zenith. Research papers, summarised and ranked for you.</p>
        <nav className="flex gap-6">
          <Link href="/feed" className="transition hover:text-neutral-900">Feed</Link>
          <Link href="/projects" className="transition hover:text-neutral-900">Projects</Link>
          <Link href="/login" className="transition hover:text-neutral-900">Sign in</Link>
        </nav>
      </div>
    </footer>
  );
}
