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
  { value: 'anthropic/claude-opus-4', label: 'Claude Opus 4' },
  { value: 'anthropic/claude-sonnet-4-5', label: 'Claude Sonnet 4.5' },
  { value: 'openai/gpt-4o', label: 'GPT-4o' },
  { value: 'openai/gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'google/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'google/gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  { value: 'mistralai/mistral-large', label: 'Mistral Large' },
  { value: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
  { value: 'deepseek/deepseek-r1', label: 'DeepSeek R1' },
];

export function ModelSelector() {
  const { selectedModel, setSelectedModel } = useAppStore();
  const [models, setModels] = useState<{ value: string; label: string }[]>(FALLBACK_MODELS);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getJWT();
        const res = await fetch(`${API_BASE}/api/models`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data.models)) {
          setModels(data.models.map((m: { id: string }) => ({ value: m.id, label: m.id })));
        }
      } catch {
        /* keep fallback list */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="model-select" className="text-[13px] font-semibold text-ink-900">
        Model
      </label>
      <select
        id="model-select"
        value={selectedModel}
        onChange={(e) => setSelectedModel(e.target.value as LLMModel)}
        className="rounded-lg border border-zenith-border bg-white px-3 py-1.5 text-[13px] text-ink-900 shadow-soft focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30 transition duration-200"
      >
        {models.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}
