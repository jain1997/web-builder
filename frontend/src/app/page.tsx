/**
 * Main IDE Page — The workspace that ties everything together.
 *
 * Layout: 2-pane resizable split (Chat + Preview/Editor)
 *   [Chat Panel] | [Live Preview] | [Code Editor]
 */

"use client";

import { useEffect, useRef } from "react";
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import dynamic from "next/dynamic";

import ChatPanel from "@/components/ChatPanel";
import ErrorBoundary from "@/components/ErrorBoundary";
import LivePreview from "@/components/LivePreview";
import { useChat } from "@/hooks/useChat";
import { useIDEStore } from "@/lib/store";

type FileTree = Record<string, string>;

const CodeEditor = dynamic(() => import("@/components/CodeEditor"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-[#0d1117] text-gray-600 text-sm">
      Loading editor…
    </div>
  ),
});

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function IDEPage() {
  const {
    setFiles,
    setPreviewReady,
    isGenerating,
    compilationErrors,
    addMessage,
    hydrateFromStorage,
  } = useIDEStore();

  const { sendPrompt } = useChat();
  const autoFixedRef = useRef(false);

  // Hydrate persisted state from localStorage after mount (avoids SSR mismatch)
  useEffect(() => {
    hydrateFromStorage();
  }, [hydrateFromStorage]);

  // Reset auto-fix guard whenever a new generation starts
  useEffect(() => {
    if (isGenerating) autoFixedRef.current = false;
  }, [isGenerating]);

  // Boot: fetch template files from backend on mount
  useEffect(() => {
    const init = async () => {
      try {
        let templateFiles: FileTree;
        try {
          const res = await fetch(`${API_URL}/v1/template`);
          if (!res.ok) throw new Error(`Server returned ${res.status}`);
          const data = await res.json();
          templateFiles = data.files || {};
        } catch {
          // Fallback — use minimal template if backend is not running
          templateFiles = {
            "App.tsx": `export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col items-center justify-center p-8">
      <div className="max-w-xl text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-2xl font-bold mx-auto mb-6">
          A
        </div>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent mb-4">
          Agentic Web IDE
        </h1>
        <p className="text-slate-400 text-lg">
          Type a prompt in the chat panel to start building your website.
        </p>
      </div>
    </div>
  );
}`,
          };
        }

        setFiles(templateFiles);
        setPreviewReady(true);
      } catch (err) {
        console.error("Failed to initialize:", err);
      }
    };

    setTimeout(init, 500);
  }, [setFiles, setPreviewReady]);

  // Auto-fix: detect Sandpack render errors and trigger backend self-repair.
  // Guard with autoFixedRef so we only attempt once per generation cycle.
  useEffect(() => {
    if (isGenerating || compilationErrors.length === 0) return;
    if (autoFixedRef.current) return;

    const timer = setTimeout(() => {
      const currentErrors = useIDEStore.getState().compilationErrors;
      if (currentErrors.length === 0 || autoFixedRef.current) return;

      autoFixedRef.current = true;
      // Clear errors first so the effect doesn't re-fire while the fix runs
      useIDEStore.getState().setCompilationErrors([]);

      addMessage({
        role: "system",
        content: `Auto-fixing ${currentErrors.length} rendering error(s)…`,
      });
      sendPrompt(`Fix these rendering errors:\n${currentErrors.join("\n")}`);
    }, 2000); // Give Sandpack 2s to finish bundling before reading errors

    return () => clearTimeout(timer);
  }, [compilationErrors, isGenerating, addMessage, sendPrompt]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#010409]">
      {/* Top bar */}
      <header className="h-10 flex items-center px-4 bg-[#010409] border-b border-[#21262d]">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-[10px] font-bold text-white">
            A
          </div>
          <span className="text-sm font-semibold text-gray-200 tracking-tight">
            Agentic Web IDE
          </span>
        </div>
        <div className="ml-auto flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1 text-green-400">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            Preview Ready
          </span>
        </div>
      </header>

      {/* Main content */}
      <div className="h-[calc(100vh-2.5rem)]">
        <PanelGroup direction="horizontal">
          {/* ── Left: Chat panel ──────────────────────────────── */}
          <Panel defaultSize={22} minSize={15} maxSize={40}>
            <ErrorBoundary fallbackLabel="Chat">
              <ChatPanel />
            </ErrorBoundary>
          </Panel>

          <PanelResizeHandle className="w-[3px] bg-[#21262d] hover:bg-blue-500 transition-colors cursor-col-resize" />

          {/* ── Center: Live Preview ──────────────────────────── */}
          <Panel defaultSize={45} minSize={25}>
            <ErrorBoundary fallbackLabel="Preview">
              <LivePreview />
            </ErrorBoundary>
          </Panel>

          <PanelResizeHandle className="w-[3px] bg-[#21262d] hover:bg-blue-500 transition-colors cursor-col-resize" />

          {/* ── Right: Editor ───────────────────────── */}
          <Panel defaultSize={33} minSize={20}>
            <ErrorBoundary fallbackLabel="Editor">
              <CodeEditor />
            </ErrorBoundary>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
