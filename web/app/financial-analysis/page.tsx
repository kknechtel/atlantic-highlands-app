"use client";
import { TOWN, SCHOOL_ENTITY } from "@/lib/municipality";

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getOverview, type OverviewEntity } from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";
import FinanceSummary from "@/components/overview/FinanceSummary";
import { AcademicCapIcon, BuildingOfficeIcon, TableCellsIcon, WrenchScrewdriverIcon } from "@heroicons/react/24/outline";

export default function FinancialAnalysisPage() {
  // useSearchParams must be inside Suspense for the App Router.
  return (
    <Suspense fallback={null}>
      <Financials />
    </Suspense>
  );
}

function Financials() {
  const router = useRouter();
  const params = useSearchParams();
  const { user } = useAuth();
  const entity: OverviewEntity = params.get("entity") === "school" ? "school" : "town";

  const { data, isLoading, error } = useQuery({
    queryKey: ["overview", entity],
    queryFn: () => getOverview(entity),
  });

  const tabs = [
    { key: "town" as const, label: TOWN.official_name, icon: BuildingOfficeIcon },
    { key: "school" as const, label: SCHOOL_ENTITY.label, icon: AcademicCapIcon },
  ];

  return (
    <div className="p-3 md:p-8 max-w-6xl">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-4 md:mb-6">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900">Finances</h1>
          <p className="text-xs md:text-sm text-gray-500 mt-1">
            Where the money comes from, where it goes, and how that has changed
          </p>
        </div>
        <div className="flex gap-3 text-xs">
          <Link href={`/financial-analysis/statements?entity=${entity}`} className="inline-flex items-center gap-1 text-gray-600 hover:text-gray-900">
            <TableCellsIcon className="w-4 h-4" /> Line-item detail
          </Link>
          {user?.is_admin && (
            <Link href="/financial-analysis/data" className="inline-flex items-center gap-1 text-gray-600 hover:text-gray-900">
              <WrenchScrewdriverIcon className="w-4 h-4" /> Financial data
            </Link>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-6" role="tablist">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            role="tab"
            aria-selected={entity === key}
            onClick={() => router.replace(`/financial-analysis?entity=${key}`)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors min-h-[40px] ${
              entity === key ? "bg-primary-600 text-white" : "bg-white border border-gray-300 text-gray-700 hover:bg-gray-50"
            }`}
          >
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-600">Could not load finances: {(error as Error).message}</p>}
      {data && <FinanceSummary fin={data.finances} entity={entity} />}
    </div>
  );
}
