/** "$12.3M", "$850K", "$400" — what residents read. Full dollars belong in line-item tables. */
export function fmtMoney(n: number | null | undefined): string {
  if (n == null) return "—";
  const a = Math.abs(n);
  const s = a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${(a / 1e3).toFixed(0)}K` : `$${a.toFixed(0)}`;
  return n < 0 ? `-${s}` : s;
}

/** "+4.0%" / "-2.1%", or "" when there's nothing to compare against. */
export function fmtChange(pct: number | null | undefined): string {
  if (pct == null) return "";
  return `${pct >= 0 ? "+" : "-"}${Math.abs(pct).toFixed(1)}%`;
}

/** "Oct 22" (this year) or "Oct 22, 2025". Takes YYYY-MM-DD without shifting time zones. */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString(undefined, {
    month: "short", day: "numeric",
    ...(y !== new Date().getFullYear() ? { year: "numeric" } : {}),
  });
}
