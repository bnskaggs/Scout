import { NextResponse } from "next/server";

const CHATKIT_URL = "https://api.openai.com/v1/chatkit/sessions";

export async function POST() {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return NextResponse.json(
      { error: "Missing OPENAI_API_KEY environment variable." },
      { status: 500 },
    );
  }

  const workflowId = process.env.NEXT_PUBLIC_CHATKIT_WORKFLOW_ID;

  if (!workflowId) {
    return NextResponse.json(
      { error: "Missing NEXT_PUBLIC_CHATKIT_WORKFLOW_ID environment variable." },
      { status: 500 },
    );
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
    "OpenAI-Beta": "chatkit_beta=v1",
  };

  const projectId = process.env.OPENAI_PROJECT;
  if (projectId) {
    headers["OpenAI-Project"] = projectId;
  }

  const response = await fetch(CHATKIT_URL, {
    method: "POST",
    headers,
    body: JSON.stringify({
      workflow: { id: workflowId },
      user: { id: "test_user_1", name: "Ben Skaggs" },
    }),
  });

  if (!response.ok) {
    let errorBody: unknown;
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      try {
        errorBody = await response.json();
      } catch {
        errorBody = { error: "Failed to parse error response." };
      }
    } else {
      errorBody = { error: await response.text() };
    }

    return NextResponse.json(errorBody, { status: response.status });
  }

  const json = (await response.json()) as { client_secret?: string };

  if (!json.client_secret) {
    return NextResponse.json(
      { error: "No client_secret returned from ChatKit session creation." },
      { status: 500 },
    );
  }

  return NextResponse.json({ client_secret: json.client_secret });
}
