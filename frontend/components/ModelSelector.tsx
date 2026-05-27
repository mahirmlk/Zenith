'use client';

import { LLMModel } from '@/types';
import { useAppStore } from '@/store/useAppStore';

const MODELS: { value: LLMModel; label: string }[] = [
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

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="model-select" className="text-sm font-medium text-gray-700">
        Model
      </label>
      <select
        id="model-select"
        value={selectedModel}
        onChange={(e) => setSelectedModel(e.target.value as LLMModel)}
        className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
      >
        {MODELS.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}
