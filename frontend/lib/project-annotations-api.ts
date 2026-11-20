import { getJWT } from '@/lib/auth';
import type { ProjectAnnotation, ProjectAnnotationAnchor } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function fetchProjectAnnotations(projectId: string): Promise<ProjectAnnotation[]> {
  return request<ProjectAnnotation[]>(`/api/projects/${encodeURIComponent(projectId)}/annotations`);
}

export function createProjectAnnotation(
  projectId: string,
  anchor: ProjectAnnotationAnchor,
  content: string,
): Promise<ProjectAnnotation> {
  return request<ProjectAnnotation>(`/api/projects/${encodeURIComponent(projectId)}/annotations`, {
    method: 'POST',
    body: JSON.stringify({ ...anchor, content }),
  });
}

export function updateProjectAnnotation(
  projectId: string,
  annotationId: string,
  content: string,
): Promise<ProjectAnnotation> {
  return request<ProjectAnnotation>(
    `/api/projects/${encodeURIComponent(projectId)}/annotations/${encodeURIComponent(annotationId)}`,
    { method: 'PATCH', body: JSON.stringify({ content }) },
  );
}

export function deleteProjectAnnotation(
  projectId: string,
  annotationId: string,
): Promise<{ status: 'ok' }> {
  return request<{ status: 'ok' }>(
    `/api/projects/${encodeURIComponent(projectId)}/annotations/${encodeURIComponent(annotationId)}`,
    { method: 'DELETE' },
  );
}
