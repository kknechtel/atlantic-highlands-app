"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { getStatements, getAnalyses, type FinancialStatement } from "@/lib/api";
import StatementsList from "@/components/financial/StatementsList";
import AnalysisPanel from "@/components/financial/AnalysisPanel";
import ExtractModal from "@/components/financial/ExtractModal";
import { PlusIcon, ChartBarSquareIcon } from "@heroicons/react/24/outline";

export default function FinancialAnalysisPage() {
  const searchParams = useSearchParams();
  const entityFilter = searchParams.get("entity") || "";
  const [activeTab, setActiveTab] = useState<"statements" | "analysis">("statements");
  const [showExtract, setShowExtract] = useState(false);
  const [selectedStatements, setSelectedStatements] = useState<string[]>([]);

  const { data: statements } = useQuery({
    queryKey: ["statements", entityFilter],
    queryFn: () => getStatements({ entity_type: entityFilter || undefined }),
  });

  const { data: analyses } = useQuery({
    queryKey: ["analyses", entityFilter],
    queryFn: () => getAnalyses(entityFilter || undefined),
  });

  const entityLabel = entityFilter === "town" ? "Town" : entityFilter === "school" ? "School District" : "All Entities";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Financial Analysis</h1>
          <p className="text-gray-500 mt-1">{entityLabel}</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowExtract(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <PlusIcon className="w-4 h-4" /> Extract Statement
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b mb-6">
        <button
          onClick={() => setActiveTab("statements")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "statements"
              ? "border-primary-600 text-primary-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Statements ({statements?.length || 0})
        </button>
        <button
          onClick={() => setActiveTab("analysis")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "analysis"
              ? "border-primary-600 text-primary-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Analyses ({analyses?.length || 0})
        </button>
      </div>

      {activeTab === "statements" && (
        <StatementsList
          statements={statements || []}
          selectedIds={selectedStatements}
          onSelectionChange={setSelectedStatements}
          onAnalyze={() => setActiveTab("analysis")}
        />
      )}

      {activeTab === "analysis" && (
        <AnalysisPanel
          analyses={analyses || []}
          statements={statements || []}
          preSelectedIds={selectedStatements}
        />
      )}

      {showExtract && <ExtractModal onClose={() => setShowExtract(false)} />}
    </div>
  );
}
