'use client';

import React, { useState } from 'react';
import { ShieldCheck, ShieldAlert, ShieldX, HelpCircle, FileQuestion, Loader2, X } from 'lucide-react';
import { factCheckPresentation, type FactCheckRecord } from '@/lib/presentationsApi';

interface Props {
  presentationId: string;
  initial?: FactCheckRecord | null;
  onClose?: () => void;
}

const VERDICTS = {
  supported:   { label: 'Supported',   color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-300', Icon: ShieldCheck },
  partial:     { label: 'Partial',     color: 'text-amber-700',   bg: 'bg-amber-50',   border: 'border-amber-300',   Icon: ShieldAlert },
  unsupported: { label: 'Unsupported', color: 'text-red-700',     bg: 'bg-red-50',     border: 'border-red-300',     Icon: ShieldX },
  unresolved:  { label: 'Unresolved',  color: 'text-gray-700',    bg: 'bg-gray-50',    border: 'border-gray-300',    Icon: HelpCircle },
  no_source:   { label: 'No source',   color: 'text-gray-500',    bg: 'bg-gray-50',    border: 'border-gray-200',    Icon: FileQuestion },
};

export default function FactCheckPanel({ presentationId, initial, onClose }: Props) {
  const [data, setData] = useState<FactCheckRecord | null>(initial || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true); setError(null);
    try {
      setData(await factCheckPresentation(presentationId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Fact-check failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-[#385854]" />
          <span className="font-semibold text-sm text-gray-800">Fact Check</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded"><X className="w-4 h-4" /></button>
        )}
      </div>

      <div className="p-3 border-b border-gray-200">
        <button
          onClick={run}
          disabled={busy}
          className="w-full px-3 py-2 rounded text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2"
          style={{ backgroundColor: '#385854' }}
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
          {busy ? 'Checking…' : data ? 'Re-run fact check' : 'Run fact check'}
        </button>
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
      </div>

      {data && (
        <div className="p-3 border-b border-gray-200 grid grid-cols-5 gap-1 text-center text-[11px]">
          {(Object.keys(VERDICTS) as Array<keyof typeof VERDICTS>).map((k) => {
            const v = VERDICTS[k];
            const count = data.summary[k] || 0;
            return (
              <div key={k} className={`p-1.5 rounded ${v.bg} ${v.border} border`}>
                <div className={`${v.color} font-semibold text-base leading-tight`}>{count}</div>
                <div className={`${v.color} text-[9px] uppercase tracking-wide`}>{v.label}</div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {!data && !busy && (
          <p className="p-3 text-xs text-gray-500">
            Click <strong>Run fact check</strong> to verify every <code className="text-[10px]">[source: …]</code> citation in narrative sections against the indexed document.
          </p>
        )}
        {data?.results.map((r, i) => {
          const v = VERDICTS[r.verdict];
          const Icon = v.Icon;
          return (
            <div key={i} className={`mx-3 my-2 p-2 rounded border ${v.bg} ${v.border}`}>
              <div className="flex items-start gap-2">
                <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${v.color}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-[11px] mb-0.5">
                    <span className={`font-semibold ${v.color}`}>{v.label}</span>
                    <span className="text-gray-500 truncate">{r.label}</span>
                  </div>
                  {r.evidence_quote && (
                    <p className="text-[11px] text-gray-700 italic">&ldquo;{r.evidence_quote}&rdquo;</p>
                  )}
                  {r.missing.length > 0 && (
                    <p className="text-[11px] text-red-700 mt-1">Missing: {r.missing.join(', ')}</p>
                  )}
                  {r.conflicting.length > 0 && (
                    <p className="text-[11px] text-red-700 mt-1">Conflicting: {r.conflicting.join(', ')}</p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
