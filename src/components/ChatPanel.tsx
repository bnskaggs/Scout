"use client";

import { ChatKit, useChatKit } from "@openai/chatkit-react";
import { useState } from "react";

type SessionResponse = {
  client_secret?: string;
};

export function ChatPanel() {
  const [error, setError] = useState<string | null>(null);

  const { control } = useChatKit({
    api: {
      async getClientSecret(existingClientSecret: string | null) {
        try {
          const response = await fetch("/api/chatkit/session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          });

          if (!response.ok) {
            const message = await response.text();
            throw new Error(
              message || `Failed to fetch ChatKit client secret (${response.status}).`,
            );
          }

          const { client_secret: clientSecret } = (await response.json()) as SessionResponse;

          if (typeof clientSecret !== "string" || clientSecret.length === 0) {
            throw new Error("ChatKit session response missing client_secret.");
          }

          setError(null);
          return clientSecret;
        } catch (err) {
          const message = err instanceof Error ? err.message : "Unknown error";
          console.error("ChatKit getClientSecret failed", {
            error: err,
            hasExistingClientSecret: Boolean(existingClientSecret),
          });
          setError(message);
          throw err;
        }
      },
    },
  });

  return (
    <div className="h-[600px] w-[400px]">
      {error ? (
        <div className="flex h-full items-center justify-center rounded-xl border border-red-200 bg-red-50 p-4 text-center text-sm text-red-600">
          {error}
        </div>
      ) : (
        <ChatKit control={control} className="h-full w-full" />
      )}
    </div>
  );
}

export default ChatPanel;
