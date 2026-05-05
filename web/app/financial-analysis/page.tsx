"use client";

import { useState } from "react";
import FinancialDashboardV2 from "@/components/financial/v2/FinancialDashboardV2";
import ExtractModal from "@/components/financial/ExtractModal";
import { PlusIcon } from "@heroicons/react/24/outline";

export default function FinancialAnalysisPage() {
  const [showExtract, setShowExtract] = useState(false);

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-auto">
        <div className="p-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Financial Analysis</h1>
              <p className="text-sm text-gray-500 mt-1">
                Multi-pass extraction · Agent drill-downs · NJ-aware anomaly detection
              </p>
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

          <FinancialDashboardV2 />
        </div>
      </div>

      {showExtract && <ExtractModal onClose={() => setShowExtract(false)} />}
    </div>
  );
}
