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
