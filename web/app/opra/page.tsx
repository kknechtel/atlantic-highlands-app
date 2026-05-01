"use client";

import { useState, useRef, useEffect } from "react";
import {
  DocumentTextIcon,
  ArrowDownTrayIcon,
  ClipboardIcon,
  CheckIcon,
  ShieldCheckIcon,
  ArrowTopRightOnSquareIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  InformationCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from "@heroicons/react/24/outline";

const API_BASE = "";
const brandColor = "#385854";
const GOVPILOT_URL =
  "https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1";

interface RecordCategory {
  label: string;
  description: string;
  example_records: string[];
  notes: string;
}

interface FactCheckResult {
  fact_check_result: string;
  grounding_sources: { title: string; uri: string }[];
  model: string;
  search_grounding: boolean;
  error?: string;
}

export default function OPRAPage() {
  // Form state
  const [categories, setCategories] = useState<Record<string, RecordCategory>>({});
  const [selectedCategory, setSelectedCategory] = useState("financial");
  const [specificRecords, setSpecificRecords] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [preferredFormat, setPreferredFormat] = useState("electronic");
  const [requestorName, setRequestorName] = useState("");
  const [requestorAddress, setRequestorAddress] = useState("");
  const [requestorEmail, setRequestorEmail] = useState("");
  const [requestorPhone, setRequestorPhone] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");

  // Output state
  const [generatedRequest, setGeneratedRequest] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showExamples, setShowExamples] = useState(false);

  // Fact-check state
  const [factCheckResult, setFactCheckResult] = useState<FactCheckResult | null>(null);
  const [isFactChecking, setIsFactChecking] = useState(false);

  // Regulations panel
  const [showRegulations, setShowRegulations] = useState(false);
  const [regulations, setRegulations] = useState<{ regulations: string; atlantic_highlands_info: string } | null>(null);

  const outputRef = useRef<HTMLDivElement>(null);

  // Load categories on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/opra/categories`)
      .then((r) => r.json())
      .then(setCategories)
      .catch(console.error);
  }, []);

  // Load regulations on demand
  const loadRegulations = async () => {
    if (regulations) {
      setShowRegulations(!showRegulations);
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/api/opra/regulations`);
      const data = await r.json();
      setRegulations(data);
      setShowRegulations(true);
    } catch (e) {
      console.error(e);
    }
  };

  const handleGenerate = async () => {
    setGeneratedRequest("");
    setFactCheckResult(null);
    setIsGenerating(true);

    try {
      const response = await fetch(`${API_BASE}/api/opra/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: selectedCategory,
          specific_records: specificRecords,
          date_range_start: dateStart || null,
          date_range_end: dateEnd || null,
          preferred_format: preferredFormat,
          requestor_name: requestorName,
          requestor_address: requestorAddress,
          requestor_email: requestorEmail,
          requestor_phone: requestorPhone,
          additional_context: additionalContext,
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
              if (d.type === "delta") {
                full += d.content;
                setGeneratedRequest(full);
              }
              if (d.type === "error") {
                full += `\n\nError: ${d.content}`;
                setGeneratedRequest(full);
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setGeneratedRequest(`Error generating request: ${e.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFactCheck = async () => {
    if (!generatedRequest) return;
    setIsFactChecking(true);
    setFactCheckResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/opra/fact-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_text: generatedRequest }),
      });
      const data = await r.json();
      setFactCheckResult(data);
    } catch (e: any) {
      setFactCheckResult({ fact_check_result: `Error: ${e.message}`, grounding_sources: [], model: "", search_grounding: false, error: e.message });
    } finally {
      setIsFactChecking(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(generatedRequest);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadTxt = () => {
    const blob = new Blob([generatedRequest], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `OPRA-Request-${selectedCategory}-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
  };

  const handleDownloadPdf = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/opra/generate-pdf-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: selectedCategory,
          specific_records: specificRecords,
          date_range_start: dateStart || null,
          date_range_end: dateEnd || null,
          preferred_format: preferredFormat,
          requestor_name: requestorName,
          requestor_address: requestorAddress,
          requestor_email: requestorEmail,
          requestor_phone: requestorPhone,
          additional_context: additionalContext,
        }),
      });
      const data = await r.json();

      // Generate a formatted text document from the structured data
      const lines = [
        data.date,
        "",
        "TO:",
        `  ${data.to.title}`,
        `  ${data.to.organization}`,
        `  ${data.to.address}`,
        `  ${data.to.phone}`,
        "",
        "FROM:",
        `  ${data.from.name}`,
        `  ${data.from.address}`,
        `  ${data.from.email}`,
        `  ${data.from.phone}`,
        "",
        `RE: ${data.subject}`,
        `Legal Basis: ${data.legal_basis}`,
        "",
        "=" .repeat(70),
        "OPEN PUBLIC RECORDS ACT (OPRA) REQUEST",
        "=".repeat(70),
        "",
        "RECORDS REQUESTED:",
        data.records_requested,
        "",
        `Category: ${data.record_category}`,
        data.date_range ? `Date Range: ${data.date_range}` : "",
        `Delivery Format: ${data.delivery_format}`,
        "",
        "CERTIFICATIONS:",
        `  ${data.certifications.commercial_purpose}`,
        `  ${data.certifications.litigation}`,
        "",
        `Response Deadline: ${data.response_deadline}`,
        "",
        "FEE SCHEDULE:",
        `  Letter-size: ${data.fee_schedule.letter_size}`,
        `  Legal-size: ${data.fee_schedule.legal_size}`,
        `  Electronic: ${data.fee_schedule.electronic}`,
        "",
        data.additional_context ? `ADDITIONAL CONTEXT:\n${data.additional_context}\n` : "",
        `LEGAL NOTES:\n${data.legal_notes}`,
        "",
        "---",
        `Online Submission: ${data.govpilot_url}`,
        "",
        "Signature: ________________________________",
        `Name: ${data.from.name}`,
        `Date: ${data.date}`,
      ].filter(Boolean);

      const blob = new Blob([lines.join("\n")], { type: "text/plain" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `OPRA-Request-Formal-${new Date().toISOString().slice(0, 10)}.txt`;
      a.click();
    } catch (e) {
      console.error("PDF text generation failed:", e);
    }
  };

  const currentCategory = categories[selectedCategory];

  // Render markdown-like formatting
  const renderFormatted = (text: string) => {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/^### (.+)$/gm, '<h3 class="text-lg font-bold mt-6 mb-2 text-gray-800">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold mt-8 mb-3 text-gray-900 border-b pb-2">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-8 mb-4 text-gray-900">$1</h1>')
      .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-gray-700">$1</li>')
      .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-gray-700">$1</li>')
      .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded text-sm font-mono">$1</code>')
      .replace(/\n\n/g, "</p><p>")
      .replace(/\n/g, "<br/>");
  };

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <DocumentTextIcon className="w-6 h-6" style={{ color: brandColor }} />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">OPRA Request Generator</h1>
            <p className="text-sm text-gray-500">
              Open Public Records Act - Borough of Atlantic Highlands, NJ
            </p>
          </div>
        </div>
        <a
          href={GOVPILOT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 text-white rounded-lg hover:opacity-90 text-sm font-medium shadow"
          style={{ backgroundColor: brandColor }}
        >
          <ArrowTopRightOnSquareIcon className="w-4 h-4" />
          Submit on GovPilot
        </a>
      </div>

      {/* Legal Notice */}
      <div
        className="mb-6 p-4 rounded-xl border-l-4"
        style={{ borderColor: brandColor, backgroundColor: `${brandColor}08` }}
      >
        <div className="flex items-start gap-3">
          <InformationCircleIcon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: brandColor }} />
          <div className="text-sm text-gray-700">
            <p className="font-medium mb-1">Legal Authority: N.J.S.A. 47:1A-1 et seq.</p>
            <p>
              As amended by P.L. 2024, c.16 (effective September 3, 2024). The custodian must respond
              within <strong>7 business days</strong> for non-commercial requests. Fees: $0.05/letter
              page, $0.07/legal page. Electronic copies are provided at no charge for the medium.
            </p>
            <button
              onClick={loadRegulations}
              className="mt-2 text-xs font-medium underline hover:no-underline"
              style={{ color: brandColor }}
            >
              {showRegulations ? "Hide" : "View"} Full OPRA Regulations & Exemptions
            </button>
          </div>
        </div>
      </div>

      {/* Regulations Panel */}
      {showRegulations && regulations && (
        <div className="mb-6 bg-gray-50 border border-gray-200 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-gray-200 bg-white flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">
              OPRA Regulatory Reference (N.J.S.A. 47:1A-1 et seq.)
            </span>
            <button onClick={() => setShowRegulations(false)} className="text-gray-400 hover:text-gray-600">
              <ChevronUpIcon className="w-4 h-4" />
            </button>
          </div>
          <pre className="p-4 text-xs text-gray-600 whitespace-pre-wrap max-h-96 overflow-y-auto font-mono leading-relaxed">
            {regulations.regulations}
            {"\n\n"}
            {regulations.atlantic_highlands_info}
          </pre>
        </div>
      )}

      {/* Form */}
      <div className="bg-white rounded-xl shadow border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Request Details</h2>

        {/* Category Selection */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Record Category
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(categories).map(([key, cat]) => (
              <button
                key={key}
                onClick={() => {
                  setSelectedCategory(key);
                  setShowExamples(false);
                }}
                className={`p-3 rounded-lg border-2 text-left transition-colors ${
                  selectedCategory === key
                    ? "border-gray-300"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                style={
                  selectedCategory === key
                    ? { borderColor: brandColor, backgroundColor: `${brandColor}08` }
                    : {}
                }
              >
                <p className="font-medium text-sm text-gray-900">{cat.label}</p>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{cat.description}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Category Notes & Examples */}
        {currentCategory && (
          <div className="mb-5 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-start gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 mt-0.5 text-amber-600 flex-shrink-0" />
              <div className="text-xs text-amber-800">
                <p className="font-medium mb-1">Legal Note for {currentCategory.label}:</p>
                <p>{currentCategory.notes}</p>
              </div>
            </div>
            {currentCategory.example_records.length > 0 && (
              <div className="mt-2">
                <button
                  onClick={() => setShowExamples(!showExamples)}
                  className="flex items-center gap-1 text-xs font-medium text-amber-700 hover:text-amber-900"
                >
                  {showExamples ? <ChevronUpIcon className="w-3 h-3" /> : <ChevronDownIcon className="w-3 h-3" />}
                  {showExamples ? "Hide" : "Show"} Example Requests
                </button>
                {showExamples && (
                  <ul className="mt-2 space-y-1">
                    {currentCategory.example_records.map((ex, i) => (
                      <li key={i} className="text-xs text-amber-700 ml-4 list-disc">
                        <button
                          onClick={() => setSpecificRecords(ex)}
                          className="text-left hover:underline"
                        >
                          {ex}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}

        {/* Specific Records */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Specific Records Requested <span className="text-red-500">*</span>
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Be specific. Per OPRA, vague requests (e.g., &quot;any and all&quot;) may be denied.
            Include department, document type, and relevant identifiers.
          </p>
          <textarea
            value={specificRecords}
            onChange={(e) => setSpecificRecords(e.target.value)}
            placeholder="e.g., All purchase orders and vouchers from the Department of Public Works exceeding $5,000 for fiscal year 2024..."
            className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:border-transparent"
            style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
            rows={4}
          />
        </div>

        {/* Date Range */}
        <div className="grid grid-cols-2 gap-4 mb-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date Range Start
            </label>
            <input
              type="date"
              value={dateStart}
              onChange={(e) => setDateStart(e.target.value)}
              className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:border-transparent"
              style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date Range End
            </label>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:border-transparent"
              style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
            />
          </div>
        </div>

        {/* Delivery Format */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Preferred Delivery Format
          </label>
          <div className="flex gap-2">
            {[
              { id: "electronic", label: "Electronic (Email)", desc: "No charge for medium" },
              { id: "copies", label: "Paper Copies", desc: "$0.05-0.07/page" },
              { id: "inspect", label: "In-Person Inspection", desc: "At municipal offices" },
            ].map((fmt) => (
              <button
                key={fmt.id}
                onClick={() => setPreferredFormat(fmt.id)}
                className={`flex-1 p-3 rounded-lg border-2 text-left transition-colors ${
                  preferredFormat === fmt.id
                    ? "border-gray-300"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                style={
                  preferredFormat === fmt.id
                    ? { borderColor: brandColor, backgroundColor: `${brandColor}08` }
                    : {}
                }
              >
                <p className="font-medium text-sm text-gray-900">{fmt.label}</p>
                <p className="text-xs text-gray-500">{fmt.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Requestor Info */}
        <div className="border-t border-gray-200 pt-5 mt-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">
            Requestor Information
            <span className="text-xs font-normal text-gray-500 ml-2">
              (Optional - leave blank for placeholders)
            </span>
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Full Name</label>
              <input
                type="text"
                value={requestorName}
                onChange={(e) => setRequestorName(e.target.value)}
                placeholder="Your full legal name"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
              <input
                type="email"
                value={requestorEmail}
                onChange={(e) => setRequestorEmail(e.target.value)}
                placeholder="your.email@example.com"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Mailing Address</label>
              <input
                type="text"
                value={requestorAddress}
                onChange={(e) => setRequestorAddress(e.target.value)}
                placeholder="123 Main St, Atlantic Highlands, NJ 07716"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
              <input
                type="tel"
                value={requestorPhone}
                onChange={(e) => setRequestorPhone(e.target.value)}
                placeholder="(732) 555-0000"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm"
              />
            </div>
          </div>
        </div>

        {/* Additional Context */}
        <div className="mt-5">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Additional Context or Notes
          </label>
          <textarea
            value={additionalContext}
            onChange={(e) => setAdditionalContext(e.target.value)}
            placeholder="Any additional details that would help the custodian locate the records..."
            className="w-full p-3 border border-gray-300 rounded-lg text-sm"
            rows={2}
          />
        </div>

        {/* Generate Button */}
        <div className="mt-6 flex items-center gap-3">
          <button
            onClick={handleGenerate}
            disabled={isGenerating || !specificRecords.trim()}
            className="flex items-center gap-2 px-6 py-2.5 text-white rounded-lg hover:opacity-90 disabled:opacity-50 text-sm font-medium shadow"
            style={{ backgroundColor: brandColor }}
          >
            <DocumentTextIcon className="w-4 h-4" />
            {isGenerating ? "Generating..." : "Generate OPRA Request"}
          </button>
          {!specificRecords.trim() && (
            <span className="text-xs text-gray-500">
              Describe the records you want above
            </span>
          )}
        </div>
      </div>

      {/* Generated Output */}
      {generatedRequest && (
        <div className="bg-white rounded-xl shadow border border-gray-200 mb-6">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-xl">
            <span className="text-sm font-medium text-gray-700">Generated OPRA Request</span>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100"
              >
                {copied ? (
                  <CheckIcon className="w-3.5 h-3.5" style={{ color: brandColor }} />
                ) : (
                  <ClipboardIcon className="w-3.5 h-3.5" />
                )}
                {copied ? "Copied!" : "Copy"}
              </button>
              <button
                onClick={handleDownloadTxt}
                className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100"
              >
                <ArrowDownTrayIcon className="w-3.5 h-3.5" /> .txt
              </button>
              <button
                onClick={handleDownloadPdf}
                className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100"
              >
                <ArrowDownTrayIcon className="w-3.5 h-3.5" /> Formal
              </button>
              <a
                href={GOVPILOT_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-3 py-1.5 text-xs text-white rounded-lg hover:opacity-90"
                style={{ backgroundColor: brandColor }}
              >
                <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" /> Submit
              </a>
            </div>
          </div>
          <div
            ref={outputRef}
            className="p-6 prose prose-sm max-w-none prose-strong:text-gray-900"
            dangerouslySetInnerHTML={{ __html: renderFormatted(generatedRequest) }}
          />
          {isGenerating && (
            <div
              className="px-6 py-3 border-t flex items-center gap-2"
              style={{ backgroundColor: `${brandColor}08` }}
            >
              <div
                className="w-3 h-3 border-2 rounded-full animate-spin"
                style={{ borderColor: `${brandColor}40`, borderTopColor: brandColor }}
              />
              <span className="text-xs" style={{ color: brandColor }}>
                Generating request with legal citations...
              </span>
            </div>
          )}

          {/* Fact Check Section */}
          {!isGenerating && (
            <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 rounded-b-xl">
              <div className="flex items-center gap-3">
                <button
                  onClick={handleFactCheck}
                  disabled={isFactChecking}
                  className="flex items-center gap-2 px-4 py-2 border-2 rounded-lg text-sm font-medium transition-colors hover:bg-gray-100 disabled:opacity-50"
                  style={{ borderColor: brandColor, color: brandColor }}
                >
                  <ShieldCheckIcon className="w-4 h-4" />
                  {isFactChecking ? "Checking..." : "Fact-Check with Gemini"}
                </button>
                <span className="text-xs text-gray-500">
                  Verifies all statutory citations and legal claims using Gemini with Google Search grounding
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Fact Check Loading */}
      {isFactChecking && (
        <div className="bg-white rounded-xl shadow border border-gray-200 p-6 mb-6">
          <div className="flex items-center gap-3">
            <div
              className="w-5 h-5 border-2 rounded-full animate-spin"
              style={{ borderColor: `${brandColor}40`, borderTopColor: brandColor }}
            />
            <div>
              <p className="text-sm font-medium text-gray-900">Running Fact-Check...</p>
              <p className="text-xs text-gray-500">
                Gemini is verifying all citations against N.J.S.A. 47:1A-1 et seq. using Google Search grounding
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Fact Check Results */}
      {factCheckResult && !factCheckResult.error && (
        <div className="bg-white rounded-xl shadow border border-gray-200 mb-6">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-emerald-50 rounded-t-xl">
            <div className="flex items-center gap-2">
              <CheckCircleIcon className="w-5 h-5 text-emerald-600" />
              <span className="text-sm font-medium text-emerald-800">
                Fact-Check Complete
              </span>
            </div>
            <span className="text-xs text-emerald-600">
              Powered by {factCheckResult.model} {factCheckResult.search_grounding ? "with Google Search" : ""}
            </span>
          </div>
          <div
            className="p-6 prose prose-sm max-w-none prose-strong:text-gray-900"
            dangerouslySetInnerHTML={{ __html: renderFormatted(factCheckResult.fact_check_result) }}
          />
          {factCheckResult.grounding_sources.length > 0 && (
            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
              <p className="text-xs font-medium text-gray-700 mb-2">Grounding Sources:</p>
              <ul className="space-y-1">
                {factCheckResult.grounding_sources.map((src, i) => (
                  <li key={i} className="text-xs">
                    <a
                      href={src.uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                      style={{ color: brandColor }}
                    >
                      {src.title || src.uri}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Error display for fact check */}
      {factCheckResult?.error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2">
            <ExclamationTriangleIcon className="w-5 h-5 text-red-600" />
            <p className="text-sm text-red-800">Fact-check failed: {factCheckResult.error}</p>
          </div>
        </div>
      )}

      {/* GovPilot Link Footer */}
      <div className="text-center py-6 border-t border-gray-200">
        <p className="text-sm text-gray-600 mb-3">
          Ready to submit? Copy the generated text and paste it into the official form:
        </p>
        <a
          href={GOVPILOT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-6 py-3 text-white rounded-lg hover:opacity-90 text-sm font-medium shadow-lg"
          style={{ backgroundColor: brandColor }}
        >
          <ArrowTopRightOnSquareIcon className="w-5 h-5" />
          Open Atlantic Highlands OPRA Form on GovPilot
        </a>
        <p className="text-xs text-gray-400 mt-3">
          N.J.S.A. 47:1A-1 et seq. | P.L. 2024, c.16 | Borough of Atlantic Highlands, Monmouth County, NJ
        </p>
      </div>
    </div>
  );
}
