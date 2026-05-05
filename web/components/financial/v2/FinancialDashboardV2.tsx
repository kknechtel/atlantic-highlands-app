"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStatements, type FinancialStatement } from "@/lib/api";
import { BuildingOfficeIcon, AcademicCapIcon } from "@heroicons/react/24/outline";
import StatementCard from "./StatementCard";
import DrillPanel from "./DrillPanel";

type EntityFilter = "all" | "town" | "school";

export default function FinancialDashboardV2() {
  const [entityFilter, setEntityFilter] = useState<EntityFilter>("school");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: statements } = useQuery({
    queryKey: ["statements"],
    queryFn: () => getStatements(),
    refetchInterval: 10_000,
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
      <div className="flex items-center gap-3">
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
      </div>

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
