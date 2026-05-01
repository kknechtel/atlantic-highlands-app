'use client';

import React, { useEffect, useRef, useState } from 'react';

interface EnhancedMarkdownRendererProps {
    content: string;
    onCitationClick?: (info: { filename: string }) => void;
    brandColor?: string;
}

const EnhancedMarkdownRenderer: React.FC<EnhancedMarkdownRendererProps> = ({
    content,
    onCitationClick,
    brandColor = '#385854'
}) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [html, setHtml] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        let isMounted = true;
        const render = async () => {
            try {
                setIsLoading(true);
                const { marked } = await import('marked');

                const rendered = await marked.parse(content || '', {
                    gfm: true,
                    breaks: true,
                });

                // Process [source: filename] citations AFTER markdown rendering
                // so marked doesn't escape our HTML
                let final = (typeof rendered === 'string' ? rendered : String(rendered));
                final = final.replace(
                    /\[source:\s*([^\]]+)\]/g,
                    `<button class="ah-citation" data-filename="$1" style="display:inline-flex;align-items:center;gap:3px;background:${brandColor}12;color:${brandColor};border:1px solid ${brandColor}30;padding:2px 8px;border-radius:5px;font-size:0.7rem;cursor:pointer;font-weight:500;margin:0 2px">📄 $1</button>`
                );

                if (isMounted) {
                    setHtml(final);
                    setIsLoading(false);
                }
            } catch (error) {
                console.warn('Markdown rendering failed, falling back to basic:', error);
                const escaped = (content || '')
                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\n/g, '<br/>');
                if (isMounted) {
                    setHtml(escaped);
                    setIsLoading(false);
                }
            }
        };
        render();
        return () => { isMounted = false; };
    }, [content, brandColor]);

    const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
        const target = e.target as HTMLElement;
        if (target.classList.contains('ah-citation') && onCitationClick) {
            e.preventDefault();
            const filename = target.getAttribute('data-filename') || '';
            if (filename) onCitationClick({ filename: filename.trim() });
        }
    };

    return (
        <div
            ref={containerRef}
            onClick={handleClick}
            className={`enhanced-markdown prose prose-sm max-w-none transition-opacity duration-200 ${isLoading ? 'opacity-50' : 'opacity-100'}`}
            dangerouslySetInnerHTML={{ __html: html }}
        />
    );
};

export default EnhancedMarkdownRenderer;
