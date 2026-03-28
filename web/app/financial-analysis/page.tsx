"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocuments, getStatements, type Document, type FinancialStatement } from "@/lib/api";
import FinancialDashboard from "@/components/financial/FinancialDashboard";
import DocumentChatModal from "@/components/DocumentChatModal";
// Chat is now global via GlobalChat component
import ExtractModal from "@/components/financial/ExtractModal";
import { PlusIcon, ChatBubbleLeftRightIcon } from "@heroicons/react/24/outline";

export default function FinancialAnalysisPage() {
  const [showExtract, setShowExtract] = useState(false);
  const [showChat, setShowChat] = useState(false);

  const { data: statements } = useQuery({
    queryKey: ["statements"],
    queryFn: () => getStatements(),
  });

  const { data: financialDocs } = useQuery({
    queryKey: ["financial-docs"],
    queryFn: () => getDocuments({ doc_type: "budget" }),
  });

  const { data: allFinDocs } = useQuery({
    queryKey: ["all-financial-docs"],
    queryFn: async () => {
      const [budgets, audits, fs] = await Promise.all([
        getDocuments({ doc_type: "budget" }),
        getDocuments({ doc_type: "audit" }),
        getDocuments({ doc_type: "financial_statement" }),
      ]);
      return [...budgets, ...audits, ...fs];
    },
  });

  // Group docs by entity and year for the dashboard
  const townDocs = allFinDocs?.filter((d) => d.category === "town") || [];
  const schoolDocs = allFinDocs?.filter((d) => d.category === "school") || [];

  return (
    <div className="flex h-full">
      {/* Main content */}
      <div className={`flex-1 overflow-auto ${showChat ? "" : ""}`}>
        <div className="p-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Financial Analysis</h1>
              <p className="text-sm text-gray-500 mt-1">
                Town & School District - Year over Year Comparison
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowChat(!showChat)}
                className={`flex items-center gap-2 px-4 py-2 text-sm border rounded-lg ${
                  showChat
                    ? "bg-purple-50 border-purple-300 text-purple-700"
                    : "border-gray-300 hover:bg-gray-50"
                }`}
              >
                <ChatBubbleLeftRightIcon className="w-4 h-4" />
                {showChat ? "Hide Chat" : "AI Chat"}
              </button>
              <button
                onClick={() => setShowExtract(true)}
                className="flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                <PlusIcon className="w-4 h-4" /> Extract Statement
              </button>
            </div>
          </div>

          <FinancialDashboard
            townDocs={townDocs}
            schoolDocs={schoolDocs}
            statements={statements || []}
          />
        </div>
      </div>

      {showExtract && <ExtractModal onClose={() => setShowExtract(false)} />}
    </div>
  );
}
