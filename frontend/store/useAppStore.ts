import { create } from 'zustand';
import { LLMModel, UserPrefs } from '@/types';

interface AppState {
  selectedModel: LLMModel;
  setSelectedModel: (model: LLMModel) => void;
  userPrefs: UserPrefs | null;
  setUserPrefs: (prefs: UserPrefs) => void;
  isSearchLoading: boolean;
  setIsSearchLoading: (loading: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedModel: 'anthropic/claude-sonnet-4-5',
  setSelectedModel: (model) => set({ selectedModel: model }),
  userPrefs: null,
  setUserPrefs: (prefs) => set({ userPrefs: prefs }),
  isSearchLoading: false,
  setIsSearchLoading: (loading) => set({ isSearchLoading: loading }),
}));
