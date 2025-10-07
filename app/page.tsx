import dynamic from 'next/dynamic';

"use client";

import { ChatKit, useChatKit } from "@openai/chatkit-react";

export default function ChatPage() {
  const { control, error } = useChatKit({
    api: {
      async getClientSecret(existing) {
        // If you store/refresh sessions, handle `existing` here
        const res = await fetch("/api/chatkit/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const { client_secret, error } = await res.json();
        if (error) throw new Error(error);
        return client_secret;
      },
    },
  });

  return (
    <div className="w-full max-w-3xl h-[600px]">
      {error ? (
        <div className="text-red-500 text-sm p-2">Chat init failed: {String(error)}</div>
      ) : null}
      <ChatKit control={control} className="h-full w-full" />
    </div>
  );
}
