import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import Script from "next/script";
import './globals.css';

export const metadata: Metadata = {
  title: 'TrueSight Agent',
  description: 'Explore metrics with the TrueSight analytics copilot.',
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <Script
          src={process.env.NEXT_PUBLIC_CHATKIT_SCRIPT_URL
            || "https://cdn.platform.openai.com/deployments/chatkit/chatkit.js"}
          strategy="afterInteractive"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
