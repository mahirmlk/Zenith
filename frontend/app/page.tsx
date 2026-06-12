import Link from 'next/link';
import { CanvasAsciiBackground } from '@/components/CanvasAsciiBackground';

function ArrowUpRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 12L12 4M12 4H6M12 4V10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronLeft({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M11.25 13.5L6.75 9L11.25 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M6.75 13.5L11.25 9L6.75 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M5 5L15 15M15 5L5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function XTwitterIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" clipRule="evenodd" d="M10 1.75A8.25 8.25 0 0 0 7.39 17.83c.41.08.56-.18.56-.39v-1.52c-2.28.5-2.76-.98-2.76-.98-.37-.95-.91-1.2-.91-1.2-.74-.51.06-.5.06-.5.82.06 1.25.85 1.25.85.73 1.25 1.92.89 2.39.68.07-.53.28-.89.52-1.09-1.82-.21-3.73-.91-3.73-4.05 0-.89.32-1.62.84-2.2-.08-.21-.36-1.05.08-2.17 0 0 .69-.22 2.27.84A7.85 7.85 0 0 1 10 5.82c.7 0 1.4.09 2.06.28 1.57-1.06 2.26-.84 2.26-.84.45 1.12.17 1.96.09 2.17.52.58.84 1.31.84 2.2 0 3.15-1.92 3.84-3.75 4.04.29.26.55.76.55 1.53v2.24c0 .21.15.47.57.39A8.25 8.25 0 0 0 10 1.75Z" />
    </svg>
  );
}

function FileIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M11.5 2.5H5.75A1.75 1.75 0 0 0 4 4.25v11.5c0 .97.78 1.75 1.75 1.75h8.5c.97 0 1.75-.78 1.75-1.75V7L11.5 2.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M11.5 2.5V7H16M7 11h6M7 14h4.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PaperThumbnail() {
  return (
    <svg className="h-14 w-12" viewBox="0 0 112 128" fill="none" aria-hidden="true">
      <defs>
        <pattern id="thumbDots" x="0" y="0" width="4" height="4" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="0.5" fill="#0A1633" opacity="0.04" />
        </pattern>
      </defs>
      <ellipse cx="57" cy="112" rx="38" ry="7" fill="#94a3b8" fillOpacity="0.08" />
      <path d="M27 15h51l22 24v69c0 7.18-5.82 13-13 13H27c-7.18 0-13-5.82-13-13V28c0-7.18 5.82-13 13-13Z" fill="white" stroke="#E3E8EF" strokeWidth="1.5" />
      <path d="M78 15v24h22" fill="#F7F8FA" />
      <path d="M78 15v24h22" stroke="#E3E8EF" strokeWidth="1.5" strokeLinejoin="round" />
      <rect x="30" y="38" width="26" height="4" rx="2" fill="#0A1633" opacity="0.15" />
      <rect x="30" y="52" width="52" height="3" rx="1.5" fill="#E3E8EF" />
      <rect x="30" y="62" width="52" height="3" rx="1.5" fill="#E3E8EF" />
      <rect x="30" y="72" width="44" height="3" rx="1.5" fill="#E3E8EF" />
      <rect x="30" y="82" width="48" height="3" rx="1.5" fill="#E3E8EF" />
      <rect x="30" y="99" width="32" height="14" rx="4" fill="#F7F8FA" stroke="#E3E8EF" />
    </svg>
  );
}

function AsciiGridBackground() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" style={{ opacity: 0.1 }}>
      <defs>
        <pattern id="asciiGrid" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
          <line x1="0" y1="40" x2="40" y2="40" stroke="#CBD5E1" strokeWidth="0.5" strokeDasharray="1 3" />
          <line x1="40" y1="0" x2="40" y2="40" stroke="#CBD5E1" strokeWidth="0.5" strokeDasharray="1 3" />
        </pattern>
        <pattern id="asciiGridFine" x="0" y="0" width="10" height="10" patternUnits="userSpaceOnUse">
          <line x1="0" y1="10" x2="10" y2="10" stroke="#E2E8F0" strokeWidth="0.3" strokeDasharray="1 2" />
          <line x1="10" y1="0" x2="10" y2="10" stroke="#E2E8F0" strokeWidth="0.3" strokeDasharray="1 2" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#asciiGrid)" />
      <rect width="100%" height="100%" fill="url(#asciiGridFine)" opacity="0.5" />
    </svg>
  );
}

