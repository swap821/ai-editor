import { describe, it, expect } from 'vitest';
import { API_BASE } from './config';
import { AIOS_BASE } from './superbrain/lib/aiosAdapter';

describe('backend origin unification', () => {
  it('config.js and aiosAdapter.ts resolve to the same default origin', () => {
    // Both fall back to http://localhost:8000; vite.config.js also injects
    // NEXT_PUBLIC_AIOS_URL from VITE_API_BASE so an operator override applies
    // to both. This test catches the 127.0.0.1-vs-localhost drift if the build
    // shim ever stops bridging them.
    expect(AIOS_BASE).toBe(API_BASE);
  });
});
