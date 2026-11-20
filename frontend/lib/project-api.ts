import { getJWT } from '@/lib/auth';
import type { ProjectExportSource } from '@/lib/project-export';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function fetchProjectSources(projectId: string): Promise<ProjectExportSource[]> {
  const token = await getJWT();
  const sources: ProjectExportSource[] = [];
  const limit = 200;
  let offset = 0;

  while (true) {
    const response = await fetch(
      `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/sources?limit=${limit}&offset=${offset}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!response.ok) {
      if (response.status === 401 && typeof window !== 'undefined') window.location.href = '/login';
      throw new Error(`Could not load project sources (${response.status})`);
    }
    const page = await response.json() as ProjectExportSource[];
    sources.push(...page);
    if (page.length < limit) return sources;
    offset += page.length;
  }
}
