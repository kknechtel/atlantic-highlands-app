"use client";

import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getDocumentViewUrl, type OverviewEntity, type OverviewFinances } from "@/lib/api";
import { fmtChange, fmtMoney } from "@/lib/money";
import { RESERVE_STYLES } from "./OverviewParts";
import { ExclamationTriangleIcon, InformationCircleIcon, DocumentTextIcon } from "@heroicons/react/24/outline";

// Reference categorical slots 1-2, validated as a pair (light surface).
const REVENUE_COLOR = "#2a78d6";
const SPENDING_COLOR = "#eb6834";

const BASIS_NOTE: Record<OverviewEntity, string> = {
  school: "School districts report on a July–June year using standard government accounting (GAAP).",
  town: "New Jersey towns report on a calendar year using the state's own “regulatory” accounting rules, so their figures aren't directly comparable with the school district's.",
};

const STATEMENT_LABEL: Record<string, string> = {
  audit: "audit", acfr: "annual financial report (ACFR)", annual_report: "annual financial report",
  financial_statement: "financial statement", budget: "budget", ufb: "user-friendly budget",
};

async function openSource(documentId: string) {
  try {
    const { url } = await getDocumentViewUrl(documentId);
    window.open(url, "_blank", "noopener,noreferrer");
  } catch (e) {
    alert(`Could not open document: ${(e as Error).message}`);
  }
}

