import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import { Terminal, Code, Play, Send, GitBranch, Network, Mic, FolderOpen, FileCode2, PanelLeftClose, PanelLeft, Check, X, Plus, Trash2, Sparkles, Bot } from "lucide-react";
import CodeCanvas from './components/CodeCanvas';
import LivePreview from './components/LivePreview';
import TestingDashboard from './components/TestingDashboard';
import MessageBubble from './components/MessageBubble';

/* ─── Resize Handles ─────────────────────────────────────────── */
const ResizeHandle = () => (
  <PanelResizeHandle className="w-[3px] bg-[#13141b] hover:bg-[#3b82f6] transition-colors duration-200 cursor-col-resize shrink-0 group relative">
    <span className="absolute inset-y-0 -left-[2px] -right-[2px] group-hover:bg-blue-500/10 transition-colors duration-200" />
  </PanelResizeHandle>
);
const HorizontalResizeHandle = () => (
  <PanelResizeHandle className="h-[3px] w-full bg-[#13141b] hover:bg-[#3b82f6] transition-colors duration-200 cursor-row-resize shrink-0" />
);

/* ─── Model Dictionary ───────────────────────────────────────── */
// Cloud (Bedrock) models. The "Local (Ollama)" group is injected at runtime
// from whatever is actually installed in the local engine (see availableModels),
// so the list never claims a model you don't have pulled.
const BEDROCK_MODELS = [
  {
    group: "Anthropic Claude (Next-Gen)",
    models: [
      { id: "anthropic.claude-4-8-opus-v1:0", name: "Claude Opus 4.8" },
      { id: "anthropic.claude-4-7-opus-v1:0", name: "Claude Opus 4.7" },
      { id: "anthropic.claude-4-6-sonnet-v1:0", name: "Claude Sonnet 4.6" },
      { id: "anthropic.claude-4-6-opus-v1:0", name: "Claude Opus 4.6" },
      { id: "anthropic.claude-4-5-opus-v1:0", name: "Claude Opus 4.5" },
      { id: "anthropic.claude-4-5-haiku-v1:0", name: "Claude Haiku 4.5" }
    ]
  },
  {
    group: "DeepSeek (Advanced Reasoning)",
    models: [
      { id: "deepseek.r1-v1:0", name: "DeepSeek-R1" },
      { id: "deepseek.v3.2", name: "DeepSeek V3.2" }
    ]
  },
  {
    group: "OpenAI (OSS Series)",
    models: [
      { id: "openai.gpt-oss-120b-1:0", name: "gpt-oss-120b" },
      { id: "openai.gpt-oss-20b-1:0", name: "gpt-oss-20b" },
      { id: "openai.gpt-oss-safeguard-120b-1:0", name: "GPT OSS Safeguard 120B" },
      { id: "openai.gpt-oss-safeguard-20b-1:0", name: "GPT OSS Safeguard 20B" }
    ]
  },
  {
    group: "Google",
    models: [
      { id: "google.gemma-3-27b-it", name: "Gemma 3 (27B IT)" },
      { id: "google.gemma-3-12b-it", name: "Gemma 3 (12B IT)" },
      { id: "google.gemma-3-4b-it", name: "Gemma 3 (4B IT)" }
    ]
  },
  {
    group: "Moonshot AI",
    models: [
      { id: "moonshotai.kimi-k2.5", name: "Kimi K2.5" },
      { id: "moonshotai.kimi-k2-thinking", name: "Kimi K2 Thinking" }
    ]
  },
  {
    group: "Cohere (Enterprise Logic)",
    models: [
      { id: "cohere.command-r-plus-v1:0", name: "Command R+" },
      { id: "cohere.command-r-v1:0", name: "Command R" }
    ]
  },
  {
    group: "Mistral AI",
    models: [
      { id: "mistral.mistral-large-3-675b-instruct-v1:0", name: "Mistral Large 3" },
      { id: "mistral.mistral-large-2407-v1:0", name: "Mistral Large 2" },
      { id: "mistral.pixtral-large-v1:0", name: "Pixtral Large" }
    ]
  },
  {
    group: "Amazon Nova",
    models: [
      { id: "amazon.nova-pro-v1:0", name: "Nova Pro" },
      { id: "amazon.nova-lite-v1:0", name: "Nova Lite" },
      { id: "amazon.nova-micro-v1:0", name: "Nova Micro" }
    ]
  },
  {
    group: "Meta Llama",
    models: [
      { id: "us.meta.llama3-2-90b-instruct-v1:0", name: "Llama 3.2 (90B)" },
      { id: "us.meta.llama3-1-70b-instruct-v1:0", name: "Llama 3.1 (70B)" },
      { id: "us.meta.llama3-1-8b-instruct-v1:0", name: "Llama 3.1 (8B)" }
    ]
  }
];

/* ─── File Icon Colour Map ───────────────────────────────────── */
const fileIconColor = { html: '#e8855d', css: '#64b5f6', js: '#f0db4f' };
const getExt = (name) => name.split('.').pop();

/* ─── Model Selector (2026 Standard) ───────────────────────── */
const PROVIDER_META = {
  "Local (Ollama)": { color: "#34d399", icon: "⬡", tags: ["Offline", "Private"] },
  "Anthropic Claude (Next-Gen)": { color: "#d97757", icon: "◆", tags: ["Vision", "Reasoning"] },
  "DeepSeek (Advanced Reasoning)": { color: "#4f6ef7", icon: "◈", tags: ["Reasoning"] },
  "OpenAI (OSS Series)": { color: "#10a37f", icon: "◇", tags: ["Open Source"] },
  "Google": { color: "#4285f4", icon: "◉", tags: ["Lightweight"] },
  "Moonshot AI": { color: "#6366f1", icon: "◎", tags: ["Long Context"] },
  "Cohere (Enterprise Logic)": { color: "#d1d5db", icon: "□", tags: ["Enterprise"] },
  "Mistral AI": { color: "#f97316", icon: "△", tags: ["Multilingual"] },
  "Amazon Nova": { color: "#ff9900", icon: "☆", tags: ["Balanced"] },
  "Meta Llama": { color: "#0668e1", icon: "○", tags: ["Open Source"] }
};

