"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { startScraper, getScraperStatus, getScraperRuns, type ScraperStatus, type ScraperRunSummary } from "@/lib/api";
import {
  GlobeAltIcon,
  PlayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";

type Site = { key: string; name: string; desc: string; siteId: string; note?: string };

// `siteId` is the human-readable site name the backend uses as the per_site key
// (e.g. "ahnj.com", "highlands-nj.municodemeetings.com"). Use it to look up
// per-site progress in status.per_site.
const SITES: Site[] = [
  { key: "ahnj", siteId: "ahnj.com", name: "ahnj.com", desc: "Borough website — Planning Board, Council Archives, Budgets, Ordinances, Annual Audits" },
  { key: "ecode", siteId: "ecode360.com", name: "ecode360.com", desc: "Document archive — Agendas, Minutes, Resolutions, Legislation, Budgets" },
  { key: "tri", siteId: "tridistrict.org", name: "tridistrict.org", desc: "HHRSD + AHES + HES + HHRS — BOE Agendas/Minutes, Budget, Curriculum, Performance Reports" },
  { key: "nj_state", siteId: "NJ State / Courts", name: "NJ State / Courts", desc: "ACFR school finance (0130, 2120, 2160), Sea Bright court opinions, Master Plan, DCA UFB" },
  { key: "highlands_borough", siteId: "highlandsnj.gov", name: "highlandsnj.gov", desc: "Borough of Highlands — regionalization, council letters, public docs" },
  { key: "highlands_meetings", siteId: "highlands-nj.municodemeetings.com", name: "Highlands Council (Municode)", desc: "Highlands Borough Council meeting agendas + packets" },
  { key: "opra", siteId: "OPRAmachine", name: "OPRAmachine", desc: "Crowdsourced OPRA public records requests for Atlantic Highlands" },
  { key: "police", siteId: "Police/Crime Data", name: "Police / Crime", desc: "SpotCrime, CrimeMapping, Nixle, AHPD page", note: "Limited — these are mostly interactive maps, not document repositories." },
  { key: "fire", siteId: "Fire/EMS Data", name: "Fire / EMS", desc: "PulsePoint, Monmouth County OEM, Fire Dept reports", note: "Limited — interactive feeds." },
  { key: "county", siteId: "Monmouth County", name: "Monmouth County", desc: "County clerk archives, property records, tax data" },
  { key: "census", siteId: "Census ACS Data", name: "Census ACS", desc: "Demographics, income, housing, poverty data via Census API" },
];

export default function ScraperPage() {
  const [selectedSites, setSelectedSites] = useState<string[]>(["ahnj", "ecode", "tri", "nj_state"]);
  const [polling, setPolling] = useState(false);
  const [recentOnly, setRecentOnly] = useState(false);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  const { data: status, refetch } = useQuery({
    queryKey: ["scraper-status"],
    queryFn: getScraperStatus,
    refetchInterval: polling ? 2000 : false,
  });

  // Run history. Refetch when a run finishes (running flips false) so the
  // newly-persisted row shows up without a manual reload.
  const { data: runs, refetch: refetchRuns } = useQuery({
    queryKey: ["scraper-runs"],
    queryFn: () => getScraperRuns(10),
  });
  useEffect(() => {
    if (status && !status.running && status.completed_at) {
      refetchRuns();
    }
  }, [status?.running, status?.completed_at]);

  // Start/stop polling based on running state
  useEffect(() => {
    if (status?.running) {
      setPolling(true);
    } else if (polling && status && !status.running) {
      setPolling(false);
    }
  }, [status?.running]);

  const [notice, setNotice] = useState<string | null>(null);

  const startMutation = useMutation({
    mutationFn: () => startScraper(
      selectedSites.length > 0 ? selectedSites : undefined,
      { historical: !recentOnly },
    ),
    onSuccess: (data) => {
      // Backend returns "Scraper is already running" when a previous run is still active.
      // Surface that to the user so the click doesn't appear to do nothing.
      setNotice(data.detail || null);
      setPolling(true);
      refetch();
    },
    onError: (err: Error) => {
      setNotice(err.message);
    },
  });

  const toggleSite = (key: string) => {
    setSelectedSites((prev) =>
      prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key]
    );
  };

  const isRunning = status?.running;

  return (
    <div className="p-3 md:p-8">
      <div className="mb-4 md:mb-6">
        <h1 className="text-xl md:text-2xl font-bold text-gray-900">Document Scraper</h1>
        <p className="text-xs md:text-sm text-gray-500 mt-1">
          Automatically download documents from town and school websites to S3
        </p>
      </div>

      {/* Site selection */}
      <div className="bg-white rounded-xl shadow p-4 md:p-6 mb-4 md:mb-6">
        <h2 className="font-semibold text-gray-900 mb-4">Sources</h2>
        <div className="space-y-3">
          {SITES.map((site) => {
            const stats = status?.per_site?.[site.siteId];
            return (
              <label
                key={site.key}
                className="flex items-center gap-3 p-3 rounded-lg border hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedSites.includes(site.key)}
                  onChange={() => toggleSite(site.key)}
                  disabled={isRunning}
                  className="rounded"
                />
                <GlobeAltIcon className="w-5 h-5 text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-900">{site.name}</p>
                    {stats && (
                      <span
                        className={
                          "text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide " +
                          (stats.status === "running"
                            ? "bg-blue-100 text-blue-700"
                            : stats.status === "done"
                            ? "bg-green-100 text-green-700"
                            : stats.status === "error"
                            ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-600")
                        }
                      >
                        {stats.status}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">{site.desc}</p>
                  {site.note && (
                    <p className="text-xs text-amber-600 mt-0.5">{site.note}</p>
                  )}
                  {stats && (
                    <p className="text-xs text-gray-600 mt-1">
                      {stats.documents_found} found · {stats.documents_uploaded} uploaded · {stats.documents_skipped} skipped
                      {stats.errors > 0 && ` · ${stats.errors} errors`}
                    </p>
                  )}
                </div>
              </label>
            );
          })}
        </div>

        <label className="mt-4 flex items-start gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={recentOnly}
            onChange={(e) => setRecentOnly(e.target.checked)}
            disabled={isRunning}
            className="mt-0.5 rounded"
          />
          <span className="text-sm text-gray-700">
            <span className="font-medium">Skip historical archives</span>
            <span className="block text-xs text-gray-500">
              Don't re-crawl frozen content (AHNJ 2005-2013 archives, older Planning Board years). ~30-40% faster.
            </span>
          </span>
        </label>

        <button
          onClick={() => startMutation.mutate()}
          disabled={isRunning || selectedSites.length === 0}
          className="mt-3 flex items-center gap-2 px-6 py-2.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          {isRunning ? (
            <>
              <ArrowPathIcon className="w-4 h-4 animate-spin" /> Scraping...
            </>
          ) : (
            <>
              <PlayIcon className="w-4 h-4" /> Start Scraper
            </>
          )}
        </button>

        {notice && (
          <p
            className={
              "mt-2 text-sm " +
              (startMutation.isError ? "text-red-500" : "text-blue-600")
            }
          >
            {notice}
          </p>
        )}
      </div>

      {/* Status panel */}
      {status && (status.running || status.completed_at) && (
        <div className="bg-white rounded-xl shadow p-4 md:p-6 mb-4 md:mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
            <h2 className="font-semibold text-gray-900">
              {status.running ? "Scraper Running" : "Last Run"}
            </h2>
            {status.running && status.current_site && (
              <span className="flex items-center gap-2 text-sm text-primary-600">
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
                Crawling {status.current_site}
              </span>
            )}
            {!status.running && status.completed_at && (
              <span className="flex items-center gap-2 text-sm text-green-600">
                <CheckCircleIcon className="w-4 h-4" />
                Completed
              </span>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2 md:gap-4">
            <div className="bg-blue-50 rounded-lg p-3 md:p-4 text-center">
              <p className="text-xl md:text-2xl font-bold text-blue-700">{status.documents_found}</p>
              <p className="text-[10px] md:text-xs text-blue-500">Found</p>
            </div>
            <div className="bg-green-50 rounded-lg p-3 md:p-4 text-center">
              <p className="text-xl md:text-2xl font-bold text-green-700">{status.documents_uploaded}</p>
              <p className="text-[10px] md:text-xs text-green-500">Uploaded</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 md:p-4 text-center">
              <p className="text-xl md:text-2xl font-bold text-gray-700">{status.documents_skipped}</p>
              <p className="text-[10px] md:text-xs text-gray-500">Skipped</p>
            </div>
          </div>

          {status.started_at && (
            <p className="mt-3 text-xs text-gray-400">
              Started: {new Date(status.started_at).toLocaleString()}
              {status.completed_at && ` | Completed: ${new Date(status.completed_at).toLocaleString()}`}
            </p>
          )}

          {status.errors.length > 0 && (
            <div className="mt-4 bg-red-50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <ExclamationTriangleIcon className="w-4 h-4 text-red-500" />
                <p className="text-sm font-medium text-red-700">
                  {status.errors.length} error{status.errors.length > 1 ? "s" : ""}
                </p>
              </div>
              <ul className="space-y-1 max-h-32 overflow-y-auto">
                {status.errors.map((err, i) => (
                  <li key={i} className="text-xs text-red-600 truncate">
                    {err}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Recent runs */}
      {runs && runs.length > 0 && (
        <div className="bg-white rounded-xl shadow p-4 md:p-6 mb-4 md:mb-6">
          <div className="flex items-center gap-2 mb-3">
            <ClockIcon className="w-4 h-4 text-gray-400" />
            <h2 className="font-semibold text-gray-900">Recent runs</h2>
            <span className="text-xs text-gray-400">({runs.length})</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {runs.map((r) => {
              const isOpen = expandedRun === r.id;
              const startedAt = new Date(r.started_at);
              return (
                <li key={r.id} className="py-2">
                  <button
                    onClick={() => setExpandedRun(isOpen ? null : r.id)}
                    className="w-full flex items-center gap-2 text-left hover:bg-gray-50 rounded px-2 py-1"
                  >
                    {isOpen ? (
                      <ChevronDownIcon className="w-4 h-4 text-gray-400 shrink-0" />
                    ) : (
                      <ChevronRightIcon className="w-4 h-4 text-gray-400 shrink-0" />
                    )}
                    <span className="text-xs text-gray-500 w-36 shrink-0">
                      {startedAt.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                    </span>
                    <span className="text-sm flex-1 min-w-0 truncate">
                      <span className="font-semibold text-green-700">+{r.documents_uploaded}</span>
                      <span className="text-gray-400"> new</span>
                      <span className="text-gray-400 mx-1">·</span>
                      <span className="text-gray-500">{r.documents_skipped} skipped</span>
                      {r.errors_count > 0 && (
                        <>
                          <span className="text-gray-400 mx-1">·</span>
                          <span className="text-red-600">{r.errors_count} error{r.errors_count > 1 ? "s" : ""}</span>
                        </>
                      )}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide text-gray-400 shrink-0">
                      {r.mode === "recent_only" ? "recent" : "full"}
                      {r.triggered_by === "schedule" && " · auto"}
                    </span>
                  </button>
                  {isOpen && r.new_docs.length > 0 && (
                    <ul className="mt-2 ml-6 space-y-1 max-h-64 overflow-y-auto">
                      {r.new_docs.map((d, i) => (
                        <li key={i} className="text-xs text-gray-600 truncate">
                          <span className="text-gray-400">{d.source}</span>
                          <span className="mx-1">·</span>
                          <a
                            href={d.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-600 hover:underline"
                            title={d.filename}
                          >
                            {d.filename}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                  {isOpen && r.new_docs.length === 0 && (
                    <p className="ml-6 mt-2 text-xs text-gray-400">No new documents — everything was already in the library.</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Info */}
      <div className="bg-gray-50 rounded-xl p-4 md:p-6 text-sm text-gray-600">
        <h3 className="font-medium text-gray-900 mb-2">How it works</h3>
        <ul className="list-disc list-inside space-y-1">
          <li>Crawls selected websites for downloadable documents (PDFs, DOCs, spreadsheets)</li>
          <li>Deduplicates against existing documents already in the system</li>
          <li>Uploads new files directly to AWS S3</li>
          <li>Creates document records with automatic categorization (agendas, minutes, budgets, etc.)</li>
          <li>Documents appear in the Document Library once uploaded</li>
        </ul>
      </div>
    </div>
  );
}
