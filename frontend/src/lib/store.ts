/**
 * Zustand Store — Global state management for the IDE.
 */

import { create } from "zustand";

// ── Types ──────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface AgentStep {
  node: string;
  step: string;
  timestamp: number;
}

export interface IDEState {
  // Chat
  messages: ChatMessage[];
  agentSteps: AgentStep[];

  // File system (source of truth mirror)
  files: Record<string, string>;
  activeFile: string;

  // Snapshot of files before last generation — used for diff view
  previousFiles: Record<string, string>;

  // Preview (Sandpack)
  previewUrl: string;
  isPreviewReady: boolean;

  // Generation
  isGenerating: boolean;

  // Errors
  compilationErrors: string[];

  // Actions
  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => void;
  addAgentStep: (step: Omit<AgentStep, "timestamp">) => void;
  setFiles: (files: Record<string, string>) => void;
  updateFile: (path: string, content: string) => void;
  setActiveFile: (path: string) => void;
  setPreviousFiles: (files: Record<string, string>) => void;
  setPreviewUrl: (url: string) => void;
  setPreviewReady: (ready: boolean) => void;
  setGenerating: (generating: boolean) => void;
  clearAgentSteps: () => void;
  setCompilationErrors: (errors: string[]) => void;
}

// ── Store ──────────────────────────────────────────────────────────

export const useIDEStore = create<IDEState>((set) => ({
  messages: [],
  agentSteps: [],
  files: {},
  activeFile: "src/App.tsx",
  previousFiles: {},
  previewUrl: "",
  isPreviewReady: false,
  isGenerating: false,
  compilationErrors: [],

  addMessage: (msg) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { ...msg, id: crypto.randomUUID(), timestamp: Date.now() },
      ],
    })),

  addAgentStep: (step) =>
    set((s) => ({
      agentSteps: [...s.agentSteps, { ...step, timestamp: Date.now() }],
    })),

  setFiles: (files) => set({ files }),

  setPreviousFiles: (previousFiles) => set({ previousFiles }),

  updateFile: (path, content) =>
    set((s) => ({
      files: { ...s.files, [path]: content },
    })),

  setActiveFile: (path) => set({ activeFile: path }),

  setPreviewUrl: (url) => set({ previewUrl: url }),
  setPreviewReady: (ready) => set({ isPreviewReady: ready }),

  setGenerating: (generating) => set({ isGenerating: generating }),

  clearAgentSteps: () => set({ agentSteps: [] }),

  setCompilationErrors: (errors) => set({ compilationErrors: errors }),
}));
