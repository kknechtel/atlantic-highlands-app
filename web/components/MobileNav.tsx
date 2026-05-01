"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChartBarIcon,
  FolderIcon,
  CalendarDaysIcon,
  BuildingStorefrontIcon,
  EllipsisHorizontalIcon,
} from "@heroicons/react/24/outline";
import {
  ChartBarIcon as ChartBarSolid,
  FolderIcon as FolderSolid,
  CalendarDaysIcon as CalendarSolid,
  BuildingStorefrontIcon as StorefrontSolid,
} from "@heroicons/react/24/solid";
import { useState } from "react";

const brandColor = "#385854";

const mainTabs = [
  { name: "Home", href: "/", icon: ChartBarIcon, activeIcon: ChartBarSolid },
  { name: "Docs", href: "/document-library", icon: FolderIcon, activeIcon: FolderSolid },
  { name: "Calendar", href: "/calendar", icon: CalendarDaysIcon, activeIcon: CalendarSolid },
  { name: "Local", href: "/local-business", icon: BuildingStorefrontIcon, activeIcon: StorefrontSolid },
  { name: "More", href: "#more", icon: EllipsisHorizontalIcon, activeIcon: EllipsisHorizontalIcon },
];

const moreItems = [
  { name: "Events", href: "/events" },
  { name: "Financials", href: "/financial-analysis" },
  { name: "Reports", href: "/reports" },
  { name: "Scraper", href: "/scraper" },
  { name: "Admin", href: "/admin" },
];

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

            return (
              <button
                key={tab.name}
                onClick={() => {
                  if (isMore) {
                    setShowMore(!showMore);
                  } else {
                    setShowMore(false);
                    window.location.href = tab.href;
                  }
                }}
                className="flex flex-col items-center gap-0.5 px-3 py-1 min-w-0"
              >
                <Icon className="w-6 h-6" style={isActive ? { color: brandColor } : { color: "#9ca3af" }} />
                <span className={`text-[10px] font-medium ${isActive ? "" : "text-gray-400"}`}
                  style={isActive ? { color: brandColor } : {}}>
                  {tab.name}
                </span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
