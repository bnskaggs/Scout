import { NextRequest, NextResponse } from 'next/server';

function resolveSessionId(candidate: unknown): string | undefined {
  if (typeof candidate === 'string' && candidate.trim().length > 0) {
    return candidate.trim();
  }
  return undefined;
}

export async function POST(req: NextRequest) {
  const backendBase = process.env.BACKEND_BASE_URL;
  if (!backendBase) {
    return NextResponse.json({ error: 'backend_not_configured' }, { status: 500 });
  }

  const body = await req.json().catch(() => ({} as Record<string, unknown>));
  const sessionId = resolveSessionId(body?.sessionId);
  const clarification = typeof body?.clarification === 'string' ? body.clarification.trim() : '';
  const question = typeof body?.question === 'string' ? body.question.trim() : '';
  const contextEnabled = typeof body?.contextEnabled === 'boolean' ? body.contextEnabled : true;

  if (!sessionId) {
    return NextResponse.json({ error: 'missing_session' }, { status: 400 });
  }

  const headers = new Headers({ 'Content-Type': 'application/json' });
  headers.set('X-Session-Id', sessionId);

  const targetPath = clarification ? '/chat/clarify' : '/chat/complete';
  const payload = clarification
    ? { session_id: sessionId, answer: clarification }
    : { session_id: sessionId, utterance: question, context_enabled: contextEnabled };

  if (!clarification && !question) {
    return NextResponse.json({ error: 'question_required' }, { status: 400 });
  }

  const target = new URL(targetPath, backendBase);

  try {
    const response = await fetch(target, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    const text = await response.text();
    const data = text ? JSON.parse(text) : {};

    if (response.status === 409) {
      const detail = data?.detail ?? data;
      if (detail && typeof detail === 'object' && 'question' in detail) {
        return NextResponse.json({
          status: 'clarification_needed',
          clarification: {
            question: String(detail.question ?? ''),
            suggested_answers: Array.isArray(detail.suggested_answers) ? detail.suggested_answers : [],
          },
        });
      }
      const message = typeof detail?.message === 'string' ? detail.message : 'conflict';
      return NextResponse.json({ error: message, detail }, { status: response.status });
    }

    if (!response.ok) {
      const detail = data?.detail ?? data;
      const message = typeof detail === 'string' ? detail : detail?.message ?? response.statusText;
      return NextResponse.json({ error: message, detail }, { status: response.status });
    }

    if (data?.status === 'clarification_needed' && data?.question) {
      return NextResponse.json({
        status: 'clarification_needed',
        clarification: {
          question: String(data.question),
          suggested_answers: Array.isArray(data.suggested_answers) ? data.suggested_answers : [],
        },
      });
    }

    return NextResponse.json({ data });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'manual_chat_failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
