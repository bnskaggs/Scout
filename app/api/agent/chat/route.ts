import { NextResponse } from 'next/server';

/**
 * Bridge to the Python /chat/complete endpoint with conversation state.
 * Enables multi-turn conversations with context retention.
 */

type ChatRequest = {
  message: string;
  session_id: string;
};

type ChatResponse = {
  session_id: string;
  table: Array<Record<string, any>>;
  chart: Record<string, any>;
  sql: string;
  summary: string;
  warnings: string[];
  chips?: {
    dimensions?: string[];
    filters?: string[];
    time?: string[];
  };
  nql_status?: Record<string, any>;
  engine?: string;
  status?: string;
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

    if (!body.session_id || typeof body.session_id !== 'string') {
      return NextResponse.json(
        { error: 'Missing or invalid "session_id" field' },
        { status: 400 }
      );
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

    // Call the Python /chat/complete endpoint (stateful conversations)
    const backendResponse = await fetch(`${backendUrl}/chat/complete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        utterance: body.message,
        session_id: body.session_id,
        use_llm: true,
        context_enabled: true,
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

    // Transform /chat/complete response
    const response: ChatResponse = {
      session_id: body.session_id,
      table: result.table || [],
      chart: result.chart || {},
      sql: result.sql || '',
      summary: result.answer || result.summary || 'Query completed',
      warnings: result.warnings || [],
      chips: result.chips,
      nql_status: result.nql_status,
      engine: result.engine,
      status: result.status,
    };

    console.log('[Agent] Response:', {
      session_id: response.session_id,
      engine: response.engine,
      status: response.status,
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
