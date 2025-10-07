import { NextResponse } from 'next/server';

type ChatKitSessionResponse = {
  client_secret?: string;
  [key: string]: unknown;
};

export async function POST() {
  const apiKey = process.env.OPENAI_API_KEY;
  const workflowId = process.env.CHATKIT_WORKFLOW_ID;

  if (!apiKey || !workflowId) {
    console.error('ChatKit session configuration is incomplete.', {
      hasApiKey: Boolean(apiKey),
      hasWorkflowId: Boolean(workflowId),
    });
    return NextResponse.json(
      { error: 'chatkit_configuration_error' },
      { status: 500 },
    );
  }

  try {
    const upstreamResponse = await fetch('https://api.openai.com/v1/chatkit/sessions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'chatkit_beta=v1',
      },
      body: JSON.stringify({
        workflow: { id: workflowId },
        user: 'anon-device',
      }),
    });

    if (!upstreamResponse.ok) {
      const errorBody = await upstreamResponse.text();
      console.error('ChatKit session creation failed.', {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        body: errorBody,
      });

      const status = upstreamResponse.status >= 400 && upstreamResponse.status < 500 ? upstreamResponse.status : 502;
      return NextResponse.json({ error: 'chatkit_session_failed' }, { status });
    }

    const payload = (await upstreamResponse.json()) as ChatKitSessionResponse;
    const { client_secret: clientSecret } = payload;

    if (typeof clientSecret !== 'string' || clientSecret.length === 0) {
      console.error('ChatKit session response missing client_secret.', { payload });
      return NextResponse.json(
        { error: 'chatkit_invalid_session_response' },
        { status: 502 },
      );
    }

    return NextResponse.json({ client_secret: clientSecret });
  } catch (error) {
    console.error('Unexpected error while creating ChatKit session.', error);
    return NextResponse.json({ error: 'chatkit_session_error' }, { status: 500 });
  }
}
