// Cloudflare Worker: ahnj.com proxy for the scraper.
//
// Why this exists: www.ahnj.com (54.175.134.164, also AWS us-east-1)
// firewalls inbound traffic from other AWS source IPs, so our EC2-hosted
// scraper can't open TCP to it. This Worker runs on Cloudflare's edge,
// fetches the target URL from a residential-class IP, and returns the
// bytes verbatim. The scraper rewrites ahnj.com URLs through here.
//
// Deploy:
//   cd workers/ahnj-proxy
//   npx wrangler@latest login
//   npx wrangler@latest secret put PROXY_SECRET   # paste a random 32+ char secret
//   npx wrangler@latest deploy                    # prints the worker URL
//
// Then on the EC2:
//   systemctl edit ah-api
//     [Service]
//     Environment="AHNJ_PROXY_URL=https://ahnj-proxy.<your-account>.workers.dev"
//     Environment="AHNJ_PROXY_SECRET=<same secret>"
//   systemctl restart ah-api
//
// Security model: shared-secret header + host allowlist. Without the
// secret, the Worker 403s; even with the secret it will only fetch the
// allowlisted hosts, so it can't be turned into a generic open proxy.

const ALLOWED_HOSTS = new Set(["www.ahnj.com", "ahnj.com"]);

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
    if (!ALLOWED_HOSTS.has(parsed.hostname.toLowerCase())) {
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
