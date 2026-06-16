import { describe, expect, it } from 'vitest';
import { formatMaterializedTextPreview } from './materializedTextPreview';

describe('formatMaterializedTextPreview', () => {
  it('clamps the preview to the configured line budget and reports hidden lines', () => {
    const preview = formatMaterializedTextPreview('a\nb\nc\nd', { maxLines: 3, maxCharsPerLine: 12 });
    expect(preview.lines).toEqual(['a', 'b', 'c']);
    expect(preview.hiddenLines).toBe(1);
    expect(preview.totalLines).toBe(4);
  });

  it('expands indentation and truncates overlong lines', () => {
    const preview = formatMaterializedTextPreview('\treturn veryLongIdentifierName();', {
      maxLines: 4,
      maxCharsPerLine: 12,
    });
    expect(preview.lines[0]).toBe('\u00A0\u00A0return\u00A0ve\u2026');
  });

  it('drops trailing blank lines from the visible count', () => {
    const preview = formatMaterializedTextPreview('alpha\nbeta\n\n', { maxLines: 4, maxCharsPerLine: 20 });
    expect(preview.lines).toEqual(['alpha', 'beta']);
    expect(preview.hiddenLines).toBe(0);
    expect(preview.totalLines).toBe(2);
  });
});
