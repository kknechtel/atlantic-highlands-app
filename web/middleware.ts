import { NextRequest, NextResponse } from "next/server";

// Subdomain router.
//
// `ahnj.info`            → civic-research app (existing pages at /, /document-library, …)
// `events.ahnj.info`     → community app (rewrites /* → /events-app/*)
//
// The URL the user sees in the address bar stays clean
// (`events.ahnj.info/checkin`), but Next renders the page at
// `app/events-app/checkin/page.tsx`.
//
// On the main domain we redirect any direct hit on /events-app/* back to
// the home page so the events-app routes only resolve through the
// subdomain — otherwise visitors could stumble into the community UI
// without the right chrome.
//
// localhost gets the events app on either `events.localhost:3000`
// (preferred — set up a hosts entry) or by visiting /events-app/* directly.

export function middleware(req: NextRequest) {
  const host = (req.headers.get("host") || "").toLowerCase();
  const url = req.nextUrl;
  const pathname = url.pathname;

  const onEventsSubdomain =
    host.startsWith("events.") || host.startsWith("events-");

  if (onEventsSubdomain) {
    // Already on /events-app/* — no rewrite needed.
    if (pathname === "/events-app" || pathname.startsWith("/events-app/")) {
      return NextResponse.next();
    }
    // Rewrite root + every other path under the events-app tree.
    const rewritten = url.clone();
    rewritten.pathname = `/events-app${pathname === "/" ? "" : pathname}`;
    return NextResponse.rewrite(rewritten);
  }

  // Main domain — redirect direct /events-app/* visits to the subdomain
  // so the path is never user-visible there. In dev we leave the path
  // accessible because there's no real subdomain set up.
  if (
    process.env.NODE_ENV === "production" &&
    (pathname === "/events-app" || pathname.startsWith("/events-app/"))
  ) {
    const dest = url.clone();
    dest.pathname = "/";
    return NextResponse.redirect(dest);
  }

  return NextResponse.next();
}

// Skip static assets + API routes so the middleware overhead only hits
// page navigations.
export const config = {
  matcher: [
    "/((?!_next/|favicon|icon-|manifest|dashboard-banner|robots|sitemap|api/).*)",
  ],
};
