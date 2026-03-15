"""
Starter project template files for Sandpack react-ts template.

The react-ts template entry is /App.tsx (root level, no src/ prefix).
/index.tsx imports from ./App, so we must override /App.tsx.
"""

STARTER_FILES: dict[str, str] = {
    "App.tsx": """export default function App() {
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
          The AI agents will generate and render your code live here.
        </p>
      </div>
    </div>
  );
}
""",
}
