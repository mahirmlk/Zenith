import type { Metadata } from 'next';
import './globals.css';
import { QueryProvider } from '@/components/QueryProvider';
import { Navbar } from '@/components/Navbar';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Footer } from '@/components/Footer';

export const metadata: Metadata = {
  title: 'Zenith — AI-Powered Research',
  description: 'Discover, summarise, and personalise academic research from ArXiv and HuggingFace — in seconds.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-zenith-bg font-sans text-ink antialiased" suppressHydrationWarning>
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
