import { describe, it, expect } from 'vitest';
import { fromEnvelope, displayValue, MetricEnvelope } from './measuredState';

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
        { _status: 'measured', value: 'hello', envelope: {} as any },
        'fallback',
        (v) => v.toUpperCase()
      )).toBe('HELLO');
    });
  });
});
