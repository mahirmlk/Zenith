export interface ProjectExportProject {
  title: string;
  description?: string | null;
}

export interface ProjectExportPaper {
  id: string;
  title: string;
  authors?: string[];
  url?: string;
}

export interface ProjectExportNote {
  id: string;
  content: string;
  created_at?: string;
  source_id?: string | null;
}

export interface ProjectExportSource {
  id: string;
  paper_id: string;
  paper: ProjectExportPaper | null;
}

export type ExportFormat = 'md' | 'csv' | 'bib';

function csvCell(value: string): string {
  const formulaLike = /^[\s\u0000-\u001f\u007f-\u009f]*[=+\-@]/u.test(value);
  const spreadsheetSafe = formulaLike ? `'${value}` : value;
  return `"${spreadsheetSafe.replaceAll('"', '""')}"`;
}

function safeHttpUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

function bibValue(value: string): string {
  return value.replaceAll('\\', '\\\\').replace(/[{}%_$#&]/g, '\\$&').replace(/[\r\n]+/g, ' ');
}

export function buildProjectExport(
  format: ExportFormat,
  project: ProjectExportProject,
  sources: ProjectExportSource[],
  notes: ProjectExportNote[],
): string {
  if (format === 'md') {
    const paperList = sources.length
      ? sources.map(({ paper_id, paper }) => {
        const title = paper?.title ?? paper_id;
        const safeUrl = paper?.url ? safeHttpUrl(paper.url) : null;
        const escapedTitle = title.replaceAll('\\', '\\\\').replaceAll('[', '\\[').replaceAll(']', '\\]');
        const titleWithLink = safeUrl ? `[${escapedTitle}](<${safeUrl}>)` : escapedTitle;
        const authors = paper?.authors?.length ? ` — ${paper.authors.join(', ')}` : '';
        return `- ${titleWithLink} (${paper_id})${authors}`;
      }).join('\n')
      : '- No papers attached.';
    const noteList = notes.length
      ? notes.map((note) => `- ${note.content.replace(/\r?\n/g, '\n  ')}`).join('\n')
      : '- No notes.';
    return `# ${project.title}\n\n${project.description ?? ''}\n\n## Papers\n\n${paperList}\n\n## Notes\n\n${noteList}\n`;
  }

  if (format === 'csv') {
    const rows = [['kind', 'id', 'title', 'authors', 'url', 'content']];
    for (const { paper_id, paper } of sources) {
      rows.push(['paper', paper_id, paper?.title ?? '', paper?.authors?.join('; ') ?? '', paper?.url ?? '', '']);
    }
    for (const note of notes) rows.push(['note', note.id, '', '', '', note.content]);
    return rows.map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
  }

  return sources.map(({ paper_id, paper }) => {
    const key = `zenith_${paper_id.replace(/[^A-Za-z0-9_-]/g, '_')}`;
    const safeUrl = paper?.url ? safeHttpUrl(paper.url) : null;
    const fields = [
      `  title = {${bibValue(paper?.title ?? paper_id)}}`,
      ...(paper?.authors?.length ? [`  author = {${bibValue(paper.authors.join(' and '))}}`] : []),
      ...(safeUrl ? [`  url = {${bibValue(safeUrl)}}`] : []),
      `  note = {Zenith paper identifier: ${bibValue(paper_id)}}`,
    ];
    return `@misc{${key},\n${fields.join(',\n')}\n}`;
  }).join('\n\n') + (sources.length ? '\n' : '');
}
