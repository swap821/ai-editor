import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import { Terminal, Code, Play, Send, GitBranch, Network, Mic, FolderOpen, FileCode2, PanelLeftClose, PanelLeft, Check, X, Plus, Trash2, Sparkles, Bot, Activity } from "lucide-react";
import CodeCanvas from './components/CodeCanvas';
import LivePreview from './components/LivePreview';
import TestingDashboard from './components/TestingDashboard';
import MessageBubble from './components/MessageBubble';
import AlignmentPanel from './components/AlignmentPanel';
import AlignmentEvaluationPanel from './components/AlignmentEvaluationPanel';
import DiffView from './components/DiffView';
import ProposalsPanel from './components/ProposalsPanel';
import AmbientVoid from './components/AmbientVoid';
import { ErrorBoundary } from './components/ErrorBoundary';
import { API_BASE, API_HEADERS } from './config';
import { getSessionId } from './superbrain/lib/sessionId';
import { streamChatReply } from './lib/voiceChat';
import {
  clearConversationCorrection,
  correctConversationAlignment,
  restoreConversationSession,
} from './lib/conversation';
import { parseSseBuffer } from './lib/sse';
import { submitAlignmentFeedback } from './lib/alignmentEvaluation';
import './App.css';

/* ─── Premium Resize Handles ─────────────────────────────────────────── */
const ResizeHandle = () => (
  <PanelResizeHandle className="resize-handle group relative">
    <span className="absolute inset-y-0 -left-[2px] -right-[2px] group-hover:bg-blue-500/10 transition-colors duration-200" />
  </PanelResizeHandle>
);
const HorizontalResizeHandle = () => (
  <PanelResizeHandle className="resize-handle-horizontal w-full" />
);

/* ─── Model Dictionary ───────────────────────────────────────── */
// Cloud (Bedrock) models. The "Local (Ollama)" group is injected at runtime
// from whatever is actually installed in the local engine (see availableModels),
// so the list never claims a model you don't have pulled.
// Curated FALLBACK list of real, on-demand-invocable Bedrock model ids that
// support Converse tool-use (needed by the agent loop). The live picker prefers
// /api/v1/models/bedrock (the account's actual invocable models) and only falls
// back to this when discovery is unavailable. Nova is recommended: on-demand and
// broadly enabled by default. Claude/Llama use cross-region inference-profile ids
// ("us.*") and require model access to be granted in the Bedrock console.
const BEDROCK_MODELS = [
  {
    group: "Amazon Nova (recommended — on-demand + tool use)",
    models: [
      { id: "amazon.nova-pro-v1:0", name: "Nova Pro" },
      { id: "amazon.nova-lite-v1:0", name: "Nova Lite" },
      { id: "amazon.nova-micro-v1:0", name: "Nova Micro" }
    ]
  },
  {
    group: "Anthropic Claude (inference profiles)",
    models: [
      { id: "us.anthropic.claude-3-5-sonnet-20241022-v2:0", name: "Claude 3.5 Sonnet v2" },
      { id: "us.anthropic.claude-3-5-haiku-20241022-v1:0", name: "Claude 3.5 Haiku" },
      { id: "us.anthropic.claude-3-haiku-20240307-v1:0", name: "Claude 3 Haiku" }
    ]
  },
  {
    group: "Meta Llama (inference profiles)",
    models: [
      { id: "us.meta.llama3-1-70b-instruct-v1:0", name: "Llama 3.1 70B" },
      { id: "us.meta.llama3-1-8b-instruct-v1:0", name: "Llama 3.1 8B" }
    ]
  },
  {
    group: "Mistral / Cohere",
    models: [
      { id: "mistral.mistral-large-2407-v1:0", name: "Mistral Large 2" },
      { id: "cohere.command-r-plus-v1:0", name: "Command R+" }
    ]
  }
];

/* ─── File Icon Colour Map ───────────────────────────────────── */
const fileIconColor = { html: '#e8855d', css: '#64b5f6', js: '#f0db4f' };
const getExt = (name) => name.split('.').pop();

