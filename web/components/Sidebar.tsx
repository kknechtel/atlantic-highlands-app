"use client";
import { TOWN, SITE_HOST, EVENTS_URL } from "@/lib/municipality";

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  FolderIcon, ChartBarIcon, Cog6ToothIcon, ArrowRightOnRectangleIcon,
  BuildingOfficeIcon, AcademicCapIcon, GlobeAltIcon,
  CalendarDaysIcon,
  ChevronLeftIcon, ChevronRightIcon, UserIcon,
  ClipboardDocumentListIcon, PresentationChartLineIcon,
  MicrophoneIcon, HomeModernIcon, BellIcon, ArrowTopRightOnSquareIcon,
  HomeIcon, TableCellsIcon, WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";

const brandColor = TOWN.brand_color;

type NavItem = {
  name: string;
  href: string;
  icon: typeof ChartBarIcon;
  children?: { name: string; href: string; icon: typeof ChartBarIcon }[];
};

const navGroups: { label?: string; adminOnly?: boolean; items: NavItem[] }[] = [
  {
    items: [
      { name: "Home", href: "/", icon: HomeIcon },
      { name: "Borough", href: "/town", icon: BuildingOfficeIcon },
      { name: "School District", href: "/school", icon: AcademicCapIcon },
      {
        name: "Finances",
        href: "/financial-analysis",
        icon: ChartBarIcon,
        children: [
          { name: "Borough", href: "/financial-analysis?entity=town", icon: BuildingOfficeIcon },
          { name: "School", href: "/financial-analysis?entity=school", icon: AcademicCapIcon },
          { name: "Line items", href: "/financial-analysis/statements", icon: TableCellsIcon },
        ],
      },
      { name: "Meetings", href: "/meetings", icon: MicrophoneIcon },
      { name: "Calendar", href: "/calendar", icon: CalendarDaysIcon },
      { name: "Documents", href: "/document-library", icon: FolderIcon },
      { name: "Property & Tax", href: "/parcels", icon: HomeModernIcon },
    ],
  },
  {
    label: "Tools",
    items: [
      { name: "OPRA Requests", href: "/opra", icon: ClipboardDocumentListIcon },
      { name: "Alerts", href: "/alerts", icon: BellIcon },
      { name: "Presentations", href: "/presentations", icon: PresentationChartLineIcon },
    ],
  },
  {
    label: "Admin",
    adminOnly: true,
    items: [
      { name: "Financial data", href: "/financial-analysis/data", icon: WrenchScrewdriverIcon },
      { name: "Scraper", href: "/scraper", icon: GlobeAltIcon },
    ],
  },
];

// A child is active when its path matches and every query param it names
// matches too. Lives in its own component because useSearchParams needs a
// Suspense boundary in the App Router.
function NavChildren({ items }: { items: NonNullable<NavItem["children"]> }) {
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <div className="ml-8 mt-0.5 space-y-0.5">
      {items.map((child) => {
        const [path, query] = child.href.split("?");
        const childActive = pathname === path &&
          Array.from(new URLSearchParams(query ?? "")).every(([k, v]) => (params.get(k) ?? "town") === v);
        return (
          <Link key={child.name} href={child.href}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-colors ${
              childActive ? "font-medium" : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
            }`}
            style={childActive ? { color: brandColor } : {}}
          >
            <child.icon className="w-3.5 h-3.5" /><span>{child.name}</span>
          </Link>
        );
      })}
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  if (!user) return null;

  const sidebar = (
    <aside className={`bg-white border-r border-gray-200 flex flex-col transition-all ${collapsed ? "w-16" : "w-64"} h-full`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/events-logo.png"
                alt={SITE_HOST}
                className="w-10 h-10 object-contain flex-shrink-0"
              />
              <div>
                <h1 className="text-sm font-semibold text-gray-900 leading-tight">{TOWN.name}</h1>
                <p className="text-[10px] text-gray-500">Document Intelligence</p>
              </div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500 hover:text-gray-700"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRightIcon className="w-5 h-5" />
            ) : (
              <ChevronLeftIcon className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Nav — Admin link moved to the bottom panel next to email/logout. */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {navGroups.filter((g) => !g.adminOnly || user.is_admin).map((group, gi) => (
          <div key={gi} className={gi ? "pt-3" : ""}>
            {group.label && !collapsed && (
              <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">{group.label}</p>
            )}
            {group.label && collapsed && <div className="mx-3 mb-2 border-t border-gray-200" />}
            {group.items.map((item) => {
              const isActive = item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(item.href + "/");
              // Finances children stay visible on its sub-pages; Financial data
              // has its own entry so it shouldn't also light up Finances.
              const ownedElsewhere = item.href === "/financial-analysis" && pathname.startsWith("/financial-analysis/data");
              const Icon = item.icon;

              return (
                <div key={item.name}>
                  <Link href={item.href}
                    className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all ${
                      isActive && !ownedElsewhere ? "text-white shadow-md" : "text-gray-700 hover:bg-gray-50"
                    }`}
                    style={isActive && !ownedElsewhere ? { backgroundColor: brandColor } : {}}
                    title={collapsed ? item.name : undefined}
                  >
                    <Icon className="w-5 h-5 flex-shrink-0" />
                    {!collapsed && <span className="font-medium">{item.name}</span>}
                  </Link>
                  {!collapsed && item.children && isActive && !ownedElsewhere && (
                    <Suspense fallback={null}>
                      <NavChildren items={item.children} />
                    </Suspense>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Cross-app link to the community subdomain. External href (not next/Link)
          because we want a hard navigation across origins. */}
      {!collapsed && (
        <div className="px-2 pb-2">
          <a
            href={EVENTS_URL}
            target="_blank"
            rel="noopener"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-gray-600 hover:bg-gray-50 border border-gray-200"
          >
            <ArrowTopRightOnSquareIcon className="w-4 h-4 flex-shrink-0" />
            <span>Around Town — events &amp; check-ins</span>
          </a>
        </div>
      )}

      {/* User — admin link lives here next to the email so it's clearly an
          account-level surface, not part of the primary product nav. */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
            <UserIcon className="w-4 h-4 text-gray-600" />
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user.email}</p>
            </div>
          )}
          {user.is_admin && (
            <Link
              href="/admin"
              className={`p-1.5 rounded-md hover:bg-gray-100 text-gray-500 hover:text-gray-700 ${
                pathname === "/admin" || pathname.startsWith("/admin/") ? "bg-gray-100 text-gray-900" : ""
              }`}
              title="Admin"
            >
              <Cog6ToothIcon className="w-4 h-4" />
            </Link>
          )}
          <button onClick={logout} className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500 hover:text-gray-700" title="Logout">
            <ArrowRightOnRectangleIcon className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );

  // Sidebar is only mounted in the desktop branch of AuthGate (Providers.tsx)
  // — mobile uses MobileNav instead. So we render the sidebar directly with
  // no mobile-specific overlay logic.
  return sidebar;
}
