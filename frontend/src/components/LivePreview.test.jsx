import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import LivePreview from './LivePreview';

describe('LivePreview', () => {
  it('renders runtime error text without parsing it as HTML', () => {
    render(<LivePreview files={{ 'app.js': { content: "throw new Error('<img src=x>')" } }} />);

    const srcDoc = screen.getByTitle('Live Preview').getAttribute('srcdoc');
    expect(srcDoc).toContain('error.textContent');
    expect(srcDoc).not.toContain('insertAdjacentHTML');
  });

  it('blocks preview network egress and does not load a CDN', () => {
    render(<LivePreview files={{ 'index.html': { content: '<p>Hello</p>' } }} />);

    const srcDoc = screen.getByTitle('Live Preview').getAttribute('srcdoc');
    expect(srcDoc).toContain("connect-src 'none'");
    expect(srcDoc).toContain("default-src 'none'");
    expect(srcDoc).not.toContain('cdn.tailwindcss.com');
  });
});
