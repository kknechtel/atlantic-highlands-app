'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
    UserIcon,
    CpuChipIcon,
    ClipboardIcon,
    CheckIcon,
    ExclamationCircleIcon,
    InformationCircleIcon,
    ArrowDownTrayIcon,
    LightBulbIcon,
    WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';
import EnhancedMarkdownRenderer from './EnhancedMarkdownRenderer';
import TypingIndicator from './TypingIndicator';

export type ToolActivity = {
    name: string;
    /** Human-readable line built from the tool's input args, e.g. `Searching: "X"`. */
    description?: string;
    input?: Record<string, unknown>;
    summary?: string;
    status: 'started' | 'done' | 'error';
};

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant' | 'error' | 'system';
    content: string;
    timestamp: Date;
    isStreaming?: boolean;
    linkedDocs?: { id: string; filename: string }[];
    /** Extended thinking status: 'started' while Claude is reasoning, 'done' once text begins. */
    thinking?: 'started' | 'done';
    /** Tool calls Claude made on this turn (search_chunks, read_document, etc.). */
    toolActivity?: ToolActivity[];
    /** Latest progress line emitted by the backend (e.g. "Calling Claude…"). */
    statusText?: string;
}

interface EnhancedMessageComponentProps {
    message: ChatMessage;
    brandColor: string;
    onCitationClick?: (info: { filename: string }) => void;
    onDocClick?: (docId: string, filename: string) => void;
    onDownload?: (content: string) => void;
}

const TOOL_LABEL: Record<string, string> = {
    search_chunks: 'Searching passages',
    search_documents: 'Searching documents',
    read_document: 'Reading document',
    get_financial_summary: 'Loading financials',
    list_recent_documents: 'Listing recent documents',
    web_search: 'Searching the web',
};

function ToolActivityList({ items, brandColor }: { items: ToolActivity[]; brandColor: string }) {
    if (!items.length) return null;
    return (
        <div className="mt-2 space-y-1">
            {items.map((t, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] text-gray-500">
                    <WrenchScrewdriverIcon className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color: brandColor }} />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="font-medium">{t.description || TOOL_LABEL[t.name] || t.name}</span>
                            {t.status === 'started' && (
                                <span className="flex gap-0.5">
                                    <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor }} />
                                    <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor, animationDelay: '120ms' }} />
                                    <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor, animationDelay: '240ms' }} />
                                </span>
                            )}
                        </div>
                        {t.summary && t.status !== 'started' && (
                            <div className="text-gray-400 truncate">{t.summary}</div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

function StatusIndicator({ text, brandColor }: { text: string; brandColor: string }) {
    return (
        <div className="flex items-center gap-2 text-[11px] text-gray-500">
            <span className="flex gap-0.5">
                <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor }} />
                <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor, animationDelay: '120ms' }} />
                <span className="w-1 h-1 rounded-full animate-bounce" style={{ backgroundColor: brandColor, animationDelay: '240ms' }} />
            </span>
            <span className="italic">{text}</span>
        </div>
    );
}

/** Tiny live-updating mm:ss elapsed-time chip. Re-renders every second. */
function ElapsedTicker({ since }: { since: Date }) {
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(id);
    }, []);
    const sec = Math.max(0, Math.floor((now - since.getTime()) / 1000));
    if (sec < 3) return null; // hide for the first couple seconds — looks frantic otherwise
    const mm = Math.floor(sec / 60);
    const ss = sec % 60;
    return (
        <span className="text-[10px] text-gray-400 font-mono tabular-nums">
            {mm > 0 ? `${mm}m ${ss}s` : `${ss}s`}
        </span>
    );
}

function ThinkingIndicator({ status, brandColor }: { status: 'started' | 'done'; brandColor: string }) {
    if (status === 'done') return null;
    return (
        <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-2">
            <LightBulbIcon className="w-3.5 h-3.5 animate-pulse" style={{ color: brandColor }} />
            <span className="italic">Thinking deeply…</span>
        </div>
    );
}

