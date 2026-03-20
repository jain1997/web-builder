/**
 * useChat Hook — SSE streaming connection to the backend agent pipeline.
 *
 * Uses fetch() + ReadableStream to consume Server-Sent Events from
 * POST /v1/generate. No WebSocket needed — simpler, works through
 * CDNs/proxies, and supports standard HTTP auth.
 */

"use client";

import { useCallback, useRef } from "react";
import { useIDEStore } from "@/lib/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN = process.env.NEXT_PUBLIC_AUTH_TOKEN || "";

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

/** Parse SSE text stream into individual events. */
function parseSSE(chunk: string): Array<{ event: string; data: string }> {
  const events: Array<{ event: string; data: string }> = [];
  const blocks = chunk.split("\n\n").filter(Boolean);

  for (const block of blocks) {
    let event = "message";
    let data = "";

    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        data += line.slice(6);
      } else if (line.startsWith("data:")) {
        data += line.slice(5);
      }
    }

    if (data) {
      events.push({ event, data });
    }
  }

  return events;
}

export function useChat() {
  const abortRef = useRef<AbortController | null>(null);
  const {
    addMessage,
    addAgentStep,
    setFiles,
    setGenerating,
    clearAgentSteps,
    setCompilationErrors,
    setPreviousFiles,
  } = useIDEStore();

  const sendPrompt = useCallback(
    async (prompt: string) => {
      // Abort any in-flight request
      if (abortRef.current) {
        abortRef.current.abort();
      }

      // Capture errors BEFORE clearing
      const errorsToSend = useIDEStore.getState().compilationErrors;

      // Snapshot current files for diff view
      setPreviousFiles(useIDEStore.getState().files);

      // Update UI state
      addMessage({ role: "user", content: prompt });
      clearAgentSteps();
      setCompilationErrors([]);
      setGenerating(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (AUTH_TOKEN) {
        headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
      }

      try {
        const response = await fetch(`${API_URL}/v1/generate`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            prompt,
            session_id: getSessionId(),
            files: useIDEStore.getState().files,
            errors: errorsToSend,
            history: useIDEStore.getState().messages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `Server error: ${response.status}`);
        }

        if (!response.body) {
          throw new Error("No response body — SSE streaming not supported");
        }

        // Read the SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Split on double newline (SSE event boundary)
          const parts = buffer.split("\n\n");
          // Keep the last partial chunk in the buffer
          buffer = parts.pop() || "";

          for (const part of parts) {
            const events = parseSSE(part + "\n\n");

            for (const { event, data } of events) {
              // Skip keep-alive pings
              if (event === "ping" || !data.trim()) continue;

              let parsed;
              try {
                parsed = JSON.parse(data);
              } catch {
                continue;
              }

              switch (event) {
                case "status":
                  if (parsed.node) setGenerating(parsed.node);
                  if (parsed.files) setFiles(parsed.files);
                  addAgentStep({
                    node: parsed.node || "system",
                    step: parsed.step,
                  });
                  break;

                case "result":
                  if (parsed.session_id) {
                    localStorage.setItem("agentic_session_id", parsed.session_id);
                  }
                  if (parsed.files && Object.keys(parsed.files).length > 0) {
                    setFiles(parsed.files);
                    addMessage({
                      role: "assistant",
                      content: `Generated ${Object.keys(parsed.files).length} file(s).`,
                    });
                  }
                  addAgentStep({
                    node: "system",
                    step: parsed.step || "Done",
                  });
                  setGenerating(false);
                  break;

                case "error":
                  addMessage({
                    role: "system",
                    content: `Error: ${parsed.message}`,
                  });
                  setGenerating(false);
                  break;
              }
            }
          }
        }

        // Stream finished — ensure generating is off
        setGenerating(false);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // User cancelled — not an error
          return;
        }

        const message = err instanceof Error ? err.message : "Unknown error";
        addMessage({ role: "system", content: `Connection error: ${message}` });
        setGenerating(false);
      } finally {
        abortRef.current = null;
      }
    },
    [
      addMessage,
      addAgentStep,
      clearAgentSteps,
      setFiles,
      setGenerating,
      setCompilationErrors,
      setPreviousFiles,
    ],
  );

  /** Cancel any in-flight generation. */
  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setGenerating(false);
      addMessage({ role: "system", content: "Generation cancelled." });
    }
  }, [setGenerating, addMessage]);

  return { sendPrompt, cancel };
}
