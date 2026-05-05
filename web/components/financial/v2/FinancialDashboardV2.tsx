"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getStatements, getFinancialDiagnostics, drillAll,
  type FinancialStatement,
} from "@/lib/api";
import { BuildingOfficeIcon, AcademicCapIcon, BoltIcon, BugAntIcon } from "@heroicons/react/24/outline";
import StatementCard from "./StatementCard";
import DrillPanel from "./DrillPanel";
import YoYTrajectory from "./YoYTrajectory";

type EntityFilter = "all" | "town" | "school";

export default function FinancialDashboardV2() {
  const [entityFilter, setEntityFilter] = useState<EntityFilter>("school");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showDiag, setShowDiag] = useState(false);
  const qc = useQueryClient();

  const { data: statements } = useQuery({
    queryKey: ["statements"],
    queryFn: () => getStatements(),
    refetchInterval: 10_000,
  });

  const { data: diag } = useQuery({
    queryKey: ["financial-diagnostics"],
    queryFn: () => getFinancialDiagnostics(),
    refetchInterval: 30_000,
  });

  const drillAllMut = useMutation({
    mutationFn: () => drillAll({
      entity_type: entityFilter === "all" ? undefined : entityFilter,
      concurrency: 2,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      qc.invalidateQueries({ queryKey: ["financial-diagnostics"] });
    },
  });

  const filtered = useMemo(() => {
    if (!statements) return [];
    return entityFilter === "all"
      ? statements
      : statements.filter(s => s.entity_type === entityFilter);
  }, [statements, entityFilter]);

  const grouped = useMemo(() => {
    const out: Record<string, FinancialStatement[]> = {};
    for (const s of filtered) {
      const fy = s.fiscal_year ?? "unknown";
      (out[fy] ??= []).push(s);
    }
    return Object.entries(out).sort((a, b) => b[0].localeCompare(a[0]));
  }, [filtered]);

  const selected = filtered.find(s => s.id === selectedId);

  // Top-level KPIs from filtered statements
  const totals = useMemo(() => {
    let revenue = 0, expenditures = 0, fundBalance = 0, debt = 0, count = 0;
    for (const s of filtered) {
      if (s.status !== "extracted" && s.status !== "drilled" && s.status !== "verified") continue;
      revenue += s.total_revenue ?? 0;
      expenditures += s.total_expenditures ?? 0;
      fundBalance += s.fund_balance ?? 0;
      debt += s.total_debt ?? 0;
      count++;
    }
    return { revenue, expenditures, fundBalance, debt, count };
  }, [filtered]);

  return (
    <div className="space-y-6">
      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {[
          { key: "school" as const, label: "School (Henry Hudson Regional)", icon: AcademicCapIcon, color: "orange" },
          { key: "town" as const, label: "Town (Atlantic Highlands Borough)", icon: BuildingOfficeIcon, color: "blue" },
          { key: "all" as const, label: "All", icon: null, color: "gray" },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => { setEntityFilter(key); setSelectedId(null); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
              ${entityFilter === key
                ? "bg-primary-600 text-white"
                : "bg-white border border-gray-300 text-gray-700 hover:bg-gray-50"}`}
          >
            {Icon && <Icon className="w-4 h-4" />}
            {label}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => drillAllMut.mutate()}
            disabled={drillAllMut.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
            title="Run drill agents on every extracted statement matching the current filter"
          >
            <BoltIcon className="w-4 h-4" />
            Drill All
          </button>
          <button
            onClick={() => setShowDiag(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50"
          >
            <BugAntIcon className="w-4 h-4" />
            Diagnostics
          </button>
        </div>
      </div>

      {drillAllMut.data && (
        <div className="rounded-lg bg-purple-50 border border-purple-200 px-4 py-2 text-sm text-purple-900">
          Queued <strong>{drillAllMut.data.queued}</strong> drills (concurrency {drillAllMut.data.concurrency}). Watch the cards for status changes.
        </div>
      )}

      {showDiag && diag && (
        <div className="rounded-xl bg-white border border-gray-200 p-4 space-y-3 text-xs">
          <div className="font-semibold text-gray-700 text-sm">Pipeline Diagnostics</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <DiagBlock title="LLM Keys">
              <div>Anthropic: <span className={diag.llm_keys.anthropic_api_key_set ? "text-green-700" : "text-red-700"}>{diag.llm_keys.anthropic_api_key_set ? "set" : "MISSING"}</span></div>
              <div>Gemini: <span className={diag.llm_keys.gemini_api_key_set ? "text-green-700" : "text-red-700"}>{diag.llm_keys.gemini_api_key_set ? "set" : "MISSING"}</span></div>
            </DiagBlock>
            <DiagBlock title={`Statements (${diag.statements.total})`}>
              {Object.entries(diag.statements.by_status).map(([k, v]) => (
                <div key={k}><span className="font-mono">{v}</span> {k}</div>
              ))}
            </DiagBlock>
            <DiagBlock title="Extraction Issues">
              <div>Empty (no line items): <span className="font-mono text-red-700">{diag.extraction_issues.extracted_with_no_line_items_count}</span></div>
            </DiagBlock>
            <DiagBlock title="Drill Issues">
              <div>With errors: <span className="font-mono text-red-700">{diag.drill_issues.drills_with_errors_count}</span></div>
            </DiagBlock>
          </div>
          {diag.next_steps_hint && (
            <div className="rounded bg-blue-50 border border-blue-200 px-3 py-2 text-blue-900">
              <strong>Next:</strong> {diag.next_steps_hint}
            </div>
          )}
          {diag.drill_issues.drills_with_errors_sample.length > 0 && (
            <details>
              <summary className="cursor-pointer text-gray-600">Drill error details ({diag.drill_issues.drills_with_errors_sample.length})</summary>
              <div className="mt-2 space-y-1">
                {diag.drill_issues.drills_with_errors_sample.map((s: any, i: number) => (
                  <div key={i} className="rounded bg-red-50 border border-red-200 p-2 text-[11px]">
                    <div className="font-medium">{s.entity_type} FY {s.fiscal_year}</div>
                    {s.errors.map((e: any, j: number) => (
                      <div key={j} className="text-red-800">· {e.drill}: {e.error} {e.msg ? `— ${e.msg}` : ""}</div>
                    ))}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ["Statements", String(totals.count)],
          ["Total Revenue", `$${Math.round(totals.revenue).toLocaleString()}`],
          ["Total Expenditures", `$${Math.round(totals.expenditures).toLocaleString()}`],
          ["Fund Balance", `$${Math.round(totals.fundBalance).toLocaleString()}`],
          ["Total Debt", `$${Math.round(totals.debt).toLocaleString()}`],
        ].map(([label, value], i) => (
          <div key={i} className="bg-white rounded-xl border p-4">
            <p className="text-[10px] uppercase font-semibold tracking-wide text-gray-500">{label}</p>
            <p className="text-lg font-mono mt-1">{value}</p>
          </div>
        ))}
      </div>

      {/* NJ basis explainer */}
      {entityFilter !== "all" && (
        <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-900">
          {entityFilter === "school" ? (
            <>
              <strong>NJ School District (GAAP/GASB):</strong> Surplus statutorily capped at greater of 2% of expenditures or $250K (N.J.S.A. 18A:7F-7).
              {" "}HHRSD is a 7/1/2024 consolidation — pre-consolidation figures from AHSD/HSD/HHRS-HS cannot be summed naively.
            </>
          ) : (
            <>
              <strong>NJ Municipal (Regulatory Basis):</strong> AFS filed Feb 10 to DLGS; ACFR by Jun 30. Healthy Current Fund balance ≥8%, warn &lt;5%.
              {" "}For FY26+, CMPTRA fully consolidated into ETR — expect $0 CMPTRA, not a decline.
            </>
          )}
        </div>
      )}

      <YoYTrajectory statements={filtered} entity={entityFilter} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: cards grouped by FY */}
        <div className="lg:col-span-1 space-y-5 max-h-[80vh] overflow-y-auto pr-2">
          {grouped.length === 0 && (
            <div className="rounded-xl border-2 border-dashed border-gray-200 p-8 text-center text-sm text-gray-400">
              No extracted statements. Upload a budget or audit and click <strong>Extract</strong>.
            </div>
          )}
          {grouped.map(([fy, stmts]) => (
            <div key={fy}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">FY {fy}</h3>
              <div className="space-y-2">
                {stmts.map(s => (
                  <StatementCard
                    key={s.id}
                    stmt={s}
                    selected={s.id === selectedId}
                    onClick={() => setSelectedId(s.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Right: drill panel */}
        <div className="lg:col-span-2">
          {selected ? (
            <DrillPanel statement={selected} />
          ) : (
            <div className="rounded-xl border-2 border-dashed border-gray-200 bg-white p-12 text-center">
              <p className="text-sm text-gray-500">Select a statement to view its drill analysis.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DiagBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-gray-50 border p-3">
      <div className="text-[10px] uppercase font-semibold tracking-wide text-gray-500 mb-1">{title}</div>
      <div className="space-y-0.5 text-gray-800">{children}</div>
    </div>
  );
}
