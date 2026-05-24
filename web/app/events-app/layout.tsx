"use client";

// Events-app shell (events.ahnj.info). Brings its own brand color, top
// header, and a bottom-tab nav. The civic-research sidebar/GlobalChat is
// suppressed by the AuthGate when pathname starts with /events-app.
//
// The tab nav uses CLEAN URLs (no /events-app prefix) — the middleware
// rewrites the user-visible URL on every request, so a `<Link href="/calendar">`
// from a page served under events.ahnj.info navigates to
// events.ahnj.info/calendar which the middleware then routes to
// /events-app/calendar/page.tsx.

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  HomeIcon, CalendarDaysIcon, BuildingStorefrontIcon,
  MapPinIcon, ChatBubbleLeftRightIcon,
} from "@heroicons/react/24/outline";
import {
  HomeIcon as HomeSolid, CalendarDaysIcon as CalendarSolid,
  BuildingStorefrontIcon as StoreSolid,
  MapPinIcon as PinSolid, ChatBubbleLeftRightIcon as ChatSolid,
} from "@heroicons/react/24/solid";

// Lighter, friendlier brand color than the civic-research deep teal —
// signals "community + going-out" vs "compliance + research".
const eventsBrand = "#1d7a6c";

// Strip the /events-app prefix before comparing pathnames; on the
// subdomain the middleware-rewritten pathname carries it, but our Link
// hrefs don't. Matching both shapes keeps the active-tab logic stable
// across dev (direct path) and prod (rewritten path).
function stripPrefix(p: string | null): string {
  if (!p) return "/";
  const cleaned = p.replace(/^\/events-app/, "");
  return cleaned === "" ? "/" : cleaned;
}

type Tab = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  iconActive: React.ComponentType<{ className?: string }>;
};

const TABS: Tab[] = [
  { href: "/", label: "Home", icon: HomeIcon, iconActive: HomeSolid },
  { href: "/calendar", label: "Events", icon: CalendarDaysIcon, iconActive: CalendarSolid },
  { href: "/places", label: "Places", icon: BuildingStorefrontIcon, iconActive: StoreSolid },
  { href: "/checkin", label: "Check In", icon: MapPinIcon, iconActive: PinSolid },
  { href: "/chat", label: "Chat", icon: ChatBubbleLeftRightIcon, iconActive: ChatSolid },
];

export default function EventsAppLayout({ children }: { children: React.ReactNode }) {
  const raw = usePathname();
  const current = stripPrefix(raw);

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Top bar — on desktop the nav lives inline here. On mobile the nav
          drops to the bottom (see <nav> below). */}
      <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 flex-shrink-0">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
              style={{ backgroundColor: eventsBrand }}
            >
              AH
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-gray-900">Around Town</div>
              <div className="hidden sm:block text-[10px] text-gray-500">
                Atlantic Highlands · Highlands · Sea Bright
              </div>
            </div>
          </Link>
          {/* Desktop top nav */}
          <nav className="hidden md:flex items-center gap-1">
            {TABS.map((tab) => {
              const active =
                tab.href === "/"
                  ? current === "/"
                  : current === tab.href || current.startsWith(tab.href + "/");
              const Icon = active ? tab.iconActive : tab.icon;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                    active ? "" : "text-gray-600 hover:bg-gray-50"
                  }`}
                  style={active ? { backgroundColor: `${eventsBrand}15`, color: eventsBrand } : {}}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Main — wider container on desktop now that the nav doesn't compete
          for horizontal space at the bottom. */}
      <main className="flex-1 max-w-5xl w-full mx-auto pb-24 md:pb-8">{children}</main>

      {/* Bottom tab nav — MOBILE ONLY. Desktop uses the top nav in the header
          above. safe-area-inset-bottom handles the home-bar inset on iOS. */}
      <nav
        className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-gray-200"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="max-w-3xl mx-auto flex">
          {TABS.map((tab) => {
            const active =
              tab.href === "/"
                ? current === "/"
                : current === tab.href || current.startsWith(tab.href + "/");
            const Icon = active ? tab.iconActive : tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="flex-1 flex flex-col items-center justify-center py-2.5 text-[10px]"
                style={{ color: active ? eventsBrand : "#6b7280" }}
              >
                <Icon className="w-5 h-5 mb-0.5" />
                <span>{tab.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
