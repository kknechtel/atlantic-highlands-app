"use client";

// Events-app shell (events.ahnj.info).
//   Mobile:  top bar (logo + profile avatar) + bottom tab nav
//   Desktop: left sidebar with logo on top, nav links, profile at bottom
//
// The civic-research sidebar/GlobalChat is suppressed by AuthGate when
// hostname starts with "events." (see web/components/Providers.tsx).
//
// The nav uses CLEAN URLs (no /events-app prefix). The Host-based
// middleware rewrites the user-visible URL on every request, so a
// <Link href="/calendar"> from a page served under events.ahnj.info
// navigates to events.ahnj.info/calendar → middleware routes to
// /events-app/calendar/page.tsx.

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  HomeIcon, CalendarDaysIcon, BuildingStorefrontIcon,
  MapPinIcon, ChatBubbleLeftRightIcon, BookmarkIcon,
  ArrowRightOnRectangleIcon, MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  HomeIcon as HomeSolid, CalendarDaysIcon as CalendarSolid,
  BuildingStorefrontIcon as StoreSolid,
  MapPinIcon as PinSolid, ChatBubbleLeftRightIcon as ChatSolid,
  BookmarkIcon as BookmarkSolid,
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
  /** Hide from anon users — they can't have saved events. */
  authOnly?: boolean;
};

const TABS: Tab[] = [
  { href: "/", label: "Home", icon: HomeIcon, iconActive: HomeSolid },
  { href: "/calendar", label: "Events", icon: CalendarDaysIcon, iconActive: CalendarSolid },
  { href: "/my-calendar", label: "Saved", icon: BookmarkIcon, iconActive: BookmarkSolid, authOnly: true },
  { href: "/places", label: "Places", icon: BuildingStorefrontIcon, iconActive: StoreSolid },
  { href: "/checkin", label: "Check In", icon: MapPinIcon, iconActive: PinSolid },
  { href: "/chat", label: "Chat", icon: ChatBubbleLeftRightIcon, iconActive: ChatSolid },
];

