/**
 * CodeEditor — Monaco Editor with:
 *   - File tab bar (changed-file indicator dots)
 *   - Normal editor / Diff editor toggle (per-file diff vs previous generation)
 *   - Download as ZIP button
 */

"use client";

import { useCallback, useState } from "react";
import Editor, { DiffEditor } from "@monaco-editor/react";
import { useIDEStore } from "@/lib/store";
import { downloadAsZip } from "@/lib/downloadZip";

function getLanguage(path: string) {
  if (path.endsWith(".tsx") || path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".jsx") || path.endsWith(".js")) return "javascript";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".html")) return "html";
  return "plaintext";
}

const EDITOR_OPTIONS = {
  minimap: { enabled: false },
  fontSize: 13,
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  lineNumbers: "on" as const,
  wordWrap: "on" as const,
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorSmoothCaretAnimation: "on" as const,
  padding: { top: 8, bottom: 8 },
  renderLineHighlight: "gutter" as const,
  tabSize: 2,
};

export default function CodeEditor() {
  const { files, activeFile, previousFiles, setActiveFile, updateFile } =
    useIDEStore();
  const [isDiffMode, setIsDiffMode] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const filePaths = Object.keys(files || {});

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      if (value !== undefined && activeFile) {
        updateFile(activeFile, value);
      }
    },
    [activeFile, updateFile]
  );

  const handleDownload = async () => {
    if (isDownloading || Object.keys(files).length === 0) return;
    setIsDownloading(true);
    try {
      await downloadAsZip(files, "project.zip");
    } finally {
      setIsDownloading(false);
    }
  };

  // A file is "changed" when it differs from the previous snapshot
  const isImage = (path: string) =>
    files[path]?.startsWith("data:image/") ?? false;
  const isChanged = (path: string) =>
    previousFiles[path] !== undefined && previousFiles[path] !== files[path];

  // Any file has a diff to show
  const hasDiff =
    Object.keys(previousFiles).length > 0 &&
    filePaths.some((p) => isChanged(p) || !(p in previousFiles));

  const currentCode = activeFile ? (files[activeFile] ?? "") : "";
  const previousCode = activeFile ? (previousFiles[activeFile] ?? "") : "";
  const showDiff = isDiffMode && hasDiff;

  return (
    <div className="flex flex-col h-full bg-[#0d1117]">
      {/* ── Toolbar ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1 px-2 py-1.5 bg-[#010409] border-b border-[#21262d] shrink-0">
        {/* Mode toggle */}
        <div className="flex rounded overflow-hidden border border-[#30363d] text-[11px] font-medium">
          <button
            onClick={() => setIsDiffMode(false)}
            className={`px-2.5 py-1 transition-colors ${
              !isDiffMode
                ? "bg-[#21262d] text-gray-100"
                : "text-gray-500 hover:text-gray-300 hover:bg-[#161b22]"
            }`}
          >
            Code
          </button>
          <button
            onClick={() => setIsDiffMode(true)}
            disabled={!hasDiff}
            title={hasDiff ? "Show diff vs previous generation" : "No diff yet — generate code first"}
            className={`px-2.5 py-1 transition-colors flex items-center gap-1 ${
              isDiffMode
                ? "bg-[#21262d] text-gray-100"
                : hasDiff
                ? "text-gray-500 hover:text-gray-300 hover:bg-[#161b22]"
                : "text-gray-700 cursor-not-allowed"
            }`}
          >
            Diff
            {hasDiff && (
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
            )}
          </button>
        </div>

        <div className="flex-1" />

        {/* Download ZIP */}
        <button
          onClick={handleDownload}
          disabled={isDownloading || filePaths.length === 0}
          title="Download all files as ZIP"
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium border transition-colors ${
            filePaths.length === 0
              ? "border-[#30363d] text-gray-700 cursor-not-allowed"
              : "border-[#30363d] text-gray-400 hover:text-gray-100 hover:border-gray-500 hover:bg-[#161b22]"
          }`}
        >
          {isDownloading ? (
            <>
              <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Zipping…
            </>
          ) : (
            <>
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download ZIP
            </>
          )}
        </button>
      </div>

      {/* ── File tabs ────────────────────────────────────────── */}
      <div className="flex gap-0 overflow-x-auto border-b border-[#21262d] bg-[#010409] shrink-0">
        {filePaths.map((path) => {
          const changed = isChanged(path);
          const isNew = hasDiff && !(path in previousFiles);
          const imgFile = isImage(path);
          return (
            <button
              key={path}
              onClick={() => setActiveFile(path)}
              className={`px-3 py-2 text-xs font-mono whitespace-nowrap border-r border-[#21262d]
                          transition-colors flex items-center gap-1.5 ${
                            path === activeFile
                              ? "bg-[#0d1117] text-gray-100 border-b-2 border-b-blue-500"
                              : "text-gray-500 hover:text-gray-300 hover:bg-[#161b22]"
                          }`}
            >
              {imgFile && (
                <svg className="w-3 h-3 text-purple-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              )}
              {path.split("/").pop()}
              {isNew && (
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" title="New file" />
              )}
              {!isNew && changed && (
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 shrink-0" title="Modified" />
              )}
            </button>
          );
        })}
      </div>

      {/* ── Editor area ──────────────────────────────────────── */}
      <div className="flex-1 min-h-0">
        {activeFile && files[activeFile] !== undefined ? (
          /* Image preview for data URI files */
          files[activeFile].startsWith("data:image/") ? (
            <div className="flex flex-col items-center justify-center h-full bg-[#0d1117] p-6 gap-4">
              <img
                src={files[activeFile]}
                alt={activeFile}
                className="max-w-full max-h-[80%] rounded-lg border border-[#30363d] shadow-lg object-contain"
              />
              <span className="text-xs text-gray-500 font-mono">{activeFile}</span>
            </div>
          ) : showDiff ? (
            <>
              {/* Diff header */}
              <div className="flex items-center justify-between px-3 py-1 bg-[#161b22] border-b border-[#21262d] text-[10px] text-gray-500 shrink-0">
                <span className="text-gray-600">Previous</span>
                <span className="font-mono text-gray-400">{activeFile}</span>
                <span className="text-gray-600">Current</span>
              </div>
              <div className="h-[calc(100%-1.75rem)]">
                <DiffEditor
                  height="100%"
                  language={getLanguage(activeFile)}
                  original={previousCode}
                  modified={currentCode}
                  theme="vs-dark"
                  options={{
                    ...EDITOR_OPTIONS,
                    readOnly: true,
                    renderSideBySide: true,
                    enableSplitViewResizing: true,
                    diffWordWrap: "on",
                  }}
                />
              </div>
            </>
          ) : (
            <Editor
              height="100%"
              language={getLanguage(activeFile)}
              value={currentCode}
              onChange={handleEditorChange}
              theme="vs-dark"
              options={EDITOR_OPTIONS}
            />
          )
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            {filePaths.length === 0
              ? "No files yet — send a prompt to generate code"
              : "Select a file to edit"}
          </div>
        )}
      </div>

      {/* ── Diff legend ──────────────────────────────────────── */}
      {showDiff && (
        <div className="flex items-center gap-4 px-3 py-1.5 bg-[#010409] border-t border-[#21262d] text-[10px] text-gray-600 shrink-0">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-yellow-400" /> Modified
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-400" /> New file
          </span>
          <span className="ml-auto text-gray-700">
            {filePaths.filter(isChanged).length} changed ·{" "}
            {filePaths.filter((p) => !(p in previousFiles)).length} new
          </span>
        </div>
      )}
    </div>
  );
}
