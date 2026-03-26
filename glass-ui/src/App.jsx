import React, { useState } from "react";

const NAV_LINKS = ["Studio", "Explore", "Library", "Settings"];

const FEATURE_CARDS = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      </svg>
    ),
    tag: "Ambient",
    title: "Aurora",
    desc: "Soft light gradients that breathe life into every surface with dynamic color shifting.",
    accent: "from-blue-400/20 to-purple-400/10",
    glow: "rgba(120,120,255,0.25)",
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
      </svg>
    ),
    tag: "Clarity",
    title: "Frost",
    desc: "Crystal-clear glass layers with depth diffusion and precise backdrop blur rendering.",
    accent: "from-cyan-400/20 to-teal-400/10",
    glow: "rgba(80,220,210,0.25)",
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
      </svg>
    ),
    tag: "Depth",
    title: "Lumen",
    desc: "Luminous reflections and inner light that add tactile dimensionality to flat surfaces.",
    accent: "from-amber-400/20 to-rose-400/10",
    glow: "rgba(255,160,80,0.25)",
  },
];

const STATS = [
  { label: "Blur Layers", value: "12" },
  { label: "Opacity", value: "10%" },
  { label: "Render FPS", value: "120" },
  { label: "Glass Depth", value: "4px" },
];

export default function App() {
  const [active, setActive] = useState("Studio");
  const [hoveredCard, setHoveredCard] = useState(null);

  return (
    <div className="relative min-h-screen overflow-hidden font-sans">
      <AnimatedBackground />

      <div className="relative z-10 flex flex-col min-h-screen px-6 py-6 gap-10">
        {/* NAV */}
        <nav className="glass-nav mx-auto w-full max-w-5xl rounded-2xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-white/30 to-white/5 border border-white/20 flex items-center justify-center shadow-inner">
              <div className="w-2.5 h-2.5 rounded-sm bg-white/80" />
            </div>
            <span className="text-sm font-semibold text-white/85 tracking-wide">GlassUI</span>
          </div>

          <div className="flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <button
                key={link}
                onClick={() => setActive(link)}
                className={`nav-pill px-4 py-1.5 text-xs font-medium rounded-xl transition-all duration-300 ${
                  active === link
                    ? "bg-white/20 text-white shadow-ambient border border-white/25"
                    : "text-white/55 hover:text-white/80 hover:bg-white/10"
                }`}
              >
                {link}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
            <span className="text-xs text-white/50">Live</span>
          </div>
        </nav>

        {/* HERO */}
        <main className="flex-1 flex items-center justify-center">
          <div className="glass-shell w-full max-w-5xl rounded-[28px] p-8 sm:p-10">

            {/* Header row */}
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div>
                <p className="text-[10px] uppercase tracking-[0.4em] text-white/40 font-medium">
                  Premium · Glassmorphism · v2.0
                </p>
                <h1 className="mt-3 text-4xl sm:text-5xl font-bold text-white/90 leading-tight tracking-tight">
                  Glassmorphism<br />
                  <span className="gradient-text">Studio</span>
                </h1>
                <p className="mt-4 max-w-sm text-sm text-white/60 leading-relaxed">
                  A modern Apple-inspired glass surface system — layered translucency,
                  soft highlights, and depth that you can feel.
                </p>
              </div>

              <div className="flex flex-col items-end gap-3">
                <div className="flex gap-2">
                  <button className="glass-btn-secondary px-5 py-2 text-sm">
                    Explore
                  </button>
                  <button className="glass-btn-primary px-5 py-2 text-sm">
                    Create
                  </button>
                </div>
                <div className="glass-pill px-3 py-1 text-[10px] text-white/50 tracking-widest uppercase">
                  Blur 30px · Overlay 10%
                </div>
              </div>
            </div>

            {/* Divider */}
            <div className="my-8 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

            {/* Feature cards */}
            <div className="grid gap-5 sm:grid-cols-3">
              {FEATURE_CARDS.map((card, i) => (
                <div
                  key={card.title}
                  className="glass-card rounded-2xl p-6 cursor-pointer"
                  style={{ "--glow": card.glow }}
                  onMouseEnter={() => setHoveredCard(i)}
                  onMouseLeave={() => setHoveredCard(null)}
                >
                  <div className={`card-icon-wrap w-10 h-10 rounded-xl bg-gradient-to-br ${card.accent} border border-white/15 flex items-center justify-center text-white/70 mb-4 transition-all duration-300`}>
                    {card.icon}
                  </div>
                  <span className="text-[10px] uppercase tracking-[0.3em] text-white/45 font-medium">
                    {card.tag}
                  </span>
                  <h3 className="mt-2 text-lg font-semibold text-white/90">{card.title}</h3>
                  <p className="mt-1.5 text-xs text-white/55 leading-relaxed">{card.desc}</p>

                  <div className="mt-4 flex items-center gap-1.5 text-xs text-white/40 group-hover:text-white/60 transition-colors">
                    <span>Learn more</span>
                    <svg className="w-3 h-3 transition-transform duration-200 group-hover:translate-x-0.5" viewBox="0 0 16 16" fill="currentColor">
                      <path fillRule="evenodd" d="M4 8a.5.5 0 01.5-.5h5.793L8.146 5.354a.5.5 0 11.708-.708l3 3a.5.5 0 010 .708l-3 3a.5.5 0 01-.708-.708L10.293 8.5H4.5A.5.5 0 014 8z" />
                    </svg>
                  </div>
                </div>
              ))}
            </div>

            {/* Divider */}
            <div className="my-8 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {STATS.map((s) => (
                <div key={s.label} className="glass-stat rounded-xl px-4 py-3 text-center">
                  <div className="text-xl font-bold text-white/85">{s.value}</div>
                  <div className="mt-0.5 text-[10px] uppercase tracking-widest text-white/40">{s.label}</div>
                </div>
              ))}
            </div>

          </div>
        </main>

        {/* Footer pills */}
        <footer className="flex flex-wrap justify-center gap-3">
          {["Ambient Reflection", "Noise Texture", "Layered Depth", "Soft Shadows"].map((t) => (
            <div key={t} className="glass-pill px-4 py-1.5 text-[10px] uppercase tracking-[0.3em] text-white/50">
              {t}
            </div>
          ))}
        </footer>
      </div>
    </div>
  );
}

function AnimatedBackground() {
  return (
    <div className="absolute inset-0">
      <div className="bg-layer" />
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-orb bg-orb-3" />
      <div className="bg-orb bg-orb-4" />
      <div className="bg-noise" />
    </div>
  );
}
