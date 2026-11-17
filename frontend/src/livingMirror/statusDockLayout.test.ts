import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';

// JSDOM has no layout, so the painted result was measured in Chrome on the
// face that ships (2026-11-17): at 1262x624, 1280x720 and 1440x900 in Guided,
// the status pills wrapped to a second row and ran 30px under the rest dock's
// mic, mute, language and Send. This pins the rule that ends the dock above
// the status band's real top, and its fallback guard.
const sheet = readFileSync('src/livingMirror/livingMirror.css', 'utf8').replace(/\r\n/g, '\n');

it('ends the rest dock above the status band where anchor positioning exists', () => {
  const block = sheet.slice(sheet.indexOf('@supports (anchor-name: --lm-status-band)'));
  expect(block.length).toBeGreaterThan(0);
  const guarded = block.slice(0, block.indexOf('\n}\n') + 3);
  expect(guarded).toContain('@media (min-width: 1200px) and (min-height: 521px)');
  expect(guarded).toMatch(/\.lm-app \.gagos-status \{ anchor-name: --lm-status-band; \}/);
  expect(guarded).toMatch(
    /\.lm-app\[data-working="false"\]:not\(:has\(\.gagos-chrome\[data-approval-pending="true"\], \.gagos-approval-hold\)\) \.gagos-chat \{\s*bottom: calc\(anchor\(--lm-status-band top\) \+ 12px\);/,
  );
});

it('keeps the reserved single status row as the fallback outside the guard', () => {
  const before = sheet.slice(0, sheet.indexOf('@supports (anchor-name: --lm-status-band)'));
  expect(before).toContain('bottom: calc(18px + var(--lm-desktop-connection-slot) + 12px + 40px + 12px);');
});
