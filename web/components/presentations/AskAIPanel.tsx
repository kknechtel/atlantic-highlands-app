'use client';

import React, { useState } from 'react';
import { Sparkles, Send, X, Wand2, Check, Loader2 } from 'lucide-react';
import MarkdownWithCharts from '@/components/MarkdownWithCharts';

import type { DeckSection } from '@/lib/presentationsApi';
import type { DeckProposal } from '@/app/contexts/DeckChatContext';

type Proposal = DeckProposal;

interface ChatTurn {
  role: 'user' | 'assistant';
  text: string;
  toolCalls: { name: string; summary?: string }[];
  proposals: Proposal[];
}

interface AskAIPanelProps {
  presentationId: string;
  brandColor?: string;
  onAcceptProposal: (proposal: Proposal) => void;
  onClose?: () => void;
}

const API_BASE = typeof window !== 'undefined' ? '' : (process.env.NEXT_PUBLIC_API_URL || '');

export default function AskAIPanel({ presentationId, brandColor = '#385854', onAcceptProposal, onClose }: AskAIPanelProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const message = input.trim();
    if (!message || busy) return;
    setInput('');
    setBusy(true);

    const userTurn: ChatTurn = { role: 'user', text: message, toolCalls: [], proposals: [] };
    const aiTurn: ChatTurn = { role: 'assistant', text: '', toolCalls: [], proposals: [] };
    setTurns(t => [...t, userTurn, aiTurn]);

    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('ah_token') : null;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const history = turns.map(t => ({ role: t.role, content: t.role === 'user' ? t.text : t.text }));
      const resp = await fetch(`${API_BASE}/api/presentations/${presentationId}/ai-chat`, {
        method: 'POST', headers,
        body: JSON.stringify({ message, history }),
      });
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('No response stream');
      const decoder = new TextDecoder();
      let pending = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        let sep: number;
        while ((sep = pending.indexOf('\n\n')) !== -1) {
          const frame = pending.slice(0, sep);
          pending = pending.slice(sep + 2);
          if (!frame.trim() || frame.startsWith(':')) continue;
          let dataLine = '';
          for (const line of frame.split('\n')) {
            if (line.startsWith('data: ')) dataLine += line.slice(6);
            else if (line.startsWith('data:')) dataLine += line.slice(5);
          }
          if (!dataLine) continue;
          let d: any;
          try { d = JSON.parse(dataLine); } catch { continue; }

          setTurns(prev => prev.map((t, i) => {
            if (i !== prev.length - 1) return t;
            switch (d.type) {
              case 'delta': return { ...t, text: t.text + (d.content || '') };
              case 'tool_use': return { ...t, toolCalls: [...t.toolCalls, { name: d.name }] };
              case 'tool_result':
                return {
                  ...t,
                  toolCalls: t.toolCalls.map((tc, idx) =>
                    idx === t.toolCalls.length - 1 && tc.name === d.name
                      ? { ...tc, summary: d.summary }
                      : tc
                  ),
                };
              case 'proposal':
                return { ...t, proposals: [...t.proposals, d.input as Proposal] };
              default: return t;
            }
          }));
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setTurns(prev => prev.map((t, i) => i === prev.length - 1 ? { ...t, text: `Error: ${msg}` } : t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 text-white" style={{ backgroundColor: brandColor }}>
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4" />
          <span className="font-semibold text-sm">AI Assistant</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 hover:bg-white/20 rounded"><X className="w-4 h-4" /></button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {turns.length === 0 && (
          <div className="text-xs text-gray-500 leading-relaxed">
            Ask me to draft a section, rewrite for tone, or pull figures from the document corpus.
            <br /><br />
            Try: <em className="text-gray-700">&ldquo;Write an executive summary of FY24 borough finances&rdquo;</em>
            &nbsp;or&nbsp;
            <em className="text-gray-700">&ldquo;Build a table comparing AHES enrollment 2020-2024&rdquo;</em>.
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === 'user' ? 'flex justify-end' : ''}>
            <div className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${
              t.role === 'user' ? 'text-white' : 'bg-gray-50 border border-gray-200 text-gray-800'
            }`} style={t.role === 'user' ? { backgroundColor: brandColor } : {}}>
              {t.role === 'assistant' && t.toolCalls.length > 0 && (
                <div className="mb-2 space-y-0.5">
                  {t.toolCalls.map((tc, idx) => (
                    <div key={idx} className="text-[11px] text-gray-500 flex items-center gap-1">
                      <Wand2 className="w-3 h-3" />
                      <span>{tc.name}</span>
                      {tc.summary && <span className="text-gray-400">— {tc.summary}</span>}
                    </div>
                  ))}
                </div>
              )}
              {t.role === 'assistant' ? (
                t.text ? <MarkdownWithCharts content={t.text} brandColor={brandColor} />
                       : <span className="text-xs text-gray-400 italic">thinking…</span>
              ) : (
                <span className="whitespace-pre-wrap">{t.text}</span>
              )}

              {t.role === 'assistant' && t.proposals.length > 0 && (
                <div className="mt-3 space-y-2">
                  {t.proposals.map((p, pi) => (
                    <ProposalCard key={pi} proposal={p} onAccept={() => onAcceptProposal(p)} brandColor={brandColor} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="p-2 border-t border-gray-200 flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask the AI…"
          className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-gray-400"
          disabled={busy}
        />
        <button onClick={send} disabled={!input.trim() || busy}
          className="px-3 rounded-lg text-white disabled:opacity-50"
          style={{ backgroundColor: brandColor }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}

function ProposalCard({ proposal, onAccept, brandColor }: { proposal: Proposal; onAccept: () => void; brandColor: string }) {
  const { label, headline, body, meta } = describeProposal(proposal);
  return (
    <div className="border border-amber-300 bg-amber-50 rounded-lg p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
          AI proposal — {label}
        </span>
        <button
          onClick={onAccept}
          className="text-xs px-2 py-0.5 rounded text-white flex items-center gap-1"
          style={{ backgroundColor: brandColor }}
        >
          <Check className="w-3 h-3" /> Apply
        </button>
      </div>
      {headline && <p className="text-xs font-medium text-gray-800">{headline}</p>}
      {proposal.rationale && <p className="text-[11px] text-gray-600 italic mt-1">{proposal.rationale}</p>}
      {body && (
        <pre className={`text-[11px] text-gray-700 whitespace-pre-wrap mt-1 max-h-32 overflow-y-auto${body.kind === 'code' ? ' font-mono' : ''}`}>
          {body.text.slice(0, 600)}{body.text.length > 600 ? '…' : ''}
        </pre>
      )}
      {meta && <div className="text-[11px] text-gray-700 mt-1">{meta}</div>}
    </div>
  );
}

/** Map a proposal to display fields: label (uppercase tag), headline (one-line title),
 *  body (optional preview pre block), meta (optional row count etc).  Handles both
 *  the new proposal_type-discriminated shapes and the legacy kind-based shape. */
function describeProposal(p: Proposal): {
  label: string;
  headline?: string;
  body?: { kind: 'prose' | 'code'; text: string };
  meta?: string;
} {
  switch (p.proposal_type) {
    case 'section_edit':
      return {
        label: 'edit section',
        headline: p.section_id ? `Rewrite section ${p.section_id}` : 'Rewrite section',
        body: p.new_markdown ? { kind: 'prose', text: p.new_markdown } : undefined,
      };
    case 'new_section':
      return {
        label: 'new section',
        headline: p.heading,
        body: p.markdown ? { kind: 'prose', text: p.markdown } : undefined,
      };
    case 'inline_chart':
      return {
        label: `inline ${p.chart_type || 'bar'} chart`,
        headline: p.title || 'Chart',
        meta: p.headers ? `${p.headers.length} cols × ${(p.rows || []).length} rows` : undefined,
      };
    case 'diagram':
      return {
        label: 'mermaid diagram',
        headline: p.section_id ? `Add diagram to ${p.section_id}` : 'Add diagram',
        body: p.source ? { kind: 'code', text: p.source } : undefined,
      };
    case 'react_component':
      return {
        label: p.section_id ? 'replace component' : 'new component',
        headline: p.name || p.title,
        body: p.tsx ? { kind: 'code', text: p.tsx } : undefined,
      };
    case 'section_data_edit':
      return {
        label: 'replace component data',
        headline: p.section_id ? `Update data on ${p.section_id}` : 'Update data',
        body: p.new_data
          ? { kind: 'code', text: safeStringify(p.new_data) }
          : undefined,
      };
    case 'section_data_patch':
      return {
        label: 'patch component data',
        headline: p.section_id ? `Patch data on ${p.section_id}` : 'Patch data',
        meta: summarizePatchOps(p),
      };
    default:
      return {
        label: `${p.kind || 'section'} ${p.section_id ? '(rewrite)' : '(new)'}`,
        headline: p.title,
        body: p.body ? { kind: 'prose', text: p.body }
            : p.tsx ? { kind: 'code', text: p.tsx }
            : undefined,
        meta: p.kind === 'table' && p.headers
          ? `${p.headers.length} cols × ${(p.rows || []).length} rows`
          : undefined,
      };
  }
}

function safeStringify(v: unknown): string {
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

function summarizePatchOps(p: Proposal): string {
  const parts: string[] = [];
  const ap = (p.array_patches || []).reduce((n, x) => n + (x.items?.length || 0), 0);
  if (ap) parts.push(`${ap} row patch${ap === 1 ? '' : 'es'}`);
  if (p.scalar_set && Object.keys(p.scalar_set).length) parts.push(`${Object.keys(p.scalar_set).length} field set`);
  if (p.scalar_unset?.length) parts.push(`${p.scalar_unset.length} field unset`);
  const apx = (p.appends || []).reduce((n, x) => n + (x.items?.length || 0), 0);
  if (apx) parts.push(`${apx} append${apx === 1 ? '' : 's'}`);
  const rmx = (p.removes || []).reduce((n, x) => n + (x.keys?.length || 0), 0);
  if (rmx) parts.push(`${rmx} remove${rmx === 1 ? '' : 's'}`);
  return parts.join(', ') || 'no-op';
}
