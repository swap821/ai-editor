export interface MaterializedTextPreview {
  lines: string[];
  hiddenLines: number;
  totalLines: number;
}

export interface MaterializedTextPreviewOptions {
  maxLines?: number;
  maxCharsPerLine?: number;
}

const NBSP = '\u00A0';
const ELLIPSIS = '\u2026';

function normalizePreviewLine(line: string, maxCharsPerLine: number): string {
  const expanded = String(line).replace(/\t/g, '  ');
  const clipped =
    expanded.length > maxCharsPerLine
      ? `${expanded.slice(0, Math.max(1, maxCharsPerLine - 1))}${ELLIPSIS}`
      : expanded;
  return clipped.replace(/ /g, NBSP);
}

export function formatMaterializedTextPreview(
  text: string,
  options: MaterializedTextPreviewOptions = {},
): MaterializedTextPreview {
  const maxLines = Math.max(1, options.maxLines ?? 24);
  const maxCharsPerLine = Math.max(8, options.maxCharsPerLine ?? 56);
  const normalized = String(text ?? '').replace(/\r\n?/g, '\n');
  const rawLines = normalized.split('\n');

  while (rawLines.length > 0 && rawLines[rawLines.length - 1] === '') {
    rawLines.pop();
  }

  const totalLines = rawLines.length;
  const lines = rawLines
    .slice(0, maxLines)
    .map((line) => normalizePreviewLine(line, maxCharsPerLine));

  return {
    lines,
    hiddenLines: Math.max(0, totalLines - lines.length),
    totalLines,
  };
}