function AsciiRiver() {
  const riverLines = [
    "          ~                    ~                    ~                    ",
    "      ~       ~            ~       ~            ~       ~            ~    ",
    "   ~  ~  ~  ~  ~       ~  ~  ~  ~  ~       ~  ~  ~  ~  ~       ~  ~  ~  ",
    " ~~~~~~~~~~~~~~  ~  ~~~~~~~~~~~~~~  ~  ~~~~~~~~~~~~~~  ~  ~~~~~~~~~~~~~~~ ",
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    " ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~ ",
    "  ~~~    ~~~    ~~~~    ~~~    ~~~    ~~~~    ~~~    ~~~    ~~~~    ~~~  ",
    "    ~~~      ~~~    ~~~      ~~~    ~~~      ~~~      ~~~    ~~~      ~~~ ",
    "      ~        ~        ~        ~        ~        ~        ~        ~     ",
    "  ~       ~        ~        ~        ~        ~        ~        ~       ~  ",
    "  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ",
    " ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    "    ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~    ",
    "  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ",
    "      ~         ~         ~         ~         ~         ~         ~       ",
    "  ~       ~         ~         ~         ~         ~         ~       ~      ",
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    " ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~ ",
    "  ~~~    ~~~    ~~~~    ~~~    ~~~    ~~~~    ~~~    ~~~    ~~~~    ~~~   ",
    "    ~~~      ~~~    ~~~      ~~~    ~~~      ~~~      ~~~    ~~~      ~~~",
    "      ~        ~        ~        ~        ~        ~        ~        ~      ",
    "  ~       ~        ~        ~        ~        ~        ~        ~       ~ ",
    "  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~  ~~~~  ~~  ~~~~~~~~   ",
    " ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~~~~  ~~~~  ~~~~~  ~~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    "    ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~     ~~     ",
    "  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~  ~    ~   ",
    "      ~         ~         ~         ~         ~         ~         ~        ",
    "  ~       ~         ~         ~         ~         ~         ~       ~      ",
    "    ~  ~  ~  ~  ~       ~  ~  ~  ~  ~       ~  ~  ~  ~  ~       ~  ~  ~   ",
    "          ~                    ~                    ~                       ",
  ];

  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" style={{ opacity: 0.06 }}>
      <defs>
        <linearGradient id="riverGradient" x1="0%" y1="0%" x2="100%" y2="0%" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0EA5E9" stopOpacity="0" />
          <stop offset="20%" stopColor="#0EA5E9" stopOpacity="0.4" />
          <stop offset="50%" stopColor="#0284C7" stopOpacity="0.8" />
          <stop offset="80%" stopColor="#0EA5E9" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#0EA5E9" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#riverGradient)" opacity="0.1" />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="middle"
        fontFamily="'Courier New', monospace"
        fontSize="12"
        fill="#0369A1"
        style={{ opacity: 0.15, whiteSpace: 'pre' }}
      >
        {riverLines.map((line, i) => (
          <tspan key={i} x="50%" dy={i === 0 ? "-220" : "16"}>
            {line}
          </tspan>
        ))}
      </text>
    </svg>
  );
}

