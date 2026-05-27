/// <reference types="vitest/globals" />
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
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
});
