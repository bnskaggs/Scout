import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const thread_id = typeof body?.thread_id === 'string' && body.thread_id.length > 0 ? body.thread_id : undefined;

  const backendBase = process.env.BACKEND_BASE_URL;
  if (!backendBase) {
    return NextResponse.json({ error: 'backend_not_configured' }, { status: 500 });
  }

  const target = new URL('/api/chatkit/session', backendBase);

  try {
    const res = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thread_id }),
    });

    if (!res.ok) {
      return NextResponse.json({ error: 'session_failed' }, { status: 500 });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'session_failed' }, { status: 500 });
  }
}
