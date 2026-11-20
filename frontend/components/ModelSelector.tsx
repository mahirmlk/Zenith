'use client';

import { useEffect, useState } from 'react';
import { LLMModel } from '@/types';
import { useAppStore } from '@/store/useAppStore';
import { getJWT } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// Fallback labels only — the source of truth is GET /api/models
// (backend MODEL_REGISTRY, update.md §14). Static list kept so the
// selector still renders when the API is unreachable.
const FALLBACK_MODELS: { value: string; label: string }[] = [
  { value: 'anthropic/claude-opus-5.5', label: 'Claude Opus 5.5' },
  { value: 'anthropic/claude-sonnet-5.5', label: 'Claude Sonnet 5.5' },
  { value: 'openai/gpt-4o', label: 'GPT-4o' },
  { value: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
];

const DEFAULT_MODEL: LLMModel = 'anthropic/claude-sonnet-5.5';

export function ModelSelector() {
  const { selectedModel, setSelectedModel } = useAppStore();
  const [models, setModels] = useState<{ value: string; label: string }[]>([]);
  const [defaultModel, setDefaultModel] = useState<LLMModel | null>(null);
  const [catalogState, setCatalogState] = useState<'loading' | 'available' | 'fallback' | 'unavailable'>('loading');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let token: string | null;
      try {
        token = await getJWT();
      } catch {
        if (!cancelled) setCatalogState('unavailable');
        return;
      }

      let response: Response;
      try {
        response = await fetch(`${API_BASE}/api/models`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } catch {
        // Keep the selector usable during a network outage. The API remains
        // authoritative whenever it responds successfully.
        if (!cancelled) {
          setModels(FALLBACK_MODELS);
          setDefaultModel(DEFAULT_MODEL);
          setCatalogState('fallback');
        }
        return;
      }

      if (!response.ok) {
        if (!cancelled) setCatalogState('unavailable');
        return;
      }

      try {
        const data = await response.json();
        if (cancelled) return;
        if (data?.available !== true || !Array.isArray(data.models)) {
          setCatalogState('unavailable');
          return;
        }

        const availableModels = data.models
          .filter((model: unknown): model is { id: string; agents: string[] } => (
            typeof model === 'object'
            && model !== null
            && 'id' in model
            && typeof model.id === 'string'
            && 'agents' in model
            && Array.isArray(model.agents)
            && model.agents.includes('summary_default')
          ))
          .map((model: { id: string; agents: string[] }) => ({
            value: model.id,
            label: FALLBACK_MODELS.find((known) => known.value === model.id)?.label ?? model.id,
          }));
        const serverDefault = typeof data.default_model === 'string'
          && availableModels.some((model: { value: string }) => model.value === data.default_model)
          ? data.default_model
          : null;

        if (availableModels.length === 0 || serverDefault === null) {
          setCatalogState('unavailable');
          return;
        }

        setModels(availableModels);
        setDefaultModel(serverDefault as LLMModel);
        setCatalogState('available');
      } catch {
        // A reachable API with an invalid response is unavailable, not offline.
        if (!cancelled) setCatalogState('unavailable');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if ((catalogState !== 'available' && catalogState !== 'fallback') || defaultModel === null) return;
    if (!models.some((model) => model.value === selectedModel)) {
      setSelectedModel(defaultModel);
    }
  }, [catalogState, defaultModel, models, selectedModel, setSelectedModel]);

  const isUnavailable = catalogState === 'unavailable';
  const isLoading = catalogState === 'loading';
  const selectedValue = models.some((model) => model.value === selectedModel) ? selectedModel : '';

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="model-select" className="text-[13px] font-semibold text-ink-900">
        Model
      </label>
      <select
        id="model-select"
        value={selectedValue}
        disabled={isLoading || isUnavailable || models.length === 0}
        onChange={(e) => setSelectedModel(e.target.value as LLMModel)}
        className="rounded-lg border border-zenith-border bg-white px-3 py-1.5 text-[13px] text-ink-900 shadow-soft focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
      >
        {isLoading && <option value="">Loading available models…</option>}
        {models.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
      {isUnavailable && (
        <span role="status" className="text-xs text-ink-600">
          No callable models are configured. Check provider and spend-budget configuration.
        </span>
      )}
      {catalogState === 'fallback' && (
        <span role="status" className="text-xs text-ink-600">
          Model catalog is unreachable; showing built-in choices.
        </span>
      )}
    </div>
  );
}
