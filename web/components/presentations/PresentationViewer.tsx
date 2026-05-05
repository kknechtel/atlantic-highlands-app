'use client';

import React, { useState } from 'react';
import { Globe } from 'lucide-react';
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

/** Read-only renderer used by both public viewer and authenticated preview. */
export default function PresentationViewer({ title, sections, attachments, publicAttachmentBase, onResolveCitation }: Props) {
  const [preview, setPreview] = useState<{ url: string; filename: string } | null>(null);

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