const MODEL_TAGS = {
  "ollama.llama3.2": ["Offline", "Fast", "Local"],
  "ollama.qwen2.5-coder": ["Offline", "Coding", "Local"],
  "ollama.mistral": ["Offline", "Reasoning", "Local"],
  "anthropic.claude-4-8-opus-v1:0": ["Reasoning", "Vision", "Coding"],
  "anthropic.claude-4-7-opus-v1:0": ["Reasoning", "Vision"],
  "anthropic.claude-4-6-sonnet-v1:0": ["Vision", "Coding"],
  "anthropic.claude-4-6-opus-v1:0": ["Reasoning", "Vision"],
  "anthropic.claude-4-5-opus-v1:0": ["Vision"],
  "anthropic.claude-4-5-haiku-v1:0": ["Fast"],
  "deepseek.r1-v1:0": ["Reasoning", "Chain-of-Thought"],
  "deepseek.v3.2": ["Coding", "General"],
  "openai.gpt-oss-120b-1:0": ["Open", "120B"],
  "openai.gpt-oss-20b-1:0": ["Open", "20B"],
  "openai.gpt-oss-safeguard-120b-1:0": ["Safety", "120B"],
  "openai.gpt-oss-safeguard-20b-1:0": ["Safety", "20B"],
  "google.gemma-3-27b-it": ["27B", "Lightweight"],
  "google.gemma-3-12b-it": ["12B", "Lightweight"],
  "google.gemma-3-4b-it": ["4B", "Edge"],
  "moonshotai.kimi-k2.5": ["Long Context", "General"],
  "moonshotai.kimi-k2-thinking": ["Reasoning", "Long Context"],
  "cohere.command-r-plus-v1:0": ["Enterprise", "RAG"],
  "cohere.command-r-v1:0": ["Enterprise"],
  "mistral.mistral-large-3-675b-instruct-v1:0": ["675B", "Multilingual"],
  "mistral.mistral-large-2407-v1:0": ["Multilingual"],
  "mistral.pixtral-large-v1:0": ["Vision", "Multilingual"],
  "amazon.nova-pro-v1:0": ["Balanced", "Vision"],
  "amazon.nova-lite-v1:0": ["Fast", "Vision"],
  "amazon.nova-micro-v1:0": ["Fast", "Cost-Effective"],
  "us.meta.llama3-2-90b-instruct-v1:0": ["90B", "Vision"],
  "us.meta.llama3-1-70b-instruct-v1:0": ["70B"],
  "us.meta.llama3-1-8b-instruct-v1:0": ["8B", "Edge"]
};