/* ─── Model Selector (2026 Standard) ───────────────────────── */
const PROVIDER_META = {
  "Agent (automatic)": { color: "#a855f7", icon: "✨", tags: ["Auto", "Smart"] },
  "Local (Ollama)": { color: "#34d399", icon: "⬡", tags: ["Offline", "Private"] },
  "Cloud (Bedrock)": { color: "#ff9900", icon: "☁", tags: ["AWS", "Cloud"] },
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
  "ollama.llama3.2:3b": ["Offline", "Fast", "3B"],
  "ollama.llama3.1:8b": ["Offline", "General", "8B"],
  "ollama.qwen2.5-coder": ["Offline", "Coding", "Local"],
  "ollama.qwen2.5-coder:7b": ["Coding", "Tool Use", "7B"],
  "ollama.qwen2.5-coder:3b": ["Coding", "Fast", "3B"],
  "ollama.qwen2.5:7b": ["General", "Tool Use", "7B"],
  "ollama.deepseek-r1:8b": ["Reasoning", "8B", "Local"],
  "ollama.mistral:7b": ["General", "Fallback", "7B"],
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

function inferModelTags(id) {
  const known = MODEL_TAGS[id];
  if (known) return known;
  if (!id.startsWith("ollama.")) return [];
  const lower = id.toLowerCase();
  const tags = ["Offline"];
  if (lower.includes("coder")) tags.push("Coding");
  else if (lower.includes("r1") || lower.includes("qwq")) tags.push("Reasoning");
  else tags.push("General");
  const size = lower.match(/:(\d+(?:\.\d+)?)b/);
  if (size) tags.push(`${size[1]}B`);
  return tags.slice(0, 3);
}

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
        inferModelTags(m.id).some(t => t.toLowerCase().includes(search.toLowerCase()))
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
    <div ref={containerRef} className="model-selector-root">
      {/* Trigger */}
      <button
        onClick={() => { if (!open) setHighlighted(0); setOpen(!open); }}
        className={open ? "model-selector-trigger is-open" : "model-selector-trigger"}
      >
        <div
          className="model-selector-icon"
          style={provider ? {
            '--ms-icon-bg': `${provider.color}18`,
            '--ms-icon-border': `${provider.color}30`,
            '--ms-icon-color': provider.color,
          } : undefined}
        >
          {provider?.icon || "◆"}
        </div>
        <div className="model-selector-label">
          <span className="model-selector-label-name">
            {current?.name || "Select Model"}
          </span>
          <span className="model-selector-label-group">
            {current?.group || "Model"}
          </span>
        </div>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" className={open ? "model-selector-dropdown-chevron is-open" : "model-selector-dropdown-chevron"}>
          <path d="M1 1L5 5L9 1" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="model-selector-dropdown">
          {/* Search */}
          <div className="model-selector-search">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="model-selector-search-icon">
              <circle cx="6" cy="6" r="5" stroke="var(--text-3)" strokeWidth="1.5"/>
              <path d="M10 10L13 13" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input
              ref={inputRef}
              value={search}
              onChange={e => { setSearch(e.target.value); setHighlighted(0); }}
              placeholder="Search models, providers, tags…"
              className="model-selector-search-input"
            />
            {search && (
              <button onClick={() => { setSearch(""); inputRef.current?.focus(); }} className="model-selector-search-clear-btn">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </button>
            )}
            <span className="model-selector-search-count">
              {flatList.length}
            </span>
          </div>

          {/* List */}
          <div ref={listRef} className="model-selector-list">
            {/* Recent Section */}
            {!search && recentModels.length > 0 && (
              <div className="model-selector-recent-section">
                <div className="model-selector-recent-header">
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
                <div className="model-selector-recent-divider" />
              </div>
            )}

            {/* Grouped Models */}
            {Object.entries(grouped).map(([group, items]) => {
              const meta = PROVIDER_META[group] || { color: "var(--text-3)", icon: "◆" };
              return (
                <div key={group} className="model-selector-group">
                  <div className="model-selector-group-header" style={{ '--mg-color': meta.color }}>
                    <span className="model-selector-group-header-icon">{meta.icon}</span>
                    <span className="model-selector-group-header-label">{group}</span>
                    <span className="model-selector-group-header-count">{items.length}</span>
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
              <div className="model-selector-empty">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="model-selector-empty-icon">
                  <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M21 21L16.65 16.65" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                No models match “{search}”
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="model-selector-footer">
            <span className="model-selector-footer-item">
              <kbd className="model-selector-kbd">↑↓</kbd>
              <span>Navigate</span>
            </span>
            <span className="model-selector-footer-item">
              <kbd className="model-selector-kbd">↵</kbd>
              <span>Select</span>
            </span>
            <span className="model-selector-footer-item">
              <kbd className="model-selector-kbd">esc</kbd>
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
  const tags = inferModelTags(model.id);
  const rowClasses = ["model-row"];
  if (isActive) rowClasses.push("is-active");
  if (isHighlighted && !isActive) rowClasses.push("is-highlighted");
  return (
    <button
      onClick={onClick}
      className={rowClasses.join(" ")}
    >
      <div
        className="model-row-indicator"
        style={{
          '--row-color': meta.color,
          '--row-glow': `${meta.color}80`,
        }}
      />
      <div className="model-row-content">
        <div className="model-row-name-row">
          <span className="model-row-name">
            {model.name}
          </span>
          {isActive && (
            <span className="model-row-active-badge">
              ACTIVE
            </span>
          )}
        </div>
        <div className="model-row-tags">
          {tags.slice(0, 3).map(tag => (
            <span key={tag} className="model-row-tag">
              {tag}
            </span>
          ))}
        </div>
      </div>
      {isActive && (
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="model-row-check">
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
    <div className="new-file-dialog-overlay" onClick={onCancel}>
      <div className="new-file-dialog-content" onClick={e => e.stopPropagation()}>
        <div className="new-file-dialog-title">New File</div>
        <form onSubmit={submit}>
          <input
            ref={inputRef}
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="filename.js"
            className="new-file-dialog-input"
          />
          <div className="new-file-dialog-actions">
            <button type="submit" className="new-file-dialog-btn-create">
              Create
            </button>
            <button type="button" onClick={onCancel} className="new-file-dialog-btn-cancel">
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
  // The code editor + live preview are hidden by default so the 3D void owns
  // that space; they slide in on demand (agent generates code, or the pill).
  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  // Honest greeting: makes NO backend-connection claim (the old "Amazon Bedrock
  // connected" was fabricated — it fired regardless of real provider state, a
  // data-true violation). The live provider/route is shown truthfully by the
  // active-brain badge from the real `route` SSE frame, not asserted here.
  const [messages, setMessages]        = useState([{ id: 1, sender: 'ai', text: 'AI-OS workspace ready. What shall we build today?', steps: [] }]);
  const [convHistory, setConvHistory]  = useState([]); // Bedrock-format conversation history
  const [alignmentFrame, setAlignmentFrame] = useState(null);
  const [correctionHistory, setCorrectionHistory] = useState([]);
  const [alignmentEvaluationRevision, setAlignmentEvaluationRevision] = useState(0);
  const [input, setInput]              = useState('');
  const [isStreaming, setIsStreaming]   = useState(false);
  // W2-3 honest send path: a transport/backend failure on the typed OR voice send
  // surfaces an inline banner, so a fetch that never reached the AI-OS is never a
  // silent "sent, nothing happened". null | { code, message, isNetworkError }.
  const [sendError, setSendError]       = useState(null);
  const sendErrorTimerRef = useRef(null);

  // Default to "Auto": the agent picks the best installed model — the user
  // doesn't have to. They can still override via the picker.
  const [selectedModel, setSelectedModel] = useState('auto');
  const [pendingAction, setPendingAction] = useState(null);
  const [, setApprovalTokens] = useState([]);
  // The shared session id (read-or-create-persist) — the SAME resolver the
  // superbrain adapter and the workbench organs use, so the classic face
  // continues the SAME backend conversation as the superbrain shell.
  const [sessionId] = useState(getSessionId);
  const [activeBottomTab, setActiveBottomTab] = useState('terminal');
  const [termHistory, setTermHistory] = useState(['AI Editor OS v2.0', 'Type "help" for available commands.']);
  const [termInput,   setTermInput]   = useState('');
  const [gitHistory,  setGitHistory]  = useState(['Git Bash integrated.', 'Type "git status" to begin.']);
  const [gitInput,    setGitInput]    = useState('');
  const [isListening, setIsListening] = useState(false);
  // Jarvis VOICE conversation (the mic): talk -> POST /api/v1/chat -> the mind
  // talks back via SpeechSynthesis. This is a CONVERSATION channel, separate from
  // the typed agentic forge (/api/generate): /api/v1/chat runs NO tools and has NO
  // approval mechanism, so a spoken word can never redeem an approval token.
  const [voiceLang, setVoiceLang] = useState('en-IN'); // en-IN | hi-IN (Hinglish)
  const [voiceSpeaking, setVoiceSpeaking] = useState(false); // TTS speaking now
  const [voiceBusy, setVoiceBusy] = useState(false);   // a voice turn is in flight
  const [voiceError, setVoiceError] = useState(null);  // honest mic/voice problem
  const [ollamaStatus, setOllamaStatus] = useState({ available: false, models: [] });
  const [bedrockStatus, setBedrockStatus] = useState({ configured: false, available: false, models: [] });
  const [autoModel, setAutoModel] = useState(null); // model the agent auto-selects (Auto badge)
  // The LIVE active brain for the current/last turn, from the backend `route` SSE
  // frame: {provider, model, privacy, task, auto}. Truthful per-turn routing (incl.
  // a cloud escalation), unlike the static pre-turn picker. null until a turn runs.
  const [activeBrain, setActiveBrain] = useState(null);

  const terminalEndRef  = useRef(null);
  const gitEndRef       = useRef(null);
  const recognitionRef  = useRef(null);
  const chatEndRef      = useRef(null);
  const sidebarPanelRef = useRef(null);
  const textareaRef     = useRef(null);

  useEffect(() => { terminalEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [termHistory]);
  useEffect(() => { gitEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [gitHistory]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  // Clear the send-error auto-dismiss timer on unmount (no dangling timeout).
  useEffect(() => () => { if (sendErrorTimerRef.current) clearTimeout(sendErrorTimerRef.current); }, []);

  useEffect(() => {
    let cancelled = false;
    restoreConversationSession(sessionId)
      .then(restored => {
        if (cancelled) return;
        if (restored.alignment) {
          setAlignmentFrame(current => current || restored.alignment);
        }
        setCorrectionHistory(restored.correctionHistory);
        if (restored.history.length > 0) {
          setConvHistory(current => current.length > 0 ? current : restored.history);
          setMessages(current => current.length > 1 ? current : restored.messages);
        }
      })
      .catch(() => {
        // A fresh or temporarily unavailable session is a normal startup state.
      });
    return () => { cancelled = true; };
  }, [sessionId]);

  // Probe both engines for available models. Runs on mount and on window focus,
  // so a model pulled locally or enabled in Bedrock shows up without a refresh.
  useEffect(() => {
    const probeLocal = () => fetch(`${API_BASE}/api/v1/models/local`, { headers: API_HEADERS })
      .then(r => r.json())
      .then(s => setOllamaStatus(s))
      .catch(() => setOllamaStatus({ available: false, models: [] }));
    const probeBedrock = () => fetch(`${API_BASE}/api/v1/models/bedrock`, { headers: API_HEADERS })
      .then(r => r.json())
      .then(s => setBedrockStatus(s))
      .catch(() => setBedrockStatus({ configured: false, available: false, models: [] }));
    // Ask the backend which model the agent would auto-select right now.
    const probeAuto = () => fetch(`${API_BASE}/api/v1/models/auto`, { headers: API_HEADERS })
      .then(r => r.json())
      .then(s => setAutoModel(s.available ? s.model : null))
      .catch(() => setAutoModel(null));
    const probe = () => { probeLocal(); probeBedrock(); probeAuto(); };
    probe();
    window.addEventListener('focus', probe);
    return () => window.removeEventListener('focus', probe);
  }, []);

  // Build the selector list: a dynamic "Local (Ollama)" group (installed chat
  // models) + a "Cloud (Bedrock)" group of the models this AWS account can
  // actually invoke. Falls back to the curated static cloud list when Bedrock
  // discovery is unavailable, so the dropdown is never empty.
  const availableModels = useMemo(() => {
    const chatModels = (ollamaStatus.models || []).filter(m => !/embed/i.test(m));
    const localGroup = chatModels.length
      ? [{ group: 'Local (Ollama)', models: chatModels.map(m => ({ id: `ollama.${m}`, name: m })) }]
      : [];
    const bedrockModels = bedrockStatus.models || [];
    const cloudGroups = bedrockModels.length
      ? [{ group: 'Cloud (Bedrock)', models: bedrockModels.map(m => ({ id: m.id, name: m.name })) }]
      : (bedrockStatus.configured ? BEDROCK_MODELS : []);
    // The agent auto-picks the best installed model — surfaced as the default
    // "Auto" entry (only when there are local models to choose among).
    const autoGroup = chatModels.length
      ? [{ group: 'Agent (automatic)', models: [{ id: 'auto', name: autoModel ? `Auto · ${autoModel}` : 'Auto — best installed' }] }]
      : [];
    return [...autoGroup, ...localGroup, ...cloudGroups];
  }, [ollamaStatus, bedrockStatus, autoModel]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return; // unsupported -> the mic surfaces a text-only hint
    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.interimResults = false; // act on the FINAL transcript (one spoken turn)
    rec.onstart = () => setIsListening(true);
    rec.onend = () => setIsListening(false);
    recognitionRef.current = rec;
    // onresult / onerror / lang are (re)assigned per start in startVoiceListening
    // so each turn captures the current language + a fresh handler closure.
  }, []);

  /* ─── Handlers ─────────────────────────────────────────────── */
  const appendTerminalLines = (target, lines) => {
    const append = prev => [...prev, ...lines];
    if (target === 'git') setGitHistory(append);
    else setTermHistory(append);
  };

  const runTerminalCommand = async (cmd, target) => {
    const res = await fetch(`${API_BASE}/api/terminal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...API_HEADERS },
      body: JSON.stringify({ command: cmd, sessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
    appendTerminalLines(target, data.output.split('\n').filter(l => l.length > 0));
    if (data.requiresApproval && data.approvalToken) {
      setPendingAction({
        source: 'terminal',
        terminalTarget: target,
        approvalToken: data.approvalToken,
        commands: [cmd],
        explanation: 'This terminal command requires explicit approval before it can run.',
      });
    }
  };

  const handleTerminalSubmit = async (e) => {
    e.preventDefault();
    if (!termInput.trim()) return;
    const cmd = termInput.trim();
    setTermHistory(prev => [...prev, `user@desktop:~/ai-editor$ ${cmd}`]);
    setTermInput('');
    if (cmd.toLowerCase() === 'clear') return setTermHistory([]);
    try {
      await runTerminalCommand(cmd, 'terminal');
    } catch (err) {
      setTermHistory(prev => [...prev, `Error: ${err.message}`]);
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
      await runTerminalCommand(cmd, 'git');
    } catch (err) {
      setGitHistory(prev => [...prev, `Error: ${err.message}`]);
    }
  };

  /* ─── Stream one agent turn over SSE ────────────────────────── */
  // Extracted so it can be invoked both for a fresh user message and to *resume*
  // a turn that paused for YELLOW approval. `historyMessages` already includes
  // the user turn; the paused assistant turn is never recorded (no `done`), so
  // resuming simply replays the same history with the approved command(s) now
  // whitelisted in `approvedCmds`.
  // W2-3: surface a send/transport failure as an inline banner (auto-dismiss), so a
  // turn that never reached the AI-OS is honest, never a silent "sent, nothing
  // happened". The error is ALSO kept in the chat bubble (below) for context.
  const surfaceSendError = useCallback((err) => {
    setSendError(err);
    if (sendErrorTimerRef.current) clearTimeout(sendErrorTimerRef.current);
    sendErrorTimerRef.current = setTimeout(() => setSendError(null), 6000);
  }, []);

  const streamGenerate = async (historyMessages, tokens = [], onError = null) => {
    const aiMsgId = Date.now() + 1;
    setMessages(prev => [...prev, { id: aiMsgId, sender: 'ai', text: '', loading: true, steps: [], streaming: false }]);
    setIsStreaming(true);
    setActiveBrain(null); // the new turn announces its brain via the `route` frame

    let accText = '';
    let accSteps = [];

    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ messages: historyMessages, modelId: selectedModel, sessionId, approvalTokens: tokens })
      });

      if (!response.ok) {
        // The POST reached the server but it answered not-ok — surface the code so
        // the operator sees the truth (a 5xx is a backend error, retryable).
        onError?.({ code: response.status, message: `Send failed: HTTP ${response.status}.`, isNetworkError: false });
        throw new Error(`Server error ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processEvent = (eventType, rawData) => {
        let data;
        try { data = JSON.parse(rawData); } catch { return; }

        if (eventType === 'route') {
          // The active brain for this turn: which provider/model served it and
          // whether it stayed local. Drives the live header badge.
          setActiveBrain(data);
        } else if (eventType === 'alignment') {
          setAlignmentFrame(data);
        } else if (eventType === 'step') {
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
          // Fenced code is part of the answer, not authority to overwrite the
          // currently selected virtual editor file.
        } else if (eventType === 'earned_autonomy') {
          // The brain applied a write on its OWN earned trust — a YELLOW action
          // class that graduated by repeated verified success, so it ran with no
          // human pause (still gateway-gated + audited as a distinct chain entry).
          // The classic UI never handled this frame; surface it honestly as a
          // settled step rather than silently dropping it (the superbrain shows
          // the same event as "AUTONOMOUS ACTION").
          const what = data.command || data.filepath || 'a write';
          accSteps = [...accSteps, {
            id: `earned-${Date.now()}`,
            type: 'tool_result',
            tool: 'earned_autonomy',
            output: `AUTONOMOUS ACTION (earned trust): ${what}`,
          }];
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, steps: accSteps, loading: false } : m
          ));
        } else if (eventType === 'done') {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: accText || 'Done.', loading: false, streaming: false, settled: true } : m
          ));
          if (accText) {
            setConvHistory(prev => [...prev, { role: 'assistant', content: [{ text: accText }] }]);
          }
          setIsStreaming(false);
        } else if (eventType === 'human_required') {
          setPendingAction(data.input);
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: data.text || 'Authorization required.', loading: false, streaming: false, settled: true, steps: accSteps } : m
          ));
          setIsStreaming(false);
        } else if (eventType === 'error') {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, text: `Error: ${data.text}`, loading: false, streaming: false, settled: true } : m
          ));
          setIsStreaming(false);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const { frames, rest } = parseSseBuffer(buffer);
        buffer = rest;
        for (const frame of frames) processEvent(frame.event, frame.data);
      }
    } catch (err) {
      // A network-layer throw (failed to fetch / aborted) vs a parse/other error.
      // (A not-ok response already called onError above; calling again here is
      // harmless and keeps the single most-recent error shown.)
      const isNetworkError = err?.name === 'TypeError' || err?.name === 'AbortError';
      onError?.({
        code: isNetworkError ? 'NETWORK_ERROR' : 'SEND_ERROR',
        message: err?.message || 'Send failed. Check your connection.',
        isNetworkError,
      });
      // STILL surface the error in the chat bubble so the failed turn persists in
      // context — the banner is the loud signal, the bubble is the record.
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId ? { ...m, text: `Error: ${err.message}`, loading: false, streaming: false } : m
      ));
      setIsStreaming(false);
    }
  };

  const handleApproveAction = async () => {
    if (!pendingAction || isStreaming) return;
    if (pendingAction.source === 'terminal') {
      const action = pendingAction;
      setIsStreaming(true);
      try {
        const response = await fetch(`${API_BASE}/api/v1/approval/req`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...API_HEADERS },
          body: JSON.stringify({
            approvalToken: action.approvalToken,
            sessionId,
            approve: true,
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `Server error ${response.status}`);
        const result = data.result || {};
        const output = `${result.stdout || ''}${result.stderr || ''}`.trim()
          || `[${result.status || 'OK'}] ${result.reason || '(no output)'}`;
        appendTerminalLines(action.terminalTarget, output.split('\n'));
        setPendingAction(null);
      } catch (err) {
        appendTerminalLines(action.terminalTarget, [`Error: ${err.message}`]);
      } finally {
        setIsStreaming(false);
      }
      return;
    }
    const commandsToRun = pendingAction.commands || [];
    const editsToApply = pendingAction.edits || [];
    const creationsToApply = pendingAction.creations || [];
    const token = pendingAction.approvalToken;
    if (!token) return;
    const newTokens = [token];
    setApprovalTokens(newTokens);
    setPendingAction(null);
    const approvedSummary = creationsToApply.length
      ? `${creationsToApply.length} new file(s)`
      : editsToApply.length
        ? `${editsToApply.length} file edit(s)`
        : `${commandsToRun.length} command(s)`;
    setMessages(prev => [...prev, {
      id: Date.now(), sender: 'ai', steps: [],
      text: `✅ Approved — resuming with ${approvedSummary} authorised…`,
    }]);
    await streamGenerate(convHistory, newTokens, surfaceSendError);
  };

  const handleRejectAction = async () => {
    if (!pendingAction) return;
    const action = pendingAction;
    try {
      const response = await fetch(`${API_BASE}/api/v1/approval/req`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ approvalToken: action.approvalToken, sessionId, approve: false }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Server error ${response.status}`);
      setApprovalTokens([]);
      setPendingAction(null);
      if (action.source === 'terminal') {
        appendTerminalLines(action.terminalTarget, ['[REJECTED] Command was not run.']);
      } else {
        setMessages(prev => [...prev, { id: Date.now(), sender: 'user', text: 'Rejected - the action was not run.' }]);
      }
    } catch (err) {
      if (action.source === 'terminal') {
        appendTerminalLines(action.terminalTarget, [`Error: Could not record rejection: ${err.message}`]);
      } else {
        setMessages(prev => [...prev, { id: Date.now(), sender: 'ai', text: `Error: Could not record rejection: ${err.message}` }]);
      }
    }
  };

  /* Speak the mind's reply back (SpeechSynthesis). Honest + non-blocking: if the
   * browser has no TTS we simply stay silent (the reply is still on screen). */
  const speakReply = (text) => {
    const synth = typeof window !== 'undefined' ? window.speechSynthesis : null;
    if (!synth || !text) return;
    try {
      synth.cancel(); // never stack utterances
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = voiceLang;
      utter.onstart = () => setVoiceSpeaking(true);
      utter.onend = () => setVoiceSpeaking(false);
      utter.onerror = () => setVoiceSpeaking(false);
      synth.speak(utter);
    } catch {
      setVoiceSpeaking(false);
    }
  };

  /* One spoken conversational turn: the transcript goes to the CONVERSATIONAL
   * /api/v1/chat (NOT the agentic forge), the reply streams into a chat bubble,
   * then the mind speaks it back. A spoken turn can never approve anything — this
   * endpoint has no tools and no approval mechanism. */
  const handleVoiceTurn = async (transcript) => {
    const text = transcript.trim();
    if (!text || voiceBusy || isStreaming || pendingAction) return;
    setVoiceBusy(true);
    setVoiceError(null);
    const userMsgId = Date.now();
    const aiMsgId = userMsgId + 1;
    setMessages(prev => [
      ...prev,
      { id: userMsgId, sender: 'user', text, voice: true, steps: [] },
      { id: aiMsgId, sender: 'ai', text: '', loading: true, voice: true, steps: [] },
    ]);
    try {
      const reply = await streamChatReply(text, sessionId, {
        onChunk: (r) => setMessages(prev => prev.map(m =>
          m.id === aiMsgId ? { ...m, text: r, loading: false } : m)),
      });
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId ? { ...m, text: reply, loading: false } : m));
      speakReply(reply);
    } catch (err) {
      // Honest, never silent (W2-3): the failed reply stays in the bubble AND the
      // inline send-error banner fires, so a voice turn that never reached the
      // AI-OS is loud. streamChatReply already throws with the status / detail.
      surfaceSendError({
        code: 'VOICE_SEND_ERROR',
        message: `Voice send failed: ${err?.message || 'AI-OS unreachable'}.`,
        isNetworkError: err?.name === 'TypeError' || err?.name === 'AbortError',
      });
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId
          ? { ...m, text: `Voice link issue: ${err.message}. You can type instead.`, loading: false, error: true }
          : m));
    } finally {
      setVoiceBusy(false);
    }
  };

  /* Start listening for one push-to-talk turn. Handlers are assigned here (not at
   * mount) so each turn uses the current language and a fresh closure, and every
   * error path is honest: mic-denied, no-speech, and generic input errors each
   * say what happened and that typing still works. */
  const startVoiceListening = () => {
    const rec = recognitionRef.current;
    if (!rec) {
      setVoiceError('Voice input is not supported in this browser. Type your message instead.');
      return;
    }
    if (voiceBusy || isStreaming || pendingAction) return;
    rec.lang = voiceLang;
    rec.onresult = (e) => {
      let finalText = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
      }
      if (finalText) handleVoiceTurn(finalText);
    };
    rec.onerror = (e) => {
      setIsListening(false);
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        setVoiceError('Microphone access was denied. Allow it in your browser to talk, or type instead.');
      } else if (e.error === 'no-speech') {
        setVoiceError('No speech heard. Tap the mic and try again.');
      } else if (e.error !== 'aborted') {
        setVoiceError(`Voice input error (${e.error}). You can type instead.`);
      }
    };
    try {
      setVoiceError(null);
      rec.start();
    } catch {
      /* start() throws if already running; the toggle below avoids that */
    }
  };

  const toggleVoice = () => {
    if (!recognitionRef.current) {
      setVoiceError('Voice input is not supported in this browser. Type your message instead.');
      return;
    }
    if (isListening) recognitionRef.current.stop();
    else startVoiceListening();
  };

  /* Cycle the spoken language: Indian English <-> Hindi (both handle Hinglish). */
  const cycleVoiceLang = () => setVoiceLang(prev => (prev === 'en-IN' ? 'hi-IN' : 'en-IN'));

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
    setAlignmentFrame(null);
    setSendError(null); // clear any prior send error on a fresh turn
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

    // A fresh request starts with a clean approval whitelist, then streams the
    // turn (which pauses for human approval if it hits a YELLOW command). A
    // transport/backend failure surfaces an inline banner (W2-3) — never silent.
    setApprovalTokens([]);
    await streamGenerate(newHistory, [], surfaceSendError);
  };

  const handleCorrectAlignment = async (corrections) => {
    const result = await correctConversationAlignment(sessionId, corrections);
    setAlignmentFrame(result.alignment);
    setCorrectionHistory(result.correctionHistory);
  };

  const handleClearAlignmentCorrection = async () => {
    const result = await clearConversationCorrection(sessionId);
    setAlignmentFrame(result.alignment);
    setCorrectionHistory(result.correctionHistory);
  };

  const handleAlignmentFeedback = async (feedback) => {
    await submitAlignmentFeedback(sessionId, {
      observationId: alignmentFrame?.evaluation?.observation_id,
      ...feedback,
    });
    setAlignmentEvaluationRevision(value => value + 1);
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
    <ErrorBoundary name="App">
    <div
      className="app-root h-screen w-screen flex flex-col select-none overflow-hidden"
    >
      <AmbientVoid energy={isStreaming ? 1 : 0.15} />

      {/* ══ TITLE BAR ══════════════════════════════════════════ */}
      <header className="app-header-root h-11 shrink-0 flex items-center justify-between px-4">
        {/* Left cluster */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5">
            <div className="app-header-logo w-6 h-6 rounded-md flex items-center justify-center shadow-lg">
              <Code size={13} color="#fff" strokeWidth={2.5} />
            </div>
            <span className="app-header-title">
              AI Orchestrator
            </span>
            <span className="app-header-badge">
              Enterprise
            </span>
          </div>

          <div className="app-header-divider" />

          <button
            onClick={() => {
              if (sidebarOpen) {
                sidebarPanelRef.current?.collapse();
              } else {
                sidebarPanelRef.current?.expand();
              }
            }}
            className="sidebar-toggle-btn transition-all duration-200"
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

          {/* Active-brain indicator — the LIVE per-turn route when available,
              else the static pre-turn pick. */}
          {(() => {
            // LIVE: the brain that actually served the current/last turn. Truthful
            // even when `auto` escalated to a cloud provider for this task.
            if (activeBrain && activeBrain.model) {
              const isLocal = activeBrain.privacy === 'local';
              const color = isLocal
                ? '#34d399'
                : (activeBrain.provider === 'gemini' ? '#4285f4'
                    : activeBrain.provider === 'bedrock' ? '#ff9900' : '#60a5fa');
              const label = `${activeBrain.model} · ${String(activeBrain.privacy || '').toUpperCase()}`
                + (activeBrain.auto ? ' · auto' : '');
              return (
                <div
                  className="brain-indicator flex items-center gap-2 px-3 py-1.5 rounded-lg"
                  title={`Active brain: ${activeBrain.provider} · ${activeBrain.model}`
                    + ` (${activeBrain.privacy}${activeBrain.auto ? ', auto-routed' : ''})`}
                  style={{
                    '--brain-color': color,
                    '--brain-bg': `${color}10`,
                    '--brain-border': `${color}28`,
                    '--brain-shadow': `${color}10`,
                  }}
                >
                  <span className="brain-indicator-pulse" />
                  {label}
                </div>
              );
            }
            const isAuto = selectedModel === 'auto';
            const local = isAuto || selectedModel.startsWith('ollama.');
            const tag = isAuto ? (autoModel || '') : selectedModel.replace(/^ollama\./, '');
            const ready = local && ollamaStatus.available &&
              (isAuto ? !!autoModel
                      : ollamaStatus.models.some(m => m === tag || m.startsWith(tag + ':')));
            const color = local ? (ollamaStatus.available ? '#34d399' : '#fbbf24') : '#60a5fa';
            const label = isAuto
              ? (ollamaStatus.available ? (autoModel ? `Auto · ${tag}` : 'Auto · picking…') : 'Local · offline')
              : (local
                  ? (ollamaStatus.available ? (ready ? 'Local · ready' : 'Local · not pulled') : 'Local · offline')
                  : 'Cloud');
            return (
              <div
                className="brain-indicator flex items-center gap-2 px-3 py-1.5 rounded-lg"
                title={isAuto
                  ? (autoModel ? `Agent auto-selected ${tag} (best installed model)` : 'The agent will pick the best installed model when you send a message.')
                  : (local
                      ? (ollamaStatus.available
                          ? (ready ? `Running offline on ${tag}` : `Ollama is up, but "${tag}" isn't pulled. Run: ollama pull ${tag}`)
                          : 'Ollama not reachable on :11434. Start it to run offline.')
                      : 'Inference runs on Amazon Bedrock (cloud).')}
                style={{
                  '--brain-color': color,
                  '--brain-bg': `${color}10`,
                  '--brain-border': `${color}28`,
                  '--brain-shadow': `${color}10`,
                }}
              >
                <span className="brain-indicator-pulse" />
                {label}
              </div>
            );
          })()}

          <div className="gateway-indicator flex items-center gap-2 px-3 py-1.5 rounded-lg">
            <span className="gateway-indicator-pulse" />
            Secure Gateway
          </div>
        </div>
      </header>

      {/* ══ MAIN BODY ══════════════════════════════════════════ */}
      {/* Padding leaves a margin of the 3D void around the workspace, and the
          PanelGroup is a rounded, shadowed "slab" floating in that space. */}
      <div className="app-body flex-1 overflow-hidden">
        <PanelGroup
          orientation="vertical"
          className="app-slab"
        >

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
                className="sidebar-panel"
              >
                <div className="sidebar-header">
                  <FolderOpen size={11} className="sidebar-header-icon" />
                  <span className="sidebar-header-label">Explorer</span>
                  <button
                    onClick={() => setShowNewFile(true)}
                    title="New file"
                    className="new-file-btn"
                  >
                    <Plus size={13} />
                  </button>
                </div>

                <div className="sidebar-tree">
                  <div className="sidebar-project-row">
                    <FolderOpen size={13} className="sidebar-project-icon" />
                    my-ai-project
                  </div>

                  {Object.keys(files).map(filename => {
                    const ext    = getExt(filename);
                    const color  = fileIconColor[ext] || '#8b8fa8';
                    const active = activeFile === filename;
                    const canDelete = Object.keys(files).length > 1;
                    return (
                      <div key={filename} className="sidebar-file-row">
                        <button
                          onClick={() => setActiveFile(filename)}
                          className={active ? "file-tab-btn is-active" : "file-tab-btn"}
                        >
                          {active && (
                            <span className="file-tab-active-indicator" />
                          )}
                          <FileCode2 size={12} className="file-tab-icon" style={{ '--file-icon-color': color }} />
                          <span className="file-tab-name">
                            {filename}
                          </span>
                        </button>
                        {canDelete && (
                          <button
                            onClick={() => handleDeleteFile(filename)}
                            title={`Delete ${filename}`}
                            className="file-delete-btn"
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
                className={`ai-panel-root ai-aura${isStreaming ? ' is-generating' : ''}`}
              >
                {/* Header */}
                <div className="ai-panel-header">
                  <Bot size={12} className="ai-panel-header-icon" />
                  AI Agent
                  {isStreaming && (
                    <span className="ai-working-badge">
                      Working
                    </span>
                  )}
                  <span className="ai-panel-turns">
                    {convHistory.length > 0 && `${Math.ceil(convHistory.length / 2)} turn${convHistory.length > 2 ? 's' : ''}`}
                  </span>
                </div>

                <AlignmentPanel
                  key={alignmentFrame?.evaluation?.observation_id || 'alignment-frame'}
                  frame={alignmentFrame}
                  correctionHistory={correctionHistory}
                  onCorrect={handleCorrectAlignment}
                  onClearCorrection={handleClearAlignmentCorrection}
                  onFeedback={handleAlignmentFeedback}
                />

                {/* Messages */}
                {/* Soft top fade (mask) so messages dissolve under the header as they scroll. */}
                <div className="messages-area">
                  {messages.map(msg => (
                    <MessageBubble key={msg.id} msg={msg} />
                  ))}

                  <div ref={chatEndRef} />
                </div>

                {/* Pinned approval bar — lives OUTSIDE the scrollable message
                    list (as a flex-shrink-0 sibling above the composer) so its
                    Run / Reject controls are ALWAYS fully visible and can never
                    be clipped below the fold, regardless of scroll position. */}
                {pendingAction && (
                  <div className="approval-bar">
                    {/* sweeping top accent */}
                    <div className="approval-bar-sweep">
                      <div className="approval-bar-sweep-inner" />
                    </div>

                    {/* header */}
                    <div className="approval-bar-header">
                      <span className="approval-icon">⚠</span>
                      <span className="approval-title">
                        Security approval required
                      </span>
                      <span className="approval-status-badge">Yellow</span>
                    </div>

                    {/* explanation */}
                    {pendingAction.explanation && (
                      <p className="approval-explanation">
                        {pendingAction.explanation}
                      </p>
                    )}

                    {/* the unified diff (file edit) or the command(s) to authorise */}
                    {pendingAction.diff ? (
                      <DiffView diff={pendingAction.diff} />
                    ) : (
                      <div className="approval-command-block">
                        {(pendingAction.commands || []).map((cmd, i) => (
                          <div key={i} className="approval-command-row">
                            <span className="approval-command-prompt">$</span>
                            <span className="approval-command-text">{cmd}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* actions */}
                    <div className="approval-actions">
                      <button
                        onClick={handleApproveAction}
                        className="approval-btn-approve"
                      >
                        <Check size={14} strokeWidth={2.8} /> {pendingAction.creations ? 'Create file' : pendingAction.diff ? 'Apply edit' : 'Run command'}
                      </button>
                      <button
                        onClick={handleRejectAction}
                        className="approval-btn-reject"
                      >
                        <X size={14} strokeWidth={2.8} /> Reject
                      </button>
                    </div>
                  </div>
                )}

                {/* Input area */}
                <div className="input-area">
                  {/* Suggested prompts — shown when input is empty and not streaming */}
                  {!input && !isStreaming && !pendingAction && messages.length <= 1 && (
                    <div className="suggested-prompts">
                      {SUGGESTED_PROMPTS.map((p, i) => (
                        <button
                          key={i}
                          onClick={() => setInput(p.text)}
                          className="suggested-prompt-btn"
                        >
                          <span>{p.icon}</span>
                          <span className="suggested-prompt-text">{p.text.split(' ').slice(0, 4).join(' ')}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Honest voice status / error line (aria-live for AT). */}
                  {(voiceError || isListening || voiceBusy || voiceSpeaking) && (
                    <div
                      role="status"
                      aria-live="polite"
                      className={voiceError ? "voice-status is-error" : "voice-status"}
                    >
                      {voiceError
                        ? voiceError
                        : isListening
                        ? `Listening (${voiceLang === 'hi-IN' ? 'Hindi' : 'Indian English'})…`
                        : voiceBusy
                        ? 'Jarvis is thinking…'
                        : voiceSpeaking
                        ? 'Jarvis is speaking…'
                        : null}
                    </div>
                  )}

                  {/* W2-3 · honest send-error banner. A typed OR voice send that fails
                      to reach the AI-OS surfaces HERE inline (assertive aria-live), so a
                      turn is never a silent "sent, nothing happened". Auto-dismisses (6s)
                      and is operator-dismissable. No animation (reduced-motion-safe). */}
                  {sendError && (
                    <div
                      role="alert"
                      aria-live="assertive"
                      className="send-error-banner"
                    >
                      <span aria-hidden="true" className="send-error-icon">⚠</span>
                      <div className="send-error-text">
                        {sendError.message}
                        {sendError.isNetworkError && ' Check your connection.'}
                        {typeof sendError.code === 'number' && sendError.code >= 500 && ' Server error — try again.'}
                      </div>
                      <button
                        type="button"
                        onClick={() => setSendError(null)}
                        aria-label="Dismiss error"
                        className="send-error-dismiss"
                      >
                        ✕
                      </button>
                    </div>
                  )}

                  <div className="input-controls-row">
                    {/* Voice (talk to Jarvis) button — push to talk; the mind talks back. */}
                    <button
                      type="button"
                      onClick={toggleVoice}
                      aria-label={isListening ? 'Stop listening' : 'Talk to Jarvis (voice)'}
                      aria-pressed={isListening}
                      title="Talk to Jarvis — speak, and the mind replies aloud"
                      className={`voice-btn${isListening ? ' is-listening' : voiceSpeaking ? ' is-speaking' : ''}`}
                    >
                      <Mic size={14} className={isListening ? 'voice-mic-icon-listening' : undefined} />
                    </button>

                    {/* Spoken-language toggle: Indian English <-> Hindi (Hinglish). */}
                    <button
                      type="button"
                      onClick={cycleVoiceLang}
                      aria-label={`Voice language: ${voiceLang === 'hi-IN' ? 'Hindi' : 'Indian English'} (tap to switch)`}
                      title="Switch spoken language (EN-IN / HI-IN)"
                      className="voice-lang-btn"
                    >
                      {voiceLang === 'hi-IN' ? 'HI' : 'EN'}
                    </button>

                    {/* Auto-expanding textarea */}
                    <div className="textarea-wrapper">
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
                        className={(pendingAction || isStreaming) ? "textarea-input is-disabled" : "textarea-input"}
                      />
                      {input && (
                        <div className="textarea-hint">
                          ↵ send · ⇧↵ newline
                        </div>
                      )}
                    </div>

                    {/* Send button */}
                    <button
                      type="button"
                      onClick={handleSendMessage}
                      disabled={!input.trim() || !!pendingAction || isStreaming}
                      className={(!input.trim() || pendingAction || isStreaming) ? "send-btn is-disabled" : "send-btn"}
                    >
                      {isStreaming
                        ? <Sparkles size={14} className="send-btn-icon-streaming" />
                        : <Send size={14} strokeWidth={2.5} />
                      }
                    </button>
                  </div>
                </div>
              </Panel>

              <ResizeHandle />

              {/* ── WORKSPACE (code editor + live preview) ──────────────────
                  Hidden by default so the 3D void owns this space. Summoned on
                  demand — the agent opens it when it generates code, or click the
                  "Open workspace" pill — and slides in. */}
              <Panel
                defaultSize={60} minSize={20}
                className="workspace-panel"
              >
                {workspaceOpen ? (
                  <div className="workspace-in workspace-inner">
                    {/* Code editor */}
                    <div className="editor-container">
                      <div className="workspace-tab-bar">
                        {Object.keys(files).map(filename => {
                          const ext    = getExt(filename);
                          const color  = fileIconColor[ext] || '#8b8fa8';
                          const active = activeFile === filename;
                          return (
                            <button
                              key={filename}
                              onClick={() => setActiveFile(filename)}
                              className={active ? "workspace-tab-btn is-active" : "workspace-tab-btn"}
                            >
                              <FileCode2 size={12} className="workspace-tab-icon" style={{ '--file-icon-color': color }} />
                              {filename}
                            </button>
                          );
                        })}
                        <button
                          onClick={() => setWorkspaceOpen(false)}
                          title="Hide workspace"
                          className="workspace-hide-btn"
                        >
                          <X size={13} /> Hide
                        </button>
                      </div>
                      <div className="editor-canvas-wrap">
                        <CodeCanvas
                          code={files[activeFile].content}
                          onChange={newCode => setFiles(prev => ({ ...prev, [activeFile]: { ...prev[activeFile], content: newCode } }))}
                          language={files[activeFile].language}
                        />
                      </div>
                    </div>
                    {/* Live preview */}
                    <div className="preview-container">
                      <div className="preview-header">
                        <span className="preview-window-control is-red" />
                        <span className="preview-window-control is-yellow" />
                        <span className="preview-window-control is-green" />
                        <div className="preview-url-bar">
                          preview://localhost
                        </div>
                        <Play size={12} className="preview-play-icon" />
                      </div>
                      <div className="preview-canvas-wrap">
                        <LivePreview files={files} />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="workspace-placeholder">
                    <button
                      onClick={() => setWorkspaceOpen(true)}
                      className="open-workspace-btn"
                    >
                      <Code size={14} /> Open workspace
                    </button>
                  </div>
                )}
              </Panel>

            </PanelGroup>
          </Panel>

          <HorizontalResizeHandle />

          {/* ══ BOTTOM DRAWER ══════════════════════════════════ */}
          <Panel
            defaultSize={30} minSize={10} collapsible
            className="bottom-drawer"
          >
            <div className="bottom-tab-bar">
              {[
                { id: 'terminal', icon: <Terminal size={13} />, label: 'Terminal' },
                { id: 'git',      icon: <GitBranch size={13} />, label: 'Git Bash' },
                { id: 'tester',   icon: <Network size={13} />,  label: 'API & Test Hub' },
                { id: 'alignment-evaluation', icon: <Activity size={13} />, label: 'Alignment Eval' },
                { id: 'self-analysis', icon: <Sparkles size={13} />, label: 'Self-Analysis' },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveBottomTab(tab.id)}
                  className={activeBottomTab === tab.id ? "bottom-tab-btn is-active" : "bottom-tab-btn"}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="bottom-content">

              {activeBottomTab === 'terminal' && (
                <div
                  className="terminal-view"
                  onClick={() => document.getElementById('term-input').focus()}
                >
                  {termHistory.map((line, i) => {
                    let lineClass = "terminal-line";
                    if (line.startsWith('user@')) lineClass += " is-user";
                    else if (line.startsWith('[AI AGENT]')) lineClass += " is-agent";
                    else if (line.startsWith('[ERROR]')) lineClass += " is-error";
                    return (
                      <div key={i} className={lineClass}>
                        {line}
                      </div>
                    );
                  })}
                  <form onSubmit={handleTerminalSubmit} className="terminal-prompt">
                    <span className="terminal-prompt-label">user@desktop:~/ai-editor$</span>
                    <input
                      id="term-input"
                      type="text"
                      value={termInput}
                      onChange={e => setTermInput(e.target.value)}
                      className="terminal-input"
                      autoComplete="off"
                      spellCheck="false"
                    />
                  </form>
                  <div ref={terminalEndRef} />
                </div>
              )}

              {activeBottomTab === 'git' && (
                <div
                  className="git-view"
                  onClick={() => document.getElementById('git-input')?.focus()}
                >
                  {gitHistory.map((line, i) => (
                    <div
                      key={i}
                      className={line.includes('user@') ? "git-line is-user" : "git-line"}
                    >
                      {line}
                    </div>
                  ))}
                  <form onSubmit={handleGitSubmit} className="git-prompt">
                    <span className="git-prompt-label">user@desktop:~/ai-editor (main)$</span>
                    <input
                      id="git-input"
                      type="text"
                      value={gitInput}
                      onChange={e => setGitInput(e.target.value)}
                      className="git-input"
                      autoComplete="off"
                      spellCheck="false"
                    />
                  </form>
                  <div ref={gitEndRef} />
                </div>
              )}

              {activeBottomTab === 'tester' && <TestingDashboard />}

              {activeBottomTab === 'alignment-evaluation' && (
                <AlignmentEvaluationPanel refreshKey={alignmentEvaluationRevision} />
              )}

              {activeBottomTab === 'self-analysis' && <ProposalsPanel />}

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
        .sidebar-file-row:hover .file-delete-btn {
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
    </ErrorBoundary>
  );
}