const EnhancedMessageComponent: React.FC<EnhancedMessageComponentProps> = ({
    message,
    brandColor,
    onCitationClick,
    onDocClick,
    onDownload,
}) => {
    const [copied, setCopied] = useState(false);
    const [isVisible, setIsVisible] = useState(false);
    const messageRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const timer = setTimeout(() => setIsVisible(true), 50);
        return () => clearTimeout(timer);
    }, []);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(message.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {}
    };

    const formatTimestamp = (date: Date) => {
        const diff = Date.now() - date.getTime();
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        if (minutes < 1) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    };

    // While we wait for the first content delta we may still have status text,
    // tool activity, or thinking already populated — render those inside the bubble
    // rather than the generic typing indicator.
    const hasEarlyActivity = (
        (message.toolActivity && message.toolActivity.length > 0) ||
        message.thinking === 'started' ||
        Boolean(message.statusText)
    );

    if (message.isStreaming && !message.content && message.role === 'assistant' && !hasEarlyActivity) {
        return (
            <div className="flex justify-start mb-4">
                <TypingIndicator brandColor={brandColor} message="Analyzing documents..." isVisible={isVisible} />
            </div>
        );
    }

    if (message.role === 'system') {
        return (
            <div className={`flex justify-center mb-3 transition-all duration-300 ${isVisible ? 'opacity-100' : 'opacity-0'}`}>
                <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg text-xs text-gray-500 border border-gray-200">
                    <InformationCircleIcon className="w-3.5 h-3.5" />
                    <span>{message.content}</span>
                </div>
            </div>
        );
    }

    if (message.role === 'error') {
        return (
            <div className={`flex justify-center mb-3 transition-all duration-300 ${isVisible ? 'opacity-100' : 'opacity-0'}`}>
                <div className="flex items-center gap-2 px-3 py-2 bg-red-50 rounded-lg text-xs text-red-700 border border-red-200">
                    <ExclamationCircleIcon className="w-3.5 h-3.5" />
                    <span>{message.content}</span>
                </div>
            </div>
        );
    }

    const isUser = message.role === 'user';

    return (
        <div
            ref={messageRef}
            className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 transition-all duration-300 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}`}
        >
            <div className={`flex items-end gap-2.5 ${isUser ? 'flex-row-reverse' : ''} max-w-[85%]`}>
                <div
                    className="w-7 h-7 rounded-full flex items-center justify-center text-white flex-shrink-0 shadow"
                    style={{ backgroundColor: brandColor }}
                >
                    {isUser ? <UserIcon className="w-3.5 h-3.5" /> : <CpuChipIcon className="w-3.5 h-3.5" />}
                </div>

                <div className={`group relative rounded-2xl px-4 py-3 text-sm shadow-lg ${
                    isUser
                        ? 'text-white rounded-br-md'
                        : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md'
                }`} style={isUser ? { backgroundColor: brandColor } : {}}>

                    {!isUser && message.thinking && <ThinkingIndicator status={message.thinking} brandColor={brandColor} />}

                    {!isUser && message.statusText && message.isStreaming && !message.content && (
                        <StatusIndicator text={message.statusText} brandColor={brandColor} />
                    )}

                    {!isUser && message.toolActivity && message.toolActivity.length > 0 && (
                        <ToolActivityList items={message.toolActivity} brandColor={brandColor} />
                    )}

                    {!isUser && message.isStreaming && !message.content && (
                        <div className="mt-1.5">
                            <ElapsedTicker since={message.timestamp} />
                        </div>
                    )}

                    {isUser ? (
                        <span className="whitespace-pre-wrap">{message.content}</span>
                    ) : message.content ? (
                        <div className={message.toolActivity?.length || message.thinking ? 'mt-2' : ''}>
                            <EnhancedMarkdownRenderer
                                content={message.content}
                                onCitationClick={onCitationClick}
                                brandColor={brandColor}
                            />
                        </div>
                    ) : null}

                    {message.isStreaming && message.content && (
                        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-100">
                            <div className="flex gap-1">
                                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                            <span className="text-xs text-gray-400">Generating...</span>
                        </div>
                    )}

                    {!isUser && !message.isStreaming && message.content && (
                        <div className="absolute top-2 right-2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                            <button onClick={handleCopy} className="p-1 hover:bg-gray-100 rounded" title="Copy">
                                {copied ? <CheckIcon className="w-3 h-3" style={{ color: brandColor }} /> : <ClipboardIcon className="w-3 h-3 text-gray-400" />}
                            </button>
                            {onDownload && (
                                <button onClick={() => onDownload(message.content)} className="p-1 hover:bg-gray-100 rounded" title="Download">
                                    <ArrowDownTrayIcon className="w-3 h-3 text-gray-400" />
                                </button>
                            )}
                        </div>
                    )}

                    {!message.isStreaming && (
                        <div className="text-[10px] text-gray-400 mt-1.5">{formatTimestamp(message.timestamp)}</div>
                    )}
                </div>
            </div>

            {message.linkedDocs && message.linkedDocs.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1 ml-9">
                    {message.linkedDocs.map(ld => (
                        <button key={ld.id} onClick={() => onDocClick?.(ld.id, ld.filename)}
                            className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg hover:opacity-80 border"
                            style={{ backgroundColor: `${brandColor}10`, color: brandColor, borderColor: `${brandColor}30` }}>
                            <span className="truncate max-w-[180px]">{ld.filename}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

export default EnhancedMessageComponent;
