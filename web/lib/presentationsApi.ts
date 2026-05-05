/**
 * Presentations API client.
 */

const API_BASE = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "");

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("ah_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  Object.assign(headers, authHeaders());
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export type SectionKind = "narrative" | "table" | "attachment" | "react_component";

export interface DeckSection {
  id: string;
  kind: SectionKind;
  title?: string;
  body?: string;
  headers?: string[];
  rows?: string[][];
  caption?: string;
  attachment_id?: string;
  /** TSX source for react_component sections — sandboxed via react-live. */
  tsx?: string;
  /** Structured data exposed to the TSX as the `data` identifier. */
  data?: unknown;
}

export interface DeckAttachment {
  id: string;
  document_id: string;
  filename: string;
  caption?: string | null;
}

export interface FactCheckRecord {
  ran_at: string;
  summary: { supported: number; partial: number; unsupported: number; unresolved: number; no_source: number };
  results: Array<{
    section_id: string | null;
    kind: "filename" | "doc_id";
    id: string;
    label: string;
    verdict: "supported" | "partial" | "unsupported" | "unresolved" | "no_source";
    evidence_quote: string;
    claim: string;
    missing: string[];
    conflicting: string[];
  }>;
}

export interface Presentation {
  id: string;
  title: string;
  slug: string | null;
  public_slug: string | null;
  status: "draft" | "published" | "archived";
  sections: DeckSection[];
  attachments: DeckAttachment[];
  theme: Record<string, unknown>;
  last_fact_check: FactCheckRecord | null;
  has_password: boolean;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export const listPresentations = () => request<Presentation[]>("/api/presentations");
export const getPresentation = (id: string) => request<Presentation>(`/api/presentations/${id}`);

export const createPresentation = (title: string) =>
  request<Presentation>("/api/presentations", { method: "POST", body: JSON.stringify({ title }) });

/** Build a new presentation from a chat transcript (assistant structures it
 *  into 4-8 sections, preserving citations). */
export const createPresentationFromChat = (
  messages: { role: string; content: string }[],
  title_hint?: string,
) =>
  request<Presentation>("/api/presentations/from-chat", {
    method: "POST",
    body: JSON.stringify({ messages, title_hint }),
  });

export const updatePresentation = (id: string, patch: Partial<Pick<Presentation, "title" | "sections" | "attachments" | "theme">>) =>
  request<Presentation>(`/api/presentations/${id}`, { method: "PUT", body: JSON.stringify(patch) });

export const deletePresentation = (id: string) =>
  request<{ ok: boolean }>(`/api/presentations/${id}`, { method: "DELETE" });

export const addSection = (id: string, section: Partial<DeckSection> & { kind: SectionKind; title: string; after_section_id?: string }) =>
  request<Presentation>(`/api/presentations/${id}/section`, { method: "POST", body: JSON.stringify(section) });

export const patchSection = (id: string, sectionId: string, patch: Partial<DeckSection>) =>
  request<Presentation>(`/api/presentations/${id}/section/${sectionId}`, { method: "PATCH", body: JSON.stringify(patch) });

export const deleteSection = (id: string, sectionId: string) =>
  request<Presentation>(`/api/presentations/${id}/section/${sectionId}`, { method: "DELETE" });

export const addAttachment = (id: string, document_id: string, caption?: string) =>
  request<Presentation>(`/api/presentations/${id}/attachments`, { method: "POST", body: JSON.stringify({ document_id, caption }) });

export const removeAttachment = (id: string, attId: string) =>
  request<Presentation>(`/api/presentations/${id}/attachments/${attId}`, { method: "DELETE" });

export const publishPresentation = (id: string) =>
  request<Presentation>(`/api/presentations/${id}/publish`, { method: "POST" });
export const unpublishPresentation = (id: string) =>
  request<Presentation>(`/api/presentations/${id}/unpublish`, { method: "POST" });

export const setPublicPassword = (id: string, password: string) =>
  request<Presentation>(`/api/presentations/${id}/password`, { method: "POST", body: JSON.stringify({ password }) });

export const factCheckPresentation = (id: string) =>
  request<FactCheckRecord>(`/api/presentations/${id}/fact-check`, { method: "POST" });

/** Public, no-auth fetch. The public-viewer page uses these. */
export async function fetchPublicMeta(slug: string): Promise<{ title: string; has_password: boolean }> {
  const res = await fetch(`${API_BASE}/api/presentations/public/${slug}/meta`);
  if (!res.ok) throw new Error("Not found");
  return res.json();
}
export async function fetchPublicDeck(slug: string, password?: string): Promise<{
  title: string; sections: DeckSection[]; attachments: DeckAttachment[];
  theme: Record<string, unknown>; published_at: string | null;
}> {
  const headers: Record<string, string> = {};
  if (password) headers["X-Deck-Password"] = password;
  const res = await fetch(`${API_BASE}/api/presentations/public/${slug}`, { headers });
  if (res.status === 401) throw new Error("password_required");
  if (!res.ok) throw new Error("Not found");
  return res.json();
}
