"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  FolderIcon, ChartBarIcon, Cog6ToothIcon, ArrowRightOnRectangleIcon,
  DocumentTextIcon, BuildingOfficeIcon, AcademicCapIcon, GlobeAltIcon,
  CalendarDaysIcon, SparklesIcon, Bars3Icon, XMarkIcon,
} from "@heroicons/react/24/outline";

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
    <aside className={`bg-gray-900 text-white flex flex-col transition-all ${collapsed ? "w-14" : "w-56"} h-full`}>
      {/* Header */}
      <div className="p-3 border-b border-gray-700">
        <button onClick={() => setCollapsed(!collapsed)} className="w-full text-left flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">AH</span>
          </div>
          {!collapsed && (
            <div>
              <h1 className="text-sm font-bold leading-tight">Atlantic Highlands</h1>
              <p className="text-[10px] text-gray-400">Document Intelligence</p>
            </div>
          )}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-1.5 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          if (item.adminOnly && !user.is_admin) return null;
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;

          return (
            <div key={item.name}>
              <Link href={item.href} onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs transition-colors ${
                  isActive ? "bg-green-600 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`}>
                <Icon className="w-4 h-4 flex-shrink-0" />
                {!collapsed && <span>{item.name}</span>}
              </Link>
              {!collapsed && item.children && isActive && (
                <div className="ml-7 mt-0.5 space-y-0.5">
                  {item.children.map((child) => (
                    <Link key={child.name} href={child.href} onClick={() => setMobileOpen(false)}
                      className="flex items-center gap-2 px-2.5 py-1.5 rounded text-[11px] text-gray-400 hover:text-white hover:bg-gray-800">
                      <child.icon className="w-3 h-3" /><span>{child.name}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div className="p-3 border-t border-gray-700">
        {!collapsed && <p className="text-xs text-gray-400 mb-2 truncate">{user.email}</p>}
        <button onClick={logout} className="flex items-center gap-2 text-xs text-gray-400 hover:text-white">
          <ArrowRightOnRectangleIcon className="w-4 h-4" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button onClick={() => setMobileOpen(true)} className="md:hidden fixed top-3 left-3 z-40 p-2 bg-gray-900 text-white rounded-lg shadow-lg">
        <Bars3Icon className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="w-56">{sidebar}</div>
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
