/// <reference types="vitest/globals" />
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PaperCard } from '@/components/PaperCard';
import { Paper } from '@/types';

const mockPaper: Paper = {
  id: 'test-1',
  title: 'Test Paper Title',
  abstract: 'This is a test abstract.',
  authors: ['Author One', 'Author Two'],
  url: 'https://arxiv.org/test',
  publishedAt: '2024-01-15T00:00:00Z',
  summaryTldr: 'This is a TL;DR.',
  relevanceScore: 0.85,
  difficulty: 'intermediate',
};

describe('PaperCard', () => {
  it('renders the paper title', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByText('Test Paper Title')).toBeInTheDocument();
  });

  it('renders the TL;DR', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByText('This is a TL;DR.')).toBeInTheDocument();
  });

  it('labels generated summaries as AI-generated', () => {
    render(<PaperCard paper={{ ...mockPaper, summaryStatus: 'generated' }} />);
    expect(screen.getByText('AI-generated summary')).toBeInTheDocument();
  });

  it('labels abstract previews and explains the fallback reason', () => {
    render(<PaperCard paper={{ ...mockPaper, summaryStatus: 'abstract_preview', summaryFallbackReason: 'spend_limit' }} />);
    expect(screen.getByText('Abstract preview')).toBeInTheDocument();
    expect(screen.getByText('The spend limit prevented a generated summary.')).toBeInTheDocument();
  });

  it('never labels unknown summary provenance as AI-generated', () => {
    render(<PaperCard paper={{ ...mockPaper, summaryStatus: 'unknown' }} />);
    expect(screen.getByText('Summary source unknown')).toBeInTheDocument();
    expect(screen.queryByText('AI-generated summary')).not.toBeInTheDocument();
  });

  it('does not render provenance for a paper without summary content or status', () => {
    const { container } = render(<PaperCard paper={{ ...mockPaper, summaryTldr: undefined }} />);
    expect(screen.queryByText('Summary source unknown')).not.toBeInTheDocument();
    expect(container.textContent).not.toContain('Summary source unknown');
  });

  it('renders provenance when the backend explicitly reports unknown status', () => {
    render(<PaperCard paper={{ ...mockPaper, summaryTldr: undefined, summaryStatus: 'unknown' }} />);
    expect(screen.getByText('Summary source unknown')).toBeInTheDocument();
  });

  it('renders author names', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByText('Author One, Author Two')).toBeInTheDocument();
  });

  it('renders relevance score', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByText(/85.*MATCH/i)).toBeInTheDocument();
  });

  it('renders difficulty badge', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByText(/intermediate/i)).toBeInTheDocument();
  });

  it('calls onSave when save button clicked', () => {
    const onSave = vi.fn();
    render(<PaperCard paper={mockPaper} onSave={onSave} />);
    fireEvent.click(screen.getByTitle('Save'));
    expect(onSave).toHaveBeenCalledWith('test-1');
  });

  it('calls onDismiss when dismiss button clicked', () => {
    const onDismiss = vi.fn();
    render(<PaperCard paper={mockPaper} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByTitle('Dismiss'));
    expect(onDismiss).toHaveBeenCalledWith('test-1');
  });

  it('shows Unsave label when showUnsave is true', () => {
    const onDismiss = vi.fn();
    render(<PaperCard paper={mockPaper} onDismiss={onDismiss} showUnsave />);
    expect(screen.getByTitle('Unsave')).toBeInTheDocument();
  });

  it('does not render save button when onSave is not provided', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.queryByTitle('Save')).not.toBeInTheDocument();
  });

  it('does not render dismiss button when onDismiss is not provided', () => {
    render(<PaperCard paper={mockPaper} />);
    expect(screen.getByTitle('Share')).toBeInTheDocument();
    expect(screen.queryByTitle('Dismiss')).not.toBeInTheDocument();
  });
});
