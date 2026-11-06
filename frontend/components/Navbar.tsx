'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { supabase } from '@/lib/supabase';
import { signOut } from '@/lib/auth';

function ArrowUpRight({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 12L12 4M12 4H6M12 4V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export function Navbar() {
  const [session, setSession] = useState<import('@supabase/supabase-js').Session | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    const handleScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', handleScroll);

    return () => {
      listener.subscription.unsubscribe();
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const handleSignOut = async () => {
    try {
      await signOut();
      window.location.href = '/';
    } catch {
      // ignore
    }
  };

  const navLinks = [
    { href: '/' as const, label: 'Discover' },
    { href: '/feed' as const, label: 'Feed' },
    { href: '/graph' as const, label: 'Graph' },
    { href: '/saved' as const, label: 'Saved' },
    { href: '/settings' as const, label: 'Settings' },
  ];

  const isActive = (href: string) => pathname === href;

  return (
    <nav
      className={`fixed left-0 right-0 top-0 z-50 transition-all duration-200 ${
        scrolled ? 'border-b border-neutral-200 bg-white/80 backdrop-blur-xl' : 'bg-white'
      }`}
    >
      <div className="mx-auto flex max-w-[1420px] items-center justify-between px-5 py-2.5 sm:px-8 lg:px-10">
        {/* Logo */}
        <Link href="/" className="group flex items-center gap-2" aria-label="Zenith home">
          <span className="font-serif text-[18px] font-normal tracking-tight text-ink-900">
            Zenith
          </span>
        </Link>

        {/* Desktop nav - centered, refined */}
        <div className="hidden items-center gap-7 md:flex lg:gap-9">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`relative font-sans text-[10px] font-bold uppercase tracking-[0.2em] transition-colors duration-150 ${
                isActive(link.href)
                  ? 'text-ink-900'
                  : 'text-zenith-body hover:text-ink-900'
              }`}
            >
              {link.label}
              {isActive(link.href) && (
                <span className="absolute -bottom-2.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-ink-900" />
              )}
            </Link>
          ))}
        </div>

        {/* Desktop auth */}
        <div className="hidden items-center md:flex">
          {session?.user ? (
            <div className="flex items-center gap-2">
              <span className="font-sans text-[10px] text-zenith-muted">{session.user.email}</span>
              <button
                onClick={handleSignOut}
                className="rounded-full border border-ink-900/40 bg-transparent px-4 py-1.5 font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-ink-900 transition duration-150 hover:bg-ink-900 hover:text-white hover:border-ink-900"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="group relative inline-flex items-center gap-1.5 rounded-full border border-ink-900/40 bg-transparent px-4.5 py-1.5 font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-ink-900 transition duration-200 hover:bg-ink-900 hover:text-white hover:border-ink-900"
            >
              <span>Sign In</span>
              <ArrowUpRight className="h-3 w-3 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden"
          onClick={() => setMobileOpen((prev) => !prev)}
          aria-label="Toggle menu"
        >
          <svg
            className="h-5 w-5 text-ink-900"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-zenith-border bg-white/95 backdrop-blur-xl px-6 py-3 md:hidden">
          <div className="flex flex-col gap-2.5">
            {navLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`font-sans text-[11px] font-bold uppercase tracking-[0.15em] transition-colors duration-150 ${
                  isActive(link.href)
                    ? 'text-ink-900'
                    : 'text-zenith-body hover:text-ink-900'
                }`}
              >
                {link.label}
              </Link>
            ))}

            <div className="border-t border-zenith-border pt-2.5">
              {session?.user ? (
                <div className="flex flex-col gap-2">
                  <span className="text-[11px] text-zenith-muted">{session.user.email}</span>
                  <button
                    onClick={() => {
                      setMobileOpen(false);
                      handleSignOut();
                    }}
                    className="w-full rounded-md bg-ink-900 px-3 py-1.5 text-left text-[12px] font-medium text-white hover:bg-ink-800"
                  >
                    Sign Out
                  </button>
                </div>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setMobileOpen(false)}
                  className="inline-flex items-center gap-1 rounded-md bg-ink-900 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-ink-800"
                >
                  Sign In
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
