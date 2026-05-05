'use client';

/**
 * Small set of brand-aligned primitives exposed to AI-generated TSX.
 * Keeps Claude's output looking like the rest of the deck instead of
 * raw divs.
 */
import React from 'react';
import { TrendingUp, TrendingDown, AlertCircle, CheckCircle2 } from 'lucide-react';

const BRAND = '#385854';

export function KPICard({ label, value, delta, trend, sub }: {
  label: string;
  value: string | number;
  delta?: string;
  trend?: 'up' | 'down' | 'flat';
  sub?: string;
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : null;
  const trendColor = trend === 'up' ? 'text-emerald-600' : trend === 'down' ? 'text-red-600' : 'text-gray-500';
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-gray-900">{value}</div>
      {(delta || trend) && (
        <div className={`mt-1 flex items-center gap-1 text-xs ${trendColor}`}>
          {TrendIcon && <TrendIcon className="w-3 h-3" />}
          {delta && <span>{delta}</span>}
        </div>
      )}
      {sub && <div className="mt-1 text-[11px] text-gray-500">{sub}</div>}
    </div>
  );
}

export function Callout({ kind = 'info', title, children }: {
  kind?: 'info' | 'warn' | 'success';
  title?: string;
  children: React.ReactNode;
}) {
  const styles = {
    info: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-900', Icon: AlertCircle },
    warn: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-900', Icon: AlertCircle },
    success: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-900', Icon: CheckCircle2 },
  }[kind];
  return (
    <div className={`rounded-lg border p-3 ${styles.bg} ${styles.border}`}>
      <div className={`flex items-start gap-2 ${styles.text}`}>
        <styles.Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div className="flex-1 text-sm">
          {title && <div className="font-semibold mb-1">{title}</div>}
          <div>{children}</div>
        </div>
      </div>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-sm font-semibold text-gray-900">{value}</div>
    </div>
  );
}

export function Section({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      {title && <h3 className="text-base font-semibold text-gray-900" style={{ color: BRAND }}>{title}</h3>}
      <div>{children}</div>
    </section>
  );
}

export const AH_BRAND = BRAND;
