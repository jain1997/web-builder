/**
 * useChat Hook — WebSocket connection to the backend agent pipeline.
 *
 * Handles sending prompts, receiving streamed status updates,
 * and processing generated files from the backend.
 */

"use client";

import { useCallback, useEffect, useRef } from "react";
import { useIDEStore } from "@/lib/store";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

/** Returns a stable session ID stored in localStorage — created once per browser. */
function getSessionId(): string {
  const KEY = "agentic_session_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(KEY, id);
  }
  return id;
}

export function useChat() {
  const wsRef = useRef<WebSocket | null>(null);
  const {
    addMessage,
    addAgentStep,
    setFiles,
    setGenerating,
    clearAgentSteps,
    setCompilationErrors,
    setPreviousFiles,
  } = useIDEStore();

  // Establish WebSocket connection with auto-reconnect
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectDelayRef = useRef(1000); // Start with 1s

  const connect = useCallback(() => {
    console.log(`[WS] Connecting to ${WS_URL}...`);
    const ws = new WebSocket(`${WS_URL}/ws/chat`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected");
      reconnectDelayRef.current = 1000; // Reset delay on success
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        console.error("[WS] Malformed JSON received:", event.data);
        return;
      }

      switch (data.type) {
        case "status":
          if (data.node) setGenerating(data.node);
          if (data.files) setFiles(data.files);
          addAgentStep({ node: data.node || "system", step: data.step });
          break;

        case "result":
          // Backend may assign a new session ID for fresh projects
          if (data.session_id) {
            localStorage.setItem("agentic_session_id", data.session_id);
          }
          if (data.files && Object.keys(data.files).length > 0) {
            // Full replace — backend sends all files that should be active.
            // Merging keeps stale/broken files from prior generations in Sandpack.
            setFiles(data.files);
            addMessage({
              role: "assistant",
              content: `Generated ${Object.keys(data.files).length} file(s).`,
            });
          }
          addAgentStep({ node: "system", step: data.step || "Done" });
          setGenerating(false);
          break;

        case "error":
          addMessage({ role: "system", content: `Error: ${data.message}` });
          setGenerating(false);
          break;
      }
    };

    ws.onclose = (e) => {
      console.log(`[WS] Disconnected (code: ${e.code}). Reconnecting in ${reconnectDelayRef.current}ms...`);
      wsRef.current = null;
      setGenerating(false);
      
      // Exponential backoff
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 30000); // Cap at 30s
        connect();
      }, reconnectDelayRef.current);
    };

    ws.onerror = (err) => {
      console.error("[WS] Socket error:", err);
      ws.close();
    };
  }, [addMessage, addAgentStep, setFiles, setGenerating]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // Send a prompt to the backend
  const sendPrompt = useCallback(
    (prompt: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        addMessage({
          role: "system",
          content: "Not connected to backend. Please wait…",
        });
        return;
      }

      // Capture errors BEFORE clearing — reading state after setCompilationErrors([])
      // returns an empty array, so errors must be snapshotted first.
      const errorsToSend = useIDEStore.getState().compilationErrors;

      // Snapshot current files for diff view before overwriting with new generation
      setPreviousFiles(useIDEStore.getState().files);

      // Add user message to chat
      addMessage({ role: "user", content: prompt });
      clearAgentSteps();
      setCompilationErrors([]);  // clear so auto-fix doesn't re-trigger
      setGenerating(true);

      // Send to backend
      ws.send(
        JSON.stringify({
          prompt,
          session_id: getSessionId(),
          files: useIDEStore.getState().files,
          errors: errorsToSend,   // snapshot taken before clearing
          history: useIDEStore.getState().messages.map(m => ({
            role: m.role,
            content: m.content
          })),
        })
      );
    },
    [addMessage, clearAgentSteps, setGenerating, setCompilationErrors, setPreviousFiles]
  );

  return { sendPrompt };
}
