import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { QueryProvider } from '@/components/QueryProvider';
import { Navbar } from '@/components/Navbar';
import { ErrorBoundary } from '@/components/ErrorBoundary';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: 'Zenith — AI-Powered Research',
  description: 'Discover, summarise, and personalise academic research from ArXiv and HuggingFace — in seconds.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} flex min-h-screen flex-col`} suppressHydrationWarning>
        <QueryProvider>
          <Navbar />
          <div className="flex-1">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
