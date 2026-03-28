"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStatements, getDocuments, getDocumentViewUrl, type FinancialStatement, type Document } from "@/lib/api";
import SplitDocViewer from "@/components/SplitDocViewer";
import {
  BuildingOfficeIcon,
  AcademicCapIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  DocumentTextIcon,
  EyeIcon,
} from "@heroicons/react/24/outline";

export default function NarrativePage() {
  const [activeTab, setActiveTab] = useState<"town" | "school">("town");
  const [splitDoc, setSplitDoc] = useState<{ url: string; filename: string } | null>(null);

  const { data: statements } = useQuery({
    queryKey: ["statements"],
    queryFn: () => getStatements(),
  });

  const { data: allDocs } = useQuery({
    queryKey: ["all-financial-docs-narrative"],
    queryFn: async () => {
      const [budgets, audits, fs] = await Promise.all([
        getDocuments({ doc_type: "budget" }),
        getDocuments({ doc_type: "audit" }),
        getDocuments({ doc_type: "financial_statement" }),
      ]);
      return [...budgets, ...audits, ...fs];
    },
  });

  const townStatements = (statements || [])
    .filter((s) => s.entity_type === "town" && s.total_revenue)
    .sort((a, b) => a.fiscal_year.localeCompare(b.fiscal_year));

  const schoolStatements = (statements || [])
    .filter((s) => s.entity_type === "school" && s.total_expenditures)
    .sort((a, b) => a.fiscal_year.localeCompare(b.fiscal_year));

  const townDocs = (allDocs || []).filter((d) => d.category === "town");
  const schoolDocs = (allDocs || []).filter((d) => d.category === "school");

  const handleViewDoc = async (doc: Document) => {
    const { url } = await getDocumentViewUrl(doc.id);
    setSplitDoc({ url, filename: doc.filename });
  };

  const activeStatements = activeTab === "town" ? townStatements : schoolStatements;
  const activeDocs = activeTab === "town" ? townDocs : schoolDocs;

  return (
    <div className="flex h-full">
      {/* Main narrative */}
      <div className={`flex-1 overflow-auto ${splitDoc ? "w-1/2" : ""}`}>
        <div className="p-8 max-w-4xl">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Financial Narrative</h1>
          <p className="text-sm text-gray-500 mb-6">
            Year-over-year analysis with supporting documents
          </p>

          {/* Tab switcher */}
          <div className="flex gap-2 mb-8">
            <button
              onClick={() => setActiveTab("town")}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === "town"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              <BuildingOfficeIcon className="w-4 h-4" /> Borough of Atlantic Highlands
            </button>
            <button
              onClick={() => setActiveTab("school")}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === "school"
                  ? "bg-orange-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              <AcademicCapIcon className="w-4 h-4" /> School District
            </button>
          </div>

          {/* Narrative content */}
          {activeTab === "town" ? (
            <TownNarrative statements={townStatements} docs={townDocs} onViewDoc={handleViewDoc} />
          ) : (
            <SchoolNarrative statements={schoolStatements} docs={schoolDocs} onViewDoc={handleViewDoc} />
          )}
        </div>
      </div>

      {/* Split document viewer */}
      {splitDoc && (
        <SplitDocViewer
          url={splitDoc.url}
          filename={splitDoc.filename}
          onClose={() => setSplitDoc(null)}
        />
      )}
    </div>
  );
}

