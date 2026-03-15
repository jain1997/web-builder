/**
 * buildPreview — Opens the generated website in a new browser tab.
 *
 * WHY THE OLD APPROACH FAILED:
 *   ES module `import` statements inside a blob: URL document cannot import
 *   other blob: URLs because the new-tab document has a null/opaque origin,
 *   and importing a blob: URL created from localhost is cross-origin → blocked.
 *
 * NEW APPROACH:
 *   1. Babel-transpile all .tsx/.ts files to CommonJS (require/exports).
 *   2. Inline every compiled module as a classic <script> tag.
 *   3. A tiny __require() polyfill resolves relative paths and maps known
 *      packages to UMD globals (React/ReactDOM from unpkg CDN) or lightweight
 *      stubs (lucide-react, framer-motion, etc.).
 *   4. Everything lives in one HTML blob → zero cross-origin issues.
 */

// ── Babel loader (singleton) ──────────────────────────────────────────────────
let babelPromise: Promise<any> | null = null;

function loadBabel(): Promise<any> {
  if ((window as any).Babel) return Promise.resolve((window as any).Babel);
  if (babelPromise) return babelPromise;
  babelPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://unpkg.com/@babel/standalone/babel.min.js";
    s.onload = () => resolve((window as any).Babel);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return babelPromise;
}

// ── Inline JS that provides stubs for external packages ───────────────────────
// React + ReactDOM come from UMD CDN scripts loaded in <head>.
// Everything else gets a lightweight stub so the page renders without crashing.
// NOTE: Every stub must have __esModule:true so Babel's _interopRequireDefault /
// _interopRequireWildcard helpers pass them through without double-wrapping.
// Without it: stub {default:fn} → interop wraps again → {default:{default:fn}}
// → _pkg.default is an object, not a function → runtime error.
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
      return { render: function(vnode) { window.ReactDOM.render(vnode, el); } };
    },
    default: { createRoot: function(el) { return { render: function(vnode) { window.ReactDOM.render(vnode, el); } }; } }
  },

  // lucide-react — every named export is an SVG icon stub
  "lucide-react": new Proxy({ __esModule: true }, {
    get: function(target, name) {
      if (name === "__esModule") return true;
      return __mkIcon(name);
    }
  }),

  // clsx — default export is the join function
  "clsx": { __esModule: true, default: __clsx },

  // tailwind-merge — default + named twMerge both work
  "tailwind-merge": { __esModule: true, default: __clsx, twMerge: __clsx, cn: __clsx },

  // framer-motion — motion.* renders as plain HTML elements; animation props stripped
  "framer-motion": (function() {
    var ANIM_PROPS = ["initial","animate","exit","variants","transition","whileHover","whileTap","layout","layoutId"];
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
      useTransform:    function(v, fn) { return { get: function(){ return fn ? fn(v.get()) : v.get(); } }; }
    };
  })(),

  // react-hook-form
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

  // date-fns
  "date-fns": {
    __esModule: true,
    format:   function(d, fmt) { try { return new Date(d).toLocaleDateString(); } catch(e){ return String(d); } },
    parseISO: function(s) { return new Date(s); },
    default:  {}
  },

  // @headlessui/react — render children passthrough
  "@headlessui/react": new Proxy({ __esModule: true }, {
    get: function(target, key) {
      if (key === "__esModule") return true;
      return function(props) { return (props && props.children) || null; };
    }
  }),

  // react-icons/* — every sub-path returns icon stubs
  "react-icons":       new Proxy({ __esModule: true }, { get: function(){ return new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }); } }),
  "react-icons/fa":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/fi":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/hi":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/md":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/bs":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/io":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),
  "react-icons/ai":    new Proxy({ __esModule: true }, { get: function(_, k){ return __mkIcon(k); } }),

  // recharts — render a placeholder div for each chart component
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
    // External package
    if (Object.prototype.hasOwnProperty.call(__externals, path)) {
      return __externals[path];
    }
    // Resolve relative path
    var resolved = path.startsWith(".") ? __resolveRelative(fromPath, path) : path;
    var key = __findKey(resolved);
    if (!key) {
      console.warn("[preview] module not found:", path, "(from " + fromPath + ")");
      return {};
    }
    if (__cache[key]) return __cache[key];
    var mod = { exports: {} };
    __cache[key] = mod.exports;          // set before exec to handle circular deps
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
    var root = document.getElementById("root");
    ReactDOM.render(React.createElement(App), root);
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
  const Babel = await loadBabel();

  // Normalize leading slashes
  const files: Record<string, string> = {};
  for (const [p, code] of Object.entries(rawFiles)) {
    files[p.startsWith("/") ? p.slice(1) : p] = code;
  }

  if (!files["App.tsx"]) {
    console.error("[buildPreview] No App.tsx found");
    return;
  }

  // ── Transpile to CommonJS ────────────────────────────────────────────────────
  const compiled: Record<string, string> = {};
  for (const [path, code] of Object.entries(files)) {
    try {
      compiled[path] = Babel.transform(code, {
        presets: [
          // runtime:"classic" so JSX becomes React.createElement (React is a UMD global)
          ["react", { runtime: "classic" }],
          ["typescript", { allExtensions: true, isTSX: true }],
          // env preset converts ES module import/export → CommonJS require/exports
          ["env", { modules: "commonjs", targets: { browsers: ["last 2 Chrome versions"] } }],
        ],
        filename: path,
      }).code;
    } catch (err: any) {
      console.warn(`[buildPreview] transpile failed for ${path}:`, err);
      // Emit a module that throws so the error appears at runtime
      compiled[path] =
        `exports.default = function() { throw new Error(${JSON.stringify("Compile error in " + path + ": " + (err.message ?? err))}); };`;
    }
  }

  // ── Build one <script> per module ───────────────────────────────────────────
  // Each module is wrapped in a factory: function(module, exports, require){...}
  // <\/script> inside code would break the surrounding <script> tag, so escape it.
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
  <!-- React + ReactDOM UMD (provides window.React and window.ReactDOM) -->
  <script src="https://unpkg.com/react@18/umd/react.development.js"><\/script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"><\/script>
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"><\/script>
</head>
<body>
  <div id="root"></div>

  <!-- 1. External package stubs -->
  <script>${EXTERNALS_SCRIPT}<\/script>

  <!-- 2. Module system (require / define) -->
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
