"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchDocuments, getDocumentViewUrl, getChatSessions, type Document } from "@/lib/api";
import EnhancedMessageComponent, { type ChatMessage } from "@/components/EnhancedMessageComponent";
import {
  XMarkIcon, PaperAirplaneIcon, SparklesIcon,
  MinusIcon, DocumentTextIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon,
  MagnifyingGlassIcon, LinkIcon, GlobeAltIcon,
  ArrowDownTrayIcon, ClockIcon, ArrowPathIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";
// Use relative URLs in browser so Next.js rewrite proxy handles it (avoids HTTPS/HTTP mixed content)
const API_BASE = "";

export default function GlobalChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionId, setSessionId] = useState(() => `s_${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: "welcome", role: "assistant", timestamp: new Date(),
    content: "I'm the **Atlantic Highlands Expert**. I've indexed 860+ documents covering budgets, audits, minutes, ordinances, school board records, and more from 2004 to present.\n\nI have deep knowledge of the borough's finances, the school district regionalization, Superstorm Sandy recovery, and current issues.\n\nToggle the 🌐 button to enable **web search** for current news and real-time information.",
  }]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
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

  const handleViewDoc = async (docId: string, filename: string) => {
    try {
      if (!docId && filename) {
        const r = await searchDocuments(filename);
        if (r.length > 0) docId = r[0].id;
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

  const handleCitationClick = (info: { filename: string }) => {
    handleViewDoc("", info.filename);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput(""); setShowDocPicker(false); setShowHistory(false);

    const userMsg: ChatMessage = {
      id: Date.now().toString(), role: "user", content: text, timestamp: new Date(),
      linkedDocs: selectedDoc ? [{ id: selectedDoc.id, filename: selectedDoc.filename }] : undefined,
    };
    const assistantMsg: ChatMessage = {
      id: (Date.now() + 1).toString(), role: "assistant", content: "", timestamp: new Date(), isStreaming: true,
    };
    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const body: any = { query: text, model: webSearchEnabled ? "claude" : "gemini", session_id: sessionId, web_search: webSearchEnabled };
      if (selectedDoc) body.document_id = selectedDoc.id;

      const token = typeof window !== "undefined" ? localStorage.getItem("ah_token") : null;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST", headers, body: JSON.stringify(body),
      });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let full = "";
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const line of decoder.decode(value, { stream: true }).split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const d = JSON.parse(line.slice(6));
              if (d.type === "delta") { full += d.content; setMessages(p => p.map(m => m.id === assistantMsg.id ? { ...m, content: full } : m)); }
              else if (d.type === "done") setMessages(p => p.map(m => m.id === assistantMsg.id ? { ...m, isStreaming: false } : m));
              else if (d.type === "error") setMessages(p => p.map(m => m.id === assistantMsg.id ? { ...m, content: full + "\nError: " + d.content, isStreaming: false, role: "error" as const } : m));
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setMessages(p => p.map(m => m.id === assistantMsg.id ? { ...m, content: `Error: ${e.message}`, isStreaming: false, role: "error" as const } : m));
    } finally { setIsStreaming(false); setSelectedDoc(null); }
  };

  // Closed state - FAB button (higher on mobile to avoid bottom nav)
  if (!isOpen) return (
    <button onClick={() => setIsOpen(true)}
      className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-50 text-white p-3.5 md:p-4 rounded-full shadow-xl hover:shadow-2xl transition-all hover:scale-105 group"
      style={{ backgroundColor: brandColor }}>
      <SparklesIcon className="w-5 h-5 md:w-6 md:h-6 group-hover:rotate-12 transition-transform" />
    </button>
  );

  // Minimized state
  if (isMinimized) return (
    <div className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-50 text-white rounded-full shadow-xl flex items-center gap-2 px-4 py-2.5 md:px-5 md:py-3 cursor-pointer hover:shadow-2xl"
      style={{ backgroundColor: brandColor }} onClick={() => setIsMinimized(false)}>
      <SparklesIcon className="w-4 h-4" /><span className="text-sm font-medium">AH Expert</span>
      {isStreaming && <span className="w-2 h-2 bg-white rounded-full animate-pulse" />}
      <button onClick={e => { e.stopPropagation(); setIsOpen(false); setIsMinimized(false); setSplitDoc(null); }} className="ml-1 hover:bg-white/20 rounded p-0.5"><XMarkIcon className="w-4 h-4" /></button>
    </div>
  );

  // Constrain widths so the chat always fits within the viewport
  const widthClass = isExpanded
    ? (splitDoc ? "md:w-[min(1100px,calc(100vw-3rem))]" : "md:w-[min(560px,calc(100vw-3rem))]")
    : splitDoc ? "md:w-[min(820px,calc(100vw-3rem))]" : "md:w-[min(420px,calc(100vw-3rem))]";
  const heightClass = isExpanded ? "md:h-[min(85vh,800px)]" : "md:h-[min(620px,calc(100vh-6rem))]";

  return (
    <div className={`fixed z-50
      /* Mobile: full screen */
      inset-0 md:inset-auto
      /* Desktop: positioned bottom-right, never exceeds viewport */
      md:bottom-6 md:right-6 ${widthClass} ${heightClass}
      flex md:rounded-2xl shadow-2xl md:border md:border-gray-200 overflow-hidden transition-all duration-200`}>
      <div className={`${splitDoc ? "w-1/2" : "w-full"} bg-gray-50 flex flex-col min-w-0`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 text-white flex-shrink-0" style={{ backgroundColor: brandColor }}>
          <div className="flex items-center gap-2">
            <SparklesIcon className="w-5 h-5" />
            <span className="font-semibold text-sm">Atlantic Highlands Expert</span>
            {webSearchEnabled && <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded">+ Web</span>}
          </div>
          <div className="flex items-center gap-0.5">
            <button onClick={handleNewSession} className="p-1.5 hover:bg-white/20 rounded" title="New chat"><ArrowPathIcon className="w-4 h-4" /></button>
            <button onClick={() => setShowHistory(!showHistory)} className="p-1.5 hover:bg-white/20 rounded" title="History"><ClockIcon className="w-4 h-4" /></button>
            <button onClick={handleDownloadChat} className="p-1.5 hover:bg-white/20 rounded" title="Download chat"><ArrowDownTrayIcon className="w-4 h-4" /></button>
            <button onClick={() => setIsExpanded(!isExpanded)} className="p-1.5 hover:bg-white/20 rounded">{isExpanded ? <ArrowsPointingInIcon className="w-4 h-4" /> : <ArrowsPointingOutIcon className="w-4 h-4" />}</button>
            <button onClick={() => setIsMinimized(true)} className="p-1.5 hover:bg-white/20 rounded"><MinusIcon className="w-4 h-4" /></button>
            <button onClick={() => { setIsOpen(false); setSplitDoc(null); }} className="p-1.5 hover:bg-white/20 rounded"><XMarkIcon className="w-4 h-4" /></button>
          </div>
        </div>

        {/* History panel */}
        {showHistory && (
          <div className="border-b border-gray-200 bg-white px-3 py-2 max-h-48 overflow-y-auto flex-shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-gray-500">Chat History</span>
              <button onClick={handleNewSession} className="text-xs hover:opacity-80" style={{ color: brandColor }}>+ New Chat</button>
            </div>
            {sessions?.map((s: any) => (
              <button key={s.session_id} onClick={() => { setSessionId(s.session_id); setShowHistory(false); }}
                className={`w-full text-left px-2 py-1.5 text-xs rounded hover:bg-gray-100 ${s.session_id === sessionId ? "text-gray-900" : "text-gray-600"}`}
                style={s.session_id === sessionId ? { backgroundColor: `${brandColor}10` } : {}}>
                <p className="truncate font-medium">{s.last_query || "Conversation"}</p>
                <p className="text-gray-400">{s.message_count} msgs &middot; {s.last_activity ? new Date(s.last_activity).toLocaleDateString() : ""}</p>
              </button>
            ))}
            {!sessions?.length && <p className="text-xs text-gray-400 py-2">No previous conversations</p>}
          </div>
        )}

        {/* Selected doc badge */}
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
            />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Doc picker */}
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

        {/* Input */}
        <div className="p-3 border-t border-gray-200 bg-white flex-shrink-0">
          <div className="flex gap-1.5">
            <button onClick={() => setShowDocPicker(!showDocPicker)}
              className={`p-2 rounded-lg border transition-colors ${showDocPicker || selectedDoc ? "border-gray-400 text-gray-700 bg-gray-100" : "border-gray-300 text-gray-400 hover:text-gray-600"}`} title="Attach document">
              <DocumentTextIcon className="w-4 h-4" />
            </button>
            <button onClick={() => setWebSearchEnabled(!webSearchEnabled)}
              className={`p-2 rounded-lg border transition-colors ${webSearchEnabled ? "bg-blue-50 border-blue-300 text-blue-600" : "border-gray-300 text-gray-400 hover:text-gray-600"}`}
              title={webSearchEnabled ? "Web search ON (uses Claude)" : "Enable web search"}>
              <GlobeAltIcon className="w-4 h-4" />
            </button>
            <input type="text" value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={selectedDoc ? `Ask about ${selectedDoc.filename}...` : webSearchEnabled ? "Ask anything (+ web search)..." : "Ask about AH documents..."}
              className="flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:border-transparent"
              style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
              disabled={isStreaming} />
            <button onClick={handleSend} disabled={!input.trim() || isStreaming}
              className="px-3 py-2 text-white rounded-xl hover:opacity-90 disabled:opacity-50 shadow-lg"
              style={{ backgroundColor: brandColor }}>
              <PaperAirplaneIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Split document viewer */}
      {splitDoc && (
        <div className="w-1/2 border-l border-gray-200 flex flex-col bg-white">
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
