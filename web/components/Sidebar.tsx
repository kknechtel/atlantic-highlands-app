"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  FolderIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  DocumentTextIcon,
  BuildingOfficeIcon,
  AcademicCapIcon,
  GlobeAltIcon,
} from "@heroicons/react/24/outline";

const navItems = [
  { name: "Dashboard", href: "/", icon: ChartBarIcon },
  { name: "Document Library", href: "/document-library", icon: FolderIcon },
  {
    name: "Financial Analysis",
    href: "/financial-analysis",
    icon: DocumentTextIcon,
    children: [
      { name: "Narrative", href: "/financial-analysis/narrative", icon: DocumentTextIcon },
      { name: "Town", href: "/financial-analysis?entity=town", icon: BuildingOfficeIcon },
      { name: "School District", href: "/financial-analysis?entity=school", icon: AcademicCapIcon },
    ],
  },
  { name: "Scraper", href: "/scraper", icon: GlobeAltIcon },
  { name: "Admin", href: "/admin", icon: Cog6ToothIcon, adminOnly: true },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  if (!user) return null;

  return (
    <aside
      className={`bg-gray-900 text-white flex flex-col transition-all ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <button onClick={() => setCollapsed(!collapsed)} className="w-full text-left">
          {collapsed ? (
            <span className="text-lg font-bold">AH</span>
          ) : (
            <h1 className="text-lg font-bold">Atlantic Highlands</h1>
          )}
        </button>
        {!collapsed && (
          <p className="text-xs text-gray-400 mt-1">Document Library & Financial Analysis</p>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          if (item.adminOnly && !user.is_admin) return null;
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;

          return (
            <div key={item.name}>
              <Link
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-primary-600 text-white"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {!collapsed && <span>{item.name}</span>}
              </Link>
              {!collapsed && item.children && (
                <div className="ml-8 mt-1 space-y-1">
                  {item.children.map((child) => (
                    <Link
                      key={child.name}
                      href={child.href}
                      className="flex items-center gap-2 px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
                    >
                      <child.icon className="w-4 h-4" />
                      <span>{child.name}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* User section */}
      <div className="p-4 border-t border-gray-700">
        {!collapsed && (
          <p className="text-sm text-gray-300 mb-2 truncate">{user.email}</p>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRightOnRectangleIcon className="w-5 h-5" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );
}
