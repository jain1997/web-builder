"""
Component Library.

Pre-defined, high-quality React/Tailwind component blocks.
The Architect can reference these to avoid writing boilerplate.
"""

COMPONENT_LIBRARY = {
    "Navbar": """
import React from 'react';

export default function Navbar() {
  return (
    <nav className="flex items-center justify-between px-8 py-4 bg-[#010409]/80 backdrop-blur-md border-b border-[#30363d] sticky top-0 z-50">
      <div className="text-xl font-bold text-white tracking-tight">BRAND</div>
      <div className="hidden md:flex gap-8 text-sm font-medium text-gray-400">
        <a href="#" className="hover:text-white transition-colors">Products</a>
        <a href="#" className="hover:text-white transition-colors">Solutions</a>
        <a href="#" className="hover:text-white transition-colors">Pricing</a>
      </div>
      <button className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-full transition-all">
        Get Started
      </button>
    </nav>
  );
}
""",
    "Hero": """
import React from 'react';

export default function Hero() {
  return (
    <section className="relative pt-32 pb-20 px-8 text-center overflow-hidden">
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-blue-600/20 blur-[120px] rounded-full -z-10" />
      <h1 className="text-6xl font-extrabold text-white mb-6 leading-tight">
        Build Faster with <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-300">Intelligent</span> Design
      </h1>
      <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
        The ultimate platform for creating stunning, responsive websites in seconds using a multi-agent AI pipeline.
      </p>
      <div className="flex justify-center gap-4">
        <button className="px-8 py-4 bg-white text-black font-bold rounded-xl hover:bg-gray-200 transition-all">
          Start Building
        </button>
        <button className="px-8 py-4 bg-[#161b22] text-white font-bold rounded-xl border border-[#30363d] hover:bg-[#21262d] transition-all">
          View Demo
        </button>
      </div>
    </section>
  );
}
""",
    "FeatureGrid": """
import React from 'react';

export default function FeatureGrid() {
  const features = [
    { title: 'Lightning Fast', desc: 'Optimized for performance and SEO out of the box.' },
    { title: 'AI Driven', desc: 'Intelligent agents handle the heavy lifting for you.' },
    { title: 'Responsive', desc: 'Looks stunning on every device, from mobile to desktop.' }
  ];

  return (
    <section className="py-20 px-8 bg-[#0d1117]">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl mx-auto">
        {features.map((f, i) => (
          <div key={i} className="p-8 bg-[#010409] border border-[#30363d] rounded-2xl hover:border-blue-500/50 transition-all group">
            <h3 className="text-xl font-bold text-white mb-4 group-hover:text-blue-400">{f.title}</h3>
            <p className="text-gray-400 leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
""",
    "Footer": """
import React from 'react';

export default function Footer() {
  return (
    <footer className="py-12 px-8 border-t border-[#30363d] bg-[#010409]">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-8">
        <div className="text-lg font-bold text-white">BRAND</div>
        <div className="flex gap-8 text-sm text-gray-500">
          <a href="#" className="hover:text-gray-300">Privacy Policy</a>
          <a href="#" className="hover:text-gray-300">Terms of Service</a>
          <a href="#" className="hover:text-gray-300">Contact</a>
        </div>
        <div className="text-sm text-gray-600">© 2026 Brand Inc. All rights reserved.</div>
      </div>
    </footer>
  );
}
"""
}
