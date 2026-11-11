import Link from 'next/link';

const features = [
  {
    title: 'Search that reads the paper for you',
    body: 'Ask a question. Zenith pulls from arXiv and Hugging Face, writes a short summary, and shows only the papers it can cite.',
  },
  {
    title: 'A feed that learns your taste',
    body: 'Save papers you like. The next feed is ranked from those choices, not from a global trending list.',
  },
  {
    title: 'Projects you can keep',
    body: 'Create research projects to organize your work and keep project notes.',
  },
];

const steps = [
  {
    n: '1',
    title: 'Ask',
    body: 'Type a question in plain words. Pick a model from the registry.',
  },
  {
    n: '2',
    title: 'Read',
    body: 'Follow agent progress and view the completed results in your feed.',
  },
  {
    n: '3',
    title: 'Keep',
    body: 'Save the papers that matter and organize your reading into projects.',
  },
];

export default function Home() {
  return (
    <main className="bg-white text-neutral-900">
      <section className="mx-auto flex max-w-5xl flex-col items-center px-6 pb-20 pt-24 text-center">
        <p className="text-sm font-medium text-blue-600">Zenith</p>
        <h1 className="mt-4 max-w-3xl text-5xl font-semibold leading-tight tracking-tight sm:text-6xl">
          Research papers, without the reading pile.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-600">
          Zenith finds new papers from arXiv and Hugging Face, summarizes them in plain
          language, and ranks them by what you have already saved. Every answer links to a
          paper you can open.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/feed"
            className="rounded-full bg-blue-600 px-7 py-3 text-sm font-medium text-white transition hover:bg-blue-700"
          >
            Open the feed
          </Link>
          <Link
            href="/login"
            className="rounded-full border border-neutral-300 px-7 py-3 text-sm font-medium text-neutral-900 transition hover:border-neutral-400"
          >
            Sign in
          </Link>
        </div>
        <p className="mt-6 text-sm text-neutral-500">
          Free to try. Your library stays yours.
        </p>
      </section>

      <section className="border-t border-neutral-100 bg-neutral-50">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <h2 className="text-center text-3xl font-semibold tracking-tight">
            What it does
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-neutral-600">
            Three things, done well. No extra panels you have to learn.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-3">
            {features.map((f) => (
              <div
                key={f.title}
                className="rounded-3xl border border-neutral-200 bg-white p-7"
              >
                <h3 className="text-base font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-600">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-6 py-20">
        <h2 className="text-center text-3xl font-semibold tracking-tight">
          How a search works
        </h2>
        <div className="mt-12 grid gap-10 sm:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
                {s.n}
              </div>
              <h3 className="mt-4 text-base font-semibold">{s.title}</h3>
              <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-neutral-600">
                {s.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-6 pb-24 text-center">
        <h2 className="text-3xl font-semibold tracking-tight">
          Start with one question.
        </h2>
        <p className="mt-4 text-neutral-600">
          If the papers are useful, save them. If they are not, ask again. That is the whole loop.
        </p>
        <Link
          href="/feed"
          className="mt-8 inline-block rounded-full bg-neutral-900 px-7 py-3 text-sm font-medium text-white transition hover:bg-neutral-700"
        >
          Try a search
        </Link>
      </section>
    </main>
  );
}
