const fs = require("fs");
const path = require("path");

// The town this build serves: municipalities/<MUNICIPALITY>/profile.json at the
// repo root (MUNICIPALITY_DIR overrides the folder, e.g. inside Docker). It is
// read once here and inlined, so pages get it with no API call.
const municipalityDir =
  process.env.MUNICIPALITY_DIR ||
  path.join(__dirname, "..", "municipalities", process.env.MUNICIPALITY || "atlantic-highlands-nj");
const profile = JSON.parse(fs.readFileSync(path.join(municipalityDir, "profile.json"), "utf8"));
const sources = JSON.parse(fs.readFileSync(path.join(municipalityDir, "sources.json"), "utf8"));

// The scraper admin page's site list. key/siteId follow the API's
// services/scraper/runner.site_crawlers(): site_key or name, and label or host.
const scraperSites = Object.values(sources).flatMap((group) =>
  Object.entries(group).map(([name, cfg]) => {
    let host = "";
    try { host = new URL(cfg.base_url).host.replace(/^www\./, ""); } catch {}
    const siteId = cfg.label || host || name;
    return {
      key: cfg.site_key || name,
      siteId,
      name: cfg.ui_name || siteId,
      desc: cfg.summary || cfg.description || "",
      note: cfg.note,
      needsBrowser: !!cfg.needs_browser,
    };
  }),
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone is only needed for the production bundle (Docker/Amplify
  // deploy). Setting it in dev mode breaks chunk resolution on Windows
  // ("Cannot find module './611.js'"), so we gate it behind NODE_ENV.
  ...(process.env.NODE_ENV === "production" ? { output: "standalone" } : {}),
  env: {
    NEXT_PUBLIC_MUNICIPALITY: JSON.stringify(profile),
    NEXT_PUBLIC_SCRAPER_SITES: JSON.stringify(scraperSites),
  },
  // API proxy handled by app/api/[...path]/route.ts
  // Note: `experimental.missingSuspenseWithCSRBailout` was removed in Next 15.
};

module.exports = nextConfig;
