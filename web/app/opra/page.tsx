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
  BuildingLibraryIcon,
  AcademicCapIcon,
} from "@heroicons/react/24/outline";

const API_BASE = "";
const brandColor = "#385854";
const GOVPILOT_URL =
  "https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1";

type EntityKey = "borough" | "school";

interface AgencyInfo {
  agency_name: string;
  address_line: string;
  phone: string;
  email: string;
  custodian_name: string;
  custodian_title: string;
  submission_note: string;
  govpilot_url?: string;
  form_url?: string;
}

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
  // Entity selector — borough vs school district. Drives which custodian
  // address, which categories, and which submission link the page shows.
  const [entity, setEntity] = useState<EntityKey>("borough");
  const [agencies, setAgencies] = useState<Record<EntityKey, AgencyInfo> | null>(null);

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
  // Certification answers (typical defaults — clearable in UI).
  const [certNoIndictable, setCertNoIndictable] = useState(true);
  const [certNotCommercial, setCertNotCommercial] = useState(true);
  const [certLitigation, setCertLitigation] = useState(false);

  // Output state
  const [generatedRequest, setGeneratedRequest] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPdfBuilding, setIsPdfBuilding] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showExamples, setShowExamples] = useState(false);

  // Fact-check state
  const [factCheckResult, setFactCheckResult] = useState<FactCheckResult | null>(null);
  const [isFactChecking, setIsFactChecking] = useState(false);

  // Regulations panel
  const [showRegulations, setShowRegulations] = useState(false);
  const [regulations, setRegulations] = useState<{ regulations: string; entity_info?: string } | null>(null);

  const outputRef = useRef<HTMLDivElement>(null);

  // Load agencies once
  useEffect(() => {
    fetch(`${API_BASE}/api/opra/agencies`)
      .then((r) => r.json())
      .then((data) => setAgencies(data as Record<EntityKey, AgencyInfo>))
      .catch(console.error);
  }, []);

  // Re-load categories whenever the entity changes (school vs borough have
  // different applicable categories and different example wording).
  useEffect(() => {
    fetch(`${API_BASE}/api/opra/categories?entity=${entity}`)
      .then((r) => r.json())
      .then((cats: Record<string, RecordCategory>) => {
        setCategories(cats);
        // If the previously-selected category isn't valid for this entity,
        // fall back to "financial" (always available) so the form stays usable.
        if (!cats[selectedCategory]) {
          setSelectedCategory(cats["financial"] ? "financial" : Object.keys(cats)[0] || "custom");
        }
        setShowExamples(false);
      })
      .catch(console.error);
    // We intentionally don't depend on selectedCategory — only refetch when
    // entity changes; selectedCategory is reset inline if invalidated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity]);

  const agency = agencies?.[entity];

  // Load regulations on demand (entity-specific so the submission info block
  // shown matches the selected agency).
  const loadRegulations = async () => {
    if (regulations) {
      setShowRegulations(!showRegulations);
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/api/opra/regulations?entity=${entity}`);
      const data = await r.json();
      setRegulations(data);
      setShowRegulations(true);
    } catch (e) {
      console.error(e);
    }
  };

  const buildRequestPayload = () => ({
    entity,
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
    cert_no_indictable: certNoIndictable,
    cert_not_commercial: certNotCommercial,
    cert_litigation: certLitigation,
  });

  const handleGenerate = async () => {
    setGeneratedRequest("");
    setFactCheckResult(null);
    setIsGenerating(true);

    try {
      const response = await fetch(`${API_BASE}/api/opra/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestPayload()),
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

  /** Download a formal, prefilled PDF that mirrors the NJ DCA model OPRA
   *  form. Long requests overflow into a Detailed Records Request attachment
   *  page rather than being crammed into the page-1 box. */
  const handleDownloadPdf = async () => {
    if (!specificRecords.trim()) {
      alert("Describe the records you want above first — the form box can't be left blank.");
      return;
    }
    setIsPdfBuilding(true);
    try {
      const r = await fetch(`${API_BASE}/api/opra/generate-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestPayload()),
      });
      if (!r.ok) {
        const detail = await r.text().catch(() => "");
        throw new Error(`PDF generation failed (${r.status}): ${detail.slice(0, 200)}`);
      }
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      const fname = m ? m[1] : `OPRA-Request-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      console.error("PDF generation failed:", e);
      alert(`PDF download failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIsPdfBuilding(false);
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
              Open Public Records Act &mdash;{" "}
              {agency ? agency.agency_name : (entity === "school" ? "Henry Hudson Regional School District" : "Borough of Atlantic Highlands")}
            </p>
          </div>
        </div>
        {entity === "borough" ? (
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
        ) : agency?.email ? (
          <a
            href={`mailto:${agency.email}?subject=${encodeURIComponent("OPRA Request — " + (categories[selectedCategory]?.label || ""))}`}
            className="flex items-center gap-2 px-4 py-2 text-white rounded-lg hover:opacity-90 text-sm font-medium shadow"
            style={{ backgroundColor: brandColor }}
          >
            <ArrowTopRightOnSquareIcon className="w-4 h-4" />
            Email {agency.custodian_name.split(" ")[0]}
          </a>
        ) : null}
      </div>

      {/* Entity selector — borough vs school */}
      <div className="mb-6">
        <p className="text-sm font-medium text-gray-700 mb-2">Submitting to</p>
        <div className="grid grid-cols-2 gap-2">
          {([
            { id: "borough", label: "Borough of Atlantic Highlands", sub: "Michelle Clark, Municipal Clerk", Icon: BuildingLibraryIcon },
            { id: "school",  label: "Henry Hudson Regional School District", sub: "Janet Sherlock, School Business Administrator", Icon: AcademicCapIcon },
          ] as const).map(({ id, label, sub, Icon }) => (
            <button
              key={id}
              onClick={() => setEntity(id)}
              className={`p-3 rounded-lg border-2 text-left transition-colors flex items-start gap-3 ${
                entity === id ? "border-gray-300" : "border-gray-200 hover:border-gray-300"
              }`}
              style={
                entity === id
                  ? { borderColor: brandColor, backgroundColor: `${brandColor}08` }
                  : {}
              }
            >
              <Icon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: entity === id ? brandColor : "#9CA3AF" }} />
              <div>
                <p className="font-medium text-sm text-gray-900">{label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Legal Notice — entity-specific submission info */}
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
            {agency && (
              <p className="mt-2 text-xs">
                <strong>Custodian:</strong> {agency.custodian_name}, {agency.custodian_title} &middot;{" "}
                <a href={`mailto:${agency.email}`} className="underline" style={{ color: brandColor }}>
                  {agency.email}
                </a>{" "}
                &middot; {agency.phone} &middot; {agency.address_line}
              </p>
            )}
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
            {regulations.entity_info || ""}
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
          <p className="text-xs text-gray-500 mb-2">
            Any context that would help the custodian narrow scope, prioritize, or
            understand the request. If the request is detailed, this and the description
            above will move to the <strong>Detailed Records Request</strong> attachment
            page in the PDF rather than be crammed into the form box.
          </p>
          <textarea
            value={additionalContext}
            onChange={(e) => setAdditionalContext(e.target.value)}
            placeholder="e.g. 'If the audit and management letter exceed 500 pages, please contact me before processing so we can scope it down.'"
            className="w-full p-3 border border-gray-300 rounded-lg text-sm"
            rows={3}
          />
        </div>

        {/* Certifications — required by NJSA 2C:28-3 */}
        <div className="mt-5 p-3 border border-gray-200 rounded-lg bg-gray-50">
          <p className="text-xs font-medium text-gray-700 mb-2">
            Certifications (under penalty of N.J.S.A. 2C:28-3)
          </p>
          <label className="flex items-start gap-2 mb-1.5 cursor-pointer">
            <input
              type="checkbox" checked={certNoIndictable}
              onChange={(e) => setCertNoIndictable(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-xs text-gray-700">
              I <strong>HAVE NOT</strong> been convicted of any indictable offense under
              the laws of New Jersey, any other state, or the United States.
            </span>
          </label>
          <label className="flex items-start gap-2 mb-1.5 cursor-pointer">
            <input
              type="checkbox" checked={certNotCommercial}
              onChange={(e) => setCertNotCommercial(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-xs text-gray-700">
              I <strong>WILL NOT</strong> use the requested government records for a
              commercial purpose (as defined in N.J.S.A. 47:1A-1.1).
            </span>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox" checked={certLitigation}
              onChange={(e) => setCertLitigation(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-xs text-gray-700">
              I <strong>AM</strong> seeking these records in connection with a legal
              proceeding (check only if true; identification of the proceeding is required
              in the request body below).
            </span>
          </label>
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
                disabled={isPdfBuilding}
                className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-lg hover:bg-gray-100 disabled:opacity-50"
                title="Download as a formal, prefilled OPRA Request PDF (mirrors the NJ DCA model form). Long requests overflow into a Detailed Records Request attachment page rather than being crammed into the form box."
              >
                <ArrowDownTrayIcon className="w-3.5 h-3.5" />
                {isPdfBuilding ? "Building…" : "Form PDF"}
              </button>
              {entity === "borough" ? (
                <a
                  href={GOVPILOT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 px-3 py-1.5 text-xs text-white rounded-lg hover:opacity-90"
                  style={{ backgroundColor: brandColor }}
                >
                  <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" /> Submit
                </a>
              ) : agency?.email ? (
                <a
                  href={`mailto:${agency.email}?subject=${encodeURIComponent("OPRA Request — " + (categories[selectedCategory]?.label || ""))}`}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs text-white rounded-lg hover:opacity-90"
                  style={{ backgroundColor: brandColor }}
                >
                  <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" /> Email Custodian
                </a>
              ) : null}
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

      {/* Submission footer — entity-aware */}
      <div className="text-center py-6 border-t border-gray-200">
        {entity === "borough" ? (
          <>
            <p className="text-sm text-gray-600 mb-3">
              Ready to submit? Download the prefilled <strong>Form PDF</strong> above
              and email it to <a href="mailto:clerk@ahnj.com" className="underline" style={{ color: brandColor }}>clerk@ahnj.com</a>,
              or paste the generated text into the GovPilot online form.
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
          </>
        ) : (
          <>
            <p className="text-sm text-gray-600 mb-3">
              Ready to submit? Download the prefilled <strong>Form PDF</strong> above
              and email it to{" "}
              <a href={`mailto:${agency?.email || "jsherlock@henryhudsonreg.k12.nj.us"}`} className="underline" style={{ color: brandColor }}>
                {agency?.email || "jsherlock@henryhudsonreg.k12.nj.us"}
              </a>
              . Mail or fax (732-872-1315) to <strong>1 Grand Tour, Highlands, NJ 07732</strong> also accepted.
            </p>
            {agency?.form_url && (
              <a
                href={agency.form_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-6 py-3 text-white rounded-lg hover:opacity-90 text-sm font-medium shadow-lg"
                style={{ backgroundColor: brandColor }}
              >
                <ArrowTopRightOnSquareIcon className="w-5 h-5" />
                View District&apos;s Official OPRA Form
              </a>
            )}
          </>
        )}
        <p className="text-xs text-gray-400 mt-3">
          N.J.S.A. 47:1A-1 et seq. | P.L. 2024, c.16 |{" "}
          {entity === "school" ? "Henry Hudson Regional School District" : "Borough of Atlantic Highlands, Monmouth County, NJ"}
        </p>
      </div>
    </div>
  );
}
