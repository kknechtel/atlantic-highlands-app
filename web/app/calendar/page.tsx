"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocuments, getDocumentViewUrl, type Document } from "@/lib/api";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  DocumentTextIcon,
  EyeIcon,
  CalendarDaysIcon,
} from "@heroicons/react/24/outline";

export default function CalendarPage() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewerDoc, setViewerDoc] = useState<{ url: string; filename: string } | null>(null);

  const { data: documents } = useQuery({
    queryKey: ["calendar-docs"],
    queryFn: async () => {
      const [agendas, minutes] = await Promise.all([
        getDocuments({ doc_type: "agenda" }),
        getDocuments({ doc_type: "minutes" }),
      ]);
      return [...agendas, ...minutes];
    },
  });

  // Parse dates from filenames
  const events = useMemo(() => {
    if (!documents) return new Map<string, Document[]>();
    const map = new Map<string, Document[]>();

    for (const doc of documents) {
      const dateStr = extractDateFromFilename(doc.filename);
      if (dateStr) {
        if (!map.has(dateStr)) map.set(dateStr, []);
        map.get(dateStr)!.push(doc);
      }
    }
    return map;
  }, [documents]);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const monthName = currentDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });

  const days = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(d);

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));

  const handleViewDoc = async (doc: Document) => {
    const { url } = await getDocumentViewUrl(doc.id);
    setViewerDoc({ url, filename: doc.filename });
  };

  const selectedDocs = selectedDate ? events.get(selectedDate) || [] : [];

  return (
    <div className="flex h-full">
      {/* Calendar */}
      <div className={`${viewerDoc ? "w-1/2" : "flex-1"} p-8 overflow-auto`}>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <CalendarDaysIcon className="w-6 h-6 text-green-600" />
            <h1 className="text-2xl font-bold text-gray-900">Meeting Calendar</h1>
          </div>
          <p className="text-sm text-gray-500">{documents?.length || 0} meeting documents linked</p>
        </div>

        {/* Month navigation */}
        <div className="bg-white rounded-xl shadow mb-6">
          <div className="flex items-center justify-between px-6 py-4 border-b">
            <button onClick={prevMonth} className="p-2 hover:bg-gray-100 rounded-lg">
              <ChevronLeftIcon className="w-5 h-5 text-gray-600" />
            </button>
            <h2 className="text-lg font-semibold text-gray-900">{monthName}</h2>
            <button onClick={nextMonth} className="p-2 hover:bg-gray-100 rounded-lg">
              <ChevronRightIcon className="w-5 h-5 text-gray-600" />
            </button>
          </div>

          {/* Calendar grid */}
          <div className="p-4">
            <div className="grid grid-cols-7 gap-1 mb-2">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div key={d} className="text-center text-xs font-medium text-gray-500 py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {days.map((day, i) => {
                if (day === null) return <div key={`empty-${i}`} />;
                const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                const hasEvents = events.has(dateStr);
                const isSelected = dateStr === selectedDate;
                const isToday = new Date().toISOString().slice(0, 10) === dateStr;

                return (
                  <button
                    key={day}
                    onClick={() => setSelectedDate(isSelected ? null : dateStr)}
                    className={`relative p-2 text-sm rounded-lg transition-colors ${
                      isSelected
                        ? "bg-green-600 text-white font-bold"
                        : hasEvents
                        ? "bg-green-50 text-green-800 hover:bg-green-100 font-medium"
                        : isToday
                        ? "bg-gray-100 font-medium"
                        : "hover:bg-gray-50"
                    }`}
                  >
                    {day}
                    {hasEvents && !isSelected && (
                      <span className="absolute bottom-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 bg-green-500 rounded-full" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Selected date documents */}
        {selectedDate && (
          <div className="bg-white rounded-xl shadow p-6">
            <h3 className="font-semibold text-gray-900 mb-3">
              {new Date(selectedDate + "T12:00:00").toLocaleDateString("en-US", {
                weekday: "long", month: "long", day: "numeric", year: "numeric",
              })}
            </h3>
            {selectedDocs.length > 0 ? (
              <div className="space-y-2">
                {selectedDocs.map((doc) => (
                  <div key={doc.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg hover:bg-green-50 transition-colors">
                    <DocumentTextIcon className="w-5 h-5 text-green-600 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
                      <p className="text-xs text-gray-500 capitalize">{doc.doc_type} &middot; {doc.category}</p>
                      {doc.notes && <p className="text-xs text-gray-500 mt-1 line-clamp-2">{doc.notes}</p>}
                    </div>
                    <button onClick={() => handleViewDoc(doc)}
                      className="p-2 text-green-600 hover:bg-green-100 rounded-lg" title="View">
                      <EyeIcon className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">No meeting documents for this date.</p>
            )}
          </div>
        )}

        {/* Upcoming events */}
        {!selectedDate && (
          <div className="bg-white rounded-xl shadow p-6">
            <h3 className="font-semibold text-gray-900 mb-3">Recent Meetings with Documents</h3>
            <div className="space-y-2">
              {Array.from(events.entries())
                .sort((a, b) => b[0].localeCompare(a[0]))
                .slice(0, 10)
                .map(([date, docs]) => (
                  <button key={date} onClick={() => setSelectedDate(date)}
                    className="w-full flex items-center gap-3 p-3 bg-gray-50 rounded-lg hover:bg-green-50 text-left transition-colors">
                    <div className="w-12 h-12 bg-green-100 rounded-lg flex flex-col items-center justify-center flex-shrink-0">
                      <span className="text-[10px] text-green-600 font-medium">
                        {new Date(date + "T12:00:00").toLocaleDateString("en-US", { month: "short" })}
                      </span>
                      <span className="text-lg font-bold text-green-700">
                        {new Date(date + "T12:00:00").getDate()}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">{docs.length} document{docs.length > 1 ? "s" : ""}</p>
                      <p className="text-xs text-gray-500 truncate">{docs.map((d) => d.doc_type).join(", ")}</p>
                    </div>
                  </button>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Document viewer */}
      {viewerDoc && (
        <div className="w-1/2 border-l flex flex-col bg-white">
          <div className="flex items-center justify-between px-4 py-2 border-b bg-gray-50">
            <span className="text-sm font-medium text-gray-600 truncate">{viewerDoc.filename}</span>
            <button onClick={() => setViewerDoc(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded">
              <ChevronLeftIcon className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden bg-gray-900">
            <iframe src={viewerDoc.url} className="w-full h-full border-0" title={viewerDoc.filename} />
          </div>
        </div>
      )}
    </div>
  );
}

function extractDateFromFilename(filename: string): string | null {
  // Try patterns like: 2026-03-02, 2025-12-15, 2024.01.24, 1.24.2024, 01_24_2024
  const patterns = [
    /(\d{4})-(\d{1,2})-(\d{1,2})/, // 2026-03-02
    /(\d{4})\.(\d{1,2})\.(\d{1,2})/, // 2024.01.15
    /(\d{1,2})\.(\d{1,2})\.(\d{4})/, // 1.24.2024
    /(\d{1,2})_(\d{1,2})_(\d{4})/, // 01_24_2024
    /(\d{1,2})-(\d{1,2})-(\d{4})/, // 01-24-2024
  ];

  for (const pattern of patterns) {
    const match = filename.match(pattern);
    if (match) {
      let y: number, m: number, d: number;
      if (parseInt(match[1]) > 1900) {
        // Year first: YYYY-MM-DD
        y = parseInt(match[1]); m = parseInt(match[2]); d = parseInt(match[3]);
      } else {
        // Month first: MM.DD.YYYY or MM_DD_YYYY
        m = parseInt(match[1]); d = parseInt(match[2]); y = parseInt(match[3]);
      }
      if (y >= 2000 && y <= 2030 && m >= 1 && m <= 12 && d >= 1 && d <= 31) {
        return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      }
    }
  }
  return null;
}
