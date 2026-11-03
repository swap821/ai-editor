import { describe, expect, it } from 'vitest';
import { redactProjection } from './redaction';

describe('redactProjection', () => {
  it('withholds sensitive keys case-insensitively and in snake or camel form, keeping others', () => {
    const input = {
      token: 'a',
      Approval_Token: 'b',
      accessToken: 'c',
      refresh_token: 'd',
      API_KEY: 'e',
      apiKey: 'f',
      secret: 'g',
      Password: 'h',
      authorization: 'i',
      cookie: 'j',
      capabilityToken: 'k',
      name: 'visible',
      count: 3,
    };
    const out = redactProjection(input) as Record<string, unknown>;
    for (const key of Object.keys(input)) {
      if (key === 'name' || key === 'count') continue;
      expect(out[key]).toBe('[withheld]');
    }
    expect(out.name).toBe('visible');
    expect(out.count).toBe(3);
  });

  it('only matches whole key names and redacts nested objects and arrays', () => {
    const out = redactProjection({
      tokenizer: 'keep',
      items: [{ password: 'x', id: 1 }, { nested: { secret: 'y', ok: true } }],
    });
    expect(out).toEqual({
      tokenizer: 'keep',
      items: [{ password: '[withheld]', id: 1 }, { nested: { secret: '[withheld]', ok: true } }],
    });
  });

  it('returns primitives and null unchanged without mutating the input', () => {
    expect(redactProjection('text')).toBe('text');
    expect(redactProjection(null)).toBeNull();
    expect(redactProjection(undefined)).toBeUndefined();
    const input = { token: 'abc', list: [1, 2] };
    redactProjection(input);
    expect(input).toEqual({ token: 'abc', list: [1, 2] });
  });

  it('truncates arrays to 256 items', () => {
    const out = redactProjection(Array.from({ length: 300 }, (_, i) => i)) as number[];
    expect(out).toHaveLength(256);
    expect(out[255]).toBe(255);
  });

  it('omits data nested deeper than 16 levels', () => {
    let deep: unknown = { leaf: 'x' };
    for (let i = 0; i < 20; i++) deep = { child: deep };
    let cursor = redactProjection(deep) as Record<string, unknown>;
    for (let i = 0; i < 16; i++) cursor = cursor.child as Record<string, unknown>;
    expect(cursor.child).toBe('[nested data omitted]');
    expect(redactProjection({ a: 1 }, 17)).toBe('[nested data omitted]');
  });
});
