'use client';

import React, { useState, useMemo } from 'react';
import { Globe, FileText } from 'lucide-react';
import type { DeckSection, DeckAttachment } from '@/lib/presentationsApi';
import NarrativeBlock from './NarrativeBlock';
import TableBlock from './TableBlock';
import AttachmentBlock from './AttachmentBlock';
import ReactComponentBlock from './ReactComponentBlock';
import FilePreviewModal from '@/components/FilePreviewModal';

interface Props {
  title: string;
  sections: DeckSection[];
  attachments: DeckAttachment[];
  /** When provided, attachment previews fetch from this base URL (used by public viewer). */
  publicAttachmentBase?: string;
  /** When provided, [source: filename] citations resolve through this callback
   *  (returns a signed URL the viewer opens in FilePreviewModal). */
  onResolveCitation?: (filename: string) => Promise<{ url: string; filename: string }>;
}

const brandColor = '#385854';

/** Walk every narrative section body and pull out the unique filenames cited
 *  via [source: filename.pdf]. Used to render an always-visible Sources panel
 *  at the bottom — guarantees the user can always click through to citations
 *  even if the inline button rendering somehow fails (CSS conflict, JS error). */
function collectCitedFilenames(sections: DeckSection[]): string[] {
  const seen = new Set<string>();
  const re = /\[source:\s*([^\]]+)\]/g;
  for (const s of sections) {
    const body = (s as { body?: string }).body || '';
    let m: RegExpExecArray | null;
    while ((m = re.exec(body)) !== null) {
      for (const fn of m[1].split(/\s*[,;|]\s*|\s+\|\s+/)) {
        const trimmed = fn.trim();
        if (trimmed) seen.add(trimmed);
      }
    }
  }
  return Array.from(seen).sort();
}


/** Read-only renderer used by both public viewer and authenticated preview. */
export default function PresentationViewer({ title, sections, attachments, publicAttachmentBase, onResolveCitation }: Props) {
  const [preview, setPreview] = useState<{ url: string; filename: string } | null>(null);
  const citedFilenames = useMemo(() => collectCitedFilenames(sections), [sections]);

  const previewAttachment = (att: DeckAttachment) => {
    if (publicAttachmentBase) {
      setPreview({ url: `${publicAttachmentBase}/${att.id}`, filename: att.filename });
    } else {
      // Editor uses authenticated /api/documents/{id}/view-url — but this read-only
      // viewer is also used by the public flow, so we just no-op without a base.
      console.warn('No attachment preview base configured');
    }
  };

  const handleCitationClick = async (info: { filename: string }) => {
    if (!onResolveCitation) return;
    try {
      const { url, filename } = await onResolveCitation(info.filename);
      setPreview({ url, filename });
    } catch (e) {
      console.warn('Citation lookup failed', e);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex items-center gap-2 mb-6">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: brandColor }}>
          <Globe className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="text-xs text-gray-500">Atlantic Highlands</p>
        </div>
      </div>

      <div className="space-y-8">
        {sections.length === 0 && (
          <p className="text-sm text-gray-500 italic">This presentation has no sections.</p>
        )}
        {sections.map((s) => (
          <div key={s.id} className="bg-white rounded-lg border border-gray-200 p-5">
            {s.kind === 'narrative' && (
              <NarrativeBlock
                section={s} editable={false} onSave={() => {}} brandColor={brandColor}
                onCitationClick={onResolveCitation ? handleCitationClick : undefined}
              />
            )}
            {s.kind === 'table' && (
              <TableBlock section={s} editable={false} onSave={() => {}} brandColor={brandColor} />
            )}
            {s.kind === 'attachment' && (
              <AttachmentBlock section={s} attachments={attachments} onPreview={publicAttachmentBase ? previewAttachment : undefined} brandColor={brandColor} />
            )}
            {s.kind === 'react_component' && (
              <ReactComponentBlock section={s} editable={false} onSave={() => {}} brandColor={brandColor} />
            )}
          </div>
        ))}
      </div>

      {/* Always-visible Sources panel — guarantees doc links are reachable
          even if inline citation buttons fail to render (CSS conflict, etc.).
          Lists every unique filename cited anywhere in the deck. */}
      {citedFilenames.length > 0 && (
        <div className="mt-8 bg-white rounded-lg border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="w-4 h-4" style={{ color: brandColor }} />
            <h2 className="text-base font-semibold text-gray-900">
              Sources ({citedFilenames.length})
            </h2>
          </div>
          <p className="text-xs text-gray-500 mb-3">Click any document to open its preview.</p>
          <div className="flex flex-wrap gap-2">
            {citedFilenames.map((fn) => (
              <button
                key={fn}
                type="button"
                onClick={() => onResolveCitation && handleCitationClick({ filename: fn })}
                className="text-xs inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border transition-colors hover:bg-gray-50"
                style={{
                  color: brandColor,
                  borderColor: `${brandColor}40`,
                  backgroundColor: `${brandColor}08`,
                }}
              >
                <FileText className="w-3 h-3" />
                <span className="truncate max-w-md">{fn}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {preview && (
        <FilePreviewModal
          isOpen
          url={preview.url}
          filename={preview.filename}
          onClose={() => setPreview(null)}
          noAuth
        />
      )}
    </div>
  );
}
