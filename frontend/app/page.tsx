import Link from 'next/link';

/* ───────── Icons ───────── */

function ArrowUpRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 12L12 4M12 4H6M12 4V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ChevronLeft({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 12L10 8L6 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function StarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 2L11.5 7.5H17L12.5 10.5L14 16L10 13L6 16L7.5 10.5L3 7.5H8.5L10 2Z" stroke="#94a3b8" strokeWidth="1.2" strokeLinejoin="round" fill="none"/>
    </svg>
  );
}

function GlobeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="10" r="7.5" stroke="#94a3b8" strokeWidth="1.2"/>
      <ellipse cx="10" cy="10" rx="3" ry="7.5" stroke="#94a3b8" strokeWidth="1.2"/>
      <path d="M2.5 10H17.5" stroke="#94a3b8" strokeWidth="1.2"/>
    </svg>
  );
}

function DocIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M11.5 1.5H5C4.17157 1.5 3.5 2.17157 3.5 3V17C3.5 17.8284 4.17157 18.5 5 18.5H15C15.8284 18.5 16.5 17.8284 16.5 17V6.5L11.5 1.5Z" stroke="#94a3b8" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M11.5 1.5V6.5H16.5" stroke="#94a3b8" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M7 13.5H13" stroke="#94a3b8" strokeWidth="1.2" strokeLinecap="round"/>
      <path d="M7 10.5H13" stroke="#94a3b8" strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  );
}

/* ───────── Document Illustration (matches third image) ───────── */

function DocumentIllustration() {
  return (
    <svg width="340" height="420" viewBox="0 0 340 420" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Soft shadow beneath */}
      <ellipse cx="170" cy="395" rx="110" ry="14" fill="#0f172a" fillOpacity="0.05" />
      
      {/* Main paper body */}
      <rect x="40" y="15" width="260" height="360" rx="20" fill="white" stroke="#e2e8f0" strokeWidth="0.8"/>
      
      {/* Folded corner */}
      <path d="M260 15L295 50V35C295 24.5066 286.493 16 276 16H260Z" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="0.8"/>
      <path d="M260 15V50H295" stroke="#e2e8f0" strokeWidth="0.8" fill="none"/>
      
      {/* Blue header line */}
      <rect x="75" y="70" width="75" height="7" rx="3.5" fill="#bae6fd" fillOpacity="0.8"/>
      
      {/* Gray content lines */}
      <rect x="75" y="110" width="190" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="130" width="190" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="150" width="170" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="170" width="190" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="190" width="150" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="210" width="190" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="230" width="180" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="250" width="130" height="5" rx="2.5" fill="#d1d5db"/>
      <rect x="75" y="270" width="190" height="5" rx="2.5" fill="#d1d5db"/>
      
      {/* Bottom image placeholder */}
      <rect x="75" y="305" width="90" height="38" rx="8" fill="#f1f5f9" stroke="#e2e8f0" strokeWidth="0.8"/>
    </svg>
  );
}

/* ───────── Small Paper Thumbnail ───────── */

function PaperThumbnail() {
  return (
    <svg width="100" height="120" viewBox="0 0 100 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="8" y="4" width="84" height="112" rx="12" fill="white" stroke="#e2e8f0" strokeWidth="0.8"/>
      <path d="M68 4V38H92L68 4Z" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="0.8"/>
      <rect x="20" y="24" width="36" height="5" rx="2.5" fill="#bae6fd" fillOpacity="0.7"/>
      <rect x="20" y="38" width="60" height="3.5" rx="1.75" fill="#d1d5db"/>
      <rect x="20" y="47" width="60" height="3.5" rx="1.75" fill="#d1d5db"/>
      <rect x="20" y="56" width="50" height="3.5" rx="1.75" fill="#d1d5db"/>
      <rect x="20" y="65" width="60" height="3.5" rx="1.75" fill="#d1d5db"/>
      <rect x="20" y="74" width="42" height="3.5" rx="1.75" fill="#d1d5db"/>
      <rect x="20" y="90" width="32" height="14" rx="4" fill="#f1f5f9" stroke="#e2e8f0" strokeWidth="0.8"/>
    </svg>
  );
}

/* ───────── Page ───────── */

