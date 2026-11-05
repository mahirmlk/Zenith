'use client';

import { useEffect, useState } from 'react';
import { getJWT } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface Project {
  id: string;
  title: string;
  description?: string | null;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const token = await getJWT();
    const res = await fetch(`${API_BASE}/api/projects`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) setProjects(await res.json());
    else setError(`Failed to load projects (${res.status})`);
  }

  useEffect(() => {
    load().catch(() => setError('Failed to load projects'));
  }, []);

  async function create() {
    if (!title.trim()) return;
    const token = await getJWT();
    const res = await fetch(`${API_BASE}/api/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ title }),
    });
    if (res.ok) {
      setTitle('');
      await load();
    } else {
      setError(`Failed to create project (${res.status})`);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Research Projects</h1>
      {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <div className="mb-6 flex gap-2">
        <input
          aria-label="Project title"
          className="flex-1 rounded border px-3 py-2"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="New project title"
        />
        <button className="rounded bg-black px-4 py-2 text-white" onClick={create}>
          Create
        </button>
      </div>
      <ul className="space-y-2">
        {projects.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <strong>{p.title}</strong>
            {p.description && <p className="text-sm text-gray-600">{p.description}</p>}
          </li>
        ))}
      </ul>
      {projects.length === 0 && !error && <p className="text-sm text-gray-500">No projects yet.</p>}
    </main>
  );
}
