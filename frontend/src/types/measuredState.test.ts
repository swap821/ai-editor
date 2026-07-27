import { describe, it, expect } from 'vitest';
import { fromEnvelope, displayValue, booleanTone, isMeasured, MetricEnvelope } from './measuredState';

/** A real, typed envelope. Using `{} as any` here is what pushed the repo's
 * eslint warning budget over its limit -- and a test for a type-safety helper
 * should not be the thing reaching for `any`. */
function env<T>(value: T, status: MetricEnvelope<T>['status'] = 'measured'): MetricEnvelope<T> {
  return { value, status, measured_at: null, source: 'test', freshness: null };
}

describe('measuredState', () => {
  describe('fromEnvelope', () => {
    it('returns loading when envelope is null or undefined', () => {
      expect(fromEnvelope(null)).toEqual({ _status: 'loading' });
      expect(fromEnvelope(undefined)).toEqual({ _status: 'loading' });
    });

    it('returns unavailable when envelope status is unavailable', () => {
      const env: MetricEnvelope<string> = {
        status: 'unavailable',
        value: null,
        measured_at: null,
        source: 'test',
        freshness: null
      };
      expect(fromEnvelope(env)).toEqual({ _status: 'unavailable', envelope: env });
    });

    it('returns unavailable when value is null even if status is measured', () => {
      const env: MetricEnvelope<string> = {
        status: 'measured',
        value: null,
        measured_at: '2024-01-01',
        source: 'test',
        freshness: 0
      };
      expect(fromEnvelope(env)).toEqual({ _status: 'unavailable', envelope: env });
    });

    it('returns measured state with value when status is measured', () => {
      const env: MetricEnvelope<string> = {
        status: 'measured',
        value: 'active',
        measured_at: '2024-01-01',
        source: 'test',
        freshness: 0
      };
      expect(fromEnvelope(env)).toEqual({ _status: 'measured', value: 'active', envelope: env });
    });

    it('returns stale state with value when status is stale', () => {
      const env: MetricEnvelope<number> = {
        status: 'stale',
        value: 42,
        measured_at: '2024-01-01',
        source: 'test',
        freshness: 1000
      };
      expect(fromEnvelope(env)).toEqual({ _status: 'stale', value: 42, envelope: env });
    });

    it('falls back to unavailable for unknown status', () => {
      const env = {
        status: 'unknown_status' as any,
        value: 'test',
        measured_at: '2024-01-01',
        source: 'test',
        freshness: 0
      };
      expect(fromEnvelope(env)).toEqual({ _status: 'unavailable', envelope: env });
    });
  });

  describe('displayValue', () => {
    it('renders loading text', () => {
      expect(displayValue({ _status: 'loading' })).toBe('loading');
    });

    it('renders unavailable fallback', () => {
      expect(displayValue({ _status: 'unavailable', envelope: {} as any }, 'fallback-value')).toBe('fallback-value');
    });

    it('renders actual value', () => {
      expect(displayValue({ _status: 'measured', value: 123, envelope: {} as any })).toBe('123');
    });

    it('uses custom formatter', () => {
      expect(displayValue(
        { _status: 'measured', value: 'hello', envelope: env('') },
        'fallback',
        (v) => v.toUpperCase()
      )).toBe('HELLO');
    });

    // The distinction MetricStatus exists to draw has to survive rendering.
    // Without these, a simulated reading appeared on screen character-for-
    // character identical to a measured one.
    it('marks a simulated reading so it cannot pass as measured', () => {
      expect(displayValue({ _status: 'simulated', value: 42, envelope: env(0) })).toBe('42 (simulated)');
    });

    it('marks a stale reading', () => {
      expect(displayValue({ _status: 'stale', value: 42, envelope: env(0) })).toBe('42 (stale)');
    });

    it('marks a derived reading', () => {
      expect(displayValue({ _status: 'derived', value: 42, envelope: env(0) })).toBe('42 (derived)');
    });

    it('leaves a measured reading unqualified', () => {
      expect(displayValue({ _status: 'measured', value: 42, envelope: env(0) })).toBe('42');
    });

    it('still qualifies a formatted value', () => {
      expect(displayValue(
        { _status: 'simulated', value: 0.5, envelope: env(0) },
        'fallback',
        (v) => `${v * 100}%`,
      )).toBe('50% (simulated)');
    });
  });

  describe('isMeasured', () => {
    it('is true only for a measured reading', () => {
      expect(isMeasured({ _status: 'measured', value: 1, envelope: env(0) })).toBe(true);
      expect(isMeasured({ _status: 'loading' })).toBe(false);
      expect(isMeasured({ _status: 'unavailable', envelope: env(0) })).toBe(false);
      expect(isMeasured({ _status: 'stale', value: 1, envelope: env(0) })).toBe(false);
      expect(isMeasured({ _status: 'simulated', value: 1, envelope: env(0) })).toBe(false);
    });
  });

  describe('booleanTone', () => {
    const tones = { whenTrue: 'ok', whenFalse: 'danger', whenUnknown: 'warn' };

    it('distinguishes a measured false from an unknown', () => {
      expect(booleanTone({ _status: 'measured', value: false, envelope: env(false) }, tones)).toBe('danger');
      expect(booleanTone({ _status: 'unavailable', envelope: env(0) }, tones)).toBe('warn');
      expect(booleanTone({ _status: 'loading' }, tones)).toBe('warn');
    });

    it('reports a measured true', () => {
      expect(booleanTone({ _status: 'measured', value: true, envelope: env(false) }, tones)).toBe('ok');
    });

    // The regression this whole helper exists to stop: `envelope?.value ? a : b`
    // maps BOTH "measured false" and "unknown" onto the same branch, so an
    // unmeasured reading gets a confident colour it never earned.
    it('never reports unknown as either a healthy or a failing verdict', () => {
      const unknown = booleanTone({ _status: 'unavailable', envelope: env(0) }, tones);
      expect(unknown).not.toBe('ok');
      expect(unknown).not.toBe('danger');
    });
  });
});
