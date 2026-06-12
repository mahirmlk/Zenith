import type { Metadata } from 'next';
import { Instrument_Serif, Geist, Geist_Mono, Plus_Jakarta_Sans } from 'next/font/google';
import './globals.css';
import { QueryProvider } from '@/components/QueryProvider';
import { Navbar } from '@/components/Navbar';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Footer } from '@/components/Footer';

const geist = Geist({ subsets: ['latin'], variable: '--font-geist' });
const instrument = Instrument_Serif({ subsets: ['latin'], weight: ['400'], variable: '--font-instrument' });
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' });
const plusJakarta = Plus_Jakarta_Sans({ subsets: ['latin'], variable: '--font-plus-jakarta' });

export const metadata: Metadata = {
  title: 'Zenith — AI-Powered Research',
  description: 'Discover, summarise, and personalise academic research from ArXiv and HuggingFace — in seconds.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} ${instrument.variable} ${geistMono.variable} ${plusJakarta.variable} flex min-h-screen flex-col bg-zenith-bg text-ink antialiased`} suppressHydrationWarning>
        <QueryProvider>
          <Navbar />
          <div className="flex-1">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
          <Footer />
        </QueryProvider>
      </body>
    </html>
  );
}
