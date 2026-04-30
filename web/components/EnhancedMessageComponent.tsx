'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
    UserIcon,
    CpuChipIcon,
    ClipboardIcon,
    CheckIcon,
    ClockIcon,
    ExclamationCircleIcon,
    InformationCircleIcon,
    ArrowDownTrayIcon,
} from '@heroicons/react/24/outline';
import EnhancedMarkdownRenderer from './EnhancedMarkdownRenderer';
import TypingIndicator from './TypingIndicator';

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant' | 'error' | 'system';
    content: string;
    timestamp: Date;
    isStreaming?: boolean;
    linkedDocs?: { id: string; filename: string }[];
}

interface EnhancedMessageComponentProps {
    message: ChatMessage;
    brandColor: string;
    onCitationClick?: (info: { filename: string }) => void;
    onDocClick?: (docId: string, filename: string) => void;
    onDownload?: (content: string) => void;
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

    // Typing indicator for empty streaming messages
    if (message.isStreaming && !message.content && message.role === 'assistant') {
        return (
            <div className="flex justify-start mb-4">
                <TypingIndicator brandColor={brandColor} message="Analyzing documents..." isVisible={isVisible} />
            </div>
        );
    }

    // System messages
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

    // Error messages
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
                {/* Avatar */}
                <div
                    className="w-7 h-7 rounded-full flex items-center justify-center text-white flex-shrink-0 shadow"
                    style={{ backgroundColor: isUser ? brandColor : brandColor }}
                >
                    {isUser ? <UserIcon className="w-3.5 h-3.5" /> : <CpuChipIcon className="w-3.5 h-3.5" />}
                </div>

                {/* Bubble */}
                <div className={`group relative rounded-2xl px-4 py-3 text-sm shadow-lg ${
                    isUser
                        ? 'text-white rounded-br-md'
                        : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md'
                }`} style={isUser ? { backgroundColor: brandColor } : {}}>

                    {/* Content */}
                    {isUser ? (
                        <span className="whitespace-pre-wrap">{message.content}</span>
                    ) : (
                        <EnhancedMarkdownRenderer
                            content={message.content}
                            onCitationClick={onCitationClick}
                            brandColor={brandColor}
                        />
                    )}

                    {/* Streaming indicator */}
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

                    {/* Action buttons */}
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

                    {/* Timestamp */}
                    {!message.isStreaming && (
                        <div className="text-[10px] text-gray-400 mt-1.5">{formatTimestamp(message.timestamp)}</div>
                    )}
                </div>
            </div>

            {/* Linked docs */}
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