export default function FinanceSummary({ fin, entity }: { fin: OverviewFinances; entity: OverviewEntity }) {
  const latest = fin.latest;
  if (!latest) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-200 bg-white p-10 text-center text-sm text-gray-500">
        No financial statements have been extracted for this entity yet.
      </div>
    );
  }
  const isBudget = latest.kind === "budget";
  const prevLabel = fin.previous_year ? `vs FY ${fin.previous_year}` : "";
  const chartData = fin.years.map((y) => ({
    year: y.kind === "budget" ? `${y.fiscal_year}*` : y.fiscal_year,
    Revenue: y.revenue, Spending: y.expenditures,
  }));
  const hasBudgetYears = fin.years.some((y) => y.kind === "budget");

  return (
    <div className="space-y-6">
      {/* Headline */}
      <div className="bg-white rounded-xl border p-4 md:p-5">
        <p className="text-[10px] uppercase font-semibold tracking-wide text-gray-500">FY {latest.fiscal_year} in brief</p>
        <p className="mt-1 text-base md:text-lg text-gray-900 leading-relaxed">{fin.headline.text}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
          <button onClick={() => fin.source && openSource(fin.source.document_id)}
            className="inline-flex items-center gap-1 text-left hover:text-gray-800 underline-offset-2 hover:underline">
            <DocumentTextIcon className="w-3.5 h-3.5" />
            From the FY {latest.fiscal_year} {STATEMENT_LABEL[latest.statement_type] ?? latest.statement_type}
            {isBudget && " (planned figures, not audited)"}
          </button>
          {fin.headline.source === "ai" && (
            <span title="An AI model reworded the figures on this page; any number not in the figures is rejected automatically.">
              Summary worded by AI from these figures
            </span>
          )}
        </div>
      </div>

      {/* Four tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label={isBudget ? "Spending (budget)" : "Spending"} value={fmtMoney(latest.expenditures)}
          change={fin.changes?.expenditures} prevLabel={prevLabel}
          help="Everything spent in the year: salaries, services, debt payments and more." />
        <Tile label={isBudget ? "Revenue (budget)" : "Revenue"} value={fmtMoney(latest.revenue)}
          change={fin.changes?.revenue} prevLabel={prevLabel}
          help={entity === "school"
            ? "Money coming in: mostly local property taxes and state aid."
            : "Money coming in: property taxes, state aid, fees and other sources."} />
        <Tile label="Reserves" value={fin.reserves ? `${fin.reserves.pct.toFixed(1)}%` : "—"}
          sub={fin.reserves ? `of spending (${fmtMoney(latest.fund_balance)} fund balance)` : undefined}
          status={fin.reserves?.status ? RESERVE_STYLES[fin.reserves.status] : undefined}
          help={fin.reserves?.note ?? "Fund balance: money left over and carried into next year."} />
        <Tile label="Debt" value={fmtMoney(latest.debt)} change={fin.changes?.debt} prevLabel={prevLabel}
          help="Bonds and notes still owed, usually for buildings, roads and equipment." />
      </div>

      {/* Trend */}
      {fin.years.length > 1 && (
        <div className="bg-white rounded-xl border p-4 md:p-5">
          <h3 className="text-sm font-semibold text-gray-900">Revenue and spending over time</h3>
          <div className="h-64 mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#eef0f2" vertical={false} />
                <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#6b7280" }} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
                <YAxis tickFormatter={(v: number) => fmtMoney(v)} tick={{ fontSize: 11, fill: "#6b7280" }}
                  tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
                <Tooltip formatter={(v) => fmtMoney(typeof v === "number" ? v : null)}
                  contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e5e7eb" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline"
                  formatter={(v) => <span style={{ color: "#374151" }}>{v}</span>} />
                <Line type="linear" dataKey="Revenue" stroke={REVENUE_COLOR} strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 5 }} connectNulls />
                <Line type="linear" dataKey="Spending" stroke={SPENDING_COLOR} strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 5 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 space-y-1 text-xs text-gray-500">
            {hasBudgetYears && <p>* Budget year: planned figures rather than audited results.</p>}
            {fin.trend_note && <p>{fin.trend_note}</p>}
          </div>
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-xs text-gray-600 hover:text-gray-900">Show as a table</summary>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b">
                    <th className="py-1.5 pr-3 font-medium">Year</th>
                    <th className="py-1.5 pr-3 font-medium text-right">Revenue</th>
                    <th className="py-1.5 pr-3 font-medium text-right">Spending</th>
                    <th className="py-1.5 pr-3 font-medium text-right">Fund balance</th>
                    <th className="py-1.5 font-medium text-right">Debt</th>
                  </tr>
                </thead>
                <tbody>
                  {fin.years.slice().reverse().map((y) => (
                    <tr key={y.fiscal_year} className="border-b border-gray-50">
                      <td className="py-1.5 pr-3">FY {y.fiscal_year}{y.kind === "budget" && <span className="text-gray-400"> (budget)</span>}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(y.revenue)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(y.expenditures)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(y.fund_balance)}</td>
                      <td className="py-1.5 text-right tabular-nums">{fmtMoney(y.debt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}

      {/* Largest lines */}
      {fin.top_lines && (fin.top_lines.revenue.length > 0 || fin.top_lines.spending.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TopLines title="Largest revenue sources" rows={fin.top_lines.revenue} color={REVENUE_COLOR} />
          <TopLines title="Largest spending lines" rows={fin.top_lines.spending} color={SPENDING_COLOR} />
          <p className="md:col-span-2 -mt-2 text-xs text-gray-500">
            Individual lines from the FY {latest.fiscal_year} statement; totals and subtotals are left out.{" "}
            <Link href={`/financial-analysis/statements?entity=${entity}`} className="underline hover:text-gray-800">See every line →</Link>
          </p>
        </div>
      )}

      {/* Automated checks */}
      {((fin.flags?.length ?? 0) > 0 || (fin.line_flag_count ?? 0) > 0) && (
        <div className="bg-white rounded-xl border p-4 md:p-5">
          <h3 className="text-sm font-semibold text-gray-900">Worth a closer look</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Automated checks on the extracted figures. They can be triggered by extraction errors, so confirm against the source document.
          </p>
          <ul className="mt-3 space-y-2">
            {fin.flags?.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <ExclamationTriangleIcon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${f.severity === "high" ? "text-red-600" : "text-amber-600"}`} />
                <div>
                  <span className="font-medium text-gray-900">{f.title}</span>
                  <span className="ml-1.5 text-[10px] uppercase font-semibold text-gray-500">{f.severity === "high" ? "High" : "Check"}</span>
                  <p className="text-xs text-gray-500">{f.detail}</p>
                </div>
              </li>
            ))}
            {(fin.line_flag_count ?? 0) > 0 && (
              <li className="flex gap-2 text-sm text-gray-700">
                <InformationCircleIcon className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
                <span>
                  {fin.line_flag_count} individual line{fin.line_flag_count === 1 ? "" : "s"} changed sharply from the prior year or the budget.{" "}
                  <Link href={`/financial-analysis/statements?entity=${entity}`} className="underline hover:text-gray-900">Review lines</Link>
                </span>
              </li>
            )}
          </ul>
        </div>
      )}

      <p className="text-xs text-gray-500 flex gap-1.5">
        <InformationCircleIcon className="w-4 h-4 flex-shrink-0" />
        {BASIS_NOTE[entity]}
      </p>
    </div>
  );
}

function Tile({ label, value, change, prevLabel, sub, status, help }: {
  label: string; value: string; change?: number | null; prevLabel?: string; sub?: string;
  status?: { dot: string; label: string }; help: string;
}) {
  return (
    <div className="bg-white rounded-xl border p-4 flex flex-col">
      <p className="text-[10px] uppercase font-semibold tracking-wide text-gray-500">{label}</p>
      <p className="text-2xl font-semibold text-gray-900 mt-1">{value}</p>
      <p className="text-xs text-gray-600 mt-0.5 min-h-[1rem]">
        {sub ?? (change != null ? `${fmtChange(change)} ${prevLabel}` : "")}
      </p>
      {status && (
        <p className="mt-1 inline-flex items-center gap-1.5 text-xs font-medium text-gray-800">
          <span className={`w-2 h-2 rounded-full ${status.dot}`} aria-hidden />{status.label}
        </p>
      )}
      <p className="text-xs text-gray-500 mt-2 leading-snug">{help}</p>
    </div>
  );
}

function TopLines({ title, rows, color }: { title: string; rows: { name: string; amount: number }[]; color: string }) {
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => r.amount));
  return (
    <div className="bg-white rounded-xl border p-4 md:p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">{title}</h3>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.name} title={`${r.name}: $${Math.round(r.amount).toLocaleString()}`}>
            <div className="flex justify-between gap-3 text-xs">
              <span className="text-gray-700 truncate">{r.name}</span>
              <span className="text-gray-900 font-medium tabular-nums">{fmtMoney(r.amount)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-gray-100">
              <div className="h-1.5 rounded-full" style={{ width: `${Math.max(2, (r.amount / max) * 100)}%`, backgroundColor: color }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
