import { NextResponse } from 'next/server';

/**
 * ChatKit tool endpoint for TrueSight analytics queries.
 *
 * This endpoint is called by the ChatKit workflow when the agent
 * decides to invoke the truesight_query tool.
 */

type ToolRequest = {
  utterance: string;
  session_id?: string;
};

type ToolResponse = {
  status: 'complete' | 'error';
  answer?: string;
  table?: Array<Record<string, any>>;
  chart?: Record<string, any>;
  sql?: string;
  warnings?: string[];
  session_id?: string;
  detail?: string;
};

// Simple in-memory cache to store the last result per session
// This allows the frontend to fetch the structured data
const resultCache = new Map<string, ToolResponse>();
const recentResults: Array<{ timestamp: number; data: ToolResponse }> = [];

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    // Fallback: return the most recent result
    if (recentResults.length > 0) {
      return NextResponse.json(recentResults[recentResults.length - 1].data);
    }
    return NextResponse.json({ error: 'No recent results found' }, { status: 404 });
  }

  const cached = resultCache.get(sessionId);
  if (!cached) {
    // Fallback: return the most recent result
    if (recentResults.length > 0) {
      return NextResponse.json(recentResults[recentResults.length - 1].data);
    }
    return NextResponse.json({ error: 'No data found for this session' }, { status: 404 });
  }

  return NextResponse.json(cached);
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as ToolRequest;

    if (!body.utterance || typeof body.utterance !== 'string') {
      return NextResponse.json(
        {
          status: 'error',
          detail: 'Missing or invalid "utterance" field'
        },
        { status: 400 }
      );
    }

    // Get backend URL from environment or default to localhost
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

    // Call the Python backend's /ask endpoint
    const backendResponse = await fetch(`${backendUrl}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question: body.utterance,
        use_llm: true,
      }),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      console.error('Backend request failed:', {
        status: backendResponse.status,
        statusText: backendResponse.statusText,
        body: errorText,
      });

      return NextResponse.json(
        {
          status: 'error',
          detail: `Backend query failed: ${backendResponse.statusText}`,
          session_id: body.session_id,
        },
        { status: 502 }
      );
    }

    const result = await backendResponse.json();

    // Transform backend response to tool response format
    const toolResponse: ToolResponse = {
      status: 'complete',
      answer: result.answer || result.summary || 'Query completed',
      table: result.table || [],
      chart: result.chart || {},
      sql: result.sql || '',
      warnings: result.warnings || [],
      session_id: body.session_id,
    };

    // Cache the response so frontend can fetch it
    if (body.session_id) {
      resultCache.set(body.session_id, toolResponse);
      // Clean up old cache entries after 5 minutes
      setTimeout(() => resultCache.delete(body.session_id!), 5 * 60 * 1000);
    }

    // Also store in recent results as fallback
    recentResults.push({ timestamp: Date.now(), data: toolResponse });
    // Keep only last 10 results
    if (recentResults.length > 10) {
      recentResults.shift();
    }

    console.log('[TrueSight Tool] Response cached:', {
      session: body.session_id || 'no-session',
      hasTable: !!toolResponse.table?.length,
      hasChart: !!toolResponse.chart,
      tableRows: toolResponse.table?.length || 0,
      answer: toolResponse.answer?.substring(0, 100)
    });

    return NextResponse.json(toolResponse);
  } catch (error) {
    console.error('Tool endpoint error:', error);

    return NextResponse.json(
      {
        status: 'error',
        detail: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
