/* ─── ORGANS · SHARED FORMATTERS ───────────────────────────────────────────────
   Tiny pure helpers shared by every organ port so the five ports format text,
   dates and numbers identically (no per-port drift). Lifted verbatim from
   CurriculumPort/AutonomyLedgerPort — behavior unchanged, just deduplicated.
   ──────────────────────────────────────────────────────────────────────────── */

/** Clamp a string to `n` chars with an ellipsis (the curriculum/proposals body). */
export const truncate = (s, n) => {
  const str = String(s || '');
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
};

/** ISO-ish timestamp → YYYY-MM-DD (tolerant of the backend's "YYYY-MM-DD HH:MM:SS"). */
export const fmtDate = (iso) => {
  if (!iso) return '';
  const d = new Date(String(iso).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toISOString().slice(0, 10);
};
