import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxy(request, path, 'GET');
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxy(request, path, 'POST');
}

export async function PUT(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxy(request, path, 'PUT');
}

export async function DELETE(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxy(request, path, 'DELETE');
}

async function proxy(request: NextRequest, path: string[], method: string) {
  const url = new URL(`${API_BASE}/api/${path.join('/')}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value);
  });

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== 'host') {
      headers.set(key, value);
    }
  });

  let body: BodyInit | undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    body = await request.text();
  }

  const res = await fetch(url.toString(), {
    method,
    headers,
    body,
  });

  const responseBody = await res.text();
  return new NextResponse(responseBody, {
    status: res.status,
    headers: {
      'content-type': res.headers.get('content-type') ?? 'application/json',
    },
  });
}
