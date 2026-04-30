"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  FolderIcon, ChartBarIcon, Cog6ToothIcon, ArrowRightOnRectangleIcon,
  DocumentTextIcon, BuildingOfficeIcon, AcademicCapIcon, GlobeAltIcon,
  CalendarDaysIcon, SparklesIcon, Bars3Icon, XMarkIcon,
  ChevronLeftIcon, ChevronRightIcon, UserIcon, BuildingStorefrontIcon,
  MusicalNoteIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";

const navItems = [
  { name: "Dashboard", href: "/", icon: ChartBarIcon },
  { name: "Documents", href: "/document-library", icon: FolderIcon },
  {
    name: "Financials",
    href: "/financial-analysis",
    icon: DocumentTextIcon,
    children: [
      { name: "Statements", href: "/financial-analysis/statements", icon: DocumentTextIcon },
      { name: "Narrative", href: "/financial-analysis/narrative", icon: DocumentTextIcon },
      { name: "Town", href: "/financial-analysis?entity=town", icon: BuildingOfficeIcon },
      { name: "School", href: "/financial-analysis?entity=school", icon: AcademicCapIcon },
    ],
  },
  { name: "Calendar", href: "/calendar", icon: CalendarDaysIcon },
  { name: "Local Business", href: "/local-business", icon: BuildingStorefrontIcon },
  { name: "Events", href: "/events", icon: MusicalNoteIcon },
  { name: "Reports", href: "/reports", icon: SparklesIcon },
  { name: "Scraper", href: "/scraper", icon: GlobeAltIcon },
  { name: "Admin", href: "/admin", icon: Cog6ToothIcon, adminOnly: true },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;

  const sidebar = (
    <aside className={`bg-white border-r border-gray-200 flex flex-col transition-all ${collapsed ? "w-16" : "w-64"} h-full`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: brandColor }}
              >
                <span className="text-white font-bold text-sm">AH</span>
              </div>
              <div>
                <h1 className="text-sm font-semibold text-gray-900 leading-tight">Atlantic Highlands</h1>
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

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          if (item.adminOnly && !user.is_admin) return null;
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;

          return (
            <div key={item.name}>
              <Link href={item.href} onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all ${
                  isActive ? "text-white shadow-md" : "text-gray-700 hover:bg-gray-50"
                }`}
                style={isActive ? { backgroundColor: brandColor } : {}}
                title={collapsed ? item.name : undefined}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {!collapsed && <span className="font-medium">{item.name}</span>}
              </Link>
              {!collapsed && item.children && isActive && (
                <div className="ml-8 mt-0.5 space-y-0.5">
                  {item.children.map((child) => {
                    const childActive = pathname === child.href;
                    return (
                      <Link key={child.name} href={child.href} onClick={() => setMobileOpen(false)}
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
              )}
            </div>
          );
        })}
      </nav>

      {/* User */}
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
          <button onClick={logout} className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500 hover:text-gray-700" title="Logout">
            <ArrowRightOnRectangleIcon className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button onClick={() => setMobileOpen(true)} className="md:hidden fixed top-3 left-3 z-40 p-2 bg-white text-gray-700 rounded-lg shadow-lg border border-gray-200">
        <Bars3Icon className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="w-64">{sidebar}</div>
          <div className="flex-1 bg-black/50" onClick={() => setMobileOpen(false)}>
            <button className="absolute top-3 right-3 p-2 text-white"><XMarkIcon className="w-5 h-5" /></button>
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden md:flex">{sidebar}</div>
    </>
  );
}
