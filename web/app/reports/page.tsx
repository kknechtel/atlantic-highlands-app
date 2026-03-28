"use client";

import { useState, useRef } from "react";
import {
  DocumentTextIcon,
  ArrowDownTrayIcon,
  BuildingOfficeIcon,
  AcademicCapIcon,
  SparklesIcon,
  ClipboardIcon,
  CheckIcon,
} from "@heroicons/react/24/outline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const REPORT_TYPES = [
  { id: "financial_overview", label: "Financial Overview", desc: "Revenue, expenditures, fund balance, debt analysis", icon: DocumentTextIcon },
  { id: "budget_analysis", label: "Budget Analysis", desc: "Budget vs actual, variance analysis, trends", icon: DocumentTextIcon },
  { id: "school_district", label: "School District Report", desc: "AHES/HHRS finances, enrollment, per-pupil spending", icon: AcademicCapIcon },
];

export default function ReportsPage() {
  const [selectedType, setSelectedType] = useState("financial_overview");
  const [entityType, setEntityType] = useState("town");
  const [customPrompt, setCustomPrompt] = useState("");
  const [report, setReport] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const handleGenerate = async () => {
    setReport("");
    setIsGenerating(true);

    try {
      const response = await fetch(`${API_BASE}/api/reports/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_type: selectedType === "custom" ? "custom" : selectedType,
          entity_type: entityType,
          custom_prompt: selectedType === "custom" ? customPrompt : undefined,
        }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let full = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const line of decoder.decode(value, { stream: true }).split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const d = JSON.parse(line.slice(6));
              if (d.type === "delta") { full += d.content; setReport(full); }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setReport(`Error: ${e.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([report], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `ah-report-${selectedType}-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
  };

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <SparklesIcon className="w-6 h-6 text-green-600" />
        <h1 className="text-2xl font-bold text-gray-900">AI Reports</h1>
      </div>

      {/* Report type selection */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        {REPORT_TYPES.map((rt) => (
          <button
            key={rt.id}
            onClick={() => setSelectedType(rt.id)}
            className={`p-4 rounded-xl border-2 text-left transition-colors ${
              selectedType === rt.id
                ? "border-green-500 bg-green-50"
                : "border-gray-200 hover:border-green-300 hover:bg-green-50/50"
            }`}
          >
            <rt.icon className={`w-5 h-5 mb-2 ${selectedType === rt.id ? "text-green-600" : "text-gray-400"}`} />
            <p className="font-medium text-sm text-gray-900">{rt.label}</p>
            <p className="text-xs text-gray-500 mt-1">{rt.desc}</p>
          </button>
        ))}
        <button
          onClick={() => setSelectedType("custom")}
          className={`p-4 rounded-xl border-2 text-left transition-colors ${
            selectedType === "custom" ? "border-green-500 bg-green-50" : "border-gray-200 hover:border-green-300"
          }`}
        >
          <DocumentTextIcon className={`w-5 h-5 mb-2 ${selectedType === "custom" ? "text-green-600" : "text-gray-400"}`} />
          <p className="font-medium text-sm text-gray-900">Custom Report</p>
          <p className="text-xs text-gray-500 mt-1">Write your own prompt</p>
        </button>
      </div>

      {/* Options */}
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="flex gap-2">
          <button onClick={() => setEntityType("town")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm ${entityType === "town" ? "bg-green-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
            <BuildingOfficeIcon className="w-4 h-4" /> Town
          </button>
          <button onClick={() => setEntityType("school")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm ${entityType === "school" ? "bg-green-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
            <AcademicCapIcon className="w-4 h-4" /> School
          </button>
        </div>
        <button onClick={handleGenerate} disabled={isGenerating}
          className="flex items-center gap-2 px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium shadow">
          <SparklesIcon className="w-4 h-4" /> {isGenerating ? "Generating..." : "Generate Report"}
        </button>
      </div>

      {selectedType === "custom" && (
        <textarea value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)}
          placeholder="Describe the report you want..."
          className="w-full p-3 border border-gray-300 rounded-xl text-sm mb-4 focus:ring-2 focus:ring-green-500" rows={3} />
      )}

      {/* Report output */}
      {report && (
        <div className="bg-white rounded-xl shadow border">
          <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
            <span className="text-sm font-medium text-gray-700">Generated Report</span>
            <div className="flex gap-2">
              <button onClick={handleCopy} className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100">
                {copied ? <CheckIcon className="w-3.5 h-3.5 text-green-600" /> : <ClipboardIcon className="w-3.5 h-3.5" />} Copy
              </button>
              <button onClick={handleDownload} className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100">
                <ArrowDownTrayIcon className="w-3.5 h-3.5" /> Download
              </button>
            </div>
          </div>
          <div ref={reportRef} className="p-6 prose prose-sm max-w-none prose-headings:text-green-800 prose-strong:text-gray-900"
            dangerouslySetInnerHTML={{
              __html: report
                .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                .replace(/\*(.+?)\*/g, "<em>$1</em>")
                .replace(/^### (.+)$/gm, '<h3 class="text-lg font-bold mt-6 mb-2 text-green-800">$1</h3>')
                .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold mt-8 mb-3 text-green-900 border-b pb-2">$1</h2>')
                .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-8 mb-4 text-green-900">$1</h1>')
                .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-gray-700">$1</li>')
                .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-gray-700">$1</li>')
                .replace(/\n\n/g, "</p><p>")
                .replace(/\n/g, "<br/>"),
            }}
          />
          {isGenerating && (
            <div className="px-6 py-3 border-t bg-green-50 flex items-center gap-2">
              <div className="w-3 h-3 border-2 border-green-300 border-t-green-600 rounded-full animate-spin" />
              <span className="text-xs text-green-700">Generating report...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
