/**
 * buildPreview — Opens the generated website in a new browser tab.
 *
 * Uses sucrase (bundled, no CDN) to transpile TSX/TS → CommonJS,
 * then assembles everything into a single HTML blob with:
 *   - React + ReactDOM from CDN (UMD globals)
 *   - Tailwind CSS from CDN
 *   - Lightweight stubs for external packages (lucide, framer-motion, etc.)
 *   - A tiny __require() polyfill for module resolution
 */

import { transform } from "sucrase";

// ── Inline JS that provides stubs for external packages ───────────────────────
const EXTERNALS_SCRIPT = `
function __mkIcon(name) {
  return function Icon(props) {
    var size = (props && props.size) || 24;
    var cls  = (props && props.className) || "";
    return React.createElement("svg", {
      xmlns: "http://www.w3.org/2000/svg", width: size, height: size,
      viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      strokeWidth: 2, className: cls, "aria-label": String(name)
    });
  };
}

function __clsx() {
  return Array.prototype.slice.call(arguments).flat().filter(Boolean).join(" ");
}

var __externals = {
  "react":     window.React,
  "react-dom": window.ReactDOM,
  "react-dom/client": {
    __esModule: true,
    createRoot: function(el) {
      return { render: function(vnode) { window.ReactDOM.createRoot(el).render(vnode); } };
    },
    default: { createRoot: function(el) { return window.ReactDOM.createRoot(el); } }
  },

  "lucide-react": new Proxy({ __esModule: true }, {
    get: function(target, name) {
      if (name === "__esModule") return true;
      return __mkIcon(name);
    }
  }),

  "clsx": { __esModule: true, default: __clsx },

  "tailwind-merge": { __esModule: true, default: __clsx, twMerge: __clsx, cn: __clsx },

  "framer-motion": (function() {
    var ANIM_PROPS = ["initial","animate","exit","variants","transition","whileHover","whileTap","whileInView","layout","layoutId"];
    var motionProxy = new Proxy({}, {
      get: function(_, tag) {
        return React.forwardRef(function(props, ref) {
          var p = Object.assign({}, props, { ref: ref });
          ANIM_PROPS.forEach(function(k) { delete p[k]; });
          return React.createElement(typeof tag === "string" ? tag : "div", p);
        });
      }
    });
    return {
      __esModule: true,
      motion: motionProxy,
      AnimatePresence: function(p) { return (p && p.children) || null; },
      useAnimation:    function() { return { start: function(){}, stop: function(){} }; },
      useMotionValue:  function(v) { return { get: function(){ return v; }, set: function(){} }; },
      useTransform:    function(v, fn) { return { get: function(){ return fn ? fn(v.get()) : v.get(); } }; },
      useInView:       function() { return true; },
      useScroll:       function() { return { scrollY: { get: function(){ return 0; } }, scrollYProgress: { get: function(){ return 0; } } }; }
    };
  })(),

  "react-hook-form": {
    __esModule: true,
    useForm: function() {
      return {
        register:     function(n) { return { name: n, onChange: function(){}, onBlur: function(){}, ref: function(){} }; },
        handleSubmit: function(fn) { return function(e){ e && e.preventDefault && e.preventDefault(); fn({}); }; },
        formState:    { errors: {}, isSubmitting: false, isValid: true },
        watch:        function() { return ""; },
        setValue:     function() {},
        getValues:    function() { return {}; },
        reset:        function() {},
        control:      {}
      };
    },
    Controller: function(props) {
      if (!props || !props.render) return null;
      return props.render({ field: { name: props.name || "", onChange: function(){}, onBlur: function(){}, value: "" }, fieldState: { error: null, invalid: false } });
    },
    default: {}
  },

  "date-fns": {
    __esModule: true,
    format:   function(d) { try { return new Date(d).toLocaleDateString(); } catch(e){ return String(d); } },
    parseISO: function(s) { return new Date(s); },
    default:  {}
  },

  "@headlessui/react": new Proxy({ __esModule: true }, {
    get: function(target, key) {
      if (key === "__esModule") return true;
      return function(props) { return (props && props.children) || null; };
    }
  }),

  "react-icons":       new Proxy({ __esModule: true }, { get: function(){ return new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }); } }),
  "react-icons/fa":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/fi":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/hi":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/md":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/bs":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/io":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/ai":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),

  "recharts": new Proxy({ __esModule: true }, {
    get: function(target, key) {
      if (key === "__esModule") return true;
      return function Chart(props) {
        return React.createElement("div", {
          style: { background: "#f8f9fa", border: "1px dashed #ccc", padding: "1.5rem", borderRadius: "0.5rem", textAlign: "center", color: "#888", fontSize: "0.875rem" }
        }, String(key) + " chart");
      };
    }
  })
};
`;

