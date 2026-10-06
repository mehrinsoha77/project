import { NextRequest, NextResponse } from "next/server";

/**
 * Forwards /api/proxy/<path> to the FastAPI backend at NADINET_API_URL.
 * Without a backend the route answers 503 and the client switches to its
 * explicit offline mode (nothing is sent; see lib/api.ts).
 */
const API = process.env.NADINET_API_URL?.replace(/\/$/, "");

export const dynamic = "force-dynamic";

async function forward(req: NextRequest, { params }: { params: { path: string[] } }) {
  if (!API) {
    return NextResponse.json({ detail: "No backend configured (NADINET_API_URL unset)" }, { status: 503 });
  }
  const url = `${API}/api/${params.path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  try {
    const r = await fetch(url, {
      method: req.method,
      headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
      cache: "no-store",
    });
    const body = await r.arrayBuffer();
    return new NextResponse(body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 503 });
  }
}

export { forward as GET, forward as POST };