function AsciiFlowLines() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" style={{ opacity: 0.04 }}>
      <defs>
        <linearGradient id="flowLineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#38BDF8" stopOpacity="0" />
          <stop offset="30%" stopColor="#38BDF8" stopOpacity="1" />
          <stop offset="70%" stopColor="#38BDF8" stopOpacity="1" />
          <stop offset="100%" stopColor="#38BDF8" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[120, 200, 280, 360, 440, 520, 600, 680, 760, 840, 920, 1000].map((y, i) => (
        <path
          key={i}
          d={`M 0 ${y} Q 300 ${y - 40} 600 ${y} Q 900 ${y + 40} 1200 ${y}`}
          stroke="url(#flowLineGrad)"
          strokeWidth="0.5"
          fill="none"
          strokeDasharray={i % 2 === 0 ? "8 12" : "12 8"}
        />
      ))}
      {[150, 250, 350, 450, 550, 650, 750, 850, 950].map((y, i) => (
        <path
          key={`rev-${i}`}
          d={`M 1200 ${y} Q 900 ${y + 40} 600 ${y} Q 300 ${y - 40} 0 ${y}`}
          stroke="url(#flowLineGrad)"
          strokeWidth="0.5"
          fill="none"
          strokeDasharray={i % 2 === 0 ? "10 10" : "6 14"}
        />
      ))}
    </svg>
  );
}

function AsciiButton({
  href,
  label,
  variant,
}: {
  href: React.ComponentProps<typeof Link>['href'];
  label: string;
  variant: 'dark' | 'light';
}) {
  const isDark = variant === 'dark';
  return (
    <Link
      href={href}
      className={`group relative inline-flex min-h-8 items-center gap-2 border px-4 text-[11px] font-semibold transition duration-200 hover:-translate-y-0.5 ${
        isDark
          ? 'border-ink-900/30 bg-transparent text-ink-900 hover:bg-ink-900 hover:text-white hover:border-ink-900/60'
          : 'border-zenith-border/50 bg-transparent text-ink-900 hover:bg-white/50 hover:border-zenith-border'
      }`}
    >
      <pre
        className={`font-mono text-[9px] leading-none select-none transition ${
          isDark ? 'text-ink-900/15 group-hover:text-white/20' : 'text-zenith-muted/25'
        }`}
        aria-hidden="true"
      >
        {isDark ? '[▓]' : '[░]'}
      </pre>
      <span>{label}</span>
      <ArrowUpRight
        className={`h-3 w-3 transition duration-200 ${
          isDark ? 'text-ink-900/40 group-hover:text-white' : 'text-zenith-muted group-hover:text-ink-900'
        }`}
      />
    </Link>
  );
}

