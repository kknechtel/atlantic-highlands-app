'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { getAuthToken } from '@/lib/api';
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Download,
  X,
  FileText,
  ExternalLink,
  Loader2,
  Search,
} from 'lucide-react';

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

interface PDFViewerProps {
  fileUrl: string;
  filename: string;
  onClose: () => void;
  isOpen: boolean;
  initialPage?: number;
  /** Render inline without modal backdrop (for split-pane / embedded use). */
  embedded?: boolean;
  /** Skip the Authorization header — for public/signed S3 URLs. */
  noAuth?: boolean;
  /** Highlight every occurrence of this term in the rendered text layer. The
   *  viewer also auto-jumps to the first page that contains the term. */
  highlightTerm?: string;
}

/** Escape regex special chars so a user-typed term is treated literally. */
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Build a single regex that matches any of the terms (case-insensitive). */
function buildHighlightRegex(term: string): RegExp | null {
  const cleaned = term.replace(/"/g, '').trim();
  if (!cleaned) return null;
  // Split on whitespace, drop very short tokens, escape each.
  const parts = cleaned.split(/\s+/).filter(p => p.length >= 2).map(escapeRegExp);
  if (!parts.length) return null;
  return new RegExp(`(${parts.join('|')})`, 'gi');
}

const PDFViewer: React.FC<PDFViewerProps> = ({
  fileUrl, filename, onClose, isOpen, initialPage, embedded, noAuth, highlightTerm,
}) => {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState<number>(initialPage && initialPage > 0 ? initialPage : 1);
  const [scale, setScale] = useState<number>(1.0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [matchPages, setMatchPages] = useState<number[]>([]);   // pages that contain the term
  const [matchIndex, setMatchIndex] = useState<number>(0);      // which match we're currently on
  const modalRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<any>(null);

  const pdfOptions = useMemo(() => ({
    cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
    standardFontDataUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/standard_fonts/`,
  }), []);

  const highlightRegex = useMemo(
    () => (highlightTerm ? buildHighlightRegex(highlightTerm) : null),
    [highlightTerm],
  );

  /**
   * Custom text renderer wraps every match in a <mark> element so the term
   * stands out inside the rendered text layer.
   */
  const customTextRenderer = useCallback(
    ({ str }: { str: string }) => {
      if (!highlightRegex) return str;
      // Reset lastIndex on each call (the regex is `g`).
      highlightRegex.lastIndex = 0;
      return str.replace(highlightRegex, '<mark class="ah-pdf-mark">$1</mark>');
    },
    [highlightRegex],
  );

  // Load PDF bytes
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setPdfUrl(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setPageNumber(initialPage && initialPage > 0 ? initialPage : 1);
    setNumPages(null);
    setMatchPages([]);
    setMatchIndex(0);

    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(fileUrl, noAuth ? undefined : { headers: getAuthToken() });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        const arr = new Uint8Array(await resp.arrayBuffer());
        if (cancelled) return;
        const blob = new Blob([arr], { type: 'application/pdf' });
        setPdfUrl(URL.createObjectURL(blob));
        setLoading(false);
      } catch (e: unknown) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load PDF');
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [isOpen, fileUrl, noAuth, initialPage]);

  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  /** Once the document is open AND we have a highlight term, scan every page's
   *  text content to build a list of matching page numbers, then jump to the
   *  first match. Capped at 200 pages so a 500-page CAFR doesn't lock the UI. */
  const scanForMatches = useCallback(
    async (pdf: any, totalPages: number) => {
      if (!highlightRegex) return;
      const matches: number[] = [];
      const cap = Math.min(totalPages, 200);
      for (let i = 1; i <= cap; i++) {
        try {
          const page = await pdf.getPage(i);
          const tc = await page.getTextContent();
          const text = tc.items.map((it: any) => ('str' in it ? it.str : '')).join(' ');
          highlightRegex.lastIndex = 0;
          if (highlightRegex.test(text)) matches.push(i);
        } catch {
          // ignore page-level errors and keep scanning
        }
      }
      setMatchPages(matches);
      if (matches.length > 0) {
        setMatchIndex(0);
        // Only auto-jump if caller didn't pin a specific initial page
        if (!initialPage) setPageNumber(matches[0]);
      }
    },
    [highlightRegex, initialPage],
  );

  const handleOverlayClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (modalRef.current && !modalRef.current.contains(event.target as Node)) onClose();
  };

  const downloadFile = () => {
    const link = document.createElement('a');
    link.href = fileUrl; link.download = filename; link.click();
  };
  const openInNewTab = () => window.open(fileUrl, '_blank');
  const changePage = (offset: number) => setPageNumber(p => Math.max(1, Math.min(p + offset, numPages || 1)));
  const zoomIn = () => setScale(s => Math.min(s + 0.25, 3.0));
  const zoomOut = () => setScale(s => Math.max(s - 0.25, 0.5));
  const resetZoom = () => setScale(1.0);

  const goToMatch = (delta: 1 | -1) => {
    if (!matchPages.length) return;
    const next = (matchIndex + delta + matchPages.length) % matchPages.length;
    setMatchIndex(next);
    setPageNumber(matchPages[next]);
  };

  if (!isOpen) return null;
  const isCompact = !!embedded;

  const inner = (
    <div
      ref={modalRef}
      className={embedded
        ? 'bg-white w-full h-full flex flex-col'
        : 'bg-white rounded-lg shadow-xl w-full max-w-4xl h-full max-h-[90vh] flex flex-col'}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Style for highlight marks. Scoped via class so it doesn't leak. */}
      <style>{`
        .ah-pdf-mark {
          background-color: #fde68a;
          color: inherit;
          padding: 0;
          border-radius: 2px;
          box-shadow: 0 0 0 1px rgba(217, 119, 6, 0.4);
        }
      `}</style>

      <div className={`flex items-center justify-between ${isCompact ? 'px-3 py-2' : 'p-4'} border-b border-gray-200`}>
        <h3 className={`${isCompact ? 'text-sm' : 'text-lg'} font-semibold text-gray-900 truncate`}>{filename}</h3>
        <div className="flex items-center gap-1">
          {/* Match navigation — visible only when we have a highlight term */}
          {highlightRegex && matchPages.length > 0 && (
            <div className="flex items-center gap-1 mr-2 text-xs">
              <Search className="w-3.5 h-3.5 text-amber-600" />
              <span className="text-gray-700 min-w-[80px] text-center">
                {matchIndex + 1} / {matchPages.length} match{matchPages.length === 1 ? '' : 'es'}
              </span>
              <button onClick={() => goToMatch(-1)} className="p-1 hover:bg-gray-100 rounded">
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => goToMatch(1)} className="p-1 hover:bg-gray-100 rounded">
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {numPages && numPages > 1 && (
            <div className="flex items-center gap-1 mr-2">
              <button onClick={() => changePage(-1)} disabled={pageNumber <= 1}
                className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded disabled:opacity-50`}>
                <ChevronLeft className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
              </button>
              <span className={`${isCompact ? 'text-xs' : 'text-sm'} text-gray-600 min-w-[60px] text-center`}>
                {pageNumber} / {numPages}
              </span>
              <button onClick={() => changePage(1)} disabled={pageNumber >= numPages}
                className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded disabled:opacity-50`}>
                <ChevronRight className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
              </button>
            </div>
          )}

          <div className="flex items-center gap-0.5 mr-2">
            <button onClick={zoomOut} className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded`}>
              <ZoomOut className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
            </button>
            <button onClick={resetZoom} className={`px-1.5 py-0.5 ${isCompact ? 'text-xs' : 'text-sm'} hover:bg-gray-100 rounded`}>
              {Math.round(scale * 100)}%
            </button>
            <button onClick={zoomIn} className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded`}>
              <ZoomIn className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
            </button>
          </div>

          {!isCompact && (
            <button onClick={openInNewTab}
              className="px-3 py-2 bg-[#385854] text-white rounded-lg hover:opacity-90 transition-colors flex items-center gap-2">
              <ExternalLink className="w-4 h-4" /> Open PDF
            </button>
          )}
          <button onClick={isCompact ? openInNewTab : downloadFile}
            className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded`}>
            {isCompact ? <ExternalLink className="w-3.5 h-3.5" /> : <Download className="w-4 h-4" />}
          </button>
          <button onClick={onClose} className={`${isCompact ? 'p-1' : 'p-2'} hover:bg-gray-100 rounded`}>
            <X className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
          </button>
        </div>
      </div>

      <div className={`flex-1 overflow-auto bg-gray-100 ${isCompact ? 'p-2' : 'p-4'}`}>
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-[#385854]" />
              <p className="text-gray-600">Loading PDF…</p>
            </div>
          </div>
        ) : pdfUrl && (numPages || !error) ? (
          <div className="flex justify-center">
            <Document
              file={pdfUrl}
              onLoadSuccess={(pdf) => {
                setNumPages(pdf.numPages);
                setError(null);
                setLoading(false);
                pdfDocRef.current = pdf;
                // Kick off async match scan when we have a term.
                if (highlightRegex) scanForMatches(pdf, pdf.numPages);
              }}
              onLoadError={(err) => { if (!numPages) setError('Failed to load PDF document'); console.error(err); }}
              loading={<div className="flex items-center justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-[#385854]" /></div>}
              error={<div className="text-center p-8"><p className="text-red-600">Failed to load PDF</p></div>}
              options={pdfOptions}
            >
              <Page
                pageNumber={pageNumber}
                scale={scale}
                renderTextLayer
                renderAnnotationLayer
                customTextRenderer={highlightRegex ? customTextRenderer : undefined}
                loading={<div className="flex items-center justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-[#385854]" /></div>}
                error={<div className="text-center p-8"><p className="text-red-600">Failed to load page</p></div>}
                className="shadow-lg"
              />
            </Document>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 mb-4">Unable to display PDF</p>
              <p className="text-sm text-gray-500 mb-4">{error}</p>
              <div className="space-x-2">
                <button onClick={openInNewTab} className="px-4 py-2 bg-[#385854] text-white rounded-lg hover:opacity-90">Open in New Tab</button>
                <button onClick={downloadFile} className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700">Download PDF</button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );

  if (embedded) return inner;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50" onClick={handleOverlayClick}>
      {inner}
    </div>
  );
};

export default PDFViewer;
