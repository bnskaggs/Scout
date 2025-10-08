import { NextResponse } from 'next/server';

/**
 * Bridge to the Python /agent endpoint which uses Assistants API with proper function calling.
 * This is simpler than ChatKit workflows and already has tools configured.
 */

type ChatRequest = {
  message: string;
  thread_id?: string;
  session_id?: string;
};

type ChatResponse = {
  thread_id: string;
  table: Array<Record<string, any>>;
  chart: Record<string, any>;
  sql: string;
  summary: string;
  warnings: string[];
};

export async function POST(request: Request) {
  try {
    const body = await request.json() as ChatRequest;

    if (!body.message || typeof body.message !== 'string') {
      return NextResponse.json(
        { error: 'Missing or invalid "message" field' },
        { status: 400 }
      );
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

    // Call the Python /ask endpoint (simpler, no agent complexity)
    const backendResponse = await fetch(`${backendUrl}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question: body.message,
        use_llm: true,
      }),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      console.error('Backend agent request failed:', {
        status: backendResponse.status,
        statusText: backendResponse.statusText,
        body: errorText,
      });

      return NextResponse.json(
        {
          error: `Backend agent failed: ${backendResponse.statusText}`,
          detail: errorText,
        },
        { status: 502 }
      );
    }

    const result = await backendResponse.json();

    // Transform /ask response to match expected format
    const response: ChatResponse = {
      thread_id: body.thread_id || `thread-${Date.now()}`,
      table: result.table || [],
      chart: result.chart || {},
      sql: result.sql || '',
      summary: result.answer || result.summary || 'Query completed',
      warnings: result.warnings || [],
    };

    console.log('[Agent] Response:', {
      thread_id: response.thread_id,
      hasTable: !!response.table?.length,
      hasChart: !!response.chart,
      summary: response.summary?.substring(0, 100),
    });

    return NextResponse.json(response);
  } catch (error) {
    console.error('Agent endpoint error:', error);

    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
