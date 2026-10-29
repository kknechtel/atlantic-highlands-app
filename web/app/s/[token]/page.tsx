'use client';
import { TOWN } from "@/lib/municipality";

import React, { useEffect, useState, use } from 'react';
import { Loader2 } from 'lucide-react';
import { getSharedAnswer, type SharedAnswer } from '@/lib/api';
import MarkdownWithCharts from '@/components/MarkdownWithCharts';

interface PageProps { params: Promise<{ token: string }> }

const brandColor = TOWN.brand_color;

/** Public, read-only view of one shared chat answer. No login required. */
export default function SharedAnswerPage({ params }: PageProps) {
  const { token } = use(params);
  const [data, setData] = useState<SharedAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSharedAnswer(token).then(setData).catch(e => setError(e.message));
  }, [token]);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="text-white px-4 py-3" style={{ backgroundColor: brandColor }}>
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-3">
          <a href="/" className="font-semibold">{TOWN.site_name}</a>
          <span className="text-xs opacity-80">Shared answer</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6">
        {!data && !error && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        )}
        {error && <p className="text-gray-600">{error}</p>}
        {data && (
          <article className="space-y-4">
            {data.question && (
              <div className="rounded-xl px-4 py-3 text-sm text-white whitespace-pre-wrap" style={{ backgroundColor: brandColor }}>
                {data.question}
              </div>
            )}
            <div className="rounded-xl bg-white border border-gray-200 shadow-sm px-4 py-3 text-sm text-gray-800">
              <MarkdownWithCharts content={data.answer} brandColor={brandColor} />
            </div>
            <p className="text-xs text-gray-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              This answer was written by AI from public records on {new Date(data.created_at).toLocaleDateString()} and
              can be wrong or out of date. Sources are named in brackets; verify anything important in the original documents.
            </p>
          </article>
        )}
      </main>
    </div>
  );
}