export default function EventsAppLayout({ children }: { children: React.ReactNode }) {
  const raw = usePathname();
  const current = stripPrefix(raw);
  const { user, logout } = useAuth();
  const profileInitial = (user?.display_name || user?.email || "?").trim().charAt(0).toUpperCase();
  // Anon users don't see auth-only tabs (Saved). Sign-in CTA replaces the
  // profile slot so the navigation stays predictable across login state.
  const visibleTabs = TABS.filter(t => !t.authOnly || user);

  function isActive(href: string): boolean {
    return href === "/" ? current === "/" : (current === href || current.startsWith(href + "/"));
  }

  return (
    // min-h-[100dvh] (dynamic viewport) instead of min-h-screen so the
    // layout doesn't jump on iOS when Safari's URL bar shows/hides.
    <div className="min-h-[100dvh] flex bg-gray-50">
      {/* DESKTOP SIDEBAR (md+) ─────────────────────────────────────── */}
      <aside className="hidden md:flex md:flex-col w-56 lg:w-64 bg-white border-r border-gray-200 h-screen sticky top-0">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 p-4 border-b border-gray-200">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
            style={{ backgroundColor: eventsBrand }}
          >
            AH
          </div>
          <div className="leading-tight min-w-0">
            <div className="text-sm font-semibold text-gray-900 truncate">Around Town</div>
            <div className="text-[10px] text-gray-500 truncate">
              AH · Highlands · Sea Bright
            </div>
          </div>
        </Link>
        {/* Nav */}
        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {visibleTabs.map((tab) => {
            const active = isActive(tab.href);
            const Icon = active ? tab.iconActive : tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  active ? "" : "text-gray-700 hover:bg-gray-50"
                }`}
                style={active ? { backgroundColor: `${eventsBrand}15`, color: eventsBrand } : {}}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="font-medium">{tab.label}</span>
              </Link>
            );
          })}
        </nav>
        {/* Profile + sign out (logged in) OR Sign in/up CTA (anon) */}
        {user ? (
          <div className="p-3 border-t border-gray-200 flex items-center gap-2">
            <Link
              href="/profile"
              className="flex-1 min-w-0 flex items-center gap-2 p-1 -m-1 rounded-md hover:bg-gray-50"
              title="Profile"
            >
              {user.picture_url ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={user.picture_url} alt="" className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
              ) : (
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold flex-shrink-0"
                  style={{ backgroundColor: eventsBrand }}
                >
                  {profileInitial}
                </div>
              )}
              <div className="text-xs text-gray-700 truncate min-w-0">
                {user.display_name || user.full_name || user.email.split("@")[0]}
              </div>
            </Link>
            <button
              onClick={logout}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex-shrink-0"
              title="Sign out"
            >
              <ArrowRightOnRectangleIcon className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="p-3 border-t border-gray-200 space-y-1.5">
            <Link
              href="/login"
              className="block w-full text-center text-xs font-medium px-3 py-2 rounded-md text-white"
              style={{ backgroundColor: eventsBrand }}
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="block w-full text-center text-xs px-3 py-2 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              Create account
            </Link>
          </div>
        )}
      </aside>

      {/* MAIN COLUMN ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* MOBILE TOP BAR (md:hidden) ──────────────────────────────── */}
        <header className="md:hidden sticky top-0 z-30 bg-white border-b border-gray-200">
          <div className="px-4 py-3 flex items-center justify-between gap-4">
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
            <div className="flex items-center gap-2 flex-shrink-0">
              <Link
                href="/search"
                aria-label="Search events"
                className="p-1.5 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                title="Search events"
              >
                <MagnifyingGlassIcon className="w-5 h-5" />
              </Link>
              {user ? (
                <Link
                  href="/profile"
                  className="flex items-center gap-1.5 hover:opacity-80"
                  title="Profile"
                >
                  {user.picture_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img src={user.picture_url} alt="" className="w-7 h-7 rounded-full object-cover" />
                  ) : (
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold"
                      style={{ backgroundColor: eventsBrand }}
                    >
                      {profileInitial}
                    </div>
                  )}
                </Link>
              ) : (
                <Link
                  href="/login"
                  className="text-xs font-medium px-3 py-1.5 rounded-md text-white"
                  style={{ backgroundColor: eventsBrand }}
                >
                  Sign in
                </Link>
              )}
            </div>
          </div>
        </header>

        {/* Main scroll area — wider on desktop so the calendar grid can
            actually breathe. List-y pages still center inside this. */}
        <main className="flex-1 max-w-5xl xl:max-w-7xl w-full mx-auto pb-24 md:pb-8 md:py-2">{children}</main>
      </div>

      {/* MOBILE BOTTOM TAB NAV (md:hidden) ──────────────────────────────
          Pinned to the viewport bottom and isolated into its own stacking
          context so no parent transform/filter can detach it. iOS
          shadow gives a clear "floating bar" affordance. z-40 lets modals
          (z-50) cover it; bump only if a higher layer needs to too. */}
      <nav
        className="md:hidden fixed inset-x-0 bottom-0 z-40 bg-white border-t border-gray-200 shadow-[0_-2px_8px_rgba(0,0,0,0.04)] isolate"
        style={{
          paddingBottom: "env(safe-area-inset-bottom)",
          // Belt-and-suspenders: pin via inline style too, in case Tailwind
          // is purged from a parent that creates a containing block.
          position: "fixed",
        }}
      >
        <div className="max-w-3xl mx-auto flex">
          {visibleTabs.map((tab) => {
            const active = isActive(tab.href);
            const Icon = active ? tab.iconActive : tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="flex-1 flex flex-col items-center justify-center py-2 text-[10px] min-w-0"
                style={{ color: active ? eventsBrand : "#6b7280" }}
              >
                <Icon className="w-5 h-5 mb-0.5 flex-shrink-0" />
                <span className="truncate w-full text-center">{tab.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
