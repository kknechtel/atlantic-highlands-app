"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocuments, getDocumentViewUrl, searchDocuments, type Document, type SearchResult } from "@/lib/api";
import {
  ChatBubbleLeftRightIcon,
  XMarkIcon,
  PaperAirplaneIcon,
  SparklesIcon,
  MinusIcon,
  DocumentTextIcon,
  ArrowsPointingOutIcon,
  ArrowsPointingInIcon,
  MagnifyingGlassIcon,
  LinkIcon,
  ClipboardIcon,
  CheckIcon,
  ArrowDownTrayIcon,
  GlobeAltIcon,
  ChartBarIcon,
  ClockIcon,
  UserIcon,
  CpuChipIcon,
  ExclamationCircleIcon,
} from "@heroicons/react/24/outline";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "error";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  linkedDocs?: { id: string; filename: string }[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function GlobalChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => `session_${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "I'm the Atlantic Highlands Expert. I've indexed 728 documents covering budgets, audits, financial statements, council minutes, school board agendas, ordinances, and resolutions from 2004 to present.\n\nI know this town's finances, governance, and school district operations. Ask me anything specific.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [splitDoc, setSplitDoc] = useState<{ url: string; filename: string } | null>(null);
  const [showDocPicker, setShowDocPicker] = useState(false);
  const [docSearch, setDocSearch] = useState("");
  const [deepMode, setDeepMode] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: searchResults } = useQuery({
    queryKey: ["chat-doc-search", docSearch],
    queryFn: () => searchDocuments(docSearch),
    enabled: docSearch.length > 1,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleViewDoc = async (docId: string, filename: string) => {
    try {
      // Search by filename if no ID
      if (!docId && filename) {
        const results = await searchDocuments(filename);
        if (results.length > 0) docId = results[0].id;
      }
      if (!docId) return;
      const { url } = await getDocumentViewUrl(docId);
      setSplitDoc({ url, filename });
      if (!isExpanded) setIsExpanded(true);
    } catch (e) {
      console.error("Failed to view doc:", e);
    }
  };

  const handleCopy = async (content: string, id: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDownloadChat = () => {
    const text = messages
      .filter((m) => m.role !== "system")
      .map((m) => `[${m.role.toUpperCase()}] ${m.content}`)
      .join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ah-chat-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    setShowDocPicker(false);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
      linkedDocs: selectedDoc ? [{ id: selectedDoc.id, filename: selectedDoc.filename }] : undefined,
    };
    const assistantMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const body: any = { query: text, model: "gemini", session_id: sessionId };
      if (selectedDoc) body.document_id = selectedDoc.id;

      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split("\n")) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === "delta") {
                  fullContent += data.content;
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantMsg.id ? { ...m, content: fullContent } : m))
                  );
                } else if (data.type === "done") {
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantMsg.id ? { ...m, isStreaming: false } : m))
                  );
                } else if (data.type === "error") {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsg.id
                        ? { ...m, content: fullContent + "\n\nError: " + data.content, isStreaming: false, role: "error" as const }
                        : m
                    )
                  );
                }
              } catch {}
            }
          }
        }
      }
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: `Connection error: ${e.message}`, isStreaming: false, role: "error" as const }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
      setSelectedDoc(null);
    }
  };

  const formatTimestamp = (date: Date) => {
    const diff = Date.now() - date.getTime();
    if (diff < 60000) return "Just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  };

  // Floating button
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-purple-600 to-indigo-600 text-white p-4 rounded-full shadow-xl hover:shadow-2xl transition-all hover:scale-105 group"
      >
        <SparklesIcon className="w-6 h-6 group-hover:rotate-12 transition-transform" />
      </button>
    );
  }

  if (isMinimized) {
    return (
      <div
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-full shadow-xl flex items-center gap-2 px-5 py-3 cursor-pointer hover:shadow-2xl transition-all"
        onClick={() => setIsMinimized(false)}
      >
        <SparklesIcon className="w-4 h-4" />
        <span className="text-sm font-medium">AI Analyst</span>
        {isStreaming && <span className="w-2 h-2 bg-white rounded-full animate-pulse" />}
        <button onClick={(e) => { e.stopPropagation(); setIsOpen(false); setIsMinimized(false); setSplitDoc(null); }} className="ml-1 hover:bg-white/20 rounded p-0.5">
          <XMarkIcon className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const chatWidth = isExpanded ? (splitDoc ? "w-[1200px]" : "w-[600px]") : splitDoc ? "w-[900px]" : "w-[440px]";
  const chatHeight = isExpanded ? "h-[85vh]" : "h-[650px]";

  return (
    <div className={`fixed bottom-6 right-6 z-50 ${chatWidth} ${chatHeight} flex rounded-2xl shadow-2xl border overflow-hidden transition-all duration-200`}>
      {/* Chat panel */}
      <div className={`${splitDoc ? "w-1/2" : "w-full"} bg-white flex flex-col`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white">
          <div className="flex items-center gap-2">
            <SparklesIcon className="w-5 h-5" />
            <div>
              <span className="font-semibold text-sm">Atlantic Highlands Expert</span>
              <span className="text-purple-200 text-xs ml-2">728 docs indexed</span>
            </div>
          </div>
          <div className="flex items-center gap-0.5">
            <button onClick={handleDownloadChat} className="p-1.5 hover:bg-white/20 rounded" title="Download chat">
              <ArrowDownTrayIcon className="w-4 h-4" />
            </button>
            <button onClick={() => setIsExpanded(!isExpanded)} className="p-1.5 hover:bg-white/20 rounded" title="Expand">
              {isExpanded ? <ArrowsPointingInIcon className="w-4 h-4" /> : <ArrowsPointingOutIcon className="w-4 h-4" />}
            </button>
            <button onClick={() => setIsMinimized(true)} className="p-1.5 hover:bg-white/20 rounded">
              <MinusIcon className="w-4 h-4" />
            </button>
            <button onClick={() => { setIsOpen(false); setSplitDoc(null); }} className="p-1.5 hover:bg-white/20 rounded">
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Mode toggles */}
        <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b text-xs">
          <button
            onClick={() => setDeepMode(!deepMode)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
              deepMode ? "bg-purple-100 text-purple-700 font-medium" : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            <MagnifyingGlassIcon className="w-3 h-3" /> Deep
          </button>
          <button
            onClick={() => {/* TODO: report mode */}}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-gray-500 hover:bg-gray-100"
          >
            <ChartBarIcon className="w-3 h-3" /> Report
          </button>
          <div className="flex-1" />
          <span className="text-gray-400">All Data</span>
        </div>

        {/* Selected doc indicator */}
        {selectedDoc && (
          <div className="px-3 py-1.5 bg-purple-50 border-b flex items-center gap-2 text-xs">
            <LinkIcon className="w-3 h-3 text-purple-500" />
            <span className="text-purple-700 truncate flex-1">{selectedDoc.filename}</span>
            <button onClick={() => setSelectedDoc(null)} className="text-purple-400 hover:text-purple-600">
              <XMarkIcon className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {messages.map((msg) => (
            <div key={msg.id}>
              {/* Message */}
              <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} items-end gap-2`}>
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow">
                    <CpuChipIcon className="w-3.5 h-3.5 text-white" />
                  </div>
                )}
                {msg.role === "error" && (
                  <div className="w-7 h-7 rounded-full bg-red-500 flex items-center justify-center flex-shrink-0 shadow">
                    <ExclamationCircleIcon className="w-3.5 h-3.5 text-white" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm group relative ${
                    msg.role === "user"
                      ? "bg-blue-500 text-white rounded-br-md shadow-lg"
                      : msg.role === "error"
                      ? "bg-red-50 text-red-800 border border-red-200 rounded-bl-md"
                      : "bg-white text-gray-800 border border-gray-200 rounded-bl-md shadow-lg"
                  }`}
                >
                  <MessageContent content={msg.content} onCiteClick={handleViewDoc} role={msg.role} />
                  {msg.isStreaming && (
                    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-100">
                      <ClockIcon className="w-3 h-3 animate-spin text-gray-400" />
                      <span className="text-xs text-gray-400">Analyzing documents...</span>
                    </div>
                  )}

                  {/* Copy button */}
                  {msg.role === "assistant" && !msg.isStreaming && (
                    <button
                      onClick={() => handleCopy(msg.content, msg.id)}
                      className="absolute top-2 right-2 p-1 opacity-0 group-hover:opacity-100 hover:bg-gray-100 rounded transition-all"
                    >
                      {copiedId === msg.id ? (
                        <CheckIcon className="w-3 h-3 text-green-600" />
                      ) : (
                        <ClipboardIcon className="w-3 h-3 text-gray-400" />
                      )}
                    </button>
                  )}

                  {/* Timestamp */}
                  {!msg.isStreaming && (
                    <div className="text-[10px] text-gray-400 mt-1">{formatTimestamp(msg.timestamp)}</div>
                  )}
                </div>

                {msg.role === "user" && (
                  <div className="w-7 h-7 rounded-full bg-blue-500 flex items-center justify-center flex-shrink-0 shadow">
                    <UserIcon className="w-3.5 h-3.5 text-white" />
                  </div>
                )}
              </div>

              {/* Linked docs */}
              {msg.linkedDocs && msg.linkedDocs.length > 0 && (
                <div className={`mt-1 flex gap-1 ${msg.role === "user" ? "justify-end mr-9" : "justify-start ml-9"}`}>
                  {msg.linkedDocs.map((ld) => (
                    <button
                      key={ld.id}
                      onClick={() => handleViewDoc(ld.id, ld.filename)}
                      className="flex items-center gap-1 px-2 py-1 text-[11px] bg-purple-50 text-purple-600 rounded-lg hover:bg-purple-100 border border-purple-200"
                    >
                      <DocumentTextIcon className="w-3 h-3" />
                      <span className="truncate max-w-[180px]">{ld.filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Doc picker */}
        {showDocPicker && (
          <div className="border-t bg-white px-3 py-2 max-h-48 overflow-y-auto">
            <div className="relative mb-2">
              <MagnifyingGlassIcon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={docSearch}
                onChange={(e) => setDocSearch(e.target.value)}
                placeholder="Search documents by content..."
                className="w-full pl-8 pr-2 py-1.5 text-xs border border-gray-300 rounded-lg focus:ring-1 focus:ring-purple-500"
                autoFocus
              />
            </div>
            {searchResults?.slice(0, 8).map((sr) => (
              <button
                key={sr.id}
                onClick={() => {
                  setSelectedDoc({ id: sr.id, filename: sr.filename } as Document);
                  setShowDocPicker(false);
                  setDocSearch("");
                }}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-50 rounded"
              >
                <DocumentTextIcon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                <span className="truncate flex-1 text-left">{sr.filename}</span>
                {sr.snippet && <span className="text-[10px] text-gray-400 truncate max-w-[100px]">{sr.snippet}</span>}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="p-3 border-t bg-gray-50">
          <div className="flex gap-2">
            <button
              onClick={() => setShowDocPicker(!showDocPicker)}
              className={`p-2.5 rounded-xl border transition-colors ${
                showDocPicker || selectedDoc
                  ? "bg-purple-50 border-purple-300 text-purple-600"
                  : "border-gray-300 text-gray-400 hover:text-gray-600"
              }`}
              title="Attach document"
            >
              <DocumentTextIcon className="w-4 h-4" />
            </button>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={selectedDoc ? `Ask about ${selectedDoc.filename}...` : "Ask about transactions, documents..."}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              disabled={isStreaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="px-4 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-xl hover:from-purple-700 hover:to-indigo-700 disabled:opacity-50 shadow-lg"
            >
              <PaperAirplaneIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Split document viewer */}
      {splitDoc && (
        <div className="w-1/2 border-l flex flex-col bg-white">
          <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
            <span className="text-xs font-medium text-gray-600 truncate flex-1">{splitDoc.filename}</span>
            <div className="flex gap-1">
              <a href={splitDoc.url} target="_blank" rel="noopener noreferrer"
                className="p-1 text-gray-400 hover:text-gray-600 rounded" title="Open in new tab">
                <ArrowsPointingOutIcon className="w-3.5 h-3.5" />
              </a>
              <button onClick={() => setSplitDoc(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded">
                <XMarkIcon className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-hidden">
            <iframe src={splitDoc.url} className="w-full h-full border-0" title={splitDoc.filename} />
          </div>
        </div>
      )}
    </div>
  );
}

/** Renders message content with [source: filename.pdf] as clickable citation links */
function MessageContent({
  content,
  onCiteClick,
  role,
}: {
  content: string;
  onCiteClick: (docId: string, filename: string) => void;
  role: string;
}) {
  if (role === "user") return <span>{content}</span>;

  // Parse [source: filename] patterns and **bold** and bullet points
  const parts = content.split(/(\[source:\s*[^\]]+\])/g);

  return (
    <div className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0.5 prose-headings:my-2">
      {parts.map((part, i) => {
        const match = part.match(/\[source:\s*([^\]]+)\]/);
        if (match) {
          const filename = match[1].trim();
          return (
            <button
              key={i}
              onClick={() => onCiteClick("", filename)}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 text-[11px] bg-green-50 text-green-700 rounded hover:bg-green-100 font-medium border border-green-200 not-prose"
              title={`View: ${filename}`}
            >
              <DocumentTextIcon className="w-3 h-3" />
              {filename.length > 35 ? filename.slice(0, 33) + "..." : filename}
            </button>
          );
        }
        // Simple markdown-ish rendering
        return <span key={i} dangerouslySetInnerHTML={{ __html: simpleMarkdown(part) }} />;
      })}
    </div>
  );
}

function simpleMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h4 class="font-semibold text-gray-900 mt-3 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-bold text-gray-900 mt-3 mb-1">$1</h3>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    .replace(/\n/g, '<br/>');
}
