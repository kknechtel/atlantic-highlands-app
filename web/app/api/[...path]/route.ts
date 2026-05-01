import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(request, params.path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(request, params.path);
}

async function proxyRequest(request: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  // Preserve trailing slash from the original URL — FastAPI distinguishes / from no /
  const originalPath = request.nextUrl.pathname;
  const trailingSlash = originalPath.endsWith("/") ? "/" : "";
  const url = `${API_URL}/api/${path}${trailingSlash}${request.nextUrl.search}`;

  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    if (!["host", "connection", "transfer-encoding"].includes(key.toLowerCase())) {
      headers[key] = value;
    }
  });

  try {
    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      const contentType = request.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        fetchOptions.body = await request.text();
      } else if (contentType.includes("multipart/form-data")) {
        fetchOptions.body = await request.arrayBuffer();
        // Remove content-type so fetch sets it with boundary
        delete (headers as any)["content-type"];
      }
    }

    const response = await fetch(url, fetchOptions);

    // Stream the response back
    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      if (!["transfer-encoding", "connection"].includes(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });

    // For streaming responses (SSE), pipe through
    if (response.headers.get("content-type")?.includes("text/event-stream")) {
      return new NextResponse(response.body, {
        status: response.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
      });
    }

    // For binary responses (PDFs, images)
    if (response.headers.get("content-type")?.includes("application/pdf") ||
        response.headers.get("content-type")?.includes("image/")) {
      const buffer = await response.arrayBuffer();
      return new NextResponse(buffer, {
        status: response.status,
        headers: responseHeaders,
      });
    }

    // For JSON/text responses — buffer (Amplify SSR Lambda doesn't reliably stream)
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: responseHeaders,
    });

  } catch (error: any) {
    return NextResponse.json(
      { error: "API proxy error", detail: error.message },
      { status: 502 }
    );
  }
}