export default function Home() {
  return (
    <main className="relative isolate min-h-screen overflow-hidden bg-zenith-bg">
      {/* ASCII Art Background Layers */}
      <AsciiGridBackground />
      <CanvasAsciiBackground />

      {/* Subtle halftone overlay */}
      <div className="pointer-events-none absolute inset-0 dot-grid text-ink-900" />
      <div className="pointer-events-none absolute inset-0 halftone text-ink-900" style={{ opacity: 0.03 }} />

      <section className="relative z-10 mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-[1420px] flex-col items-center justify-center px-5 pb-4 pt-8 sm:px-8 lg:px-10">
        {/* Center - Hero text */}
        <div className="mt-6 text-center">
          {/* Eyebrow label */}
          <div className="mb-4 inline-flex items-center gap-2">
            <span className="h-px w-6 bg-zenith-muted/50" />
            <p className="font-mono text-[9px] font-medium uppercase tracking-[0.28em] text-zenith-muted">
              Research Intelligence
            </p>
            <span className="h-px w-6 bg-zenith-muted/50" />
          </div>

          {/* Big serif logotype */}
          <h1 className="font-serif text-[40px] font-normal leading-[1.0] tracking-[-0.02em] text-ink-900 sm:text-[48px] lg:text-[56px]">
            Zenith
          </h1>

          {/* Multi-style paragraph */}
          <div className="mx-auto mt-5 max-w-[360px] space-y-1">
            <p className="font-serif text-[15px] font-normal italic leading-[1.6] text-zenith-body">
              Turn overwhelming research into real understanding.
            </p>
            <p className="font-sans text-[11px] font-medium uppercase tracking-[0.14em] text-zenith-muted">
              Discover · Summarise · Personalise
            </p>
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <AsciiButton href="/feed" label="Explore Papers" variant="dark" />
            <AsciiButton href="/login" label="Sign In" variant="light" />
          </div>
        </div>

        {/* Trending paper card — smaller, moved further down */}
        <aside className="relative z-20 mt-8 w-full max-w-[540px] rounded-xl border border-zenith-border/70 bg-white/75 px-2.5 py-2 shadow-soft backdrop-blur-[32px] lg:mt-10">
          <div className="flex items-center gap-2.5">
            {/* Left icons column */}
            <div className="flex shrink-0 flex-col items-center gap-1.5 border-r border-zenith-border/40 pr-2.5 text-zenith-muted">
              <button className="transition duration-150 hover:text-ink-900" type="button" aria-label="Share on X">
                <XTwitterIcon className="h-3.5 w-3.5" />
              </button>
              <button className="transition duration-150 hover:text-ink-900" type="button" aria-label="Open repository">
                <GithubIcon className="h-3.5 w-3.5" />
              </button>
              <button className="transition duration-150 hover:text-ink-900" type="button" aria-label="Open paper">
                <FileIcon className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Paper thumbnail — slightly smaller */}
            <div className="flex shrink-0 items-center justify-center opacity-80">
              <svg className="h-11 w-9" viewBox="0 0 112 128" fill="none" aria-hidden="true">
                <ellipse cx="57" cy="112" rx="38" ry="7" fill="#94a3b8" fillOpacity="0.06" />
                <path d="M27 15h51l22 24v69c0 7.18-5.82 13-13 13H27c-7.18 0-13-5.82-13-13V28c0-7.18 5.82-13 13-13Z" fill="white" stroke="#DFD9CD" strokeWidth="1.5" />
                <path d="M78 15v24h22" fill="#F3F0E7" />
                <path d="M78 15v24h22" stroke="#DFD9CD" strokeWidth="1.5" strokeLinejoin="round" />
                <rect x="30" y="38" width="26" height="4" rx="2" fill="#2A2529" opacity="0.12" />
                <rect x="30" y="52" width="52" height="3" rx="1.5" fill="#DFD9CD" />
                <rect x="30" y="62" width="52" height="3" rx="1.5" fill="#DFD9CD" />
                <rect x="30" y="72" width="44" height="3" rx="1.5" fill="#DFD9CD" />
                <rect x="30" y="82" width="48" height="3" rx="1.5" fill="#DFD9CD" />
                <rect x="30" y="99" width="32" height="14" rx="4" fill="#F3F0E7" stroke="#DFD9CD" />
              </svg>
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <p className="mb-0.5 font-sans text-[8px] font-bold uppercase tracking-[0.22em] text-zenith-muted">
                Trending Paper
              </p>
              <h2 className="font-serif text-[12.5px] font-normal leading-snug text-ink-900">
                A Gentle Introduction to Diffusion Models
              </h2>
              <p className="mt-0.5 font-sans text-[9px] font-medium text-zenith-body">
                Ho, J. et al. (2020)
                <span className="ml-1 font-mono text-[8.5px] text-zenith-muted">arXiv: 2006.11239</span>
              </p>
              <p className="mt-0.5 font-sans text-[9px] font-normal leading-[1.55] text-zenith-muted-light">
                An intuitive overview of diffusion models and how they generate high-quality data.
              </p>
            </div>

            {/* Right navigation */}
            <div className="flex shrink-0 flex-col items-end gap-2">
              <div className="flex items-center gap-1.5">
                <button
                  aria-label="Previous paper"
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-zenith-border bg-white text-zenith-muted shadow-soft transition duration-150 hover:text-ink-900"
                  type="button"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <button
                  aria-label="Next paper"
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-900 text-zenith-accent shadow-soft transition duration-150 hover:bg-ink-800"
                  type="button"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
              <Link href="/feed" className="inline-flex items-center gap-0.5 font-sans text-[9px] font-bold uppercase tracking-[0.12em] text-ink-900 transition duration-150 hover:text-zenith-muted">
                View all
                <ArrowUpRight className="h-2.5 w-2.5" />
              </Link>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
