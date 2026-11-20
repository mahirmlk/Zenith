'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { getJWT } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface Project {
  id: string;
  title: string;
  description?: string | null;
}

interface ReceivedInvitation {
  id: string;
  project_id: string;
  project_title: string;
  role: 'viewer' | 'editor';
  expires_at: string;
}

interface AcceptedInvitation {
  status: 'accepted';
  project_id: string;
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [receivedInvitations, setReceivedInvitations] = useState<ReceivedInvitation[]>([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [invitationError, setInvitationError] = useState<string | null>(null);
  const [acceptingInvitation, setAcceptingInvitation] = useState<string | null>(null);

  async function load() {
    const token = await getJWT();
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
    const [projectsResponse, invitationsResponse] = await Promise.all([
      fetch(`${API_BASE}/api/projects`, { headers }),
      fetch(`${API_BASE}/api/project-invitations/received`, { headers }),
    ]);
    if (projectsResponse.ok) setProjects(await projectsResponse.json());
    else setError(`Failed to load projects (${projectsResponse.status})`);
    if (invitationsResponse.ok) setReceivedInvitations(await invitationsResponse.json());
    else setInvitationError(`Could not load project invitations (${invitationsResponse.status}).`);
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

  async function acceptInvitation(invitation: ReceivedInvitation) {
    setInvitationError(null);
    setAcceptingInvitation(invitation.id);
    try {
      const token = await getJWT();
      if (!token) throw new Error('Sign in with the invited email address to accept this invitation.');
      const response = await fetch(
        `${API_BASE}/api/project-invitations/${encodeURIComponent(invitation.id)}/accept`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) {
        let detail = `Could not accept invitation (${response.status}).`;
        try {
          const body = await response.json() as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch { /* Keep the status-based message. */ }
        throw new Error(detail);
      }
      const result = await response.json() as AcceptedInvitation;
      if (result.status !== 'accepted' || result.project_id !== invitation.project_id) {
        throw new Error('The server returned an invalid invitation result. Refresh and try again.');
      }
      router.push(`/projects/${encodeURIComponent(result.project_id)}` as Route);
    } catch (acceptError) {
      setInvitationError(acceptError instanceof Error ? acceptError.message : 'Could not accept invitation.');
    } finally {
      setAcceptingInvitation(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Research Projects</h1>
      <section className="mb-8" aria-labelledby="received-invitations-heading">
        <h2 id="received-invitations-heading" className="mb-3 text-lg font-semibold">Project invitations</h2>
        {invitationError && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700" role="alert">{invitationError}</p>}
        {receivedInvitations.length > 0 ? (
          <ul className="space-y-2">
            {receivedInvitations.map((invitation) => (
              <li key={invitation.id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3">
                <div>
                  <p className="font-medium">{invitation.project_title}</p>
                  <p className="text-sm text-gray-600">Invited as {invitation.role}; expires {new Date(invitation.expires_at).toLocaleDateString()}.</p>
                </div>
                <button
                  type="button"
                  onClick={() => acceptInvitation(invitation)}
                  disabled={acceptingInvitation !== null}
                  className="rounded bg-black px-4 py-2 text-sm font-medium text-white disabled:cursor-wait disabled:opacity-60"
                  aria-label={`Accept invitation to ${invitation.project_title}`}
                >
                  {acceptingInvitation === invitation.id ? 'Accepting…' : 'Accept invitation'}
                </button>
              </li>
            ))}
          </ul>
        ) : !invitationError ? (
          <p className="text-sm text-gray-500">No pending invitations for your verified account email.</p>
        ) : null}
      </section>
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
            <Link href={`/projects/${encodeURIComponent(p.id)}` as Route} className="font-semibold underline-offset-4 hover:underline">
              {p.title}
            </Link>
            {p.description && <p className="text-sm text-gray-600">{p.description}</p>}
          </li>
        ))}
      </ul>
      {projects.length === 0 && !error && <p className="text-sm text-gray-500">No projects yet.</p>}
    </main>
  );
}
