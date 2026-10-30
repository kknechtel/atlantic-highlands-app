"use client";

import Link from "next/link";
import type { Overview, OverviewFinances, OverviewMeeting } from "@/lib/api";
import { fmtChange, fmtDay, fmtMoney } from "@/lib/money";
import {
  CalendarDaysIcon, DocumentTextIcon, MicrophoneIcon, BanknotesIcon,
} from "@heroicons/react/24/outline";

export function Section({ title, icon: Icon, action, children }: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
          <Icon className="w-4 h-4" /> {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-gray-400">{children}</p>;
}

const OUTCOME_STYLES: Record<string, string> = {
  adopted: "bg-green-50 text-green-700 border-green-200",
  introduced: "bg-blue-50 text-blue-700 border-blue-200",
  tabled: "bg-gray-50 text-gray-600 border-gray-200",
};

export function OutcomeChip({ outcome }: { outcome: string | null }) {
  if (!outcome) return null;
  const cls = OUTCOME_STYLES[outcome.toLowerCase()] ?? "bg-gray-50 text-gray-600 border-gray-200";
  return <span className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded border ${cls}`}>{outcome}</span>;
}

export function MeetingCard({ m, detailed = false }: { m: OverviewMeeting; detailed?: boolean }) {
  const decisions = detailed ? m.decisions : m.decisions.slice(0, 2);
  return (
    <Link href={`/meetings/${m.id}`} className="block rounded-lg border border-gray-200 p-3 hover:border-gray-300 hover:bg-gray-50 transition-colors">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-gray-900">{m.body}</span>
        <span className="text-xs text-gray-500 flex-shrink-0">{fmtDay(m.date)}</span>
      </div>
      {m.tldr ? (
        <p className={`text-sm text-gray-700 mt-1 ${detailed ? "" : "line-clamp-3"}`}>{m.tldr}</p>
      ) : (
        <p className="text-xs text-gray-400 mt-1">No summary yet — open to transcribe and summarize.</p>
      )}
      {decisions.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {decisions.map((d, i) => (
            <li key={i} className="text-xs text-gray-600 flex gap-1.5">
              <span className="text-gray-400">•</span>
              <span>{d.description}{d.vote && <span className="text-gray-400"> ({d.vote})</span>}</span>
            </li>
          ))}
        </ul>
      )}
    </Link>
  );
}

export function MeetingList({ meetings, limit, detailed }: { meetings: OverviewMeeting[]; limit: number; detailed?: boolean }) {
  return (
    <Section title="Latest meetings" icon={MicrophoneIcon}
      action={<Link href="/meetings" className="text-xs text-gray-500 hover:text-gray-700">All meetings →</Link>}>
      {meetings.length === 0 ? <Empty>No meeting recordings yet.</Empty> : (
        <div className="space-y-2">
          {meetings.slice(0, limit).map((m) => <MeetingCard key={m.id} m={m} detailed={detailed} />)}
        </div>
      )}
    </Section>
  );
}

export function UpcomingList({ events, limit, emptyText }: { events: Overview["upcoming"]; limit: number; emptyText: string }) {
  return (
    <Section title="Coming up" icon={CalendarDaysIcon}
      action={<Link href="/calendar" className="text-xs text-gray-500 hover:text-gray-700">Calendar →</Link>}>
      {events.length === 0 ? <Empty>{emptyText}</Empty> : (
        <ul className="divide-y divide-gray-100">
          {events.slice(0, limit).map((e) => (
            <li key={e.id} className="py-1.5 flex gap-3 text-sm">
              <span className="w-14 flex-shrink-0 text-xs font-medium text-gray-500 pt-0.5">{fmtDay(e.date)}</span>
              <span className="min-w-0">
                <span className="text-gray-900">{e.title}</span>
                {e.time && <span className="text-xs text-gray-500"> · {e.time}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function DocumentList({ docs, limit }: { docs: Overview["documents"]; limit: number }) {
  return (
    <Section title="New documents" icon={DocumentTextIcon}
      action={<Link href="/document-library" className="text-xs text-gray-500 hover:text-gray-700">Library →</Link>}>
      {docs.length === 0 ? <Empty>Nothing new.</Empty> : (
        <ul className="divide-y divide-gray-100">
          {docs.slice(0, limit).map((d) => (
            <li key={d.id}>
              <Link href={`/document-library?doc=${encodeURIComponent(d.id)}`}
                className="flex items-baseline justify-between gap-3 py-1.5 text-sm hover:text-gray-900 text-gray-700">
                <span className="truncate">{d.title}</span>
                <span className="text-[11px] text-gray-400 flex-shrink-0">{fmtDay(d.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** Minimal SVG trend line; no axes — the numbers sit next to it. */
export function Sparkline({ values, className = "text-gray-400" }: { values: (number | null)[]; className?: string }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (pts.length < 2) return null;
  const ys = pts.map((p) => p[1]);
  const min = Math.min(...ys), max = Math.max(...ys);
  const w = 80, h = 24, n = values.length - 1;
  const d = pts.map(([i, v], k) =>
    `${k ? "L" : "M"}${((i / n) * w).toFixed(1)},${(h - 2 - ((v - min) / (max - min || 1)) * (h - 4)).toFixed(1)}`,
  ).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={`w-20 h-6 ${className}`} aria-hidden>
      <path d={d} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export const RESERVE_STYLES: Record<string, { dot: string; label: string }> = {
  ok: { dot: "bg-green-500", label: "At or above 8% target" },
  watch: { dot: "bg-amber-500", label: "Below 8% target" },
  low: { dot: "bg-red-500", label: "Below 5%" },
};

export function MoneyGlance({ fin, entity }: { fin: OverviewFinances; entity: "town" | "school" }) {
  const latest = fin.latest;
  return (
    <Section title={latest ? `Money at a glance · FY ${latest.fiscal_year}` : "Money at a glance"} icon={BanknotesIcon}
      action={<Link href={`/financial-analysis?entity=${entity}`} className="text-xs text-gray-500 hover:text-gray-700">Finances →</Link>}>
      {!latest ? <Empty>No financial statements extracted yet.</Empty> : (
        <div className="space-y-2">
          {fin.headline.text && <p className="text-sm text-gray-700">{fin.headline.text}</p>}
          <dl className="grid grid-cols-3 gap-2">
            <GlanceStat label={latest.kind === "budget" ? "Spending (budget)" : "Spending"}
              value={fmtMoney(latest.expenditures)} change={fin.changes?.expenditures}
              spark={fin.years.map((y) => y.expenditures)} />
            <GlanceStat label="Reserves"
              value={fin.reserves ? `${fin.reserves.pct.toFixed(1)}%` : "—"}
              sub={fin.reserves ? "of spending" : undefined}
              dot={fin.reserves?.status ? RESERVE_STYLES[fin.reserves.status] : undefined} />
            <GlanceStat label="Debt" value={fmtMoney(latest.debt)} change={fin.changes?.debt}
              spark={fin.years.map((y) => y.debt)} />
          </dl>
        </div>
      )}
    </Section>
  );
}

function GlanceStat({ label, value, change, sub, spark, dot }: {
  label: string; value: string; change?: number | null; sub?: string;
  spark?: (number | null)[]; dot?: { dot: string; label: string };
}) {
  return (
    <div className="rounded-lg bg-gray-50 p-2.5">
      <dt className="text-[10px] uppercase font-semibold tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-0.5 flex items-center gap-1.5">
        {dot && <span className={`w-2 h-2 rounded-full ${dot.dot}`} title={dot.label} />}
        <span className="text-base font-semibold text-gray-900">{value}</span>
      </dd>
      <div className="text-[11px] text-gray-500">{sub ?? (change != null ? `${fmtChange(change)} vs prior yr` : " ")}</div>
      {spark && <Sparkline values={spark} />}
    </div>
  );
}