// ── Inline module system ───────────────────────────────────────────────────────
const MODULE_SYSTEM_SCRIPT = `
var __modules = {};
var __cache   = {};

function __resolveRelative(from, rel) {
  var dir = from.includes("/") ? from.split("/").slice(0, -1).join("/") : "";
  var combined = dir ? dir + "/" + rel : rel;
  var parts = combined.split("/"), out = [];
  parts.forEach(function(p) {
    if (p === ".") return;
    if (p === "..") out.pop();
    else if (p) out.push(p);
  });
  return out.join("/");
}

function __findKey(path) {
  if (__modules[path]) return path;
  var exts = [".tsx", ".ts", ".jsx", ".js"];
  for (var i = 0; i < exts.length; i++) {
    if (__modules[path + exts[i]]) return path + exts[i];
  }
  return null;
}

function __makeRequire(fromPath) {
  return function __require(path) {
    if (Object.prototype.hasOwnProperty.call(__externals, path)) {
      return __externals[path];
    }
    var resolved = path.startsWith(".") ? __resolveRelative(fromPath, path) : path;
    var key = __findKey(resolved);
    if (!key) {
      console.warn("[preview] module not found:", path, "(from " + fromPath + ")");
      return {};
    }
    if (__cache[key]) return __cache[key];
    var mod = { exports: {} };
    __cache[key] = mod.exports;
    __modules[key](mod, mod.exports, __makeRequire(key));
    __cache[key] = mod.exports;
    return mod.exports;
  };
}
`;

// ── Mount script ──────────────────────────────────────────────────────────────
const MOUNT_SCRIPT = `
(function() {
  try {
    var appExports = __makeRequire("")("App.tsx");
    var App = appExports.default || appExports;
    if (typeof App !== "function") throw new Error("App.tsx did not export a default function. Got: " + typeof App);
    var container = document.getElementById("root");
    if (ReactDOM.createRoot) {
      ReactDOM.createRoot(container).render(React.createElement(App));
    } else {
      ReactDOM.render(React.createElement(App), container);
    }
  } catch (err) {
    document.getElementById("root").innerHTML =
      '<div style="color:#c00;background:#fee;padding:20px;font-family:monospace;white-space:pre-wrap">' +
      '<strong>Preview error</strong>\\n\\n' + (err.message || String(err)) + '</div>';
    console.error("[preview]", err);
  }
})();
`;

// ── Main export ───────────────────────────────────────────────────────────────
export async function openPreviewInNewTab(
  rawFiles: Record<string, string>
): Promise<void> {
  // Normalize leading slashes
  const files: Record<string, string> = {};
  for (const [p, code] of Object.entries(rawFiles)) {
    files[p.startsWith("/") ? p.slice(1) : p] = code;
  }

  if (!files["App.tsx"]) {
    console.error("[buildPreview] No App.tsx found");
    return;
  }

  // ── Separate code files from image data URIs ────────────────────────────────
  const codeFiles: Record<string, string> = {};
  for (const [path, content] of Object.entries(files)) {
    if (!content.startsWith("data:image/")) {
      codeFiles[path] = content;
    }
  }

  // ── Transpile TSX/TS → CommonJS with sucrase ──────────────────────────────
  const compiled: Record<string, string> = {};
  for (const [path, code] of Object.entries(codeFiles)) {
    try {
      // Extract data URIs before transpilation (huge base64 strings slow things down)
      const dataUriMap: Record<string, string> = {};
      let idx = 0;
      const safeCode = code.replace(
        /data:image\/[^"'`\s]+/g,
        (match) => {
          const key = `__DATA_URI_${idx++}__`;
          dataUriMap[key] = match;
          return key;
        }
      );

      let result = transform(safeCode, {
        transforms: ["typescript", "jsx", "imports"],
        jsxRuntime: "classic",
        jsxPragma: "React.createElement",
        jsxFragmentPragma: "React.Fragment",
        filePath: path,
      }).code;

      // Restore data URIs
      for (const [key, uri] of Object.entries(dataUriMap)) {
        result = result.replaceAll(key, uri);
      }

      compiled[path] = result;
    } catch (err: any) {
      console.warn(`[buildPreview] transpile failed for ${path}:`, err);
      compiled[path] =
        `exports.default = function() { return React.createElement("div", {style:{color:"#c00",background:"#fee",padding:"20px",fontFamily:"monospace",whiteSpace:"pre-wrap"}}, "Compile error in ${path}:\\n" + ${JSON.stringify(err.message ?? String(err))}); };`;
    }
  }

  // ── Build one <script> per module ───────────────────────────────────────────
  const moduleScripts = Object.entries(compiled)
    .map(([path, code]) => {
      const safeCode = code.replace(/<\/script>/gi, "<\\/script>");
      return (
        `<script>\n__modules[${JSON.stringify(path)}] = ` +
        `function(module, exports, require) {\n${safeCode}\n};\n<\/script>`
      );
    })
    .join("\n");

  // ── Assemble final HTML ──────────────────────────────────────────────────────
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Preview — Agentic Web IDE</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js"><\/script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"><\/script>
  <script src="https://cdn.tailwindcss.com"><\/script>
</head>
<body>
  <div id="root"></div>

  <!-- 1. External package stubs -->
  <script>${EXTERNALS_SCRIPT}<\/script>

  <!-- 2. Module system -->
  <script>${MODULE_SYSTEM_SCRIPT}<\/script>

  <!-- 3. Compiled app modules -->
  ${moduleScripts}

  <!-- 4. Mount -->
  <script>${MOUNT_SCRIPT}<\/script>
</body>
</html>`;

  window.open(
    URL.createObjectURL(new Blob([html], { type: "text/html" })),
    "_blank"
  );
}