function ModelSelector({ value, onChange, models }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const [recent, setRecent] = useState(() => {
    try { return JSON.parse(localStorage.getItem("recent_models") || "[]"); } catch { return []; }
  });
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const allModels = models.flatMap(g => g.models.map(m => ({ ...m, group: g.group })));
  const current = allModels.find(m => m.id === value);
  const provider = current ? PROVIDER_META[current.group] : null;

  const filtered = search.trim()
    ? allModels.filter(m =>
        m.name.toLowerCase().includes(search.toLowerCase()) ||
        m.group.toLowerCase().includes(search.toLowerCase()) ||
        (MODEL_TAGS[m.id] || []).some(t => t.toLowerCase().includes(search.toLowerCase()))
      )
    : allModels;

  const grouped = filtered.reduce((acc, m) => {
    if (!acc[m.group]) acc[m.group] = [];
    acc[m.group].push(m);
    return acc;
  }, {});

  const flatList = Object.entries(grouped).flatMap(([group, items]) => items.map(item => ({ ...item, group })));

  // Stable callback so it can be safely referenced inside effects below.
  const selectModel = useCallback((id) => {
    onChange(id);
    setOpen(false);
    setSearch("");
    setRecent(prev => {
      const next = [id, ...prev.filter(x => x !== id)].slice(0, 5);
      localStorage.setItem("recent_models", JSON.stringify(next));
      return next;
    });
  }, [onChange]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") { setOpen(false); setSearch(""); }
      if (e.key === "ArrowDown") { e.preventDefault(); setHighlighted(i => Math.min(i + 1, flatList.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setHighlighted(i => Math.max(i - 1, 0)); }
      if (e.key === "Enter") {
        e.preventDefault();
        const m = flatList[highlighted];
        if (m) selectModel(m.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, flatList, highlighted, selectModel]);

  // Focus the search input when the dropdown opens. Highlight reset happens in
  // the trigger handler and the search onChange, so no setState is needed here.
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => { if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  useEffect(() => {
    const el = listRef.current?.children[highlighted];
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [highlighted]);

  const recentModels = recent.map(id => allModels.find(m => m.id === id)).filter(Boolean);

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      {/* Trigger */}
      <button
        onClick={() => { if (!open) setHighlighted(0); setOpen(!open); }}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "6px 12px 6px 10px",
          borderRadius: 10,
          background: open ? "rgba(59,130,246,0.12)" : "var(--surface-3)",
          border: open ? "1px solid rgba(59,130,246,0.35)" : "1px solid var(--border)",
          boxShadow: open ? "0 0 20px rgba(59,130,246,0.15), inset 0 1px 0 rgba(255,255,255,0.04)" : "inset 0 1px 0 rgba(255,255,255,0.03)",
          cursor: "pointer", transition: "all 0.2s ease",
          fontFamily: "inherit", outline: "none",
        }}
      >
        <div style={{
          width: 26, height: 26, borderRadius: 7,
          background: provider ? `${provider.color}18` : "var(--surface-4)",
          border: provider ? `1px solid ${provider.color}30` : "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, color: provider?.color || "var(--text-3)",
          flexShrink: 0, transition: "all 0.2s",
        }}>
          {provider?.icon || "◆"}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", minWidth: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)", lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 180 }}>
            {current?.name || "Select Model"}
          </span>
          <span style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 500, lineHeight: 1.2 }}>
            {current?.group || "Model"}
          </span>
        </div>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ marginLeft: 4, flexShrink: 0, transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>
          <path d="M1 1L5 5L9 1" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0,
          width: 380, maxHeight: 520,
          background: "rgba(14,15,20,0.96)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 14,
          boxShadow: "0 24px 64px rgba(0,0,0,0.55), 0 0 0 1px rgba(59,130,246,0.08), 0 0 40px rgba(59,130,246,0.06)",
          backdropFilter: "blur(24px) saturate(1.5)",
          WebkitBackdropFilter: "blur(24px) saturate(1.5)",
          zIndex: 100,
          display: "flex", flexDirection: "column",
          overflow: "hidden",
          animation: "dropdownIn 0.18s cubic-bezier(0.16,1,0.3,1)",
        }}>
          {/* Search */}
          <div style={{
            padding: "12px 14px 10px",
            borderBottom: "1px solid rgba(255,255,255,0.04)",
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0, opacity: 0.5 }}>
              <circle cx="6" cy="6" r="5" stroke="var(--text-3)" strokeWidth="1.5"/>
              <path d="M10 10L13 13" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input
              ref={inputRef}
              value={search}
              onChange={e => { setSearch(e.target.value); setHighlighted(0); }}
              placeholder="Search models, providers, tags…"
              style={{
                flex: 1, background: "transparent", border: "none", outline: "none",
                color: "var(--text-1)", fontSize: 12.5, fontFamily: "inherit",
                caretColor: "var(--accent)",
              }}
            />
            {search && (
              <button onClick={() => { setSearch(""); inputRef.current?.focus(); }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 2, display: "flex" }}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </button>
            )}
            <span style={{ fontSize: 10, color: "var(--text-3)", background: "var(--surface-3)", padding: "2px 6px", borderRadius: 5, fontFamily: '"Geist Mono", monospace' }}>
              {flatList.length}
            </span>
          </div>

          {/* List */}
          <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: "6px 8px" }}>
            {/* Recent Section */}
            {!search && recentModels.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ padding: "6px 8px 4px", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", display: "flex", alignItems: "center", gap: 6 }}>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 1V5L7 7" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Recent
                </div>
                {recentModels.map(m => (
                  <ModelRow
                    key={`recent-${m.id}`}
                    model={m}
                    group={m.group}
                    isActive={m.id === value}
                    isHighlighted={flatList[highlighted]?.id === m.id}
                    onClick={() => selectModel(m.id)}
                  />
                ))}
                <div style={{ height: 1, background: "rgba(255,255,255,0.04)", margin: "6px 8px" }} />
              </div>
            )}

            {/* Grouped Models */}
            {Object.entries(grouped).map(([group, items]) => {
              const meta = PROVIDER_META[group] || { color: "var(--text-3)", icon: "◆" };
              return (
                <div key={group} style={{ marginBottom: 4 }}>
                  <div style={{ padding: "6px 8px 4px", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ color: meta.color, fontSize: 11 }}>{meta.icon}</span>
                    <span style={{ color: meta.color, opacity: 0.8 }}>{group}</span>
                    <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--text-3)", opacity: 0.6, fontWeight: 500, letterSpacing: 0, textTransform: "none" }}>{items.length}</span>
                  </div>
                  {items.map(m => (
                    <ModelRow
                      key={m.id}
                      model={m}
                      group={group}
                      isActive={m.id === value}
                      isHighlighted={flatList[highlighted]?.id === m.id}
                      onClick={() => selectModel(m.id)}
                    />
                  ))}
                </div>
              );
            })}

            {flatList.length === 0 && (
              <div style={{ padding: 32, textAlign: "center", color: "var(--text-3)", fontSize: 12 }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style={{ margin: "0 auto 8px", opacity: 0.3 }}>
                  <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M21 21L16.65 16.65" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                No models match “{search}”
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: "8px 14px",
            borderTop: "1px solid rgba(255,255,255,0.04)",
            fontSize: 10, color: "var(--text-3)",
            display: "flex", alignItems: "center", gap: 12,
            background: "rgba(0,0,0,0.2)",
          }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <kbd style={{ background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", fontFamily: '"Geist Mono", monospace', fontSize: 9 }}>↑↓</kbd>
              <span>Navigate</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <kbd style={{ background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", fontFamily: '"Geist Mono", monospace', fontSize: 9 }}>↵</kbd>
              <span>Select</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <kbd style={{ background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", fontFamily: '"Geist Mono", monospace', fontSize: 9 }}>esc</kbd>
              <span>Close</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelRow({ model, group, isActive, isHighlighted, onClick }) {
  const meta = PROVIDER_META[group] || { color: "var(--text-3)" };
  const tags = MODEL_TAGS[model.id] || [];
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%", display: "flex", alignItems: "center", gap: 10,
        padding: "7px 10px",
        borderRadius: 8,
        background: isActive ? "rgba(59,130,246,0.12)" : isHighlighted ? "rgba(255,255,255,0.04)" : "transparent",
        border: isActive ? "1px solid rgba(59,130,246,0.25)" : "1px solid transparent",
        color: "var(--text-1)", cursor: "pointer", transition: "all 0.12s ease",
        textAlign: "left", outline: "none",
        boxShadow: isActive ? "0 0 12px rgba(59,130,246,0.06)" : "none",
      }}
      onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; } }}
      onMouseLeave={e => { if (!isActive && !isHighlighted) { e.currentTarget.style.background = "transparent"; } }}
    >
      <div style={{
        width: 7, height: 7, borderRadius: "50%",
        background: meta.color,
        boxShadow: isActive ? `0 0 8px ${meta.color}80` : "none",
        flexShrink: 0, transition: "box-shadow 0.2s",
      }} />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 500, color: isActive ? "var(--text-1)" : "var(--text-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {model.name}
          </span>
          {isActive && (
            <span style={{ fontSize: 9, fontWeight: 700, color: "var(--accent)", background: "rgba(59,130,246,0.12)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 4, padding: "1px 5px", flexShrink: 0 }}>
              ACTIVE
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          {tags.slice(0, 3).map(tag => (
            <span key={tag} style={{ fontSize: 9, fontWeight: 600, color: "var(--text-3)", background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px" }}>
              {tag}
            </span>
          ))}
        </div>
      </div>
      {isActive && (
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0, color: "var(--accent)" }}>
          <path d="M2.5 7.5L5.5 10.5L11.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
    </button>
  );
}

/* ─── Suggested Prompts ─────────────────────────────────────── */
const SUGGESTED_PROMPTS = [
  { icon: '🎨', text: 'Build a landing page with hero, features, and CTA sections' },
  { icon: '🔌', text: 'Create a REST API with GET and POST endpoints' },
  { icon: '🌙', text: 'Add a dark/light mode toggle to the current file' },
  { icon: '🧪', text: 'Explain this code and suggest improvements' },
];

/* ─── New File Dialog ───────────────────────────────────────── */
function NewFileDialog({ onConfirm, onCancel }) {
  const [name, setName] = useState('');
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, []);
  const submit = (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed) onConfirm(trimmed);
  };
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onCancel}>
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--border)',
        borderRadius: 14, padding: '20px 22px', minWidth: 300,
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>New File</div>
        <form onSubmit={submit}>
          <input
            ref={inputRef}
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="filename.js"
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--surface-3)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '8px 12px',
              fontSize: 13, color: 'var(--text-1)', outline: 'none', fontFamily: 'inherit',
            }}
            onFocus={e => { e.target.style.borderColor = 'rgba(59,130,246,0.5)'; }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)'; }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button type="submit" style={{
              flex: 1, background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 8, padding: '7px 0',
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>
              Create
            </button>
            <button type="button" onClick={onCancel} style={{
              flex: 1, background: 'var(--surface-3)',
              color: 'var(--text-2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '7px 0',
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const EXT_LANG = { html: 'html', css: 'css', js: 'javascript', ts: 'typescript', jsx: 'javascript', tsx: 'typescript', json: 'json', py: 'python', md: 'markdown' };

export default function App() {
  const [files, setFiles] = useState({
    'index.html': { language: 'html', content: '<div class="text-center text-gray-400 font-mono mt-10">\n  <h1 class="title">Waiting for AI input...</h1>\n</div>' },
    'style.css':  { language: 'css',  content: '/* Add your CSS here */\n.title {\n  color: #60a5fa;\n}' },
    'app.js':     { language: 'javascript', content: '// Add your JavaScript here\nconsole.log("IDE Initialized");' }
  });
  const [activeFile, setActiveFile]   = useState('index.html');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showNewFile, setShowNewFile] = useState(false);

  const [messages, setMessages]        = useState([{ id: 1, sender: 'ai', text: 'Amazon Bedrock connected. What shall we build today?', steps: [] }]);
  const [convHistory, setConvHistory]  = useState([]); // Bedrock-format conversation history
  const [input, setInput]              = useState('');
  const [isStreaming, setIsStreaming]   = useState(false);

  const [selectedModel, setSelectedModel] = useState('amazon.nova-lite-v1:0');
  const [pendingAction, setPendingAction] = useState(null);
  const [activeBottomTab, setActiveBottomTab] = useState('terminal');
  const [termHistory, setTermHistory] = useState(['AI Editor OS v2.0', 'Type "help" for available commands.']);
  const [termInput,   setTermInput]   = useState('');
  const [gitHistory,  setGitHistory]  = useState(['Git Bash integrated.', 'Type "git status" to begin.']);
  const [gitInput,    setGitInput]    = useState('');
  const [isListening, setIsListening] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState({ available: false, models: [] });

  const terminalEndRef  = useRef(null);
  const gitEndRef       = useRef(null);
  const recognitionRef  = useRef(null);
  const chatEndRef      = useRef(null);
  const sidebarPanelRef = useRef(null);
  const textareaRef     = useRef(null);

  useEffect(() => { terminalEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [termHistory]);
  useEffect(() => { gitEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [gitHistory]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Probe the local Ollama engine for installed models. Runs on mount and again
  // whenever the window regains focus — so a model pulled in a terminal shows up
  // as soon as you switch back, without a hard refresh.
  useEffect(() => {
    const probe = () => fetch('http://localhost:5000/api/v1/models/local')
      .then(r => r.json())
      .then(s => setOllamaStatus(s))
      .catch(() => setOllamaStatus({ available: false, models: [] }));
    probe();
    window.addEventListener('focus', probe);
    return () => window.removeEventListener('focus', probe);
  }, []);

  // Build the model list shown in the selector: a dynamic "Local (Ollama)" group
  // built from the models actually installed (embedding-only models excluded,
  // since they can't chat), followed by the static cloud groups.
  const availableModels = useMemo(() => {
    const chatModels = (ollamaStatus.models || []).filter(m => !/embed/i.test(m));
    const localGroup = chatModels.length
      ? [{ group: 'Local (Ollama)', models: chatModels.map(m => ({ id: `ollama.${m}`, name: m })) }]
      : [];
    return [...localGroup, ...BEDROCK_MODELS];
  }, [ollamaStatus]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous     = false;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.onstart  = () => setIsListening(true);
      recognitionRef.current.onend    = () => setIsListening(false);
      recognitionRef.current.onresult = (e) => {
        let t = '';
        for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
        setInput(t);
      };
    }
  }, []);

  /* ─── Handlers ─────────────────────────────────────────────── */
  const handleTerminalSubmit = async (e) => {
    e.preventDefault();
    if (!termInput.trim()) return;
    const cmd = termInput.trim();
    setTermHistory(prev => [...prev, `user@desktop:~/ai-editor$ ${cmd}`]);
    setTermInput('');
    if (cmd.toLowerCase() === 'clear') return setTermHistory([]);
    try {
      const res  = await fetch('http://localhost:5000/api/terminal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: cmd }) });
      const data = await res.json();
      setTermHistory(prev => [...prev, ...data.output.split('\n').filter(l => l.length > 0)]);
    } catch {
      setTermHistory(prev => [...prev, 'Error: Could not connect to local execution server.']);
    }
  };

  const handleGitSubmit = async (e) => {
    e.preventDefault();
    if (!gitInput.trim()) return;
    const cmd = gitInput.trim();
    setGitHistory(prev => [...prev, `user@desktop:~/ai-editor (main)$ ${cmd}`]);
    setGitInput('');
    if (cmd.toLowerCase() === 'clear') return setGitHistory([]);
    try {
      const res  = await fetch('http://localhost:5000/api/terminal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: cmd }) });
      const data = await res.json();
      setGitHistory(prev => [...prev, ...data.output.split('\n').filter(l => l.length > 0)]);
    } catch {
      setGitHistory(prev => [...prev, 'Error: Could not execute git command.']);
    }
  };

  const handleApproveAction = async () => {
    if (!pendingAction) return;
    setActiveBottomTab('terminal');
    const commandsToRun = pendingAction.commands;
    setPendingAction(null);
    setMessages(prev => [...prev, { id: Date.now(), sender: 'ai', text: `✅ Executing ${commandsToRun.length} command(s) in terminal…` }]);
    for (const cmd of commandsToRun) {
      setTermHistory(prev => [...prev, `[AI AGENT]: $ ${cmd}`]);
      try {
        const res  = await fetch('http://localhost:5000/api/terminal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: cmd }) });
        const data = await res.json();
        setTermHistory(prev => [...prev, ...data.output.split('\n').filter(l => l.length > 0)]);
      } catch {
        setTermHistory(prev => [...prev, `[ERROR]: Failed to execute ${cmd}`]);
      }
    }
  };

  const handleRejectAction = () => {
    setMessages(prev => [...prev, { id: Date.now(), sender: 'user', text: '❌ Action rejected.' }]);
    setPendingAction(null);
  };

  const toggleVoice = () => {
    if (!recognitionRef.current) return alert("Voice recognition not supported.");
    isListening ? recognitionRef.current.stop() : (setInput(''), recognitionRef.current.start());
  };

  /* ─── Auto-resize textarea ─────────────────────────────────── */
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }, []);

  useEffect(() => { autoResize(); }, [input, autoResize]);

  /* ─── File management ───────────────────────────────────────── */
  const handleNewFile = (name) => {
    const ext = name.split('.').pop();
    const lang = EXT_LANG[ext] || 'javascript';
    setFiles(prev => ({ ...prev, [name]: { language: lang, content: '' } }));
    setActiveFile(name);
    setShowNewFile(false);
  };

  const handleDeleteFile = (name) => {
    const keys = Object.keys(files);
    if (keys.length <= 1) return;
    setFiles(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (activeFile === name) {
      const remaining = keys.filter(k => k !== name);
      setActiveFile(remaining[0] || 'index.html');
    }
  };

  /* ─── SSE-based send message ────────────────────────────────── */
  const handleSendMessage = async (e) => {
    e?.preventDefault();
    const userText = input.trim();
    if (!userText || isStreaming || pendingAction) return;

    setInput('');
    if (isListening) recognitionRef.current?.stop();

    // Add user message to UI
    const userMsgId = Date.now();
    setMessages(prev => [...prev, { id: userMsgId, sender: 'user', text: userText, steps: [] }]);

    // Build Bedrock-format conversation history
    const newHistory = [
      ...convHistory,
      { role: 'user', content: [{ text: userText }] }
    ];
    setConvHistory(newHistory);

    // Add loading AI message
    const aiMsgId = Date.now() + 1;
    setMessages(prev => [...prev, { id: aiMsgId, sender: 'ai', text: '', loading: true, steps: [], streaming: false }]);
    setIsStreaming(true);

    let accText = '';
    let accSteps = [];

    try {
      const response = await fetch('http://localhost:5000/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: newHistory, modelId: selectedModel })
      });

      if (!response.ok) throw new Error(`Server error ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processEvent = (eventType, rawData) => {
        let data;
        try { data = JSON.parse(rawData); } catch { return; }

        if (eventType === 'step') {
          accSteps = [...accSteps, data];
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, steps: accSteps, loading: false } : m
          ));
        } else if (eventType === 'text_chunk') {
          accText += data.text;
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: accText, loading: false, streaming: true } : m
          ));
        } else if (eventType === 'code') {
          setFiles(prev => ({ ...prev, [activeFile]: { ...prev[activeFile], content: data.code } }));
        } else if (eventType === 'done') {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: accText || 'Done.', loading: false, streaming: false } : m
          ));
          if (accText) {
            setConvHistory(prev => [...prev, { role: 'assistant', content: [{ text: accText }] }]);
          }
          setIsStreaming(false);
        } else if (eventType === 'human_required') {
          setPendingAction(data.input);
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: data.text || 'Authorization required.', loading: false, streaming: false, steps: accSteps } : m
          ));
          setIsStreaming(false);
        } else if (eventType === 'error') {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: `Error: ${data.text}`, loading: false, streaming: false } : m
          ));
          setIsStreaming(false);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const lines = part.split('\n');
          let eventType = 'message';
          let dataLine = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) dataLine = line.slice(6);
          }
          if (dataLine) processEvent(eventType, dataLine);
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId ? { ...m, text: `Error: ${err.message}`, loading: false, streaming: false } : m
      ));
      setIsStreaming(false);
    }
  };

  /* ─── Textarea key handler ──────────────────────────────────── */
  const handleInputKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };


  /* ─── Render ────────────────────────────────────────────────── */
  return (
    <div
      className="h-screen w-screen flex flex-col select-none overflow-hidden"
      style={{
        // Surfaces, accent, border and text vars now inherit from the global
        // token layer (src/styles/tokens.css) — single source of truth.
        // Only App-specific semantic aliases are declared locally.
        background: 'var(--canvas)',
        color: 'var(--text-1)',
        fontFamily: 'var(--font-sans)',
        '--border-hover': 'var(--border-strong)',
        '--green': 'var(--success)',
        '--amber': 'var(--warn)',
        '--red':   'var(--danger)',
      }}
    >

      {/* ══ TITLE BAR ══════════════════════════════════════════ */}
      <header
        className="h-11 shrink-0 flex items-center justify-between px-4"
        style={{
          background: 'rgba(14,15,20,0.85)',
          borderBottom: '1px solid var(--border)',
          backdropFilter: 'blur(12px) saturate(1.4)',
          WebkitBackdropFilter: 'blur(12px) saturate(1.4)',
          zIndex: 50,
        }}
      >
        {/* Left cluster */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center shadow-lg"
              style={{ 
                background: 'linear-gradient(135deg,#3b82f6 0%,#6366f1 100%)',
                boxShadow: '0 2px 8px rgba(59,130,246,0.25), inset 0 1px 0 rgba(255,255,255,0.15)'
              }}
            >
              <Code size={13} color="#fff" strokeWidth={2.5} />
            </div>
            <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text-1)' }}>
              AI Orchestrator
            </span>
            <span
              style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                color: 'var(--accent)', background: 'var(--accent-dim)',
                border: '1px solid var(--accent-glow)',
                borderRadius: 4, padding: '2px 7px', textTransform: 'uppercase',
                boxShadow: '0 0 12px rgba(59,130,246,0.08)',
              }}
            >
              Enterprise
            </span>
          </div>

          <div
            style={{ width: 1, height: 16, background: 'var(--border)', margin: '0 4px' }}
          />

          <button
            onClick={() => {
              if (sidebarOpen) {
                sidebarPanelRef.current?.collapse();
              } else {
                sidebarPanelRef.current?.expand();
              }
            }}
            className="transition-all duration-200"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-3)', padding: '5px',
              borderRadius: 6,
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-1)'; e.currentTarget.style.background = 'var(--surface-3)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'transparent'; }}
            title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          >
            {sidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeft size={15} />}
          </button>
        </div>

        {/* Right cluster */}
        <div className="flex items-center gap-3">
          <ModelSelector
            value={selectedModel}
            onChange={setSelectedModel}
            models={availableModels}
          />

          {/* Local / Cloud inference indicator */}
          {(() => {
            const local = selectedModel.startsWith('ollama.');
            const tag = selectedModel.replace(/^ollama\./, '');
            const ready = local && ollamaStatus.available &&
              ollamaStatus.models.some(m => m === tag || m.startsWith(tag + ':'));
            const color = local ? (ollamaStatus.available ? '#34d399' : '#fbbf24') : '#60a5fa';
            const label = local
              ? (ollamaStatus.available ? (ready ? 'Local · ready' : 'Local · not pulled') : 'Local · offline')
              : 'Cloud';
            return (
              <div
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                title={local
                  ? (ollamaStatus.available
                      ? (ready ? `Running offline on ${tag}` : `Ollama is up, but "${tag}" isn't pulled. Run: ollama pull ${tag}`)
                      : 'Ollama not reachable on :11434. Start it to run offline.')
                  : 'Inference runs on Amazon Bedrock (cloud).'}
                style={{
                  background: `${color}10`,
                  border: `1px solid ${color}28`,
                  fontSize: 11, fontWeight: 600, color,
                  boxShadow: `0 0 12px ${color}10`,
                }}
              >
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', background: color,
                  boxShadow: `0 0 8px ${color}`, display: 'inline-block',
                  animation: 'breathe 2.5s ease-in-out infinite',
                }}/>
                {label}
              </div>
            );
          })()}

          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
            style={{
              background: 'rgba(74,222,128,0.06)',
              border: '1px solid rgba(74,222,128,0.15)',
              fontSize: 11, fontWeight: 600, color: '#4ade80',
              boxShadow: '0 0 12px rgba(74,222,128,0.06)',
            }}
          >
            <span
              style={{
                width: 6, height: 6, borderRadius: '50%',
                background: '#4ade80',
                boxShadow: '0 0 8px #4ade80, 0 0 16px rgba(74,222,128,0.3)',
                display: 'inline-block',
                animation: 'breathe 2.5s ease-in-out infinite',
              }}
            />
            Secure Gateway
          </div>
        </div>
      </header>

      {/* ══ MAIN BODY ══════════════════════════════════════════ */}
      <div className="flex-1 overflow-hidden">
        <PanelGroup orientation="vertical">

          {/* Top 70% */}
          <Panel defaultSize={70} minSize={30}>
            <PanelGroup orientation="horizontal">

              {/* ── SIDEBAR ── */}
              <Panel
                ref={sidebarPanelRef}
                defaultSize={15} minSize={10}
                collapsible collapsedSize={0}
                onCollapse={() => setSidebarOpen(false)}
                onExpand={() => setSidebarOpen(true)}
                style={{ background: 'var(--surface-1)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
              >
                <div style={{
                  padding: '10px 10px 8px',
                  fontSize: 10, fontWeight: 700,
                  letterSpacing: '0.12em', textTransform: 'uppercase',
                  color: 'var(--text-3)',
                  borderBottom: '1px solid var(--border)',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  <FolderOpen size={11} style={{ color: 'var(--text-3)' }} />
                  <span style={{ flex: 1 }}>Explorer</span>
                  <button
                    onClick={() => setShowNewFile(true)}
                    title="New file"
                    style={{
                      padding: 4, borderRadius: 5, border: 'none',
                      background: 'none', cursor: 'pointer',
                      color: 'var(--text-3)', display: 'flex',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-1)'; e.currentTarget.style.background = 'var(--surface-3)'; }}
                    onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'none'; }}
                  >
                    <Plus size={13} />
                  </button>
                </div>

                <div style={{ flex: 1, padding: '8px 6px', overflowY: 'auto' }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '4px 8px', marginBottom: 4,
                    fontSize: 11, fontWeight: 600, color: 'var(--text-2)',
                  }}>
                    <FolderOpen size={13} style={{ color: 'var(--accent)' }} />
                    my-ai-project
                  </div>

                  {Object.keys(files).map(filename => {
                    const ext    = getExt(filename);
                    const color  = fileIconColor[ext] || '#8b8fa8';
                    const active = activeFile === filename;
                    const canDelete = Object.keys(files).length > 1;
                    return (
                      <div key={filename} style={{ position: 'relative' }} className="sidebar-file-row">
                        <button
                          onClick={() => setActiveFile(filename)}
                          style={{
                            width: '100%',
                            display: 'flex', alignItems: 'center', gap: 7,
                            padding: '5px 8px 5px 20px',
                            borderRadius: 6, fontSize: 11.5,
                            fontWeight: active ? 500 : 400,
                            background: active ? 'var(--accent-dim)' : 'transparent',
                            color: active ? 'var(--text-1)' : 'var(--text-2)',
                            border: active ? '1px solid var(--accent-glow)' : '1px solid transparent',
                            cursor: 'pointer', transition: 'all 0.12s',
                            textAlign: 'left', position: 'relative',
                          }}
                          onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--surface-3)'; e.currentTarget.style.color = 'var(--text-1)'; } }}
                          onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-2)'; } }}
                        >
                          {active && (
                            <span style={{
                              position: 'absolute', left: 6, top: '50%', transform: 'translateY(-50%)',
                              width: 3, height: 14, borderRadius: 2,
                              background: 'var(--accent)', boxShadow: '0 0 6px rgba(59,130,246,0.4)',
                            }}/>
                          )}
                          <FileCode2 size={12} style={{ color, flexShrink: 0 }} />
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {filename}
                          </span>
                        </button>
                        {canDelete && (
                          <button
                            onClick={() => handleDeleteFile(filename)}
                            title={`Delete ${filename}`}
                            className="delete-btn"
                            style={{
                              position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)',
                              padding: '2px 3px', borderRadius: 4, border: 'none',
                              background: 'var(--surface-4)', cursor: 'pointer',
                              color: '#f87171', display: 'none', alignItems: 'center',
                              opacity: 0, transition: 'opacity 0.15s',
                            }}
                          >
                            <Trash2 size={10} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Panel>
              <ResizeHandle />

              {/* ── AI BRAIN ── */}
              <Panel
                defaultSize={25} minSize={15}
                style={{ background: 'var(--surface-2)', display: 'flex', flexDirection: 'column', position: 'relative' }}
              >
                {/* Header */}
                <div style={{
                  padding: '0 14px', height: 40,
                  display: 'flex', alignItems: 'center', gap: 8,
                  borderBottom: '1px solid var(--border)',
                  fontSize: 10, fontWeight: 700,
                  letterSpacing: '0.1em', textTransform: 'uppercase',
                  color: 'var(--text-3)', flexShrink: 0,
                  background: 'var(--surface-1)',
                }}>
                  <Bot size={12} style={{ color: 'var(--accent)' }} />
                  AI Agent
                  {isStreaming && (
                    <span style={{
                      marginLeft: 4, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                      color: '#34d399', background: 'rgba(52,211,153,0.1)',
                      border: '1px solid rgba(52,211,153,0.2)',
                      borderRadius: 4, padding: '1px 6px', textTransform: 'uppercase',
                      animation: 'breathe 1.5s ease-in-out infinite',
                    }}>
                      Working
                    </span>
                  )}
                  <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 500, color: 'var(--text-3)', letterSpacing: 0, textTransform: 'none' }}>
                    {convHistory.length > 0 && `${Math.ceil(convHistory.length / 2)} turn${convHistory.length > 2 ? 's' : ''}`}
                  </span>
                </div>

                {/* Messages */}
                <div style={{
                  flex: 1, overflowY: 'auto', padding: '14px 10px',
                  display: 'flex', flexDirection: 'column', gap: 10,
                }}>
                  {messages.map(msg => (
                    <MessageBubble key={msg.id} msg={msg} />
                  ))}

                  {/* Human approval card */}
                  {pendingAction && (
                    <div style={{
                      background: 'var(--surface-3)',
                      border: '1px solid rgba(251,191,36,0.25)',
                      borderRadius: 14, padding: '14px',
                      fontSize: 12, marginTop: 4,
                      boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
                      position: 'relative', overflow: 'hidden',
                    }}>
                      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, transparent, #fbbf24, transparent)', opacity: 0.6 }}/>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#fbbf24', fontWeight: 700, marginBottom: 8, fontSize: 12 }}>
                        <span>⚠</span> Security Approval Required
                      </div>
                      <p style={{ color: 'var(--text-2)', marginBottom: 10, lineHeight: 1.6, fontSize: 12 }}>
                        {pendingAction.explanation}
                      </p>
                      <div style={{
                        background: '#0c0c10', borderRadius: 8, padding: '10px 12px',
                        fontFamily: '"Geist Mono", monospace', fontSize: 11.5, color: '#4ade80',
                        marginBottom: 12, overflowX: 'auto', border: '1px solid rgba(255,255,255,0.04)',
                      }}>
                        {(pendingAction.commands || []).map((cmd, i) => (
                          <div key={i} style={{ marginBottom: i < pendingAction.commands.length - 1 ? 3 : 0, display: 'flex', gap: 8 }}>
                            <span style={{ color: 'var(--text-3)', userSelect: 'none' }}>$</span>
                            <span>{cmd}</span>
                          </div>
                        ))}
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          onClick={handleApproveAction}
                          style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                            background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 8,
                            padding: '8px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                            boxShadow: '0 2px 8px rgba(59,130,246,0.25)',
                          }}
                          onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
                          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                        >
                          <Check size={13} strokeWidth={2.5} /> Run
                        </button>
                        <button
                          onClick={handleRejectAction}
                          style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                            background: 'rgba(248,113,113,0.08)', color: '#f87171',
                            border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8,
                            padding: '8px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = 'rgba(248,113,113,0.14)'}
                          onMouseLeave={e => e.currentTarget.style.background = 'rgba(248,113,113,0.08)'}
                        >
                          <X size={13} strokeWidth={2.5} /> Reject
                        </button>
                      </div>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {/* Input area */}
                <div style={{
                  padding: '8px 10px 10px',
                  borderTop: '1px solid var(--border)',
                  background: 'var(--surface-1)',
                  flexShrink: 0,
                }}>
                  {/* Suggested prompts — shown when input is empty and not streaming */}
                  {!input && !isStreaming && !pendingAction && messages.length <= 1 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                      {SUGGESTED_PROMPTS.map((p, i) => (
                        <button
                          key={i}
                          onClick={() => setInput(p.text)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 5,
                            padding: '4px 9px', borderRadius: 20,
                            background: 'var(--surface-3)', border: '1px solid var(--border)',
                            color: 'var(--text-3)', fontSize: 10.5, fontWeight: 500,
                            cursor: 'pointer', fontFamily: 'inherit',
                            transition: 'all 0.15s',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-1)'; e.currentTarget.style.borderColor = 'rgba(59,130,246,0.3)'; e.currentTarget.style.background = 'rgba(59,130,246,0.06)'; }}
                          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--surface-3)'; }}
                        >
                          <span>{p.icon}</span>
                          <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.text.split(' ').slice(0, 4).join(' ')}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 7 }}>
                    {/* Voice button */}
                    <button
                      type="button"
                      onClick={toggleVoice}
                      style={{
                        flexShrink: 0, padding: '7px', borderRadius: 9,
                        background: isListening ? 'rgba(248,113,113,0.12)' : 'var(--surface-3)',
                        color: isListening ? '#f87171' : 'var(--text-3)',
                        cursor: 'pointer', transition: 'all 0.2s',
                        boxShadow: isListening ? '0 0 12px rgba(248,113,113,0.2)' : 'none',
                        border: isListening ? '1px solid rgba(248,113,113,0.25)' : '1px solid var(--border)',
                        marginBottom: 1,
                      }}
                      onMouseEnter={e => { if (!isListening) { e.currentTarget.style.color = 'var(--text-1)'; e.currentTarget.style.background = 'var(--surface-4)'; } }}
                      onMouseLeave={e => { if (!isListening) { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'var(--surface-3)'; } }}
                    >
                      <Mic size={14} style={isListening ? { animation: 'pulse 1s ease-in-out infinite' } : {}} />
                    </button>

                    {/* Auto-expanding textarea */}
                    <div style={{ flex: 1, position: 'relative' }}>
                      <textarea
                        ref={textareaRef}
                        value={input}
                        onChange={e => { setInput(e.target.value); autoResize(); }}
                        onKeyDown={handleInputKeyDown}
                        disabled={!!pendingAction || isStreaming}
                        placeholder={
                          pendingAction ? 'Awaiting approval…'
                          : isStreaming ? 'AI is working…'
                          : `Ask about ${activeFile}, or describe what to build…`
                        }
                        rows={1}
                        style={{
                          width: '100%', boxSizing: 'border-box',
                          background: 'var(--surface-3)',
                          border: '1px solid var(--border)',
                          borderRadius: 10, padding: '8px 12px',
                          fontSize: 12.5, color: 'var(--text-1)',
                          outline: 'none', fontFamily: 'inherit',
                          resize: 'none', lineHeight: 1.5,
                          opacity: (pendingAction || isStreaming) ? 0.45 : 1,
                          transition: 'border-color 0.2s, box-shadow 0.2s',
                          overflow: 'hidden',
                        }}
                        onFocus={e => { e.target.style.borderColor = 'rgba(59,130,246,0.4)'; e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.07)'; }}
                        onBlur={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none'; }}
                      />
                      {input && (
                        <div style={{
                          position: 'absolute', bottom: 5, right: 8,
                          fontSize: 9, color: 'var(--text-3)', pointerEvents: 'none',
                        }}>
                          ↵ send · ⇧↵ newline
                        </div>
                      )}
                    </div>

                    {/* Send button */}
                    <button
                      type="button"
                      onClick={handleSendMessage}
                      disabled={!input.trim() || !!pendingAction || isStreaming}
                      style={{
                        flexShrink: 0, padding: '7px 9px', borderRadius: 9,
                        border: 'none',
                        background: (!input.trim() || pendingAction || isStreaming) ? 'var(--surface-3)' : 'var(--accent)',
                        color: (!input.trim() || pendingAction || isStreaming) ? 'var(--text-3)' : '#fff',
                        cursor: (!input.trim() || pendingAction || isStreaming) ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex', alignItems: 'center',
                        boxShadow: (!input.trim() || pendingAction || isStreaming) ? 'none' : '0 2px 8px rgba(59,130,246,0.25)',
                        marginBottom: 1,
                      }}
                    >
                      {isStreaming
                        ? <Sparkles size={14} style={{ animation: 'pulse 1s ease-in-out infinite' }} />
                        : <Send size={14} strokeWidth={2.5} />
                      }
                    </button>
                  </div>
                </div>
              </Panel>

              <ResizeHandle />

              {/* ── CODE EDITOR ── */}
              <Panel
                defaultSize={40} minSize={20}
                style={{ background: 'var(--surface-0)', display: 'flex', flexDirection: 'column' }}
              >
                <div
                  style={{
                    display: 'flex', background: 'var(--surface-1)',
                    borderBottom: '1px solid var(--border)',
                    flexShrink: 0, overflowX: 'auto',
                    padding: '0 4px',
                    gap: 2,
                  }}
                >
                  {Object.keys(files).map(filename => {
                    const ext    = getExt(filename);
                    const color  = fileIconColor[ext] || '#8b8fa8';
                    const active = activeFile === filename;
                    return (
                      <button
                        key={filename}
                        onClick={() => setActiveFile(filename)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 7,
                          padding: '0 14px',
                          height: 36,
                          fontSize: 12, fontWeight: active ? 500 : 400,
                          color: active ? 'var(--text-1)' : 'var(--text-3)',
                          background: active ? 'var(--surface-0)' : 'transparent',
                          border: 'none',
                          borderTop: active ? '2px solid var(--accent)' : '2px solid transparent',
                          borderBottom: active ? '1px solid var(--surface-0)' : '1px solid transparent',
                          borderRadius: '8px 8px 0 0',
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                          flexShrink: 0,
                          position: 'relative',
                          top: 1,
                        }}
                        onMouseEnter={e => { if (!active) { e.currentTarget.style.color = 'var(--text-2)'; e.currentTarget.style.background = 'var(--surface-2)'; } }}
                        onMouseLeave={e => { if (!active) { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'transparent'; } }}
                      >
                        <FileCode2 size={12} style={{ color: active ? color : 'inherit', opacity: active ? 1 : 0.6 }} />
                        {filename}
                      </button>
                    );
                  })}
                </div>

                <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
                  <CodeCanvas
                    code={files[activeFile].content}
                    onChange={newCode => setFiles(prev => ({ ...prev, [activeFile]: { ...prev[activeFile], content: newCode } }))}
                    language={files[activeFile].language}
                  />
                </div>
              </Panel>

              <ResizeHandle />

              {/* ── LIVE PREVIEW ── */}
              <Panel
                defaultSize={20} minSize={15}
                style={{ background: '#f8f9fb', display: 'flex', flexDirection: 'column', color: '#111' }}
              >
                <div
                  style={{
                    height: 38, display: 'flex', alignItems: 'center', gap: 10,
                    padding: '0 14px',
                    background: '#eef0f3',
                    borderBottom: '1px solid rgba(0,0,0,0.06)',
                    flexShrink: 0,
                  }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f57', display: 'inline-block', border: '1px solid rgba(0,0,0,0.06)' }} />
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffbd2e', display: 'inline-block', border: '1px solid rgba(0,0,0,0.06)' }} />
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#28c940', display: 'inline-block', border: '1px solid rgba(0,0,0,0.06)' }} />
                  <div
                    style={{
                      flex: 1, marginLeft: 6,
                      background: '#e2e5e9', borderRadius: 6,
                      height: 24, display: 'flex', alignItems: 'center',
                      padding: '0 12px', fontSize: 10.5, color: '#6b7280',
                      fontFamily: '"Geist Mono", monospace',
                      border: '1px solid rgba(0,0,0,0.04)',
                    }}
                  >
                    preview://localhost
                  </div>
                  <Play size={12} style={{ color: '#9ca3af' }} />
                </div>

                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <LivePreview files={files} />
                </div>
              </Panel>

            </PanelGroup>
          </Panel>

          <HorizontalResizeHandle />

          {/* ══ BOTTOM DRAWER ══════════════════════════════════ */}
          <Panel
            defaultSize={30} minSize={10} collapsible
            style={{ background: 'var(--surface-1)', display: 'flex', flexDirection: 'column' }}
          >
            <div
              style={{
                height: 38, display: 'flex', alignItems: 'stretch',
                background: 'var(--surface-2)',
                borderBottom: '1px solid var(--border)',
                flexShrink: 0, padding: '0 6px', gap: 2,
              }}
            >
              {[
                { id: 'terminal', icon: <Terminal size={13} />, label: 'Terminal' },
                { id: 'git',      icon: <GitBranch size={13} />, label: 'Git Bash' },
                { id: 'tester',   icon: <Network size={13} />,  label: 'API & Test Hub' },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveBottomTab(tab.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '0 16px',
                    border: 'none', background: 'transparent',
                    color: activeBottomTab === tab.id ? 'var(--text-1)' : 'var(--text-3)',
                    borderBottom: activeBottomTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                    fontSize: 12, fontWeight: activeBottomTab === tab.id ? 600 : 400,
                    cursor: 'pointer', transition: 'all 0.15s',
                    borderRadius: '6px 6px 0 0',
                    position: 'relative',
                    top: 1,
                  }}
                  onMouseEnter={e => { if (activeBottomTab !== tab.id) e.currentTarget.style.color = 'var(--text-2)'; }}
                  onMouseLeave={e => { if (activeBottomTab !== tab.id) e.currentTarget.style.color = 'var(--text-3)'; }}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            <div style={{ flex: 1, overflow: 'hidden', background: 'var(--surface-0)' }}>

              {activeBottomTab === 'terminal' && (
                <div
                  style={{
                    height: '100%', display: 'flex', flexDirection: 'column',
                    padding: '12px 16px',
                    fontFamily: '"Geist Mono", "Fira Code", "Cascadia Code", monospace',
                    fontSize: 12.5, color: '#c9cdd4',
                    overflowY: 'auto', cursor: 'text',
                  }}
                  onClick={() => document.getElementById('term-input').focus()}
                >
                  {termHistory.map((line, i) => (
                    <div
                      key={i}
                      style={{
                        color: line.startsWith('user@')       ? '#4ade80'
                             : line.startsWith('[AI AGENT]')  ? 'var(--accent)'
                             : line.startsWith('[ERROR]')     ? '#f87171'
                             : '#8b8fa8',
                        marginTop: line.startsWith('user@') || line.startsWith('[AI AGENT]') ? 6 : 0,
                        fontWeight: line.startsWith('[AI AGENT]') ? 600 : 400,
                        paddingLeft: line.startsWith('user@') || line.startsWith('[AI AGENT]') ? 0 : 16,
                        lineHeight: 1.7,
                      }}
                    >
                      {line}
                    </div>
                  ))}
                  <form onSubmit={handleTerminalSubmit} style={{ display: 'flex', alignItems: 'center', color: '#4ade80', marginTop: 6 }}>
                    <span style={{ marginRight: 10, userSelect: 'none', fontWeight: 600, whiteSpace: 'nowrap' }}>user@desktop:~/ai-editor$</span>
                    <input
                      id="term-input"
                      type="text"
                      value={termInput}
                      onChange={e => setTermInput(e.target.value)}
                      style={{
                        flex: 1, background: 'transparent', border: 'none', outline: 'none',
                        color: '#e8eaed', fontFamily: 'inherit', fontSize: 'inherit',
                        caretColor: 'var(--accent)',
                      }}
                      autoComplete="off"
                      spellCheck="false"
                    />
                  </form>
                  <div ref={terminalEndRef} />
                </div>
              )}

              {activeBottomTab === 'git' && (
                <div
                  style={{
                    height: '100%', display: 'flex', flexDirection: 'column',
                    padding: '12px 16px',
                    fontFamily: '"Geist Mono", "Fira Code", monospace',
                    fontSize: 12.5, color: '#93c5fd',
                    overflowY: 'auto', cursor: 'text',
                  }}
                  onClick={() => document.getElementById('git-input')?.focus()}
                >
                  {gitHistory.map((line, i) => (
                    <div
                      key={i}
                      style={{
                        color: line.includes('user@') ? '#93c5fd' : '#8b8fa8',
                        marginTop: line.includes('user@') ? 6 : 0,
                        paddingLeft: line.includes('user@') ? 0 : 16,
                        lineHeight: 1.7,
                      }}
                    >
                      {line}
                    </div>
                  ))}
                  <form onSubmit={handleGitSubmit} style={{ display: 'flex', alignItems: 'center', color: '#93c5fd', marginTop: 6 }}>
                    <span style={{ marginRight: 10, userSelect: 'none', fontWeight: 600, whiteSpace: 'nowrap' }}>user@desktop:~/ai-editor (main)$</span>
                    <input
                      id="git-input"
                      type="text"
                      value={gitInput}
                      onChange={e => setGitInput(e.target.value)}
                      style={{
                        flex: 1, background: 'transparent', border: 'none', outline: 'none',
                        color: '#e8eaed', fontFamily: 'inherit', fontSize: 'inherit',
                        caretColor: 'var(--accent)',
                      }}
                      autoComplete="off"
                      spellCheck="false"
                    />
                  </form>
                  <div ref={gitEndRef} />
                </div>
              )}

              {activeBottomTab === 'tester' && <TestingDashboard />}

            </div>
          </Panel>

        </PanelGroup>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.85); }
          50%       { opacity: 1;   transform: scale(1.1); }
        }
        @keyframes breathe {
          0%, 100% { opacity: 0.6; box-shadow: 0 0 8px #4ade80, 0 0 16px rgba(74,222,128,0.2); }
          50%      { opacity: 1;   box-shadow: 0 0 12px #4ade80, 0 0 24px rgba(74,222,128,0.35); }
        }
        @keyframes dropdownIn {
          0% { opacity: 0; transform: translateY(-6px) scale(0.98); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes cursor-blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
        ::-webkit-scrollbar-corner { background: transparent; }
        .sidebar-file-row:hover .delete-btn {
          display: flex !important;
          opacity: 1 !important;
        }
      `}</style>

      {/* New file dialog */}
      {showNewFile && (
        <NewFileDialog
          onConfirm={handleNewFile}
          onCancel={() => setShowNewFile(false)}
        />
      )}
    </div>
  );
}