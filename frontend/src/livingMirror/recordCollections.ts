import { isRecord } from './contracts';
import { redactProjection } from './redaction';

export function durableCollection(value: unknown, identity: string): Record<string, unknown>[] {
  if (!isRecord(value) || !Array.isArray(value.items) || value.source !== 'durable_repository'
    || !['available', 'empty'].includes(String(value.status)) || (value.status === 'empty') !== (value.items.length === 0)) throw new Error('Unsupported durable collection response.');
  return identifiedRecords(value.items, identity);
}
export function identifiedRecords(value: unknown, identity: string): Record<string, unknown>[] {
  if (!Array.isArray(value) || !value.every((item) => isRecord(item) && typeof item[identity] === 'string' && item[identity])) throw new Error(`Records lack ${identity} identity.`);
  if (new Set(value.map((item) => item[identity])).size !== value.length) throw new Error('Duplicate record identity.');
  return redactProjection(value) as Record<string, unknown>[];
}
export const textValue = (value: unknown): string => value == null ? 'Unavailable' : typeof value === 'string' ? value : JSON.stringify(value);
export const noRecords = (rows: unknown[]) => rows.length === 0;
