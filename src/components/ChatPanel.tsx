"use client";

import { useEffect, useRef, useState } from "react";

const DEFAULT_CHATKIT_SCRIPT_URL =
  "https://cdn.platform.openai.com/deployments/chatkit/chatkit.js";

type ChatKitConstructor = new (config: { clientSecret: string }) => {
  mount: (selector: string) => void;
  unmount?: () => void;
};

declare global {
  interface Window {
    ChatKit?: ChatKitConstructor;
  }
}

export default function ChatPanel() {
  const [error, setError] = useState<string | null>(null);
  const chatkitRef = useRef<{ unmount?: () => void } | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const response = await fetch("/api/chatkit/start", { method: "POST" });

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(errorBody || "Failed to create ChatKit session.");
        }

        const { client_secret: clientSecret } = (await response.json()) as {
          client_secret?: string;
        };

        if (!clientSecret) {
          throw new Error("ChatKit session response missing client_secret.");
        }

        if (cancelled) return;

        await loadChatKitScript();

        if (cancelled) return;

        if (!window.ChatKit) {
          throw new Error("ChatKit script did not load correctly.");
        }

        const instance = new window.ChatKit({ clientSecret });
        instance.mount("#chat-container");
        chatkitRef.current = instance;
        setError(null);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        console.error("ChatKit init failed", err);
        setError(message);
      }
    }

    init();

    return () => {
      cancelled = true;
      if (chatkitRef.current?.unmount) {
        chatkitRef.current.unmount();
      }
      chatkitRef.current = null;
    };
  }, []);

  return (
    <div className="w-full h-[600px] border rounded-xl overflow-hidden">
      {error ? (
        <div className="flex h-full items-center justify-center bg-red-50 text-red-600 p-4 text-center text-sm">
          {error}
        </div>
      ) : (
        <div id="chat-container" className="w-full h-full" />
      )}
    </div>
  );
}

async function loadChatKitScript() {
  const url =
    process.env.NEXT_PUBLIC_CHATKIT_SCRIPT_URL || DEFAULT_CHATKIT_SCRIPT_URL;

  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  if (window.ChatKit) {
    return;
  }

  const existingScript = document.getElementById("chatkit-script");
  if (existingScript) {
    await waitForChatKit();
    return;
  }

  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = "chatkit-script";
    script.src = url;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load ChatKit script."));
    document.body.appendChild(script);
  });

  await waitForChatKit();
}

function waitForChatKit() {
  return new Promise<void>((resolve, reject) => {
    if (window.ChatKit) {
      resolve();
      return;
    }

    const timeout = window.setTimeout(() => {
      reject(new Error("ChatKit script timed out while loading."));
    }, 10000);

    const check = () => {
      if (window.ChatKit) {
        window.clearTimeout(timeout);
        resolve();
      } else {
        requestAnimationFrame(check);
      }
    };

    check();
  });
}
