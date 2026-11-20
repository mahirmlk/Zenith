import { getJWT } from '@/lib/auth';
import type {
  ProjectBrief,
  ProjectBriefCreateResponse,
  ProjectBriefSourceLocator,
  ProjectBriefVersion,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

class ProjectBriefApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ProjectBriefApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getJWT();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') window.location.href = '/login';
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based message when an error response is not JSON.
    }
    throw new ProjectBriefApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function fetchProjectBriefs(projectId: string): Promise<ProjectBrief[]> {
  return request<ProjectBrief[]>(`/api/projects/${encodeURIComponent(projectId)}/briefs`);
}

export function createProjectBrief(
  projectId: string,
  input: { title: string; content: string; source_snapshot: ProjectBriefSourceLocator[] },
): Promise<ProjectBriefCreateResponse> {
  return request<ProjectBriefCreateResponse>(`/api/projects/${encodeURIComponent(projectId)}/briefs`, {
    method: 'POST', body: JSON.stringify(input),
  });
}

export function fetchProjectBriefVersions(
  projectId: string,
  briefId: string,
): Promise<ProjectBriefVersion[]> {
  return request<ProjectBriefVersion[]>(
    `/api/projects/${encodeURIComponent(projectId)}/briefs/${encodeURIComponent(briefId)}/versions?limit=100&offset=0`,
  );
}

export function appendProjectBriefVersion(
  projectId: string,
  briefId: string,
  input: {
    expected_current_version: number;
    content: string;
    source_snapshot: ProjectBriefSourceLocator[];
  },
): Promise<ProjectBriefVersion> {
  return request<ProjectBriefVersion>(
    `/api/projects/${encodeURIComponent(projectId)}/briefs/${encodeURIComponent(briefId)}/versions`,
    { method: 'POST', body: JSON.stringify(input) },
  );
}

export { ProjectBriefApiError };
