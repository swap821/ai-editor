/** Defense in depth for generic projection/history/scene data; never a credential store. */
export function redactProjection(value: unknown, depth = 0): unknown {
  if (depth > 16) return '[nested data omitted]';
  if (Array.isArray(value)) return value.slice(0, 256).map((item) => redactProjection(item, depth + 1));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    /^(?:token|approval_?token|access_?token|refresh_?token|api_?key|secret|password|authorization|cookie|capability_?token)$/i.test(key)
      ? '[withheld]' : redactProjection(item, depth + 1)]));
  return value;
}
