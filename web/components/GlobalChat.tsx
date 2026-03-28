"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchDocuments, getDocumentViewUrl, getChatSessions, webSearch, type Document, type SearchResult } from "@/lib/api";
import {
  ChatBubbleLeftRightIcon, XMarkIcon, PaperAirplaneIcon, SparklesIcon,
  MinusIcon, DocumentTextIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon,
  MagnifyingGlassIcon, LinkIcon, ClipboardIcon, CheckIcon,
  ArrowDownTrayIcon, GlobeAltIcon, ClockIcon, UserIcon, CpuChipIcon,
  ExclamationCircleIcon, ArrowPathIcon,
} from "@heroicons/react/24/outline";

interface ChatMessage {
  id: string; role: "user" | "assistant" | "error"; content: string;
  timestamp: Date; isStreaming?: boolean;
  linkedDocs?: { id: string; filename: string }[];
  webResults?: { title: string; url: string; snippet: string }[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function GlobalChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionId, setSessionId] = useState(() => `s_${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: "welcome", role: "assistant", timestamp: new Date(),
    content: "I'm the Atlantic Highlands Expert. I've indexed 728+ documents covering budgets, audits, minutes, ordinances, and more from 2004 to present.\n\nAsk me anything, or use the buttons below to search the web or attach a document.",
  }]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [splitDoc, setSplitDoc] = useState<{ url: string; filename: string } | null>(null);
  const [showDocPicker, setShowDocPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showWebSearch, setShowWebSearch] = useState(false);
  const [docSearch, setDocSearch] = useState("");
  const [webQuery, setWebQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: docResults } = useQuery({
    queryKey: ["chat-doc-search", docSearch], queryFn: () => searchDocuments(docSearch), enabled: docSearch.length > 1,
  });
  const { data: sessions } = useQuery({
    queryKey: ["chat-sessions"], queryFn: getChatSessions, enabled: showHistory,
  });
  const { data: webResults } = useQuery({
    queryKey: ["web-search", webQuery], queryFn: () => webSearch(webQuery), enabled: webQuery.length > 2,
  });

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleViewDoc = async (docId: string, filename: string) => {
    try {
      if (!docId && filename) {
        const r = await searchDocuments(filename);
        if (r.length > 0) docId = r[0].id;
      }
      if (!docId) return;
      const { url } = await getDocumentViewUrl(docId);
      setSplitDoc({ url, filename });
      if (!isExpanded) setIsExpanded(true);
    } catch {}
  };

  const handleCopy = async (content: string, id: string) => {
    await navigator.clipboard.writeText(content); setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDownload = () => {
    const text = messages.filter(m => m.role !== "error").map(m => `[${m.role.toUpperCase()}] ${m.content}`).join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `ah-chat-${new Date().toISOString().slice(0, 10)}.txt`; a.click();
  };

  const handleWebSearchInChat = async (query: string) => {
    const r = await webSearch(query);
    if (r.results.length > 0) {
      const webMsg: ChatMessage = {
        id: `web_${Date.now()}`, role: "assistant", timestamp: new Date(),
        content: `**Web Search Results for "${query}":**\n\n` +
          r.results.map((w, i) => `${i + 1}. **${w.title}**\n   ${w.snippet}\n   [${w.url}](${w.url})`).join("\n\n"),
        webResults: r.results,
      };
      setMessages(prev => [...prev, webMsg]);
    }
  };

  const handleNewSession = () => {
    setSessionId(`s_${Date.now()}`);
    setMessages([{
      id: "welcome", role: "assistant", timestamp: new Date(),
      content: "New conversation started. Ask me anything about Atlantic Highlands.",
    }]);
    setShowHistory(false);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput(""); setShowDocPicker(false); setShowHistory(false); setShowWebSearch(false);

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
      const body: any = { query: text, model: "gemini", session_id: sessionId };
      if (selectedDoc) body.document_id = selectedDoc.id;

      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
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

  const ts = (d: Date) => { const diff = Date.now() - d.getTime(); return diff < 60000 ? "Now" : diff < 3600000 ? `${Math.floor(diff/60000)}m` : d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); };

  if (!isOpen) return (
    <button onClick={() => setIsOpen(true)} className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-green-600 to-emerald-600 text-white p-4 rounded-full shadow-xl hover:shadow-2xl transition-all hover:scale-105 group">
      <SparklesIcon className="w-6 h-6 group-hover:rotate-12 transition-transform" />
    </button>
  );

  if (isMinimized) return (
    <div className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-full shadow-xl flex items-center gap-2 px-5 py-3 cursor-pointer hover:shadow-2xl" onClick={() => setIsMinimized(false)}>
      <SparklesIcon className="w-4 h-4" /><span className="text-sm font-medium">AH Expert</span>
      {isStreaming && <span className="w-2 h-2 bg-white rounded-full animate-pulse" />}
      <button onClick={e => { e.stopPropagation(); setIsOpen(false); setIsMinimized(false); setSplitDoc(null); }} className="ml-1 hover:bg-white/20 rounded p-0.5"><XMarkIcon className="w-4 h-4" /></button>
    </div>
  );

  const w = isExpanded ? (splitDoc ? "w-[1200px]" : "w-[600px]") : splitDoc ? "w-[900px]" : "w-[440px]";

  return (
    <div className={`fixed bottom-6 right-6 z-50 ${w} ${isExpanded ? "h-[85vh]" : "h-[650px]"} flex rounded-2xl shadow-2xl border overflow-hidden transition-all duration-200`}>
      <div className={`${splitDoc ? "w-1/2" : "w-full"} bg-white flex flex-col`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-green-600 to-emerald-600 text-white">
          <div className="flex items-center gap-2">
            <SparklesIcon className="w-5 h-5" />
            <span className="font-semibold text-sm">Atlantic Highlands Expert</span>
          </div>
          <div className="flex items-center gap-0.5">
            <button onClick={handleNewSession} className="p-1.5 hover:bg-white/20 rounded" title="New chat"><ArrowPathIcon className="w-4 h-4" /></button>
            <button onClick={() => setShowHistory(!showHistory)} className="p-1.5 hover:bg-white/20 rounded" title="History"><ClockIcon className="w-4 h-4" /></button>
            <button onClick={handleDownload} className="p-1.5 hover:bg-white/20 rounded" title="Download"><ArrowDownTrayIcon className="w-4 h-4" /></button>
            <button onClick={() => setIsExpanded(!isExpanded)} className="p-1.5 hover:bg-white/20 rounded">{isExpanded ? <ArrowsPointingInIcon className="w-4 h-4" /> : <ArrowsPointingOutIcon className="w-4 h-4" />}</button>
            <button onClick={() => setIsMinimized(true)} className="p-1.5 hover:bg-white/20 rounded"><MinusIcon className="w-4 h-4" /></button>
            <button onClick={() => { setIsOpen(false); setSplitDoc(null); }} className="p-1.5 hover:bg-white/20 rounded"><XMarkIcon className="w-4 h-4" /></button>
          </div>
        </div>

        {/* History panel */}
        {showHistory && (
          <div className="border-b bg-gray-50 px-3 py-2 max-h-48 overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-gray-500">Chat History</span>
              <button onClick={handleNewSession} className="text-xs text-green-600 hover:text-green-700">+ New Chat</button>
            </div>
            {sessions?.map(s => (
              <button key={s.session_id} onClick={() => { setSessionId(s.session_id); setShowHistory(false); }}
                className={`w-full text-left px-2 py-1.5 text-xs rounded hover:bg-gray-100 ${s.session_id === sessionId ? "bg-green-50 text-green-700" : "text-gray-600"}`}>
                <p className="truncate font-medium">{s.last_query || "Conversation"}</p>
                <p className="text-gray-400">{s.message_count} msgs &middot; {s.last_activity ? new Date(s.last_activity).toLocaleDateString() : ""}</p>
              </button>
            ))}
            {!sessions?.length && <p className="text-xs text-gray-400 py-2">No previous conversations</p>}
          </div>
        )}

        {/* Selected doc */}
        {selectedDoc && (
          <div className="px-3 py-1.5 bg-green-50 border-b flex items-center gap-2 text-xs">
            <LinkIcon className="w-3 h-3 text-green-600" />
            <span className="text-green-700 truncate flex-1">{selectedDoc.filename}</span>
            <button onClick={() => setSelectedDoc(null)} className="text-green-400 hover:text-green-600"><XMarkIcon className="w-3 h-3" /></button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {messages.map(msg => (
            <div key={msg.id}>
              <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} items-end gap-2`}>
                {msg.role !== "user" && (
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow ${msg.role === "error" ? "bg-red-500" : "bg-gradient-to-br from-green-500 to-emerald-600"}`}>
                    {msg.role === "error" ? <ExclamationCircleIcon className="w-3.5 h-3.5 text-white" /> : <CpuChipIcon className="w-3.5 h-3.5 text-white" />}
                  </div>
                )}
                <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm group relative ${
                  msg.role === "user" ? "bg-green-600 text-white rounded-br-md shadow-lg"
                    : msg.role === "error" ? "bg-red-50 text-red-800 border border-red-200 rounded-bl-md"
                    : "bg-white text-gray-800 border border-gray-200 rounded-bl-md shadow-lg"
                }`}>
                  <MessageContent content={msg.content} onCiteClick={handleViewDoc} role={msg.role} />
                  {msg.isStreaming && <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-100"><ClockIcon className="w-3 h-3 animate-spin text-gray-400" /><span className="text-xs text-gray-400">Analyzing...</span></div>}
                  {msg.role === "assistant" && !msg.isStreaming && (
                    <button onClick={() => handleCopy(msg.content, msg.id)} className="absolute top-2 right-2 p-1 opacity-0 group-hover:opacity-100 hover:bg-gray-100 rounded transition-all">
                      {copiedId === msg.id ? <CheckIcon className="w-3 h-3 text-green-600" /> : <ClipboardIcon className="w-3 h-3 text-gray-400" />}
                    </button>
                  )}
                  {!msg.isStreaming && <div className="text-[10px] text-gray-400 mt-1">{ts(msg.timestamp)}</div>}
                </div>
                {msg.role === "user" && <div className="w-7 h-7 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 shadow"><UserIcon className="w-3.5 h-3.5 text-white" /></div>}
              </div>
              {msg.linkedDocs?.map(ld => (
                <button key={ld.id} onClick={() => handleViewDoc(ld.id, ld.filename)}
                  className="mt-1 ml-9 flex items-center gap-1 px-2 py-1 text-[11px] bg-green-50 text-green-600 rounded-lg hover:bg-green-100 border border-green-200">
                  <DocumentTextIcon className="w-3 h-3" /><span className="truncate max-w-[180px]">{ld.filename}</span>
                </button>
              ))}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Doc/Web picker */}
        {(showDocPicker || showWebSearch) && (
          <div className="border-t bg-white px-3 py-2 max-h-48 overflow-y-auto">
            {showDocPicker && (<>
              <div className="relative mb-2">
                <MagnifyingGlassIcon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <input type="text" value={docSearch} onChange={e => setDocSearch(e.target.value)} placeholder="Search docs by content..." className="w-full pl-8 pr-2 py-1.5 text-xs border border-gray-300 rounded-lg" autoFocus />
              </div>
              {docResults?.slice(0, 6).map(sr => (
                <button key={sr.id} onClick={() => { setSelectedDoc({ id: sr.id, filename: sr.filename } as Document); setShowDocPicker(false); setDocSearch(""); }}
                  className="flex items-center gap-2 w-full px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-50 rounded">
                  <DocumentTextIcon className="w-3.5 h-3.5 text-gray-400" /><span className="truncate flex-1 text-left">{sr.filename}</span>
                </button>
              ))}
            </>)}
            {showWebSearch && (<>
              <div className="relative mb-2">
                <GlobeAltIcon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <input type="text" value={webQuery} onChange={e => setWebQuery(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && webQuery) { handleWebSearchInChat(webQuery); setShowWebSearch(false); setWebQuery(""); } }}
                  placeholder="Search the web..." className="w-full pl-8 pr-2 py-1.5 text-xs border border-gray-300 rounded-lg" autoFocus />
              </div>
              {webResults?.results?.slice(0, 5).map((r, i) => (
                <a key={i} href={r.url} target="_blank" rel="noopener noreferrer" className="block px-2 py-1.5 text-xs hover:bg-gray-50 rounded">
                  <p className="font-medium text-green-700 truncate">{r.title}</p>
                  <p className="text-gray-500 truncate">{r.snippet}</p>
                </a>
              ))}
            </>)}
          </div>
        )}