function TownNarrative({
  statements,
  docs,
  onViewDoc,
}: {
  statements: FinancialStatement[];
  docs: Document[];
  onViewDoc: (doc: Document) => void;
}) {
  const fmt = (n: number | null) =>
    n ? `$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "N/A";

  const pctChange = (curr: number | null, prev: number | null) => {
    if (!curr || !prev || prev === 0) return null;
    return ((curr - prev) / Math.abs(prev)) * 100;
  };

  return (
    <div className="space-y-8">
      <div className="prose prose-sm max-w-none">
        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <BuildingOfficeIcon className="w-5 h-5 text-blue-600" />
          Borough of Atlantic Highlands - Financial Overview
        </h2>
        <p className="text-gray-600 leading-relaxed">
          Atlantic Highlands is a residential borough in Monmouth County, New Jersey with a
          population of approximately 4,400. The borough operates under a mayor-council form
          of government. The following analysis covers the borough's financial performance
          based on extracted data from annual audits and financial statements.
        </p>
      </div>

      {/* Fund Balance Trend */}
      {statements.some((s) => s.fund_balance) && (
        <NarrativeSection title="Fund Balance Trend" color="blue">
          <p className="text-sm text-gray-600 mb-3">
            The fund balance represents the borough's financial reserves - the difference between
            assets and liabilities in the general fund.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {statements
              .filter((s) => s.fund_balance)
              .map((s, i, arr) => {
                const prev = i > 0 ? arr[i - 1].fund_balance : null;
                const change = pctChange(s.fund_balance, prev);
                return (
                  <MetricCard
                    key={s.fiscal_year}
                    year={s.fiscal_year}
                    value={fmt(s.fund_balance)}
                    change={change}
                  />
                );
              })}
          </div>
        </NarrativeSection>
      )}

      {/* Revenue vs Expenditures */}
      {statements.some((s) => s.total_revenue && s.total_revenue > 0) && (
        <NarrativeSection title="Revenue vs. Expenditures" color="blue">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium text-gray-500">Fiscal Year</th>
                  <th className="text-right py-2 font-medium text-green-600">Revenue</th>
                  <th className="text-right py-2 font-medium text-red-600">Expenditures</th>
                  <th className="text-right py-2 font-medium text-gray-500">Surplus/Deficit</th>
                  <th className="text-right py-2 font-medium text-gray-500">Fund Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {statements.map((s) => {
                  const surplus = (s.total_revenue || 0) - (s.total_expenditures || 0);
                  return (
                    <tr key={s.fiscal_year} className="hover:bg-gray-50">
                      <td className="py-2 font-medium">{s.fiscal_year}</td>
                      <td className="py-2 text-right text-green-600">{fmt(s.total_revenue)}</td>
                      <td className="py-2 text-right text-red-600">{fmt(s.total_expenditures)}</td>
                      <td
                        className={`py-2 text-right font-medium ${
                          surplus >= 0 ? "text-green-600" : "text-red-600"
                        }`}
                      >
                        {s.total_revenue && s.total_expenditures ? fmt(surplus) : "-"}
                      </td>
                      <td className="py-2 text-right">{fmt(s.fund_balance)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </NarrativeSection>
      )}

      {/* Supporting Documents */}
      <NarrativeSection title="Supporting Documents" color="blue">
        <DocumentList docs={docs} onView={onViewDoc} />
      </NarrativeSection>
    </div>
  );
}

function SchoolNarrative({
  statements,
  docs,
  onViewDoc,
}: {
  statements: FinancialStatement[];
  docs: Document[];
  onViewDoc: (doc: Document) => void;
}) {
  const fmt = (n: number | null) =>
    n ? `$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "N/A";

  const pctChange = (curr: number | null, prev: number | null) => {
    if (!curr || !prev || prev === 0) return null;
    return ((curr - prev) / Math.abs(prev)) * 100;
  };

  return (
    <div className="space-y-8">
      <div className="prose prose-sm max-w-none">
        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <AcademicCapIcon className="w-5 h-5 text-orange-600" />
          Atlantic Highlands School District - Financial Overview
        </h2>
        <p className="text-gray-600 leading-relaxed">
          The Atlantic Highlands Elementary School (AHES) serves pre-K through 8th grade. The
          district is part of the Henry Hudson Regional School District (Tri-District) which
          also includes Highlands Elementary and Henry Hudson Regional High School. The
          following analysis covers the district's financial performance from comprehensive
          annual financial reports (CAFRs) and annual management reports (AMRs).
        </p>
      </div>

      {/* Revenue vs Expenditures */}
      <NarrativeSection title="Revenue vs. Expenditures" color="orange">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 font-medium text-gray-500">Fiscal Year</th>
                <th className="text-right py-2 font-medium text-green-600">Revenue</th>
                <th className="text-right py-2 font-medium text-red-600">Expenditures</th>
                <th className="text-right py-2 font-medium text-gray-500">Surplus/Deficit</th>
                <th className="text-right py-2 font-medium text-gray-500">Fund Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {statements.map((s, i) => {
                const surplus =
                  s.total_revenue && s.total_expenditures
                    ? s.total_revenue - s.total_expenditures
                    : null;
                const prevExp = i > 0 ? statements[i - 1].total_expenditures : null;
                const expChange = pctChange(s.total_expenditures, prevExp);
                return (
                  <tr key={s.fiscal_year} className="hover:bg-gray-50">
                    <td className="py-2 font-medium">{s.fiscal_year}</td>
                    <td className="py-2 text-right text-green-600">{fmt(s.total_revenue)}</td>
                    <td className="py-2 text-right text-red-600">
                      {fmt(s.total_expenditures)}
                      {expChange != null && (
                        <span
                          className={`ml-1 text-xs ${
                            expChange > 0 ? "text-red-400" : "text-green-400"
                          }`}
                        >
                          ({expChange > 0 ? "+" : ""}
                          {expChange.toFixed(1)}%)
                        </span>
                      )}
                    </td>
                    <td
                      className={`py-2 text-right font-medium ${
                        surplus != null && surplus >= 0 ? "text-green-600" : "text-red-600"
                      }`}
                    >
                      {surplus != null ? fmt(surplus) : "-"}
                    </td>
                    <td className="py-2 text-right">{fmt(s.fund_balance)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Key observations */}
        {statements.length >= 2 && (
          <div className="mt-4 bg-orange-50 rounded-lg p-4">
            <h4 className="font-medium text-orange-800 text-sm mb-2">Key Observations</h4>
            <ul className="text-sm text-orange-700 space-y-1 list-disc list-inside">
              {(() => {
                const latest = statements[statements.length - 1];
                const prev = statements[statements.length - 2];
                const items = [];
                if (latest.total_expenditures && prev.total_expenditures) {
                  const change = pctChange(latest.total_expenditures, prev.total_expenditures);
                  if (change != null) {
                    items.push(
                      `Expenditures ${change > 0 ? "increased" : "decreased"} ${Math.abs(change).toFixed(1)}% from FY${prev.fiscal_year} to FY${latest.fiscal_year}`
                    );
                  }
                }
                if (latest.total_revenue && latest.total_expenditures) {
                  const surplus = latest.total_revenue - latest.total_expenditures;
                  items.push(
                    surplus >= 0
                      ? `FY${latest.fiscal_year} ended with a surplus of ${fmt(surplus)}`
                      : `FY${latest.fiscal_year} ended with a deficit of ${fmt(Math.abs(surplus))}`
                  );
                }
                if (latest.fund_balance) {
                  items.push(`Fund balance stands at ${fmt(latest.fund_balance)}`);
                }
                return items.map((item, i) => <li key={i}>{item}</li>);
              })()}
            </ul>
          </div>
        )}
      </NarrativeSection>

      {/* Supporting Documents */}
      <NarrativeSection title="Supporting Documents" color="orange">
        <DocumentList docs={docs} onView={onViewDoc} />
      </NarrativeSection>
    </div>
  );
}

function NarrativeSection({
  title,
  color,
  children,
}: {
  title: string;
  color: "blue" | "orange";
  children: React.ReactNode;
}) {
  const borderColor = color === "blue" ? "border-blue-200" : "border-orange-200";
  return (
    <div className={`bg-white rounded-xl shadow p-6 border-l-4 ${borderColor}`}>
      <h3 className="font-semibold text-gray-900 mb-4">{title}</h3>
      {children}
    </div>
  );
}

function MetricCard({
  year,
  value,
  change,
}: {
  year: string;
  value: string;
  change: number | null;
}) {
  return (
    <div className="bg-gray-50 rounded-lg p-3 text-center">
      <p className="text-xs text-gray-400 mb-1">FY {year}</p>
      <p className="text-lg font-bold text-gray-900">{value}</p>
      {change != null && (
        <p
          className={`text-xs font-medium flex items-center justify-center gap-0.5 ${
            change >= 0 ? "text-green-600" : "text-red-600"
          }`}
        >
          {change >= 0 ? (
            <ArrowTrendingUpIcon className="w-3 h-3" />
          ) : (
            <ArrowTrendingDownIcon className="w-3 h-3" />
          )}
          {change > 0 ? "+" : ""}
          {change.toFixed(1)}%
        </p>
      )}
    </div>
  );
}

function DocumentList({ docs, onView }: { docs: Document[]; onView: (d: Document) => void }) {
  // Group by type and year
  const grouped = new Map<string, Document[]>();
  docs.forEach((d) => {
    const key = `${d.doc_type || "other"}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(d);
  });

  const typeLabels: Record<string, string> = {
    budget: "Budgets",
    audit: "Audit Reports",
    financial_statement: "Financial Statements",
  };

  return (
    <div className="space-y-4">
      {Array.from(grouped.entries()).map(([type, typeDocs]) => (
        <div key={type}>
          <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">
            {typeLabels[type] || type} ({typeDocs.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {typeDocs
              .sort((a, b) => (b.fiscal_year || "").localeCompare(a.fiscal_year || ""))
              .slice(0, 10)
              .map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => onView(doc)}
                  className="flex items-center gap-2 px-3 py-2 text-left text-sm bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors group"
                >
                  <DocumentTextIcon className="w-4 h-4 text-gray-400 group-hover:text-blue-500 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-gray-700 truncate text-xs">{doc.filename}</p>
                    <p className="text-xs text-gray-400">
                      {doc.fiscal_year ? `FY ${doc.fiscal_year}` : ""}
                    </p>
                  </div>
                  <EyeIcon className="w-3.5 h-3.5 text-gray-300 group-hover:text-blue-500 flex-shrink-0" />
                </button>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
