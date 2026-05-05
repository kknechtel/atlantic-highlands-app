'use client';

import React, { useEffect, useState } from 'react';
import EnhancedMarkdownRenderer from '@/components/EnhancedMarkdownRenderer';
import type { DeckSection } from '@/lib/presentationsApi';

interface Props {
  section: DeckSection;
  editable: boolean;
  onSave: (patch: Partial<DeckSection>) => void;
  onCitationClick?: (info: { filename: string }) => void;
  brandColor?: string;
}

/**
 * Markdown narrative section. Edits in a textarea (no Tiptap dependency
 * to keep the build lean). Preview renders with the same markdown engine
 * used by chat — so charts and citations behave identically.
 */
export default function NarrativeBlock({ section, editable, onSave, onCitationClick, brandColor = '#385854' }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(section.title || '');
  const [body, setBody] = useState(section.body || '');

  useEffect(() => {
    setTitle(section.title || '');
    setBody(section.body || '');
  }, [section.id, section.title, section.body]);

  if (!editable || !editing) {
    return (
      <div className="space-y-2">
        {section.title && <h2 className="text-xl font-semibold text-gray-900">{section.title}</h2>}
        {section.body ? (
          <EnhancedMarkdownRenderer content={section.body} onCitationClick={onCitationClick} brandColor={brandColor} />
        ) : (
          <p className="text-sm text-gray-400 italic">(empty)</p>
        )}
        {editable && (
          <button onClick={() => setEditing(true)}
            className="text-xs text-gray-500 hover:text-gray-800 underline">
            Edit
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Section title"
        className="w-full text-xl font-semibold border-b border-gray-200 focus:outline-none focus:border-gray-400 pb-1"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Markdown body. Use [source: filename.pdf] to cite documents."
        rows={Math.max(8, body.split('\n').length + 1)}
        className="w-full text-sm font-mono border border-gray-200 rounded p-3 focus:outline-none focus:border-gray-400"
      />
      <div className="flex gap-2 text-xs">
        <button
          onClick={() => { onSave({ title, body }); setEditing(false); }}
          className="px-3 py-1.5 rounded text-white"
          style={{ backgroundColor: brandColor }}
        >Save</button>
        <button
          onClick={() => { setTitle(section.title || ''); setBody(section.body || ''); setEditing(false); }}
          className="px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
        >Cancel</button>
      </div>
    </div>
  );
}
