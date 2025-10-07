import dynamic from 'next/dynamic';

const ChatPanel = dynamic(() => import('@/components/ChatPanel'), { ssr: false });

export default function Page() {
  return (
    <main className="p-6 space-y-4">
      <header>
        <h1 className="text-xl font-semibold">TrueSight Agent</h1>
        <p className="text-sm text-neutral-600">Ask questions about your data and review structured answers.</p>
      </header>
      <ChatPanel />
    </main>
  );
}
