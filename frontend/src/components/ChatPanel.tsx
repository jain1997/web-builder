/**
 * ChatPanel — Conversational UI for prompting the AI agents.
 * Shows chat messages, agent execution steps, and a prompt input.
 */

"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useIDEStore } from "@/lib/store";
import { useChat } from "@/hooks/useChat";

export default function ChatPanel() {
  const [input, setInput] = useState("");
  const { sendPrompt, cancel } = useChat();
  const { messages, agentSteps, isGenerating, clearSession } = useIDEStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages/steps
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, agentSteps.length, isGenerating]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating) return;
    sendPrompt(input.trim());
    setInput("");
  };

  // Filter out heartbeat "Thinking…" noise — only keep meaningful steps
  const meaningfulSteps = agentSteps.filter(
    (s) => s.step && !s.step.startsWith("Thinking")
  );

  return (
    <div className="flex flex-col h-full bg-[#0d1117] border-r border-[#21262d]">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#21262d]">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <h2 className="text-sm font-semibold text-gray-200 tracking-wide">
          AI Agent Chat
        </h2>
        <button
          onClick={clearSession}
          disabled={isGenerating}
          className="ml-auto text-[10px] uppercase tracking-wider px-2 py-1
                     text-gray-400 hover:text-white border border-[#30363d]
                     hover:border-gray-500 rounded transition-colors
                     disabled:opacity-30 disabled:cursor-not-allowed"
        >
          New Session
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`rounded-xl px-3 py-2 text-sm leading-relaxed max-w-[90%] ${
              msg.role === "user"
                ? "ml-auto bg-blue-600/30 text-blue-100 border border-blue-500/20"
                : msg.role === "system"
                  ? "bg-red-900/20 text-red-300 border border-red-500/20"
                  : "bg-[#161b22] text-gray-300 border border-[#30363d]"
            }`}
          >
            <span className="text-[10px] uppercase tracking-widest text-gray-500 block mb-1">
              {msg.role}
            </span>
            {msg.content}
          </div>
        ))}

        {/* Agent pipeline steps */}
        {meaningfulSteps.length > 0 && (
          <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-3">
            <span className="text-[10px] uppercase tracking-widest text-purple-400 block mb-2">
              Agent Pipeline
            </span>
            <div className="space-y-1">
              {meaningfulSteps.map((step, i) => {
                const isDone = step.step.includes("✓") || step.step.includes("✓");
                const isError = step.step.toLowerCase().includes("error") || step.step.toLowerCase().includes("failed");
                const isImage = step.step.toLowerCase().includes("image");
                return (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-xs py-0.5"
                  >
                    <span className={`mt-0.5 shrink-0 ${
                      isError ? "text-red-400" :
                      isDone ? "text-green-400" :
                      isImage ? "text-purple-400" :
                      "text-blue-400"
                    }`}>
                      {isError ? "✕" : isDone ? "✓" : isImage ? "◆" : "▸"}
                    </span>
                    <span className={
                      isError ? "text-red-300" :
                      isDone ? "text-gray-300" :
                      "text-gray-400"
                    }>
                      {step.step}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isGenerating && (
          <div className="flex items-center gap-2 text-xs text-gray-500 py-1">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
            <span>Agents working…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-[#21262d]">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe your website…"
            disabled={isGenerating}
            className="flex-1 bg-[#161b22] border border-[#30363d] rounded-lg px-3 py-2
                       text-sm text-gray-100 placeholder-gray-500
                       focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50
                       disabled:opacity-50 transition-colors"
          />
          {isGenerating ? (
            <button
              type="button"
              onClick={cancel}
              className="px-4 py-2 bg-red-600 hover:bg-red-500
                         text-white text-sm font-medium rounded-lg transition-colors"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                         text-white text-sm font-medium rounded-lg
                         transition-colors disabled:cursor-not-allowed"
            >
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
