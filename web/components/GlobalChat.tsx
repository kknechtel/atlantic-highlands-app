"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchDocuments, getDocumentViewUrl, getChatSessions, getChatHistory, type Document } from "@/lib/api";
import EnhancedMessageComponent, { type ChatMessage, type ToolActivity } from "@/components/EnhancedMessageComponent";
import { useDeckChat, type DeckProposal } from "@/app/contexts/DeckChatContext";
import {
  XMarkIcon, PaperAirplaneIcon, SparklesIcon,
  MinusIcon, DocumentTextIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon,
  MagnifyingGlassIcon, LinkIcon, GlobeAltIcon,
  ArrowDownTrayIcon, ClockIcon, ArrowPathIcon,
  LightBulbIcon, DocumentChartBarIcon, CpuChipIcon, PlusIcon,
  ClipboardDocumentIcon, CheckIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";
// Non-streaming requests use the relative URL (Amplify proxy → backend).
// Streaming SSE requests bypass Amplify and hit the FastAPI box directly via
// the api.* HTTPS endpoint, because Amplify's SSR Compute has a hard 30s
// response timeout that kills long Claude streams. NEXT_PUBLIC_API_DIRECT_URL
// is set to https://api.ahnj.info in Amplify env (mirrors bank-processor's
// API_DIRECT pattern).
const API_BASE = "";
const API_DIRECT =
  process.env.NEXT_PUBLIC_API_DIRECT_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "";

// Panel widths — matches bank-processor's RKCAIChatPanel.
const CHAT_WIDTH_DEFAULT = 480;
const CHAT_WIDTH_WIDE = Math.min(900, typeof window !== "undefined" ? Math.max(480, window.innerWidth * 0.6) : 720);
const CHAT_WIDTH_MIN = 360;
const CHAT_WIDTH_KEY = "ah_chat_width";

/** Stable ref to "is the chat panel currently visible to the user".
 *  Read inside the streaming reader so the 'done' handler can decide
 *  whether to flag unread + fire a browser notification. */
function useHiddenRef(isOpen: boolean, isMinimized: boolean, dismissed: boolean) {
  const ref = useRef(false);
  useEffect(() => {
    ref.current = dismissed || !isOpen || isMinimized;
  }, [isOpen, isMinimized, dismissed]);
  return ref;
}

const DISMISSED_KEY = "ah_chat_dismissed";

export default function GlobalChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [unread, setUnread] = useState(0);
  // Fully dismissed = no FAB, no panel. Re-summon via Cmd/Ctrl+/ keyboard
  // shortcut. Persisted across reloads via localStorage so a user who hides
  // the chat doesn't see it pop back on every navigation.
  const [dismissed, setDismissed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(DISMISSED_KEY) === "1";
  });
  const hiddenRef = useHiddenRef(isOpen, isMinimized, dismissed);
  // Deck-mode: when a presentation editor is mounted, the chat sends an
  // additional `presentation_id` flag and the backend exposes deck-aware
  // tools (propose_section). Proposals come back as SSE events that the
  // chat renders as accept-or-reject cards.
  const deckChat = useDeckChat();
  const activeDeck = deckChat.activeDeck;

  // Persist dismissed state. Also wire a Cmd/Ctrl+/ shortcut to summon back.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (dismissed) localStorage.setItem(DISMISSED_KEY, "1");
    else localStorage.removeItem(DISMISSED_KEY);
  }, [dismissed]);

  // Resizable width — persisted, drag handle on the left edge.
  const [chatWidthPx, setChatWidthPx] = useState<number>(() => {
    if (typeof window === "undefined") return CHAT_WIDTH_DEFAULT;
    const stored = localStorage.getItem(CHAT_WIDTH_KEY);
    const n = stored ? parseInt(stored, 10) : NaN;
    return Number.isFinite(n) && n >= CHAT_WIDTH_MIN ? n : CHAT_WIDTH_DEFAULT;
  });
  const [isResizing, setIsResizing] = useState(false);
  const isWide = chatWidthPx >= CHAT_WIDTH_WIDE - 1;

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(CHAT_WIDTH_KEY, String(chatWidthPx));
  }, [chatWidthPx]);

  // Clamp if window resized smaller than the chat
  useEffect(() => {
    const onResize = () => {
      setChatWidthPx(w => Math.min(w, Math.max(CHAT_WIDTH_MIN, window.innerWidth - 200)));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    const startX = e.clientX;
    const startW = chatWidthPx;
    const onMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;  // drag LEFT = wider
      const next = Math.max(CHAT_WIDTH_MIN, Math.min(window.innerWidth - 200, startW + delta));
      setChatWidthPx(next);
    };
    const onUp = () => {
      setIsResizing(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const toggleMaximize = () => {
    setChatWidthPx(w => (w >= CHAT_WIDTH_WIDE - 1 ? CHAT_WIDTH_DEFAULT : CHAT_WIDTH_WIDE));
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        setDismissed(false);
        setIsOpen(true);
        setIsMinimized(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const [sessionId, setSessionId] = useState(() => `s_${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [deepThinking, setDeepThinking] = useState(false);
  const [reportMode, setReportMode] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [splitDoc, setSplitDoc] = useState<{ url: string; filename: string } | null>(null);
  const [showDocPicker, setShowDocPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [docSearch, setDocSearch] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: docResults } = useQuery({
    queryKey: ["chat-doc-search", docSearch], queryFn: () => searchDocuments(docSearch), enabled: docSearch.length > 1,
  });
  const { data: sessions } = useQuery({
    queryKey: ["chat-sessions"], queryFn: getChatSessions, enabled: showHistory,
  });

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // When the chat opens (or comes back from minimized), clear the unread count.
  useEffect(() => {
    if (isOpen && !isMinimized) setUnread(0);
  }, [isOpen, isMinimized]);

  // Ask for browser-notification permission lazily — first time the user sends.
  // We don't ask up-front because that's annoying and most browsers will ignore it.
  const ensureNotifyPermission = () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  };

  const fireDoneNotification = (preview: string) => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    const n = new Notification("AH Expert response ready", {
      body: preview.slice(0, 200),
      tag: "ah-chat-done",
      icon: "/icon-192.png",
    });
    n.onclick = () => { window.focus(); setIsOpen(true); setIsMinimized(false); n.close(); };
  };

  const handleViewDoc = async (docId: string, filename: string) => {
    try {
      if (!docId && filename) {
        const r = await searchDocuments(filename);
        const exact = r.find((d) => d.filename === filename);
        const startsWith = r.find((d) => d.filename.toLowerCase().startsWith(filename.toLowerCase()));
        const contains = r.find((d) => d.filename.toLowerCase().includes(filename.toLowerCase()));
        const best = exact || startsWith || contains || r[0];
        if (best) docId = best.id;
      }
      if (!docId) {
        console.warn("Could not find doc for citation:", filename);
        return;
      }
      const { url } = await getDocumentViewUrl(docId);
      setSplitDoc({ url, filename });
      if (!isExpanded) setIsExpanded(true);
    } catch (e) {
      console.error("Failed to open doc viewer:", e);
    }
  };

  const handleDownloadChat = () => {
    const text = messages.filter(m => m.role !== "error").map(m => `[${m.role.toUpperCase()}] ${m.content}`).join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `ah-chat-${new Date().toISOString().slice(0, 10)}.txt`; a.click();
  };

  const handleDownloadMessage = (content: string) => {
    const blob = new Blob([content], { type: "text/markdown" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `ah-response-${new Date().toISOString().slice(0, 16)}.md`; a.click();
  };

  const handleNewSession = () => {
    setSessionId(`s_${Date.now()}`);
    setMessages([{
      id: "welcome", role: "assistant", timestamp: new Date(),
      content: "New conversation started. Ask me anything about Atlantic Highlands.",
    }]);
    setShowHistory(false);
  };

  /** Load a previous session's messages and switch to it. */
  const handleLoadSession = async (newSessionId: string) => {
    setShowHistory(false);
    if (newSessionId === sessionId) return;
    try {
      const data = await getChatHistory(newSessionId);
      setSessionId(newSessionId);
      const loaded: ChatMessage[] = (data.messages || []).map((m, i) => ({
        id: `${newSessionId}_${i}`,
        role: (m.role === 'user' || m.role === 'assistant') ? m.role : 'system',
        content: m.content,
        timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
      }));
      setMessages(loaded.length ? loaded : [{
        id: "empty", role: "assistant", timestamp: new Date(),
        content: "(This conversation has no messages.)",
      }]);
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : 'Unknown error';
      setMessages(prev => [...prev, {
        id: `e_${Date.now()}`, role: "error", timestamp: new Date(),
        content: `Couldn't load that conversation: ${detail}`,
      }]);
    }
  };

  const handleCitationClick = (info: { filename: string }) => {
    handleViewDoc("", info.filename);
  };

  /** Apply a deck proposal: dispatch through DeckChatContext, then mark
   *  the proposal as applied/dismissed on the message so the UI updates. */
  const handleApplyProposal = async (messageId: string, idx: number) => {
    const msg = messages.find(m => m.id === messageId);
    const proposal = msg?.proposals?.[idx];
    if (!proposal) return;
    const ok = await deckChat.applyProposal(proposal);
    setMessages(prev => prev.map(m => {
      if (m.id !== messageId) return m;
      const ps = [...(m.proposals || [])];
      ps[idx] = { ...ps[idx], applied: ok ? "applied" : "dismissed" };
      return { ...m, proposals: ps };
    }));
  };

  /** Send an assistant message body to the active deck as a new narrative section. */
  const handleSendMessageToDeck = async (msg: ChatMessage) => {
    if (!activeDeck) return;
    const body = (msg.content || "").trim();
    if (!body) return;
    // Pull a title from the first heading or first sentence.
    const firstHeading = body.match(/^#{1,3}\s+(.+)$/m)?.[1];
    const firstSentence = body.split(/[.\n]/)[0];
    const title = (firstHeading || firstSentence || "From chat").trim().slice(0, 80);
    const ok = await deckChat.applyProposal({
      kind: "narrative",
      title,
      body,
      rationale: "Sent from chat",
    });
    if (!ok) {
      setMessages(prev => [...prev, {
        id: `n_${Date.now()}`, role: "system", timestamp: new Date(),
        content: "Couldn't add to deck — open a presentation first.",
      }]);
    }
  };

  const handleDismissProposal = (messageId: string, idx: number) => {
    setMessages(prev => prev.map(m => {
      if (m.id !== messageId) return m;
      const ps = [...(m.proposals || [])];
      ps[idx] = { ...ps[idx], applied: "dismissed" };
      return { ...m, proposals: ps };
    }));
  };

  /** Update one message in the list. */
  const patchMessage = (id: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) => {
    setMessages(prev => prev.map(m => {
      if (m.id !== id) return m;
      const p = typeof patch === "function" ? patch(m) : patch;
      return { ...m, ...p };
    }));
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput(""); setShowDocPicker(false); setShowHistory(false);
    ensureNotifyPermission();

    const userMsg: ChatMessage = {
      id: Date.now().toString(), role: "user", content: text, timestamp: new Date(),
      linkedDocs: selectedDoc ? [{ id: selectedDoc.id, filename: selectedDoc.filename }] : undefined,
    };
    const assistantMsg: ChatMessage = {
      id: (Date.now() + 1).toString(), role: "assistant", content: "", timestamp: new Date(), isStreaming: true,
      toolActivity: [],
    };
    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const body: Record<string, unknown> = {
        query: text,
        model: "claude",
        session_id: sessionId,
        web_search: webSearchEnabled,
        deep_thinking: deepThinking,
        report_mode: reportMode,
      };
      if (selectedDoc) body.document_id = selectedDoc.id;
      // Deck-mode hint to the backend so it adds propose_section to the tool surface.
      if (activeDeck) {
        body.presentation_id = activeDeck.id;
        body.presentation_summary = activeDeck.summary;
      }

      const token = typeof window !== "undefined" ? localStorage.getItem("ah_token") : null;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      // Use the direct HTTPS endpoint so Amplify's 30s SSR timeout doesn't
      // kill long streams. Falls back to the relative URL when API_DIRECT
      // isn't configured (local dev).
      const streamUrl = `${API_DIRECT || API_BASE}/api/chat/stream`;
      const response = await fetch(streamUrl, {
        method: "POST", headers, body: JSON.stringify(body),
      });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let full = "";
      let pending = "";  // SSE frames can split across reads

      if (!reader) throw new Error("No response stream");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });

        // SSE frames separated by blank line
        let sep: number;
        while ((sep = pending.indexOf("\n\n")) !== -1) {
          const frame = pending.slice(0, sep);
          pending = pending.slice(sep + 2);
          if (!frame.trim() || frame.startsWith(":")) continue;  // keepalive

          // Frame may contain `event:` and one or more `data:` lines
          let dataLine = "";
          for (const line of frame.split("\n")) {
            if (line.startsWith("data: ")) dataLine += line.slice(6);
            else if (line.startsWith("data:")) dataLine += line.slice(5);
          }
          if (!dataLine) continue;

          let d: any;
          try { d = JSON.parse(dataLine); } catch { continue; }

          switch (d.type) {
            case "session":
              if (d.session_id) setSessionId(d.session_id);
              break;

            case "status":
              // Backend transition marker: "Building context…", "Calling Claude…", etc.
              patchMessage(assistantMsg.id, { statusText: d.text || undefined });
              break;

            case "plan":
              // Claude announced its plan via share_plan. Render as a checklist.
              patchMessage(assistantMsg.id, {
                plan: {
                  steps: Array.isArray(d.steps) ? d.steps : [],
                  rationale: d.rationale || undefined,
                  completed: 0,
                },
                statusText: undefined,
              });
              break;

            case "proposal": {
              // Deck-mode: Claude proposed a section change. Show as an
              // accept/reject card. The proposal can be applied to the active
              // deck via DeckChatContext.applyProposal.
              const proposal = (d.input as DeckProposal) || (d as DeckProposal);
              patchMessage(assistantMsg.id, m => ({
                proposals: [...(m.proposals || []), proposal],
              }));
              break;
            }

            case "continuation":
              // Backend auto-resumed after hitting max_tokens. Tracked for UI.
              patchMessage(assistantMsg.id, m => ({
                continuations: (m.continuations || 0) + 1,
              }));
              break;

            case "delta":
              full += d.content || "";
              patchMessage(assistantMsg.id, { content: full, statusText: undefined });
              break;

            case "thinking":
              patchMessage(assistantMsg.id, {
                thinking: d.status === "done" ? "done" : "started",
              });
              break;

            case "tool_call":
            case "tool_use": {
              const name = d.name || (Array.isArray(d.tools) ? d.tools[0]?.name : "") || "tool";
              const newEntry: ToolActivity = {
                name,
                input: d.input,
                description: d.description,
                status: "started",
              };
              patchMessage(assistantMsg.id, m => ({
                toolActivity: [...(m.toolActivity || []), newEntry],
                // Each non-plan tool call advances one plan step (visual proxy).
                plan: m.plan ? { ...m.plan, completed: Math.min((m.plan.completed || 0) + 1, m.plan.steps.length) } : m.plan,
              }));
              break;
            }

            case "tool_result":
              patchMessage(assistantMsg.id, m => {
                const acts = [...(m.toolActivity || [])];
                for (let i = acts.length - 1; i >= 0; i--) {
                  if (acts[i].name === d.name && acts[i].status === "started") {
                    acts[i] = { ...acts[i], status: "done", summary: d.summary };
                    break;
                  }
                }
                return { toolActivity: acts };
              });
              break;

            case "done":
              patchMessage(assistantMsg.id, m => ({
                isStreaming: false,
                statusText: undefined,
                cost: {
                  input_tokens: d.input_tokens,
                  output_tokens: d.output_tokens,
                  estimated_cost_usd: d.estimated_cost_usd,
                  tool_calls_made: d.tool_calls_made,
                },
                // Mark all plan steps complete on success.
                plan: m.plan ? { ...m.plan, completed: m.plan.steps.length } : m.plan,
              }));
              if (hiddenRef.current) {
                setUnread(u => u + 1);
                fireDoneNotification(full || "Response ready");
              }
              break;

            case "error":
              patchMessage(assistantMsg.id, m => ({
                content: (m.content || "") + (m.content ? "\n\n" : "") + "Error: " + (d.content || "Unknown error"),
                isStreaming: false,
                statusText: undefined,
                role: "error" as const,
              }));
              break;
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      patchMessage(assistantMsg.id, { content: `Error: ${msg}`, isStreaming: false, role: "error" as const });
    } finally {
      setIsStreaming(false);
      setSelectedDoc(null);
    }
  };

  // Fully dismissed — no FAB, no panel. Streams continue running in the background;
  // a browser notification still fires when they complete. Press Cmd/Ctrl+/ to summon back.
  if (dismissed) return null;

  // Closed state - FAB button. Streaming pulse on the right; unread count on top-left.
  if (!isOpen) return (
    <button onClick={() => setIsOpen(true)}
      className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-50 text-white p-3.5 md:p-4 rounded-full shadow-xl hover:shadow-2xl transition-all hover:scale-105 group"
      style={{ backgroundColor: brandColor }}
      aria-label={unread > 0 ? `${unread} new response ready` : "Open AH Expert"}>
      <SparklesIcon className="w-5 h-5 md:w-6 md:h-6 group-hover:rotate-12 transition-transform" />
      {isStreaming && (
        <span className="absolute top-1 right-1 w-2 h-2 bg-white rounded-full animate-pulse"
              title="Working on a response…" />
      )}
      {unread > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1
                         bg-amber-400 text-[#1a2e2c] text-[11px] font-bold
                         rounded-full flex items-center justify-center shadow ring-2 ring-white">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );

  if (isMinimized) return (
    <div className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-50 text-white rounded-full shadow-xl flex items-center gap-2 px-4 py-2.5 md:px-5 md:py-3 cursor-pointer hover:shadow-2xl"
      style={{ backgroundColor: brandColor }} onClick={() => setIsMinimized(false)}>
      <SparklesIcon className="w-4 h-4" /><span className="text-sm font-medium">AH Expert</span>
      {isStreaming && <span className="w-2 h-2 bg-white rounded-full animate-pulse" title="Working…" />}
      {unread > 0 && (
        <span className="min-w-[18px] h-[18px] px-1 bg-amber-400 text-[#1a2e2c] text-[10px] font-bold rounded-full flex items-center justify-center">
          {unread > 9 ? "9+" : unread} new
        </span>
      )}
      <button onClick={e => { e.stopPropagation(); setIsOpen(false); setIsMinimized(false); setSplitDoc(null); }} className="ml-1 hover:bg-white/20 rounded p-0.5"><XMarkIcon className="w-4 h-4" /></button>
    </div>
  );

  // Layout matches bank-processor's RKCAIChatPanel: full-height slide-out
  // anchored to the right edge, draggable left-edge handle, maximize toggles
  // between default width and ~60% of viewport.
  const totalWidth = splitDoc ? `calc(${chatWidthPx}px + min(420px, 40vw))` : `${chatWidthPx}px`;

  return (
    <div
      className={`fixed inset-y-0 right-0 z-50 bg-white shadow-2xl flex flex-row border-l border-gray-200 ${isResizing ? "" : "transition-[width] duration-200"}`}
      style={{ width: totalWidth }}
    >
      {/* Drag handle on the LEFT edge — drag to resize, double-click to toggle wide */}
      <div
        onMouseDown={startResize}
        onDoubleClick={toggleMaximize}
        title="Drag to resize · double-click to toggle wide"
        className="absolute top-0 bottom-0 left-0 w-1.5 -translate-x-1/2 cursor-col-resize z-10 group"
      >
        <div className="h-full w-full transition-colors" style={{ backgroundColor: isResizing ? brandColor : "transparent" }} />
        <div
          className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 w-1 h-10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ backgroundColor: brandColor }}
        />
      </div>

      {/* Chat column */}
      <div
        className="flex flex-col border-r border-gray-200 bg-gray-50 min-w-0"
        style={{ width: `${chatWidthPx}px`, minWidth: `${chatWidthPx}px` }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 text-white flex-shrink-0" style={{ backgroundColor: brandColor }}>
          <div className="flex items-center gap-2.5 min-w-0">
            <CpuChipIcon className="w-5 h-5 opacity-90 flex-shrink-0" />
            <div className="min-w-0">
              <div className="font-bold text-sm leading-tight">AI Analyst</div>
              <div className="text-[10px] opacity-75 leading-tight truncate">
                {activeDeck
                  ? `Deck mode · ${activeDeck.title}`
                  : `Connected · Documents${webSearchEnabled ? " + Web" : ""}${deepThinking ? " + Deep" : ""}${reportMode ? " + Report" : ""}`}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            {messages.length > 1 && <CopyChatButton messages={messages} />}
            <button
              onClick={handleNewSession}
              title="New chat"
              className="flex items-center gap-1 px-2 py-1 text-xs bg-white/20 rounded hover:bg-white/30 transition"
            >
              <PlusIcon className="w-3.5 h-3.5" />
              <span>New</span>
            </button>
            <button onClick={() => setShowHistory(!showHistory)}
              title="Conversation history"
              className={`p-1 rounded transition ${showHistory ? "bg-white/30" : "hover:bg-white/20"}`}
            >
              <ClockIcon className="w-4 h-4 opacity-80" />
            </button>
            <button onClick={toggleMaximize} title={isWide ? "Shrink to default width" : "Expand to wide"} className="p-1 hover:bg-white/20 rounded transition">
              {isWide ? <ArrowsPointingInIcon className="w-4 h-4 opacity-80" /> : <ArrowsPointingOutIcon className="w-4 h-4 opacity-80" />}
            </button>
            <button
              onClick={() => { setIsOpen(false); setSplitDoc(null); }}
              onContextMenu={(e) => { e.preventDefault(); setDismissed(true); setIsOpen(false); setSplitDoc(null); }}
              className="p-1 hover:bg-white/20 rounded transition"
              title="Close (right-click to fully dismiss; Ctrl/Cmd+/ to summon)"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Controls bar — Deep / Report toggles + scope filters (matches bank-processor) */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white flex-shrink-0 text-[11px]">
          <label
            className={`flex items-center gap-1.5 cursor-pointer ${deepThinking ? "font-semibold" : "text-gray-500"}`}
            style={deepThinking ? { color: brandColor } : undefined}
          >
            <input type="checkbox" checked={deepThinking} onChange={e => setDeepThinking(e.target.checked)}
              className="cursor-pointer" style={{ accentColor: brandColor, width: 13, height: 13 }} />
            <LightBulbIcon className="w-3 h-3" />
            Deep
          </label>
          <label
            className={`flex items-center gap-1.5 cursor-pointer ${reportMode ? "font-semibold" : "text-gray-500"}`}
            style={reportMode ? { color: brandColor } : undefined}
          >
            <input type="checkbox" checked={reportMode} onChange={e => setReportMode(e.target.checked)}
              className="cursor-pointer" style={{ accentColor: brandColor, width: 13, height: 13 }} />
            <DocumentChartBarIcon className="w-3 h-3" />
            Report
          </label>
          <label
            className={`flex items-center gap-1.5 cursor-pointer ${webSearchEnabled ? "font-semibold" : "text-gray-500"}`}
            style={webSearchEnabled ? { color: brandColor } : undefined}
          >
            <input type="checkbox" checked={webSearchEnabled} onChange={e => setWebSearchEnabled(e.target.checked)}
              className="cursor-pointer" style={{ accentColor: brandColor, width: 13, height: 13 }} />
            <GlobeAltIcon className="w-3 h-3" />
            Web
          </label>
          <div className="flex-1" />
          <button
            onClick={() => setShowDocPicker(!showDocPicker)}
            className={`flex items-center gap-1 px-2 py-0.5 text-[11px] rounded border ${
              selectedDoc
                ? "bg-emerald-50 border-emerald-200 font-semibold"
                : "bg-white border-gray-300 text-gray-600 hover:bg-gray-100"
            }`}
            style={selectedDoc ? { color: brandColor } : undefined}
            title="Restrict the chat to a specific document"
          >
            <DocumentTextIcon className="w-3 h-3" />
            {selectedDoc ? "1 doc" : "Scope docs"}
          </button>
        </div>

        {/* History panel */}
        {showHistory && (
          <div className="border-b border-gray-200 bg-white px-3 py-2 max-h-48 overflow-y-auto flex-shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-gray-500">Chat History</span>
              <button onClick={handleNewSession} className="text-xs hover:opacity-80" style={{ color: brandColor }}>+ New Chat</button>
            </div>
            {sessions?.map((s: any) => (
              <button key={s.session_id} onClick={() => handleLoadSession(s.session_id)}
                className={`w-full text-left px-2 py-1.5 text-xs rounded hover:bg-gray-100 ${s.session_id === sessionId ? "text-gray-900" : "text-gray-600"}`}
                style={s.session_id === sessionId ? { backgroundColor: `${brandColor}10` } : {}}>
                <p className="truncate font-medium">{s.last_query || "Conversation"}</p>
                <p className="text-gray-400">{s.message_count} msgs &middot; {s.last_activity ? new Date(s.last_activity).toLocaleDateString() : ""}</p>
              </button>
            ))}
            {!sessions?.length && <p className="text-xs text-gray-400 py-2">No previous conversations</p>}
          </div>
        )}

        {selectedDoc && (
          <div className="px-3 py-1.5 border-b border-gray-200 flex items-center gap-2 text-xs flex-shrink-0" style={{ backgroundColor: `${brandColor}10` }}>
            <LinkIcon className="w-3 h-3" style={{ color: brandColor }} />
            <span className="truncate flex-1" style={{ color: brandColor }}>{selectedDoc.filename}</span>
            <button onClick={() => setSelectedDoc(null)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="w-3 h-3" /></button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 min-h-0">
          {messages.map(msg => (
            <EnhancedMessageComponent
              key={msg.id}
              message={msg}
              brandColor={brandColor}
              onCitationClick={handleCitationClick}
              onDocClick={handleViewDoc}
              onDownload={handleDownloadMessage}
              onApplyProposal={activeDeck ? handleApplyProposal : undefined}
              onDismissProposal={activeDeck ? handleDismissProposal : undefined}
              onSendMessageToDeck={activeDeck ? handleSendMessageToDeck : undefined}
              activeDeckTitle={activeDeck?.title}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {showDocPicker && (
          <div className="border-t border-gray-200 bg-white px-3 py-2 max-h-48 overflow-y-auto flex-shrink-0">
            <div className="relative mb-2">
              <MagnifyingGlassIcon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="text" value={docSearch} onChange={e => setDocSearch(e.target.value)} placeholder="Search docs by content..." className="w-full pl-8 pr-2 py-1.5 text-xs border border-gray-300 rounded-lg" autoFocus />
            </div>
            {docResults?.slice(0, 6).map((sr: any) => (
              <button key={sr.id} onClick={() => { setSelectedDoc({ id: sr.id, filename: sr.filename } as Document); setShowDocPicker(false); setDocSearch(""); }}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-50 rounded">
                <DocumentTextIcon className="w-3.5 h-3.5 text-gray-400" /><span className="truncate flex-1 text-left">{sr.filename}</span>
              </button>
            ))}
          </div>
        )}

        {/* Input — toggles live in the top controls bar; this row is just
            attach + textfield + send. */}
        <div className="p-3 border-t border-gray-200 bg-white flex-shrink-0">
          <div className="flex gap-1.5">
            <button
              onClick={() => setShowDocPicker(!showDocPicker)}
              className={`p-2 rounded-lg border transition-colors ${
                showDocPicker || selectedDoc
                  ? "border-gray-400 text-gray-700 bg-gray-100"
                  : "border-gray-300 text-gray-400 hover:text-gray-600"
              }`}
              title="Attach document"
            >
              <DocumentTextIcon className="w-4 h-4" />
            </button>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={
                selectedDoc ? `Ask about ${selectedDoc.filename}...`
                : reportMode ? "Request a report..."
                : deepThinking ? "Ask a deep analytical question..."
                : webSearchEnabled ? "Ask anything (+ web search)..."
                : "Ask about AH documents..."
              }
              className="flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:border-transparent"
              style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
              disabled={isStreaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="px-3 py-2 text-white rounded-xl hover:opacity-90 disabled:opacity-50 shadow-lg"
              style={{ backgroundColor: brandColor }}
            >
              <PaperAirplaneIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Split document viewer (when a citation was clicked) */}
      {splitDoc && (
        <div className="flex-1 border-l border-gray-200 flex flex-col bg-white min-w-0">
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50 flex-shrink-0">
            <span className="text-xs font-medium text-gray-600 truncate flex-1">{splitDoc.filename}</span>
            <button onClick={() => setSplitDoc(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded"><XMarkIcon className="w-4 h-4" /></button>
          </div>
          <div className="flex-1 overflow-hidden">
            <iframe src={splitDoc.url} className="w-full h-full border-0" title={splitDoc.filename} />
          </div>
        </div>
      )}
    </div>
  );
}


/** Header button: copy the entire chat transcript to clipboard. */
function CopyChatButton({ messages }: { messages: ChatMessage[] }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    const text = messages
      .filter(m => m.role !== "error")
      .map(m => {
        const role = m.role === "user" ? "USER" : "AH EXPERT";
        return `[${role}]\n${m.content}`;
      })
      .join("\n\n---\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };
  return (
    <button
      onClick={handleCopy}
      title={copied ? "Copied" : "Copy entire chat"}
      className="flex items-center gap-1 px-2 py-1 text-xs bg-white/20 rounded hover:bg-white/30 transition"
    >
      {copied ? <CheckIcon className="w-3.5 h-3.5" /> : <ClipboardDocumentIcon className="w-3.5 h-3.5" />}
      <span>{copied ? "Copied" : "Copy Chat"}</span>
    </button>
  );
}
