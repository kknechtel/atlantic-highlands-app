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

                // Extract chart blocks before markdown parsing
                const charts: { id: string; config: string }[] = [];
                let processedContent = (content || '').replace(
                    /```chart\s*\n([\s\S]*?)\n```/g,
                    (_match, chartJson) => {
                        const id = `chart-${charts.length}`;
                        charts.push({ id, config: chartJson.trim() });
                        return `<div class="ah-chart" data-chart-id="${id}" data-chart='${chartJson.trim().replace(/'/g, "&apos;")}'><canvas id="${id}" style="max-height:300px"></canvas></div>`;
                    }
                );

                const rendered = await marked.parse(processedContent, {
                    gfm: true,
                    breaks: true,
                });

                // Process [source: filename] citations AFTER markdown rendering.
                // Split on commas, pipes, semicolons — Claude varies the separator
                // when listing multiple sources in one tag.
                let final = (typeof rendered === 'string' ? rendered : String(rendered));
                final = final.replace(
                    /\[source:\s*([^\]]+)\]/g,
                    (_match, filenames) => {
                        const buttonStyle = `display:inline-flex;align-items:center;gap:3px;background:${brandColor}12;color:${brandColor};border:1px solid ${brandColor}30;padding:2px 8px;border-radius:5px;font-size:0.7rem;cursor:pointer;font-weight:500;margin:0 2px`;
                        return String(filenames)
                            .split(/\s*[,|;]\s*|\s+\|\s+/)
                            .map((fn: string) => fn.trim())
                            .filter((fn: string) => fn.length > 0)
                            .map((fn: string) => {
                                const escaped = fn.replace(/"/g, '&quot;');
                                return `<button class="ah-citation" data-filename="${escaped}" style="${buttonStyle}">📄 ${fn}</button>`;
                            })
                            .join('');
                    }
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

    // Render charts after HTML is set
    useEffect(() => {
        if (!html || isLoading || !containerRef.current) return;

        const chartDivs = containerRef.current.querySelectorAll('.ah-chart');
        if (chartDivs.length === 0) return;

        let cleanup: (() => void)[] = [];

        (async () => {
            try {
                // Chart.js v4 splits controllers (BarController, LineController, PieController)
                // from elements (BarElement, ArcElement). `registerables` is the bundle of
                // everything — registering only elements gives "X is not a registered controller".
                const { Chart, registerables } = await import('chart.js');
                Chart.register(...registerables);

                chartDivs.forEach((div) => {
                    const canvas = div.querySelector('canvas') as HTMLCanvasElement;
                    const configStr = div.getAttribute('data-chart');
                    if (!canvas || !configStr) return;

                    try {
                        const config = JSON.parse(configStr.replace(/&apos;/g, "'"));
                        const chart = new Chart(canvas, {
                            type: config.type || 'bar',
                            data: config.data,
                            options: {
                                ...config.options,
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    ...config.options?.plugins,
                                    legend: { display: true, position: 'bottom' as const },
                                },
                            },
                        });
                        cleanup.push(() => chart.destroy());
                    } catch (e) {
                        console.warn('Failed to render chart:', e);
                    }
                });
            } catch (e) {
                console.warn('Chart.js not available:', e);
            }
        })();

        return () => { cleanup.forEach(fn => fn()); };
    }, [html, isLoading]);

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
