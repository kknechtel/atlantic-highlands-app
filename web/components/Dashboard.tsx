"use client";

import { useQuery } from "@tanstack/react-query";
import { getProjects, getStatements } from "@/lib/api";
import { FolderIcon, DocumentTextIcon, ChartBarIcon } from "@heroicons/react/24/outline";

export default function Dashboard() {
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const { data: statements } = useQuery({ queryKey: ["statements"], queryFn: () => getStatements() });

  const totalDocs = projects?.reduce((sum, p) => sum + p.document_count, 0) || 0;
  const townStatements = statements?.filter((s) => s.entity_type === "town") || [];
  const schoolStatements = statements?.filter((s) => s.entity_type === "school") || [];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
      <p className="text-gray-500 mt-1">Atlantic Highlands Document Library & Financial Analysis</p>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-8">
        <StatCard
          icon={<FolderIcon className="w-8 h-8 text-blue-500" />}
          label="Projects"
          value={projects?.length || 0}
        />
        <StatCard
          icon={<DocumentTextIcon className="w-8 h-8 text-green-500" />}
          label="Documents"
          value={totalDocs}
        />
        <StatCard
          icon={<ChartBarIcon className="w-8 h-8 text-purple-500" />}
          label="Town Statements"
          value={townStatements.length}
        />
        <StatCard
          icon={<ChartBarIcon className="w-8 h-8 text-orange-500" />}
          label="School Statements"
          value={schoolStatements.length}
        />
      </div>

      {/* Recent activity */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Projects</h2>
          {projects?.length ? (
            <ul className="space-y-3">
              {projects.slice(0, 5).map((p) => (
                <li key={p.id} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700">{p.name}</span>
                  <span className="text-gray-400">{p.document_count} docs</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-400 text-sm">No projects yet. Create one to get started.</p>
          )}
        </div>

        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Financial Statements</h2>
          {statements?.length ? (
            <ul className="space-y-3">
              {statements.slice(0, 5).map((s) => (
                <li key={s.id} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="text-gray-700">{s.entity_name}</span>
                    <span className="text-gray-400 ml-2">FY {s.fiscal_year}</span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      s.status === "extracted"
                        ? "bg-green-100 text-green-700"
                        : s.status === "processing"
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {s.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-400 text-sm">
              No financial statements yet. Upload documents to extract financial data.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="bg-white rounded-xl shadow p-6 flex items-center gap-4">
      {icon}
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}
