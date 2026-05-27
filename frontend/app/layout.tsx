import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { QueryProvider } from '@/components/QueryProvider';
import { Navbar } from '@/components/Navbar';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Footer } from '@/components/Footer';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'AI Paper Research Agent',
  description: 'Discover and personalise academic papers with AI',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} flex min-h-screen flex-col`}>
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
