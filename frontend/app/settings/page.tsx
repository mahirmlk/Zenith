'use client';

import { useState, useEffect } from 'react';
import { ModelSelector } from '@/components/ModelSelector';
import { useAppStore } from '@/store/useAppStore';
import { getJWT } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function SettingsPage() {
  const { selectedModel, userPrefs, setUserPrefs } = useAppStore();
  const [interests, setInterests] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const token = await getJWT();
      if (!token) return;
      try {
        const res = await fetch(`${API_BASE}/api/prefs`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setUserPrefs(data);
          if (data.interests) setInterests(data.interests.join(', '));
        }
      } catch {
        // ignore
      }
    }
    load();
  }, [setUserPrefs]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const token = await getJWT();
      const res = await fetch(`${API_BASE}/api/prefs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          preferred_model: selectedModel,
          interests: interests.split(',').map((s) => s.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        setMessage('Preferences saved.');
      } else {
        setMessage('Failed to save preferences.');
      }
    } catch {
      setMessage('Failed to save preferences.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Settings</h1>

      <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Preferences</h2>
          <ModelSelector />
        </div>

        <div className="border-t border-gray-100 pt-6">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Research Interests</h2>
          <p className="mb-3 text-sm text-gray-500">
            Comma-separated topics you are interested in.
          </p>
          <textarea
            value={interests}
            onChange={(e) => setInterests(e.target.value)}
            placeholder="e.g. diffusion models, NLP, reinforcement learning"
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            rows={3}
          />
        </div>

        {message && (
          <div className={`rounded-md p-3 text-sm ${message.includes('saved') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
            {message}
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Preferences'}
        </button>
      </div>
    </main>
  );
}
