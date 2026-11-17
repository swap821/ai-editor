import { describe, expect, it } from 'vitest';
import { UNAVAILABLE_STATE, parseBootstrapReadiness } from './bootstrapReadinessParse';

const validCheck = {
  name: 'docker',
  passed: true,
  required: true,
  message: 'Docker is running',
};

describe('UNAVAILABLE_STATE', () => {
  it('is an unavailable state with the untrusted-endpoint summary and no checks', () => {
    expect(UNAVAILABLE_STATE).toEqual({
      state: 'unavailable',
      summary: 'The local setup endpoint did not answer with a trustworthy status.',
      checks: [],
    });
  });
});

describe('parseBootstrapReadiness', () => {
  it('returns a ready state with copied checks when ok is true', () => {
    expect(
      parseBootstrapReadiness({ ok: true, summary: 'All good', checks: [validCheck] }),
    ).toEqual({
      state: 'ready',
      summary: 'All good',
      checks: [validCheck],
    });
  });

  it('returns a blocked state when ok is false', () => {
    const result = parseBootstrapReadiness({
      ok: false,
      summary: 'Needs work',
      checks: [{ ...validCheck, passed: false }],
    });

    expect(result.state).toBe('blocked');
    expect(result.summary).toBe('Needs work');
    expect(result.checks).toEqual([{ ...validCheck, passed: false }]);
  });

  it('returns a ready state with an empty checks list when checks is empty', () => {
    expect(parseBootstrapReadiness({ ok: true, summary: 'Nothing to check', checks: [] })).toEqual({
      state: 'ready',
      summary: 'Nothing to check',
      checks: [],
    });
  });

  it('drops unknown properties from the top level and from each check', () => {
    const result = parseBootstrapReadiness({
      ok: true,
      summary: 'Extra fields',
      extra: 'ignored',
      checks: [{ ...validCheck, detail: 'ignored too' }],
    });

    expect(result).toEqual({
      state: 'ready',
      summary: 'Extra fields',
      checks: [validCheck],
    });
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['a string', 'ready'],
    ['a number', 42],
    ['an array', [validCheck]],
  ])('returns the unavailable state for %s', (_label, input) => {
    expect(parseBootstrapReadiness(input)).toBe(UNAVAILABLE_STATE);
  });

  it('returns the unavailable state when ok is not a boolean', () => {
    expect(parseBootstrapReadiness({ ok: 'true', summary: 'x', checks: [] })).toBe(UNAVAILABLE_STATE);
  });

  it('returns the unavailable state when summary is not a string', () => {
    expect(parseBootstrapReadiness({ ok: true, summary: 5, checks: [] })).toBe(UNAVAILABLE_STATE);
  });

  it('returns the unavailable state when checks is not an array', () => {
    expect(parseBootstrapReadiness({ ok: true, summary: 'x', checks: {} })).toBe(UNAVAILABLE_STATE);
  });

  it.each([
    ['name', { ...validCheck, name: 1 }],
    ['passed', { ...validCheck, passed: 'yes' }],
    ['required', { ...validCheck, required: null }],
    ['message', { ...validCheck, message: undefined }],
    ['the check itself', 'not-a-check'],
  ])('returns the unavailable state when a check has an invalid %s', (_label, badCheck) => {
    expect(parseBootstrapReadiness({ ok: true, summary: 'x', checks: [validCheck, badCheck] })).toBe(
      UNAVAILABLE_STATE,
    );
  });
});