export default function Home() {
  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-[#f0f4f8]">
      {/* ── Ultra-subtle ambient background ── */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-10 right-0 h-[400px] w-[400px] rounded-full bg-sky-100/30 blur-[100px]" />
        <div className="absolute top-1/4 -left-10 h-[300px] w-[300px] rounded-full bg-blue-50/40 blur-[80px]" />
      </div>

      {/* ── Hero + Trending combined section ── */}
      <section className="relative mx-auto w-full max-w-7xl flex-1 px-8 pt-28">
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 lg:items-center">
          {/* Left: Copy */}
          <div className="max-w-lg pt-4">
            {/* Title */}
            <h1 className="text-[5rem] font-bold leading-[0.9] tracking-tight text-[#0a1628] sm:text-[6rem] lg:text-[7rem]">
              Zenith<span className="text-[#38bdf8]">.</span>
            </h1>

            {/* Subtitle */}
            <p className="mb-5 mt-2 text-base font-medium tracking-wide text-[#94a3b8]">
              AI Research Agent
            </p>

            {/* Body - exact 3-line break from third image */}
            <p className="mb-6 max-w-md text-[16px] leading-[1.65] text-[#64748b]">
              Turn overwhelming papers into real understanding.
              <br />
              Discover, summarise, and personalise academic research
              <br />
              from ArXiv and HuggingFace — in seconds.
            </p>

            {/* CTAs */}
            <div className="flex flex-wrap items-center gap-3">
              <Link
                href="/feed"
                className="inline-flex items-center gap-2 rounded-full bg-[#0a1628] px-6 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#0f172a]"
              >
                Explore Papers
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-6 py-2.5 text-sm font-medium text-[#0a1628] shadow-sm transition hover:bg-gray-50"
              >
                Sign In
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>

          {/* Right: Document visual */}
          <div className="relative flex items-center justify-center lg:justify-end">
            {/* Soft glow behind document */}
            <div className="absolute h-56 w-56 rounded-full bg-sky-100/25 blur-[70px]" />
            <div className="absolute h-40 w-40 translate-x-8 translate-y-6 rounded-full bg-blue-100/15 blur-[50px]" />

            {/* Document with slight left tilt */}
            <div className="relative" style={{ transform: 'rotate(-2deg)' }}>
              <DocumentIllustration />
            </div>

            {/* Vertical step indicator */}
            <div className="absolute right-0 top-1/2 hidden -translate-y-1/2 flex-col items-center gap-2 lg:flex">
              <span className="text-[11px] font-semibold text-[#0a1628]">01</span>
              <div className="h-10 w-px bg-[#38bdf8]" />
              <div className="h-1.5 w-1.5 rounded-full bg-gray-300" />
              <div className="h-10 w-px bg-gray-200" />
              <span className="text-[11px] font-medium text-gray-400">04</span>
            </div>
          </div>
        </div>

        {/* ── Trending Paper Card (positioned directly under hero, no extra gap) ── */}
        <div className="mt-6 lg:mt-4">
          <div className="rounded-[1.75rem] border border-white/50 bg-white/60 p-5 shadow-[0_4px_24px_-4px_rgba(15,23,42,0.05)] backdrop-blur-xl lg:p-6">
            <div className="flex items-center gap-4 lg:gap-5">
              {/* Left icon sidebar */}
              <div className="hidden flex-col items-center gap-3.5 border-r border-gray-100 pr-4 lg:flex">
                <StarIcon />
                <GlobeIcon />
                <DocIcon />
              </div>

              {/* Paper thumbnail with soft bg */}
              <div className="hidden shrink-0 items-center justify-center rounded-2xl bg-[#e8f0f8] p-4 lg:flex">
                <PaperThumbnail />
              </div>

              {/* Text content */}
              <div className="min-w-0 flex-1">
                <p className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#38bdf8]">
                  Trending Paper
                </p>
                <h3 className="mb-1 text-[15px] font-semibold text-[#0a1628]">
                  A Gentle Introduction to Diffusion Models
                </h3>
                <p className="mb-1 text-[13px] text-[#64748b]">
                  Ho, J. et al. (2020) <span className="mx-1 text-gray-300">•</span> arXiv: 2006.11239
                </p>
                <p className="max-w-sm text-[13px] leading-relaxed text-[#94a3b8]">
                  An intuitive overview of diffusion models and how they generate high-quality data.
                </p>
              </div>

              {/* Controls */}
              <div className="flex shrink-0 flex-col items-end gap-3">
                <div className="flex items-center gap-2">
                  <button
                    aria-label="Previous paper"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-gray-200 text-gray-400 transition hover:border-gray-300 hover:text-gray-500"
                  >
                    <ChevronLeft />
                  </button>
                  <button
                    aria-label="Next paper"
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-[#38bdf8] text-white shadow-[0_0_16px_-4px_rgba(56,189,248,0.35)] transition hover:bg-[#7dd3fc]"
                  >
                    <ChevronRight />
                  </button>
                </div>
                <Link
                  href="/feed"
                  className="inline-flex items-center gap-1 text-[12px] font-medium text-[#0a1628] transition hover:text-[#38bdf8]"
                >
                  View all papers
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
