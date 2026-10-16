// Cloudflare Worker: town-site proxy for the scraper.
//
// Why this exists: some town sites firewall inbound traffic from AWS source
// IPs (the original case: www.ahnj.com, itself on AWS us-east-1), so an
// EC2-hosted scraper can't open TCP to them. This Worker runs on Cloudflare's
// edge, fetches the target URL from a residential-class IP, and returns the
// bytes verbatim. The scraper rewrites URLs of sources marked
// `"proxy": true` in sources.json through here.
//
// Deploy:
//   cd workers/ahnj-proxy
//   # set ALLOWED_HOSTS in wrangler.toml to the proxied sources' hosts
//   npx wrangler@latest login
//   npx wrangler@latest secret put PROXY_SECRET   # paste a random 32+ char secret
//   npx wrangler@latest deploy                    # prints the worker URL
//
// Then on the server:
//   systemctl edit ah-api
//     [Service]
//     Environment="SCRAPER_PROXY_URL=https://<worker name>.<your-account>.workers.dev"
//     Environment="SCRAPER_PROXY_SECRET=<same secret>"
//   systemctl restart ah-api
// (The scraper also reads the older AHNJ_PROXY_URL / AHNJ_PROXY_SECRET names.)
//
// Security model: shared-secret header + host allowlist. Without the
// secret, the Worker 403s; even with the secret it will only fetch the
// allowlisted hosts, so it can't be turned into a generic open proxy.

// Hosts the scraper can't reach directly: the ALLOWED_HOSTS var in
// wrangler.toml (comma-separated). The default is the original deployment's
// list: ahnj.com firewalls AWS source IPs; highlands-nj.municodemeetings.com
// appears to throttle datacenter IPs (pagination returns ~6 docs vs. ~600
// from a residential IP).
const DEFAULT_ALLOWED_HOSTS = "www.ahnj.com,ahnj.com,highlands-nj.municodemeetings.com";

function allowedHosts(env) {
  return new Set(
    (env.ALLOWED_HOSTS || DEFAULT_ALLOWED_HOSTS)
      .split(",")
      .map((h) => h.trim().toLowerCase())
      .filter(Boolean),
  );
}

const FORWARD_REQUEST_HEADERS = [
  "user-agent",
  "accept",
  "accept-language",
];

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-encoding", // let CF/our fetch handle decoding; don't re-advertise
]);

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed", { status: 405 });
    }

    if (!env.PROXY_SECRET) {
      return new Response("worker misconfigured: PROXY_SECRET not set", { status: 500 });
    }
    if (request.headers.get("x-proxy-secret") !== env.PROXY_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    const u = new URL(request.url);
    const target = u.searchParams.get("url");
    if (!target) return new Response("missing ?url=", { status: 400 });

    let parsed;
    try {
      parsed = new URL(target);
    } catch {
      return new Response("invalid target url", { status: 400 });
    }
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return new Response("only http(s) targets", { status: 400 });
    }
    if (!allowedHosts(env).has(parsed.hostname.toLowerCase())) {
      return new Response(`host not allowed: ${parsed.hostname}`, { status: 403 });
    }

    const upstreamHeaders = new Headers();
    for (const h of FORWARD_REQUEST_HEADERS) {
      const v = request.headers.get(h);
      if (v) upstreamHeaders.set(h, v);
    }

    let upstream;
    try {
      upstream = await fetch(parsed.toString(), {
        method: request.method,
        headers: upstreamHeaders,
        redirect: "follow",
      });
    } catch (e) {
      return new Response(`upstream fetch failed: ${e.message}`, { status: 502 });
    }

    const respHeaders = new Headers();
    for (const [k, v] of upstream.headers) {
      if (!HOP_BY_HOP.has(k.toLowerCase())) respHeaders.set(k, v);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: respHeaders,
    });
  },
};
