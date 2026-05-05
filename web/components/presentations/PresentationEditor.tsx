'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Plus, Trash2, ChevronUp, ChevronDown, ShieldCheck,
  Globe, Lock, Unlock, Copy, ExternalLink, Loader2, ArrowLeft, Download, Wand2,
} from 'lucide-react';
import {
  type Presentation, type DeckSection, type DeckAttachment,
  getPresentation, updatePresentation, addSection, patchSection, deleteSection,
  publishPresentation, unpublishPresentation, setPublicPassword,
} from '@/lib/presentationsApi';
import { useDeckChat, type DeckProposal } from '@/app/contexts/DeckChatContext';
import NarrativeBlock from './NarrativeBlock';
import TableBlock from './TableBlock';
import AttachmentBlock from './AttachmentBlock';
import ReactComponentBlock from './ReactComponentBlock';
import FactCheckPanel from './FactCheckPanel';
// AskAIPanel removed: the global AI Analyst chat handles AI proposals via
// DeckChatContext when this editor mounts. One chat surface, not two.
import FilePreviewModal from '@/components/FilePreviewModal';
import { getDocumentViewUrl } from '@/lib/api';

interface Props {
  presentationId: string;
}

const brandColor = '#385854';

export default function PresentationEditor({ presentationId }: Props) {
  const router = useRouter();
  const [deck, setDeck] = useState<Presentation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showFactCheck, setShowFactCheck] = useState(false);
  const [titleEditing, setTitleEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [pwEditing, setPwEditing] = useState(false);
  const [pwDraft, setPwDraft] = useState('');
  const [preview, setPreview] = useState<{ url: string; filename: string } | null>(null);
  const [exporting, setExporting] = useState<null | 'pptx' | 'docx'>(null);
  const deckChat = useDeckChat();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getPresentation(presentationId);
        if (!cancelled) { setDeck(p); setTitleDraft(p.title); }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      }
    })();
    return () => { cancelled = true; };
  }, [presentationId]);

  // Bind this deck into the global DeckChatContext so the FAB chat can
  // propose sections directly into it. Unbind on unmount.
  useEffect(() => {
    if (!deck) return;
    const summary = [
      `Title: ${deck.title}`,
      `Sections: ${(deck.sections || []).length}`,
      ...(deck.sections || []).slice(0, 12).map((s, i) =>
        `  ${i + 1}. [${s.id}] ${s.kind}: ${s.title || '(untitled)'}`
      ),
    ].join('\n');

    deckChat.bindActiveDeck({
      id: deck.id,
      title: deck.title,
      summary,
      applyProposal: async (p: DeckProposal) => {
        await handleAcceptProposal(p);
        return true;
      },
    });
    return () => deckChat.bindActiveDeck(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck?.id, deck?.title, deck?.sections?.length]);

  if (error) {
    return (
      <div className="p-6 text-red-600">
        <p>Error: {error}</p>
        <button onClick={() => router.push('/presentations')} className="mt-4 underline text-sm">← Back to list</button>
      </div>
    );
  }
  if (!deck) {
    return <div className="p-6 flex items-center gap-2 text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>;
  }

  const saveTitle = async () => {
    const updated = await updatePresentation(presentationId, { title: titleDraft });
    setDeck(updated);
    setTitleEditing(false);
  };

  const handleAddSection = async (kind: 'narrative' | 'table' | 'attachment' | 'react_component') => {
    const titles: Record<typeof kind, string> = {
      narrative: 'New section', table: 'New table',
      attachment: 'Attachment', react_component: 'Custom component',
    };
    const updated = await addSection(presentationId, { kind, title: titles[kind] });
    setDeck(updated);
  };

  const handlePatch = async (sectionId: string, patch: Partial<DeckSection>) => {
    const updated = await patchSection(presentationId, sectionId, patch);
    setDeck(updated);
  };

  const handleDelete = async (sectionId: string) => {
    if (!confirm('Delete this section?')) return;
    const updated = await deleteSection(presentationId, sectionId);
    setDeck(updated);
  };

  const moveSection = async (idx: number, dir: -1 | 1) => {
    if (!deck) return;
    const sections = [...deck.sections];
    const target = idx + dir;
    if (target < 0 || target >= sections.length) return;
    [sections[idx], sections[target]] = [sections[target], sections[idx]];
    const updated = await updatePresentation(presentationId, { sections });
    setDeck(updated);
  };

  const handleAcceptProposal = async (proposal: any) => {
    const fields = {
      body: proposal.body,
      headers: proposal.headers,
      rows: proposal.rows,
      caption: proposal.caption,
      tsx: proposal.tsx,
      data: proposal.data,
    };
    if (proposal.section_id) {
      const updated = await patchSection(presentationId, proposal.section_id, {
        kind: proposal.kind, title: proposal.title, ...fields,
      });
      setDeck(updated);
    } else {
      const updated = await addSection(presentationId, {
        kind: proposal.kind, title: proposal.title || '', ...fields,
      });
      setDeck(updated);
    }
  };

  const handleExport = async (format: 'pptx' | 'docx') => {
    setExporting(format);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('ah_token') : null;
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(`/api/presentations/${presentationId}/export?format=${format}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const cd = res.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename="([^"]+)"/);
      const filename = m ? m[1] : `${deck?.title || 'presentation'}.${format}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      alert(`Export failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExporting(null);
    }
  };

  const handleAIEdit = async (sectionId: string, action: string) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('ah_token') : null;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`/api/presentations/${presentationId}/ai-edit`, {
      method: 'POST', headers,
      body: JSON.stringify({ section_id: sectionId, action }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(`AI edit failed: ${err.detail || res.statusText}`);
      return;
    }
    const updated = await res.json();
    setDeck(updated);
  };

  const togglePublish = async () => {
    const updated = deck.public_slug ? await unpublishPresentation(presentationId) : await publishPresentation(presentationId);
    setDeck(updated);
  };

  const setPassword = async () => {
    const updated = await setPublicPassword(presentationId, pwDraft);
    setDeck(updated);
    setPwEditing(false);
    setPwDraft('');
  };

  const publicUrl = deck.public_slug ? `${typeof window !== 'undefined' ? window.location.origin : ''}/p/${deck.public_slug}` : null;

  const previewAttachment = async (att: DeckAttachment) => {
    const { url } = await getDocumentViewUrl(att.document_id);
    setPreview({ url, filename: att.filename });
  };

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <button onClick={() => router.push('/presentations')} className="p-1.5 hover:bg-gray-100 rounded text-gray-600">
              <ArrowLeft className="w-4 h-4" />
            </button>
            {titleEditing ? (
              <div className="flex items-center gap-2 flex-1">
                <input
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && saveTitle()}
                  className="text-lg font-semibold border-b border-gray-300 focus:outline-none focus:border-gray-500 flex-1"
                  autoFocus
                />
                <button onClick={saveTitle} className="text-xs px-2 py-1 rounded text-white" style={{ backgroundColor: brandColor }}>Save</button>
              </div>
            ) : (
              <h1
                className="text-lg font-semibold text-gray-900 truncate cursor-pointer hover:underline"
                onClick={() => { setTitleEditing(true); setTitleDraft(deck.title); }}
              >
                {deck.title}
              </h1>
            )}
            <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${
              deck.status === 'published' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'
            }`}>{deck.status}</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowFactCheck(!showFactCheck)}
              className={`px-2.5 py-1.5 rounded text-xs flex items-center gap-1 ${showFactCheck ? 'bg-emerald-50 text-emerald-700 border border-emerald-300' : 'border border-gray-300 text-gray-600 hover:bg-gray-50'}`}
            >
              <ShieldCheck className="w-3.5 h-3.5" /> Fact-check
            </button>
            <button
              onClick={() => handleExport('pptx')}
              disabled={exporting !== null}
              className="px-2.5 py-1.5 rounded text-xs flex items-center gap-1 border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              title="Download as PowerPoint"
            >
              {exporting === 'pptx' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} PPTX
            </button>
            <button
              onClick={() => handleExport('docx')}
              disabled={exporting !== null}
              className="px-2.5 py-1.5 rounded text-xs flex items-center gap-1 border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              title="Download as Word"
            >
              {exporting === 'docx' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} DOCX
            </button>
            <button
              onClick={togglePublish}
              className={`px-2.5 py-1.5 rounded text-xs flex items-center gap-1 ${deck.public_slug ? 'bg-emerald-100 text-emerald-700 border border-emerald-300' : 'border border-gray-300 text-gray-700 hover:bg-gray-50'}`}
            >
              <Globe className="w-3.5 h-3.5" /> {deck.public_slug ? 'Published' : 'Publish'}
            </button>
          </div>
        </div>

        {publicUrl && (
          <div className="px-4 py-2 bg-emerald-50 border-b border-emerald-200 flex items-center gap-2 text-xs flex-shrink-0">
            <Globe className="w-3.5 h-3.5 text-emerald-700" />
            <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="text-emerald-800 hover:underline truncate flex-1">{publicUrl}</a>
            <button onClick={() => navigator.clipboard.writeText(publicUrl)} className="p-1 hover:bg-emerald-100 rounded" title="Copy"><Copy className="w-3 h-3" /></button>
            <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="p-1 hover:bg-emerald-100 rounded"><ExternalLink className="w-3 h-3" /></a>
            {!pwEditing ? (
              <button onClick={() => setPwEditing(true)} className="p-1 hover:bg-emerald-100 rounded" title={deck.has_password ? 'Change password' : 'Set password'}>
                {deck.has_password ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
              </button>
            ) : (
              <>
                <input
                  type="password" value={pwDraft} onChange={(e) => setPwDraft(e.target.value)}
                  placeholder="(empty to clear)"
                  className="px-2 py-0.5 text-xs border border-gray-300 rounded"
                />
                <button onClick={setPassword} className="text-xs px-2 py-0.5 rounded text-white" style={{ backgroundColor: brandColor }}>Save</button>
                <button onClick={() => { setPwEditing(false); setPwDraft(''); }} className="text-xs px-1.5 hover:bg-gray-100 rounded">×</button>
              </>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50">
          <div className="max-w-3xl mx-auto space-y-6">
            {deck.sections.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                <p className="text-sm">No sections yet.</p>
                <p className="text-xs mt-2">Use the AI panel or the buttons below to add one.</p>
              </div>
            )}
            {deck.sections.map((s, idx) => (
              <div key={s.id} className="bg-white rounded-lg border border-gray-200 p-5 group relative">
                <div className="absolute -left-10 top-2 hidden md:flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => moveSection(idx, -1)} disabled={idx === 0} className="p-1 hover:bg-gray-100 rounded disabled:opacity-30">
                    <ChevronUp className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => moveSection(idx, 1)} disabled={idx === deck.sections.length - 1} className="p-1 hover:bg-gray-100 rounded disabled:opacity-30">
                    <ChevronDown className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => handleDelete(s.id)} className="p-1 hover:bg-red-50 text-red-500 rounded">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {s.kind === 'narrative' && (
                  <div className="absolute right-2 top-2 hidden md:flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <SectionAIMenu sectionId={s.id} onEdit={handleAIEdit} brandColor={brandColor} />
                  </div>
                )}

                {s.kind === 'narrative' && (
                  <NarrativeBlock section={s} editable onSave={(p) => handlePatch(s.id, p)} brandColor={brandColor} />
                )}
                {s.kind === 'table' && (
                  <TableBlock section={s} editable onSave={(p) => handlePatch(s.id, p)} brandColor={brandColor} />
                )}
                {s.kind === 'attachment' && (
                  <AttachmentBlock section={s} attachments={deck.attachments} onPreview={previewAttachment} brandColor={brandColor} />
                )}
                {s.kind === 'react_component' && (
                  <ReactComponentBlock section={s} editable onSave={(p) => handlePatch(s.id, p)} brandColor={brandColor} />
                )}
              </div>
            ))}

            <div className="flex gap-2 justify-center pt-4 flex-wrap">
              <button onClick={() => handleAddSection('narrative')}
                className="flex items-center gap-1 px-3 py-2 text-xs border border-gray-300 rounded hover:bg-gray-100 text-gray-700">
                <Plus className="w-3.5 h-3.5" /> Narrative
              </button>
              <button onClick={() => handleAddSection('table')}
                className="flex items-center gap-1 px-3 py-2 text-xs border border-gray-300 rounded hover:bg-gray-100 text-gray-700">
                <Plus className="w-3.5 h-3.5" /> Table
              </button>
              <button onClick={() => handleAddSection('react_component')}
                className="flex items-center gap-1 px-3 py-2 text-xs border border-gray-300 rounded hover:bg-gray-100 text-gray-700">
                <Plus className="w-3.5 h-3.5" /> Custom component
              </button>
            </div>
          </div>
        </div>
      </div>

      {showFactCheck && (
        <div className="w-[340px] flex-shrink-0">
          <FactCheckPanel
            presentationId={presentationId}
            initial={deck.last_fact_check}
            onClose={() => setShowFactCheck(false)}
          />
        </div>
      )}

      {preview && (
        <FilePreviewModal
          isOpen
          url={preview.url}
          filename={preview.filename}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}


/** Per-section dropdown that fires the AI-edit endpoint for the chosen action. */
function SectionAIMenu({
  sectionId, onEdit, brandColor,
}: {
  sectionId: string;
  onEdit: (sectionId: string, action: string) => void;
  brandColor: string;
}) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);

  const fire = async (action: string) => {
    setOpen(false);
    setRunning(true);
    try { await onEdit(sectionId, action); }
    finally { setRunning(false); }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        disabled={running}
        className="px-2 py-1 text-[11px] rounded border border-gray-300 hover:bg-gray-100 flex items-center gap-1 text-gray-700 disabled:opacity-50"
        title="AI edit"
      >
        {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" style={{ color: brandColor }} />}
        AI
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-44 rounded-md shadow-lg bg-white border border-gray-200 z-10 text-xs overflow-hidden">
          {[
            ['rewrite_tighter', 'Rewrite tighter'],
            ['expand', 'Expand with detail'],
            ['fact_polish', 'Polish facts'],
            ['translate_plain', 'Plain English'],
            ['summarize', 'Summarize as bullets'],
          ].map(([k, label]) => (
            <button
              key={k}
              onClick={() => fire(k)}
              className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-gray-800"
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
