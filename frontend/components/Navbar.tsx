'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { supabase } from '@/lib/supabase';
import { signOut } from '@/lib/auth';

function SparkLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 2L18 13H30L20 19L23 30L16 23L9 30L12 19L2 13H14L16 2Z" fill="#7dd3fc" fillOpacity="0.85" stroke="#38bdf8" strokeWidth="1" strokeLinejoin="round"/>
      <circle cx="16" cy="16" r="2.5" fill="white"/>
    </svg>
  );
}

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
    { href: '/feed' as const, label: 'Discover' },
    { href: '/feed' as const, label: 'Feed' },
    { href: '/graph' as const, label: 'Graph' },
    { href: '/saved' as const, label: 'Saved' },
    { href: '/settings' as const, label: 'Settings' },
  ];

  const isActive = (href: string) => pathname === href;

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'glass-strong shadow-soft' : 'bg-transparent'
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-8 py-5">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <SparkLogo className="h-5 w-5" />
          <span className="text-lg font-semibold tracking-tight text-zenith-navy">
            Zenith
          </span>
        </Link>

        {/* Desktop nav - centered */}
        <div className="hidden items-center gap-10 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`relative text-[13px] font-medium transition-colors ${
                isActive(link.href)
                  ? 'text-zenith-navy'
                  : 'text-zenith-muted hover:text-zenith-navy'
              }`}
            >
              {link.label}
              {isActive(link.href) && (
                <span className="absolute -bottom-2 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-zenith-accent" />
              )}
            </Link>
          ))}
        </div>

        {/* Desktop auth */}
        <div className="hidden items-center md:flex">
          {session?.user ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-zenith-muted">{session.user.email}</span>
              <button
                onClick={handleSignOut}
                className="rounded-full bg-zenith-dark px-5 py-2 text-[13px] font-medium text-white transition hover:bg-zenith-navy"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 rounded-full bg-zenith-dark px-5 py-2 text-[13px] font-medium text-white transition hover:bg-zenith-navy"
            >
              Sign In
              <ArrowUpRight className="h-3 w-3" />
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
            className="h-5 w-5 text-zenith-navy"
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
        <div className="glass-strong border-t border-white/40 px-8 py-4 md:hidden">
          <div className="flex flex-col gap-3">
            {navLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`text-sm font-medium ${
                  isActive(link.href)
                    ? 'text-zenith-navy'
                    : 'text-zenith-muted hover:text-zenith-navy'
                }`}
              >
                {link.label}
              </Link>
            ))}

            <div className="border-t border-white/40 pt-3">
              {session?.user ? (
                <div className="flex flex-col gap-2">
                  <span className="text-sm text-zenith-muted">{session.user.email}</span>
                  <button
                    onClick={() => {
                      setMobileOpen(false);
                      handleSignOut();
                    }}
                    className="w-full rounded-full bg-zenith-dark px-4 py-2 text-left text-sm font-medium text-white hover:bg-zenith-navy"
                  >
                    Sign Out
                  </button>
                </div>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setMobileOpen(false)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-zenith-dark px-4 py-2 text-sm font-medium text-white hover:bg-zenith-navy"
                >
                  Sign In
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
