"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocuments, getDocumentViewUrl, searchDocuments, type Document } from "@/lib/api";
import SplitDocViewer from "./SplitDocViewer";
import {
  ChatBubbleLeftRightIcon,
  XMarkIcon,
  PaperAirplaneIcon,
  SparklesIcon,
  MinusIcon,
  DocumentTextIcon,
  ArrowsPointingOutIcon,
  MagnifyingGlassIcon,
  LinkIcon,
} from "@heroicons/react/24/outline";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  linkedDocs?: { id: string; filename: string }[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function GlobalChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "I can help analyze Atlantic Highlands documents. Ask me about budgets, audits, minutes, ordinances, or financial data.\n\nTip: I'll link relevant documents in my responses - click them to view.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [splitDoc, setSplitDoc] = useState<{ url: string; filename: string } | null>(null);
  const [showDocPicker, setShowDocPicker] = useState(false);
  const [docSearch, setDocSearch] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: searchResults } = useQuery({
    queryKey: ["chat-doc-search", docSearch],
    queryFn: () => searchDocuments(docSearch),
    enabled: docSearch.length > 1,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleViewDoc = async (docId: string, filename: string) => {
    const { url } = await getDocumentViewUrl(docId);
    setSplitDoc({ url, filename });
    if (!isExpanded) setIsExpanded(true);
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
      linkedDocs: selectedDoc ? [{ id: selectedDoc.id, filename: selectedDoc.filename }] : undefined,
    };
    const assistantMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const body: any = { query: text, model: "gemini" };
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
                    prev.map((m) =>
                      m.id === assistantMsg.id ? { ...m, content: fullContent } : m
                    )
                  );
                } else if (data.type === "done") {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
                    )
                  );
                } else if (data.type === "error") {
                  fullContent += `\n\nError: ${data.content}`;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsg.id
                        ? { ...m, content: fullContent, isStreaming: false }
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
            ? { ...m, content: `Error: ${e.message}`, isStreaming: false }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
      setSelectedDoc(null);
    }
  };

  // Floating button
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 bg-purple-600 text-white p-4 rounded-full shadow-lg hover:bg-purple-700 transition-all hover:scale-105"
      >
        <ChatBubbleLeftRightIcon className="w-6 h-6" />
      </button>
    );
  }

  // Minimized
  if (isMinimized) {
    return (
      <div
        className="fixed bottom-6 right-6 z-50 bg-purple-600 text-white rounded-full shadow-lg flex items-center gap-2 px-4 py-3 cursor-pointer hover:bg-purple-700"
        onClick={() => setIsMinimized(false)}
      >
        <SparklesIcon className="w-4 h-4" />
        <span className="text-sm font-medium">AI Chat</span>
        {isStreaming && <span className="w-2 h-2 bg-white rounded-full animate-pulse" />}
        <button
          onClick={(e) => { e.stopPropagation(); setIsOpen(false); setIsMinimized(false); setSplitDoc(null); }}
          className="ml-1 hover:bg-purple-800 rounded p-0.5"
        >
          <XMarkIcon className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const chatWidth = isExpanded ? "w-[800px]" : "w-[420px]";
  const chatHeight = isExpanded ? "h-[85vh]" : "h-[600px]";

  return (
    <div className={`fixed bottom-6 right-6 z-50 ${isExpanded && splitDoc ? "w-[1200px]" : chatWidth} ${chatHeight} flex rounded-2xl shadow-2xl border overflow-hidden`}>
      {/* Chat panel */}
      <div className={`${splitDoc ? "w-1/2" : "w-full"} bg-white flex flex-col`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-purple-600 text-white">
          <div className="flex items-center gap-2">
            <SparklesIcon className="w-4 h-4" />
            <span className="font-semibold text-sm">AI Assistant</span>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setIsExpanded(!isExpanded)} className="p-1 hover:bg-purple-700 rounded" title="Expand">
              <ArrowsPointingOutIcon className="w-4 h-4" />
            </button>
            <button onClick={() => setIsMinimized(true)} className="p-1 hover:bg-purple-700 rounded">
              <MinusIcon className="w-4 h-4" />
            </button>
            <button onClick={() => { setIsOpen(false); setSplitDoc(null); }} className="p-1 hover:bg-purple-700 rounded">
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Selected doc indicator */}
        {selectedDoc && (
          <div className="px-3 py-1.5 bg-purple-50 border-b flex items-center gap-2 text-xs">
            <LinkIcon className="w-3 h-3 text-purple-500" />
            <span className="text-purple-700 truncate">{selectedDoc.filename}</span>
            <button onClick={() => setSelectedDoc(null)} className="text-purple-400 hover:text-purple-600 ml-auto">
              <XMarkIcon className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {messages.map((msg) => (
            <div key={msg.id}>
              <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                    msg.role === "user"
                      ? "bg-purple-600 text-white rounded-br-md"
                      : "bg-gray-100 text-gray-800 rounded-bl-md"
                  }`}
                >
                  {msg.content}
                  {msg.isStreaming && (
                    <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-gray-400 animate-pulse rounded" />
                  )}
                </div>
              </div>
              {/* Linked docs */}
              {msg.linkedDocs && msg.linkedDocs.length > 0 && (
                <div className={`mt-1 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.linkedDocs.map((ld) => (
                    <button
                      key={ld.id}
                      onClick={() => handleViewDoc(ld.id, ld.filename)}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-purple-50 text-purple-600 rounded-lg hover:bg-purple-100"
                    >
                      <DocumentTextIcon className="w-3 h-3" />
                      <span className="truncate max-w-[200px]">{ld.filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Doc picker dropdown */}
        {showDocPicker && (
          <div className="border-t bg-white px-3 py-2 max-h-48 overflow-y-auto">
            <div className="relative mb-2">
              <MagnifyingGlassIcon className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={docSearch}
                onChange={(e) => setDocSearch(e.target.value)}
                placeholder="Search documents..."
                className="w-full pl-7 pr-2 py-1.5 text-xs border border-gray-300 rounded-lg"
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
                <span className="truncate">{sr.filename}</span>
                <span className="text-gray-400 ml-auto text-[10px]">{sr.doc_type}</span>
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
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={selectedDoc ? `Ask about ${selectedDoc.filename}...` : "Ask anything..."}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              disabled={isStreaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="px-4 py-2.5 bg-purple-600 text-white rounded-xl hover:bg-purple-700 disabled:opacity-50"
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
            <span className="text-xs font-medium text-gray-600 truncate">{splitDoc.filename}</span>
            <button onClick={() => setSplitDoc(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded">
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <iframe src={splitDoc.url} className="w-full h-full border-0" title={splitDoc.filename} />
          </div>
        </div>
      )}
    </div>
  );
}
