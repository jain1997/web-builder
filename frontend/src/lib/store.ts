/**
 * Zustand Store — Global state management for the IDE.
 *
 * Persists files and messages to localStorage so a page refresh
 * doesn't lose work. Transient state (agent steps, generating flag,
 * errors) is NOT persisted.
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

// ── LocalStorage persistence helpers ─────────────────────────────

const STORAGE_KEY = "agentic_ide_state";

interface PersistedState {
  files: Record<string, string>;
  previousFiles: Record<string, string>;
  messages: ChatMessage[];
  activeFile: string;
}

function loadPersistedState(): Partial<PersistedState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PersistedState;
    // Only restore if there are actual files (not just the template)
    if (parsed.files && Object.keys(parsed.files).length > 0) {
      return parsed;
    }
  } catch {
    // Corrupted state — ignore
  }
  return {};
}

function persistState(state: IDEState) {
  try {
    const toSave: PersistedState = {
      files: state.files,
      previousFiles: state.previousFiles,
      messages: state.messages.slice(-50), // Keep last 50 messages only
      activeFile: state.activeFile,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

// ── Store ──────────────────────────────────────────────────────────

const persisted = loadPersistedState();

export const useIDEStore = create<IDEState>((set, get) => ({
  messages: persisted.messages || [],
  agentSteps: [],
  files: persisted.files || {},
  activeFile: persisted.activeFile || "src/App.tsx",
  previousFiles: persisted.previousFiles || {},
  previewUrl: "",
  isPreviewReady: false,
  isGenerating: false,
  compilationErrors: [],

  addMessage: (msg) =>
    set((s) => {
      const next = {
        messages: [
          ...s.messages,
          { ...msg, id: crypto.randomUUID(), timestamp: Date.now() },
        ],
      };
      setTimeout(() => persistState(get()), 0);
      return next;
    }),

  addAgentStep: (step) =>
    set((s) => ({
      agentSteps: [...s.agentSteps, { ...step, timestamp: Date.now() }],
    })),

  setFiles: (files) => {
    set({ files });
    setTimeout(() => persistState(get()), 0);
  },

  setPreviousFiles: (previousFiles) => {
    set({ previousFiles });
    setTimeout(() => persistState(get()), 0);
  },

  updateFile: (path, content) =>
    set((s) => {
      const next = { files: { ...s.files, [path]: content } };
      setTimeout(() => persistState(get()), 0);
      return next;
    }),

  setActiveFile: (path) => {
    set({ activeFile: path });
    setTimeout(() => persistState(get()), 0);
  },

  setPreviewUrl: (url) => set({ previewUrl: url }),
  setPreviewReady: (ready) => set({ isPreviewReady: ready }),

  setGenerating: (generating) => set({ isGenerating: generating }),

  clearAgentSteps: () => set({ agentSteps: [] }),

  setCompilationErrors: (errors) => set({ compilationErrors: errors }),
}));
