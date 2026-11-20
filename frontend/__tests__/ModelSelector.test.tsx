import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ModelSelector } from '@/components/ModelSelector';
import { useAppStore } from '@/store/useAppStore';
import type { LLMModel } from '@/types';

vi.mock('@/lib/auth', () => ({
  getJWT: vi.fn().mockResolvedValue('test-token'),
}));

const CURRENT_MODELS = [
  { id: 'anthropic/claude-opus-5.5', agents: ['orchestrator', 'summary_default'] },
  { id: 'anthropic/claude-sonnet-5.5', agents: ['summary_default', 'orchestrator'] },
  { id: 'openai/gpt-4o', agents: ['summary_default', 'orchestrator'] },
  { id: 'openai/gpt-4o-mini', agents: ['research', 'memory', 'summary_fast'] },
  { id: 'google/gemini-3.6-flash', agents: ['summary_fast', 'research'] },
  { id: 'meta-llama/llama-3.3-70b-instruct', agents: ['summary_default', 'summary_fast'] },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useAppStore.setState({ selectedModel: 'anthropic/claude-sonnet-5.5' });
});

describe('ModelSelector', () => {
  it('replaces an obsolete selected model with the current server default', async () => {
    useAppStore.setState({ selectedModel: 'anthropic/claude-opus-4' as LLMModel });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        available: true,
        default_model: 'openai/gpt-4o',
        models: CURRENT_MODELS,
      }),
    }));

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toHaveValue('openai/gpt-4o');
    });
    expect(screen.queryByRole('option', { name: 'Claude Opus 4' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(4);
    expect(screen.queryByRole('option', { name: 'openai/gpt-4o-mini' })).not.toBeInTheDocument();
  });

  it('uses the current fallback list and default when the models API is unavailable', async () => {
    useAppStore.setState({ selectedModel: 'google/gemini-2.0-flash' as LLMModel });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toHaveValue('anthropic/claude-sonnet-5.5');
    });
    expect(screen.getAllByRole('option')).toHaveLength(4);
    expect(screen.queryByRole('option', { name: 'Gemini 2.0 Flash' })).not.toBeInTheDocument();
  });

  it('does not show fallback options when a reachable API has an empty catalog', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ available: true, default_model: null, models: [] }),
    }));

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('No callable models are configured');
    });
    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });

  it('honors the server availability flag even if model records are present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        available: false,
        default_model: null,
        models: CURRENT_MODELS,
      }),
    }));

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('No callable models are configured');
    });
    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });
});
