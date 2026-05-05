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
                        const cleanJson = chartJson.trim();
                        charts.push({ id, config: cleanJson });
                        // Build a fallback HTML table from the chart config so the
                        // numbers are ALWAYS visible — Chart.js may fail silently
                        // on some deployments / ad-blocker configs, leaving an
                        // empty 320px box. The fallback renders inline; once
                        // Chart.js mounts a real chart, the fallback hides itself.
                        let fallback = '';
                        try {
                            const cfg = JSON.parse(cleanJson);
                            const labels: string[] = cfg?.data?.labels || [];
                            const datasets: { label?: string; data?: number[] }[] = cfg?.data?.datasets || [];
                            if (labels.length && datasets.length) {
                                const head = `<th style="text-align:left;padding:4px 8px;font-weight:600;border-bottom:1px solid #e5e7eb">Label</th>` +
                                    datasets.map((d) => `<th style="text-align:right;padding:4px 8px;font-weight:600;border-bottom:1px solid #e5e7eb">${(d.label || 'Value').replace(/</g, '&lt;')}</th>`).join('');
                                const rows = labels.map((lbl, i) => {
                                    const cells = datasets.map((d) => {
                                        const v = d.data?.[i];
                                        const txt = typeof v === 'number'
                                            ? v.toLocaleString('en-US', { maximumFractionDigits: 2 })
                                            : (v == null ? '—' : String(v));
                                        return `<td style="text-align:right;padding:4px 8px;border-bottom:1px solid #f3f4f6">${txt}</td>`;
                                    }).join('');
                                    return `<tr><td style="padding:4px 8px;border-bottom:1px solid #f3f4f6">${String(lbl).replace(/</g, '&lt;')}</td>${cells}</tr>`;
                                }).join('');
                                const title = (cfg?.options?.plugins?.title?.text || '').replace(/</g, '&lt;');
                                fallback = `<details class="ah-chart-fallback" style="margin:8px 0 16px;font-size:0.75rem;border:1px solid #e5e7eb;border-radius:6px;padding:8px 12px;background:#fafafa">` +
                                    `<summary style="cursor:pointer;color:#6b7280;font-weight:500">Chart data${title ? ': ' + title : ''}</summary>` +
                                    `<table style="width:100%;margin-top:8px;border-collapse:collapse"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>` +
                                    `</details>`;
                            }
                        } catch {
                            // Bad JSON — let the regular fallback in the chart renderer handle it.
                        }
                        // Container needs an explicit height: with maintainAspectRatio:false
                        // Chart.js sizes to its parent and renders 0px tall otherwise.
                        return `<div class="ah-chart" data-chart-id="${id}" data-chart='${cleanJson.replace(/'/g, "&apos;")}' style="position:relative;height:320px;width:100%;margin:12px 0"><canvas id="${id}"></canvas></div>${fallback}`;
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

        // Cancellation flag for the async effect — so a stale render pass
        // (e.g. after content prop changed) can't push fallback notices into
        // the now-fresh DOM and clobber a successfully rendered chart.
        let cancelled = false;
        const cleanup: (() => void)[] = [];

        (async () => {
            try {
                // Chart.js v4 splits controllers from elements; `registerables` is
                // the bundle of everything — registering only elements throws
                // "X is not a registered controller".
                const { Chart, registerables } = await import('chart.js');
                Chart.register(...registerables);
                if (cancelled) return;

                const showFallback = (div: Element, msg: string) => {
                    if (!div.isConnected) return; // div was already removed
                    const note = document.createElement('div');
                    note.className = 'text-xs text-gray-400 italic py-2 px-3 border border-gray-200 rounded bg-gray-50';
                    note.textContent = `Chart unavailable: ${msg}`;
                    note.style.height = 'auto';
                    div.replaceWith(note);
                };

                chartDivs.forEach((div) => {
                    if (cancelled || !div.isConnected) return;
                    // Skip if already rendered in a prior pass (StrictMode
                    // double-invokes effects — without this guard the second
                    // pass clobbers the chart created by the first).
                    if (div.getAttribute('data-rendered') === '1') return;

                    const canvas = div.querySelector('canvas') as HTMLCanvasElement;
                    const configStr = div.getAttribute('data-chart');
                    if (!canvas || !configStr) {
                        showFallback(div, 'no canvas/config');
                        return;
                    }

                    // If this canvas already has a Chart attached (StrictMode
                    // remount, hot reload), tear it down before recreating.
                    Chart.getChart(canvas)?.destroy();

                    try {
                        const config = JSON.parse(configStr.replace(/&apos;/g, "'"));
                        const datasets = config?.data?.datasets;
                        const labels = config?.data?.labels;
                        if (!Array.isArray(datasets) || datasets.length === 0
                            || !Array.isArray(labels) || labels.length === 0) {
                            showFallback(div, 'empty dataset');
                            return;
                        }
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
                        div.setAttribute('data-rendered', '1');
                        cleanup.push(() => chart.destroy());
                    } catch (e) {
                        console.warn('[chart] render failed:', e, { configStr: configStr.slice(0, 200) });
                        const msg = e instanceof Error ? e.message : 'render error';
                        showFallback(div, msg.slice(0, 80));
                    }
                });
            } catch (e) {
                console.warn('[chart] Chart.js not available:', e);
                // Make the failure visible — without this the divs sit as
                // 320px blank space.
                if (!cancelled) {
                    chartDivs.forEach((div) => {
                        if (!div.isConnected || div.getAttribute('data-rendered') === '1') return;
                        const note = document.createElement('div');
                        note.className = 'text-xs text-gray-400 italic py-2 px-3 border border-gray-200 rounded bg-gray-50';
                        note.textContent = 'Chart unavailable: failed to load chart library';
                        div.replaceWith(note);
                    });
                }
            }
        })();

        return () => {
            cancelled = true;
            cleanup.forEach(fn => fn());
        };
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
