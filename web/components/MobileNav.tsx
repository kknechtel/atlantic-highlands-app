"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChartBarIcon,
  FolderIcon,
  CalendarDaysIcon,
  PresentationChartLineIcon,
  EllipsisHorizontalIcon,
} from "@heroicons/react/24/outline";
import {
  ChartBarIcon as ChartBarSolid,
  FolderIcon as FolderSolid,
  CalendarDaysIcon as CalendarSolid,
  PresentationChartLineIcon as PresentationSolid,
} from "@heroicons/react/24/solid";
import { useState } from "react";

const brandColor = "#385854";

const mainTabs = [
  { name: "Home", href: "/", icon: ChartBarIcon, activeIcon: ChartBarSolid },
  { name: "Docs", href: "/document-library", icon: FolderIcon, activeIcon: FolderSolid },
  { name: "Decks", href: "/presentations", icon: PresentationChartLineIcon, activeIcon: PresentationSolid },
  { name: "Calendar", href: "/calendar", icon: CalendarDaysIcon, activeIcon: CalendarSolid },
  { name: "More", href: "#more", icon: EllipsisHorizontalIcon, activeIcon: EllipsisHorizontalIcon },
];

const moreItems = [
  { name: "Local Business", href: "/local-business" },
  { name: "Events", href: "/events" },
  { name: "Financials", href: "/financial-analysis" },
  { name: "OPRA Requests", href: "/opra" },
  { name: "Scraper", href: "/scraper" },
  { name: "Admin", href: "/admin" },
];

const DISMISSED_CHAT_KEY = "ah_chat_dismissed";

export default function MobileNav() {
  const pathname = usePathname();
  const [showMore, setShowMore] = useState(false);

  return (
    <>
      {/* More menu overlay */}
      {showMore && (
        <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setShowMore(false)}>
          <div className="absolute bottom-16 left-0 right-0 bg-white border-t border-gray-200 rounded-t-2xl shadow-xl p-4"
            onClick={e => e.stopPropagation()}>
            <div className="grid grid-cols-3 gap-3">
              {moreItems.map(item => (
                <Link key={item.href} href={item.href} onClick={() => setShowMore(false)}
                  className={`flex flex-col items-center gap-1 p-3 rounded-xl transition-colors ${
                    pathname === item.href || pathname.startsWith(item.href + "/")
                      ? "bg-gray-100" : "hover:bg-gray-50"
                  }`}>
                  <span className="text-sm font-medium text-gray-700">{item.name}</span>
                </Link>
              ))}
              <button
                onClick={() => {
                  // Touch counterpart to Cmd/Ctrl+/ on desktop. The chat
                  // listens for this event and re-opens itself.
                  localStorage.removeItem(DISMISSED_CHAT_KEY);
                  window.dispatchEvent(new Event("ah:show-chat"));
                  setShowMore(false);
                }}
                className="flex flex-col items-center gap-1 p-3 rounded-xl hover:bg-gray-50 transition-colors"
              >
                <span className="text-sm font-medium text-gray-700">Show chat</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bottom tab bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-30 bg-white border-t border-gray-200 safe-area-bottom">
        <div className="flex items-center justify-around h-16 px-2">
          {mainTabs.map(tab => {
            const isMore = tab.href === "#more";
            const isActive = isMore ? showMore : (
              tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href)
            );
            const Icon = isActive ? tab.activeIcon : tab.icon;
            const baseClass = "flex flex-col items-center gap-0.5 px-3 py-1 min-w-0 min-h-[44px] justify-center";
            const labelClass = `text-[10px] font-medium ${isActive ? "" : "text-gray-400"}`;
            const labelStyle = isActive ? { color: brandColor } : {};
            const iconStyle = isActive ? { color: brandColor } : { color: "#9ca3af" };

            if (isMore) {
              return (
                <button
                  key={tab.name}
                  onClick={() => setShowMore(s => !s)}
                  className={baseClass}
                  aria-label="More navigation options"
                  aria-expanded={showMore}
                >
                  <Icon className="w-6 h-6" style={iconStyle} />
                  <span className={labelClass} style={labelStyle}>{tab.name}</span>
                </button>
              );
            }

            // Link uses Next router internally (no full page reload), so the
            // chat panel, scroll position, and React Query cache survive
            // navigation.
            return (
              <Link
                key={tab.name}
                href={tab.href}
                onClick={() => setShowMore(false)}
                className={baseClass}
                prefetch
              >
                <Icon className="w-6 h-6" style={iconStyle} />
                <span className={labelClass} style={labelStyle}>{tab.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