        {/* Input */}
        <div className="p-3 border-t bg-gray-50">
          <div className="flex gap-1.5">
            <button onClick={() => { setShowDocPicker(!showDocPicker); setShowWebSearch(false); }}
              className={`p-2 rounded-lg border transition-colors ${showDocPicker || selectedDoc ? "bg-green-50 border-green-300 text-green-600" : "border-gray-300 text-gray-400 hover:text-gray-600"}`} title="Attach doc">
              <DocumentTextIcon className="w-4 h-4" />
            </button>
            <button onClick={() => { setShowWebSearch(!showWebSearch); setShowDocPicker(false); }}
              className={`p-2 rounded-lg border transition-colors ${showWebSearch ? "bg-blue-50 border-blue-300 text-blue-600" : "border-gray-300 text-gray-400 hover:text-gray-600"}`} title="Web search">
              <GlobeAltIcon className="w-4 h-4" />
            </button>
            <input type="text" value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={selectedDoc ? `Ask about ${selectedDoc.filename}...` : "Ask about AH documents..."}
              className="flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-green-500 focus:border-green-500" disabled={isStreaming} />
            <button onClick={handleSend} disabled={!input.trim() || isStreaming}
              className="px-3 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-xl hover:from-green-700 hover:to-emerald-700 disabled:opacity-50 shadow-lg">
              <PaperAirplaneIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {splitDoc && (
        <div className="w-1/2 border-l flex flex-col bg-white">
          <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
            <span className="text-xs font-medium text-gray-600 truncate flex-1">{splitDoc.filename}</span>
            <button onClick={() => setSplitDoc(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded"><XMarkIcon className="w-4 h-4" /></button>
          </div>
          <div className="flex-1 overflow-hidden"><iframe src={splitDoc.url} className="w-full h-full border-0" title={splitDoc.filename} /></div>
        </div>
      )}
    </div>
  );
}

function MessageContent({ content, onCiteClick, role }: { content: string; onCiteClick: (id: string, fn: string) => void; role: string }) {
  if (role === "user") return <span>{content}</span>;
  const parts = content.split(/(\[source:\s*[^\]]+\])/g);
  return (
    <div className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0.5">
      {parts.map((part, i) => {
        const m = part.match(/\[source:\s*([^\]]+)\]/);
        if (m) return (
          <button key={i} onClick={() => onCiteClick("", m[1].trim())}
            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 text-[11px] bg-green-50 text-green-700 rounded hover:bg-green-100 font-medium border border-green-200 not-prose">
            <DocumentTextIcon className="w-3 h-3" />{m[1].trim().length > 35 ? m[1].trim().slice(0, 33) + "..." : m[1].trim()}
          </button>
        );
        return <span key={i} dangerouslySetInnerHTML={{ __html: part.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/^### (.+)$/gm, '<h4 class="font-semibold mt-3 mb-1">$1</h4>').replace(/^## (.+)$/gm, '<h3 class="font-bold mt-3 mb-1">$1</h3>').replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>').replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>').replace(/\n/g, '<br/>') }} />;
      })}
    </div>
  );
}
