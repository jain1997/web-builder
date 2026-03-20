/**
 * LivePreview — Lightweight browser-side preview using Sandpack.
 */

"use client";
import { useEffect, useState } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackPreview,
  useSandpack,
} from "@codesandbox/sandpack-react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useIDEStore } from "@/lib/store";
import { openPreviewInNewTab } from "@/lib/buildPreview";

/**
 * Listens for Sandpack bundler messages and forwards errors to the
 * global store so the auto-fix pipeline can pick them up.
 */
function SandpackErrorWatcher() {
  const { listen } = useSandpack();
  const setCompilationErrors = useIDEStore((s) => s.setCompilationErrors);

  useEffect(() => {
    return listen((msg: any) => {
      // Only capture errors — never clear on "start" here.
      // Clearing on every bundler "start" event causes rapid set/clear cycles
      // that make the error overlay blink. Errors are cleared in sendPrompt
      // when the user submits a new request.
      if (msg.type === "action" && msg.action === "show-error") {
        const location = msg.path ? `${msg.path} (${msg.line}:${msg.column})` : "";
        const text = [msg.title, location, msg.message].filter(Boolean).join(" — ");
        setCompilationErrors([text || "Unknown Sandpack error"]);
      }
    });
  }, [listen, setCompilationErrors]);

  return null;
}

export default function LivePreview() {
  const { files } = useIDEStore();
  const [opening, setOpening] = useState(false);

  const handleOpenInNewTab = async () => {
    if (opening || Object.keys(files).length === 0) return;
    setOpening(true);
    try {
      await openPreviewInNewTab(files);
    } finally {
      setOpening(false);
    }
  };

  // Sandpack requires paths with a leading slash (e.g. /src/App.tsx).
  // Normalize all keys from the store before passing in.
  const sandpackFiles = Object.fromEntries(
    Object.entries(files).map(([path, code]) => [
      path.startsWith("/") ? path : `/${path}`,
      code,
    ])
  );

  // Force Sandpack to remount (re-initialize the bundler) whenever the
  // set of files changes. Without this, SandpackProvider only reads
  // `files` once on mount and ignores subsequent prop updates.
  const previewKey = Object.keys(sandpackFiles).sort().join("|") || "default";

  return (
    <div className="flex flex-col h-full bg-[#0d1117] overflow-hidden">
      {/* URL bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-[#010409] border-b border-[#21262d]">
        <div className="flex gap-1.5">
          <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <span className="w-3 h-3 rounded-full bg-[#28c840]" />
        </div>
        <div className="flex-1 bg-[#161b22] rounded-md px-3 py-1 text-xs text-gray-400 font-mono border border-[#30363d]">
          preview.agentic.io
        </div>
        <button
          onClick={handleOpenInNewTab}
          disabled={opening || Object.keys(files).length === 0}
          title="Open in new tab"
          className="text-gray-500 hover:text-gray-200 disabled:opacity-30 transition-colors"
        >
          {opening ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
        </button>
      </div>

      <div className="flex-1 relative">
        <div className="absolute inset-0">
          <SandpackProvider
            key={previewKey}
            files={sandpackFiles}
            template="react-ts"
            theme="dark"
            style={{ height: "100%" }}
            options={{
              recompileMode: "immediate",
              recompileDelay: 300,
              externalResources: ["https://cdn.tailwindcss.com"],
            }}
            customSetup={{
              dependencies: {
                "lucide-react": "latest",
                "clsx": "latest",
                "tailwind-merge": "latest",
                "react-router-dom": "^6",
                "react-hook-form": "latest",
                "framer-motion": "latest",
                "date-fns": "latest",
                "react-icons": "latest",
                "@headlessui/react": "latest",
                "recharts": "latest",
                "three": "latest",
                "@react-three/fiber": "latest",
                "@react-three/drei": "latest",
              },
            }}
          >
            <SandpackErrorWatcher />
            <SandpackLayout
              style={{
                height: "100%",
                border: "none",
                borderRadius: 0,
                // Override Sandpack's default fixed layout height CSS variable
                ["--sp-layout-height" as string]: "100%",
              }}
            >
              <SandpackPreview
                showNavigator={false}
                showRefreshButton={false}
                showOpenInCodeSandbox={false}
                style={{ height: "100%" }}
              />
            </SandpackLayout>
          </SandpackProvider>
        </div>
      </div>
    </div>
  );
}
