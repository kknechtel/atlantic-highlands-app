"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { startScraper, getScraperStatus, type ScraperStatus } from "@/lib/api";
import {
  GlobeAltIcon,
  PlayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";

const SITES = [
  { key: "ahnj", name: "ahnj.com", desc: "Borough website — Planning Board, Council Archives, Budgets, Ordinances" },
  { key: "ecode", name: "ecode360.com", desc: "Document archive — Agendas, Minutes, Resolutions, Legislation, Budgets" },
  { key: "tri", name: "tridistrict.org", desc: "School district — BOE Minutes, Archives, District Reports" },
  { key: "nj_state", name: "NJ State / Courts", desc: "ACFR school finance, Sea Bright court opinions, Master Plan, Housing Plan" },
  { key: "opra", name: "OPRAmachine", desc: "Crowdsourced OPRA public records requests for Atlantic Highlands" },
  { key: "police", name: "Police / Crime", desc: "SpotCrime, CrimeMapping, Nixle alerts, AHPD blotter" },
  { key: "fire", name: "Fire / EMS", desc: "PulsePoint, Monmouth County OEM, Fire Dept reports" },
  { key: "county", name: "Monmouth County", desc: "County clerk archives, property records, tax data" },
  { key: "census", name: "Census ACS", desc: "Demographics, income, housing, poverty data via Census API" },
];

export default function ScraperPage() {
  const [selectedSites, setSelectedSites] = useState<string[]>(["ahnj", "ecode", "tri", "nj_state"]);
  const [polling, setPolling] = useState(false);

  const { data: status, refetch } = useQuery({
    queryKey: ["scraper-status"],
    queryFn: getScraperStatus,
    refetchInterval: polling ? 2000 : false,
  });

  // Start/stop polling based on running state
  useEffect(() => {
    if (status?.running) {
      setPolling(true);
    } else if (polling && status && !status.running) {
      setPolling(false);
    }
  }, [status?.running]);

  const startMutation = useMutation({
    mutationFn: () => startScraper(selectedSites.length > 0 ? selectedSites : undefined),
    onSuccess: () => {
      setPolling(true);
      refetch();
    },
  });

  const toggleSite = (key: string) => {
    setSelectedSites((prev) =>
      prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key]
    );
  };

  const isRunning = status?.running;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Document Scraper</h1>
          <p className="text-gray-500 mt-1">
            Automatically download documents from town and school websites to S3
          </p>
        </div>
      </div>

      {/* Site selection */}
      <div className="bg-white rounded-xl shadow p-6 mb-6">
        <h2 className="font-semibold text-gray-900 mb-4">Sources</h2>
        <div className="space-y-3">
          {SITES.map((site) => (
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
              <GlobeAltIcon className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm font-medium text-gray-900">{site.name}</p>
                <p className="text-xs text-gray-500">{site.desc}</p>
              </div>
            </label>
          ))}
        </div>

        <button
          onClick={() => startMutation.mutate()}
          disabled={isRunning || selectedSites.length === 0}
          className="mt-4 flex items-center gap-2 px-6 py-2.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
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

        {startMutation.isError && (
          <p className="mt-2 text-sm text-red-500">{(startMutation.error as Error).message}</p>
        )}
      </div>

      {/* Status panel */}
      {status && (status.running || status.completed_at) && (
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
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

          <div className="grid grid-cols-3 gap-4">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-blue-700">{status.documents_found}</p>
              <p className="text-xs text-blue-500">Found</p>
            </div>
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-green-700">{status.documents_uploaded}</p>
              <p className="text-xs text-green-500">Uploaded to S3</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-gray-700">{status.documents_skipped}</p>
              <p className="text-xs text-gray-500">Skipped (existing)</p>
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

      {/* Info */}
      <div className="bg-gray-50 rounded-xl p-6 text-sm text-gray-600">
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
