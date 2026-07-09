# GAGOS v10 Frontend — Master Prompt for Google Antigravity
> **Paste this ENTIRE prompt into Antigravity's agent chat.**  
> **Do not break it into pieces.** Antigravity handles long prompts.  
> **This prompt uses EVERY / command Antigravity supports.**

---

## CONTEXT

You are building the frontend for **GAGOS (General Autonomous Generative Operating System)** — a sovereign AI-OS prototype by a single developer (swap821). The backend is ~18,000 lines of production-grade Python (FastAPI, Pydantic, SQLite, FAISS, Ollama, Bedrock, Gemini). The frontend is ~3,500 lines of React/Three.js.

**The 3D voyaging mind is the PRIMARY interface.** Floating HUD panels with glass morphism orbit over it like Iron Man's JARVIS HUD. The organism's body is not decoration — it is the central nervous system visualization mapped to backend state.

**Current frontend files:**
- `frontend/src/main.jsx` — entry point
- `frontend/src/index.css` — global styles, Tailwind v4 bridge, animations
- `frontend/src/tokens.css` — design system (color ramp, typography, motion, elevation)
- `frontend/src/config.js` — API base, HTTPS enforcement
- `frontend/src/superbrain/SuperbrainApp.jsx` — boot sequence, canvas, chrome
- `frontend/src/superbrain/WorkspaceCanvas.jsx` — 3D canvas (lazy loaded)
- `frontend/src/superbrain/SuperbrainReactiveEffects.jsx` — lightning, aurora, motes, spine flash
- `frontend/src/superbrain/lib/aiosAdapter.js` — API adapter, SSE parsing, voice, session
- `frontend/src/superbrain/lib/cognitionBus.js` — pub/sub event bus
- `frontend/src/superbrain/lib/tabStore.js` — materialized tab management
- `frontend/src/superbrain/lib/spineFlashBridge.js` — spine flash state
- `frontend/src/superbrain/lib/verifyAuroraBridge.js` — aurora intensity
- `frontend/src/superbrain/lib/swarmHUDStore.js` — swarm state management
- `frontend/src/workbench/GagosChrome.jsx` — 800+ lines, chat, voice, work materialization, onboarding
- `frontend/src/workbench/GagosChrome.css` — chat styles, dock, welcome, coach, verify toast
- `frontend/src/workbench/CouncilDashboard.jsx` — mission lifecycle, King Report, proposals, rollback
- `frontend/src/workbench/OperatorProfileCard.jsx` — operator model display
- `frontend/src/workbench/TrustHalo.jsx` — trust metrics polling
- `frontend/src/components/ErrorBoundary.jsx` — production error boundary
- `frontend/src/superbrain/lib/monacoConfig.js` — Monaco editor configuration (already exists, not surfaced)

**Backend API already exists:**
- SSE streaming at `/api/v1/generate` with frame types: message, tool, verify, approval, done, error, telemetry, system
- `/api/v1/chat` for chat endpoint
- `/api/v1/terminal` for terminal passthrough
- `/api/v1/missions` for council missions
- `/api/v1/self-analysis/proposals` for T2/T3 proposals
- `/api/v1/metrics` for Prometheus metrics

**Backend systems that emit events:**
- `gateway.py` — deterministic classification (RED/YELLOW/GREEN)
- `self_apply.py` — snapshot, rollback, integrity check
- `cerebellum.py` — compiled experience, playbook replay
- `skills.py` — pheromone-style skill memory with decay
- `mistake.py` — mistake pool, recurrence detection
- `council_orchestrator.py` — 5 Queens (planner, security, memory, testing, critique)
- `swarm.py` — ant-colony parallel execution, 6 castes
- `router.py` — cross-provider routing (Ollama, Bedrock, Gemini, OpenAI, Anthropic)
- `verifier.py` — verification runner, strength derivation
- `budget_guard.py` — cost tracking
- `autonomy.py` — earned autonomy with streak tracking
- `alignment.py` — alignment frames, policy resolution
- `vulture_sanitation.py` — read-only security scanner
- `ecosystem_scanner.py` — read-only dependency/API/model/git scanner

---

## THE PROMPT

Execute the following plan using ALL Antigravity features. Do not skip any command. Do not skip any phase. Generate a task checklist and execute step by step.

---

### PHASE 0: SETUP & PLANNING

/task Create a comprehensive task checklist for building the GAGOS v10 Sovereign Frontend. The plan has 4 phases over 8 weeks:

**Phase 1 (Weeks 1-2): Floating Workbench Foundation**
- Build reusable HUDPanel component (drag, resize, minimize, close, spawn animation, glass morphism)
- Build FileTree.jsx (scoped project explorer, wrapped in HUDPanel)
- Build CodeEditor.jsx (Monaco with GAGOS dark theme, wrapped in HUDPanel)
- Build DiffViewer.jsx (Monaco diff editor, wrapped in HUDPanel)
- Build TerminalPanel.jsx (bottom-docked, collapsible, glass morphism)
- Build BudgetMicroBar.jsx (energy state display in GagosChrome status cluster)
- Add keyboard shortcuts: Ctrl+O (file tree), Ctrl+W (close tab), Ctrl+` (terminal)
- Add 10 new API endpoints to aios/api/main.py
- Add 11 new SSE frame types to aiosAdapter.js

**Phase 2 (Weeks 3-4): 3D Cognition Mapping**
- Map spine vertebrae to RepoMap symbols (size=PageRank, glow=recency, color=error_count, active=cyan pulse)
- Map cortex to council gradients (6 sub-cortex nodes = ganglia, glow=gradient type+intensity)
- Map aura to energy state (hibernation=dim blue, conservation=amber, normal=cyan, expansion=purple, feast=gold)
- Map lightning to cloud routing (provider colors, thickness=cost tier, frequency=request rate)
- Map aurora to verification results (green=pass, red=fail, amber=caution, intensity=test count)
- Map orbiters to caste workers (spawn/die/success/fail animations, shape=caste, color=caste)
- Map trails to stigmergy pheromones (color=deposit type, brightness=intensity, length=age, real-time decay)
- Map scars to mistake recurrences (pulse on recurrence, fade on resolution, cluster around vertebra)
- Add click interactions: click vertebra → open editor, click orbiter → worker details, click scar → mistake history, click trail → pheromone deposit
- Add voice commands: "Show me the [symbol]" → zoom to vertebra, "Show me the council" → zoom to cortex, "Hide all panels" → minimize all

**Phase 3 (Weeks 5-6): Security & Ecosystem Observatory**
- Build CouncilDeliberationPanel.jsx (floating panel with live gradient gauges, 6 ganglia, sparklines)
- Build MemoryBrowser.jsx (floating panel, L1-L4 tabs, search, quarantine button)
- Build StigmergyPanel.jsx (floating panel, patch grid, deposit history, real-time updates)
- Build VultureFeed.jsx (floating alert stream, 7 detectors, CRITICAL triggers modal+sound+being recoil)
- Build EcosystemDashboard.jsx (floating status cards, 8 scanners, "Scan Now" button)
- Build SettingsPanel.jsx (floating configuration UI, operator-owned config)
- Add WebSocket fallback to aiosAdapter.js for SSE-blocked environments

**Phase 4 (Weeks 7-8): Voice, Mobile & Polish**
- Build VoiceCommandHandler.jsx (Web Speech API, command mapping, confirmation for destructive actions)
- Build MobileHUD.jsx (responsive layout, touch gestures, collapsible panels)
- Performance audit: 60fps, <2s first paint, <150kb JS bundle, dispose Monaco models on tab close
- Accessibility audit: screen reader, keyboard nav, reduced motion, color contrast >= 4.5:1
- Final integration test: all 4 phases working together

Mark each task as completed as you execute. Do not proceed to the next phase until I approve.

---

### PHASE 1: FLOATING WORKBENCH FOUNDATION

/walkthrough Execute Phase 1 step by step. For each step:
1. Scaffold the component file
2. Implement the component logic
3. Add CSS with glass morphism (backdrop-filter: blur(24px) saturate(1.6), inner glow, edge shimmer, NO drop shadows)
4. Add unit tests
5. Mark task complete
6. Move to next step

**Step 1.1:** Build `frontend/src/components/HUDPanel.jsx` — reusable floating shell with:
- Drag (header grab, move anywhere)
- Resize (bottom-right corner handle)
- Minimize (collapse to tab)
- Close (dissolve animation)
- Spawn animation (buoyant rise: opacity 0→1, translateY 20px→-4px→0, scale 0.96→1.01→1, blur 8px→0, easing: cubic-bezier(0.34, 1.56, 0.64, 1))
- Tint variants: base (neutral), cyan (file tree), purple (memory), amber (vulture)
- GPU compositing: will-change: transform, transform: translateZ(0)
- Contain: layout style paint
- pointer-events: auto on panel, none on empty space

**Step 1.2:** Add antigravity tokens to `frontend/src/tokens.css`:
```css
--ag-blur-xs: blur(4px);
--ag-blur-sm: blur(8px);
--ag-blur-md: blur(16px);
--ag-blur-lg: blur(24px);
--ag-blur-xl: blur(40px);
--ag-saturate: saturate(1.6);
--ag-saturate-high: saturate(2.0);
--ag-opacity-1: 0.92;
--ag-opacity-2: 0.85;
--ag-opacity-3: 0.75;
--ag-opacity-4: 0.60;
--ag-glow-cyan: inset 0 0 20px rgba(123, 245, 251, 0.06);
--ag-glow-purple: inset 0 0 20px rgba(167, 139, 250, 0.06);
--ag-glow-amber: inset 0 0 20px rgba(251, 191, 36, 0.06);
--ag-shimmer: 0 0 0 1px rgba(123, 245, 251, 0.08);
--ag-shimmer-hover: 0 0 0 1px rgba(123, 245, 251, 0.15);
--ag-shimmer-active: 0 0 0 1px rgba(123, 245, 251, 0.25);
--ag-rim-cyan: 0 0 30px rgba(123, 245, 251, 0.10);
--ag-rim-purple: 0 0 30px rgba(167, 139, 250, 0.10);
--ag-surface-base: rgba(10, 11, 16, 0.92);
--ag-surface-cyan: rgba(10, 14, 18, 0.85);
--ag-surface-purple: rgba(14, 10, 18, 0.85);
--ag-surface-amber: rgba(18, 14, 10, 0.85);
--ag-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
--ag-float: cubic-bezier(0.4, 0, 0.2, 1);
--ag-sink: cubic-bezier(0.4, 0, 0.2, 1);
--ag-wobble: cubic-bezier(0.68, -0.55, 0.265, 1.55);
--editor-bg: #0a0b10;
--editor-gutter: #0d0e13;
--editor-line-highlight: rgba(123, 245, 251, 0.04);
--editor-selection: rgba(123, 245, 251, 0.15);
--diff-add: rgba(52, 211, 153, 0.12);
--diff-del: rgba(248, 113, 113, 0.12);
--diff-change: rgba(251, 191, 36, 0.12);
--terminal-bg: #08090c;
--terminal-prompt: var(--neon-cyan);
--terminal-success: var(--success);
--terminal-error: var(--danger);
--tree-hover: rgba(255, 255, 255, 0.04);
--tree-active: rgba(123, 245, 251, 0.08);
--tree-badge-edit: var(--neon-cyan);
--tree-badge-verify: var(--warn);
--tree-badge-approve: var(--success);
--tree-badge-fail: var(--danger);
--aura-hibernation: #60a5fa;
--aura-conservation: #fbbf24;
--aura-normal: #7bf5fb;
--aura-expansion: #a78bfa;
--aura-feast: #fbbf24;
--scar-recurring: #f87171;
--scar-resolved: #34d399;
--scar-dormant: #6b7280;
```

**Step 1.3:** Build `frontend/src/workbench/FileTree.jsx` — wrapped in HUDPanel, tint="cyan".
- Fetch from `/api/v1/files/tree`
- Expandable/collapsible directories
- Click file → opens CodeEditor
- Work badges: cyan dot (editing), amber (verifying), green (approved), red (failed)
- Right-click: "Ask GAGOS to edit this"
- Search/filter by filename
- Keyboard: arrow keys, Enter, Space, typeahead

**Step 1.4:** Build `frontend/src/workbench/CodeEditor.jsx` — wrapped in HUDPanel, tint="base".
- Use existing `monacoConfig.js`
- GAGOS dark theme (match tokens.css)
- Syntax: Python, JS, TS, JSX, JSON, CSS, HTML, SQL, Go, Rust, C, C++
- Read-only for files outside scope
- Edit mode for training_ground/ and operator-owned paths
- Auto-save on Ctrl+S (with approval gate)
- Command palette: "Ask GAGOS to refactor this function"

**Step 1.5:** Build `frontend/src/workbench/DiffViewer.jsx` — wrapped in HUDPanel, tint="base".
- Monaco diff editor (side-by-side + inline toggle)
- Color: green add, red del, amber change
- Used in ApprovalPanel for proposed edits
- Used in Self-Analysis for T2 diffs
- Keyboard: Ctrl+Shift+D

**Step 1.6:** Build `frontend/src/workbench/TerminalPanel.jsx` — bottom-docked, not floating, collapsible.
- Subscribe to cognitionBus 'terminal' events
- Color: green (returncode 0), red (error)
- Show command, output, timestamp
- Auto-scroll, copy button, clear button, max 500 lines
- Keyboard: Ctrl+` toggle

**Step 1.7:** Build `frontend/src/workbench/BudgetMicroBar.jsx` — add to GagosChrome status cluster.
- Thin progress bar: daily spent / daily allowance
- Color: red (hibernation), amber (conservation), green (normal), cyan (expansion), purple (feast)
- Click → expands to full breakdown per ganglion/caste
- Updates via SSE 'budget' frames

**Step 1.8:** Add API endpoints to `aios/api/main.py`:
```python
@router.get("/api/v1/files/tree")
@router.get("/api/v1/files/read")
@router.post("/api/v1/files/write")
@router.get("/api/v1/memory/search")
@router.get("/api/v1/stigmergy/field")
@router.get("/api/v1/vulture/feed")
@router.get("/api/v1/ecosystem/status")
@router.post("/api/v1/ecosystem/scan")
@router.get("/api/v1/repomap")
@router.get("/api/v1/budget/status")
```

**Step 1.9:** Add SSE frame handlers to `frontend/src/superbrain/lib/aiosAdapter.js`:
```javascript
const FRAME_HANDLERS = {
  'budget': (data) => publishCognition({ type: 'budget', data }),
  'council-gradient': (data) => publishCognition({ type: 'council-gradient', data }),
  'vulture-finding': (data) => publishCognition({ type: 'vulture', data }),
  'ecosystem-scan': (data) => publishCognition({ type: 'ecosystem', data }),
  'stigmergy-deposit': (data) => publishCognition({ type: 'stigmergy', data }),
  'terminal': (data) => publishCognition({ type: 'terminal', data }),
  'repomap-update': (data) => publishCognition({ type: 'repomap', data }),
  'caste-spawn': (data) => publishCognition({ type: 'caste-spawn', data }),
  'caste-death': (data) => publishCognition({ type: 'caste-death', data }),
  'mistake-recurrence': (data) => publishCognition({ type: 'mistake-recurrence', data }),
  'mistake-resolved': (data) => publishCognition({ type: 'mistake-resolved', data }),
};
```

**Step 1.10:** Update `frontend/src/superbrain/SuperbrainApp.jsx` layer stack:
```
Layer 0: being-layer (3D canvas, z-index: 1)
Layer 1: hud-layer (floating panels, pointer-events: none container, auto on panels, z-index: 10)
Layer 2: command-layer (GagosChrome, z-index: 20)
Layer 3: terminal-layer (TerminalPanel, z-index: 15)
```

**Step 1.11:** Add performance guards:
- Max 3 backdrop-filter panels active simultaneously
- Minimized panels collapse to tabs (solid background, no blur)
- Fallback: @supports not (backdrop-filter) → solid opacity
- Fallback: @media (prefers-reduced-motion) → no blur, no animation
- Dispose Monaco models on tab close
- Limit open editor tabs to 5

**Step 1.12:** Run unit tests for all Phase 1 components. Verify 100% pass.

/browser Open the browser preview. Verify:
1. 3D canvas renders at 60fps
2. HUD panels have backdrop-filter blur and being is visible behind them
3. No more than 3 panels use backdrop-filter simultaneously
4. File tree shows scoped files
5. Monaco editor opens with syntax highlighting
6. Diff viewer shows side-by-side diffs
7. Terminal shows command output
8. Budget bar shows energy state
9. All panels are draggable, resizable, minimizable, closable
10. Spawn animation plays (buoyant rise)

Report test results. Mark Phase 1 complete. STOP. Wait for my approval before Phase 2.

---

### PHASE 2: 3D COGNITION MAPPING

/walkthrough Execute Phase 2 step by step. For each step:
1. Map backend event to 3D visualization
2. Add event subscription to SuperbrainReactiveEffects.jsx
3. Add click interaction handler
4. Add unit tests
5. Mark task complete
6. Move to next step

**Step 2.1:** Map spine to RepoMap:
- Subscribe to 'repomap-update' SSE frames
- Each vertebra = symbol node (function, class, method)
- Vertebra size = PageRank centrality
- Vertebra glow intensity = recency of edit
- Vertebra color = error_count (green=0, amber=1-2, red=3+)
- Active vertebra (touched by current mission) = cyan pulse
- Click vertebra → camera zooms in, opens floating editor
- Hover vertebra → tooltip: symbol name, file path, PageRank, last edit, error count

**Step 2.2:** Map cortex to council gradients:
- Subscribe to 'council-gradient' SSE frames
- 6 sub-cortex nodes = Plan, Security, Memory, Verify, Reflect, Synthesis
- Each sub-cortex glows with gradient color and intensity
- Security sub-cortex = red-bordered, unoverridable
- Main cortex glow = synthesis verdict color
- Deliberation sequence animation: Plan → Security → Memory → Verify → Reflect → Synthesis
- Security veto → being recoils (defensive posture, red aura pulse)
- Click sub-cortex → opens CouncilDeliberationPanel

**Step 2.3:** Map aura to energy state:
- Subscribe to 'budget' SSE frames
- Color: hibernation=blue, conservation=amber, normal=cyan, expansion=purple, feast=gold
- Opacity = energy ratio (dimmer as energy depletes)
- Pulse frequency = state (hibernation=slow, feast=rapid)
- Particle density = state (hibernation=sparse, feast=dense)
- Hibernation threshold (<20%) → red alarm pulse
- Success bonus → gold flash
- Click aura → opens BudgetMicroBar with full breakdown

**Step 2.4:** Map lightning to cloud routing:
- Enhance existing lightning arc code in aiosAdapter.js
- Arc color = provider (Bedrock=orange, Gemini=green, OpenAI=teal, Anthropic=brown, Ollama=cyan)
- Arc thickness = cost tier (free=thin, low=medium, high=thick)
- Arc frequency = request rate
- Click arc → shows routing details (provider, model, cost, latency)

**Step 2.5:** Map aurora to verification:
- Enhance existing verifyAuroraBridge
- Subscribe to 'verify' events
- Green aurora = pass (wide, celebratory)
- Red aurora = fail (narrow, sharp)
- Amber aurora = caution (medium, hesitant)
- Intensity = test count
- Duration = 2 seconds
- Multiple auroras can overlap

**Step 2.6:** Map orbiters to caste workers:
- Subscribe to 'caste-spawn' and 'caste-death' SSE frames
- Builder = hands, cyan, typing animation
- Scout = eyes, green, scanning animation
- Soldier = shield, red, patrolling animation
- Nurse = heart, amber, healing animation
- Vulture = shadow, purple, sweeping animation
- Forager = compass, blue, exploring animation
- Spawn: orbiter detaches from being, begins orbiting
- Death: orbiter dissolves into particles
- Success: orbiter glows brighter
- Failure: orbiter turns red and falls
- Click orbiter → opens floating panel with worker details
- Hover orbiter → tooltip: caste, patch, budget, lifespan, turns spent

**Step 2.7:** Map trails to stigmergy pheromones:
- Subscribe to 'stigmergy-deposit' SSE frames
- Trail color = deposit type (green=success, red=failure, amber=caution, blue=exploration)
- Trail brightness = intensity (decays over time)
- Trail length = age (shrinks over time)
- New deposit = bright flash that fades
- Trails cluster around relevant vertebra
- Click trail → shows deposit details (timestamp, worker, content)
- Filter by deposit type

**Step 2.8:** Map scars to mistake recurrences:
- Subscribe to 'mistake-recurrence' and 'mistake-resolved' events
- Scar color = state (red=recurring, green=resolved, gray=dormant)
- Scar pulse = recurrence detected
- Scar size = severity
- Recurrence triggers being flinch animation
- Resolution triggers scar fade animation
- Scars cluster around relevant vertebra
- Click scar → shows mistake history and resolution steps

**Step 2.9:** Add voice command handler:
- Use browser Web Speech API
- Commands:
  - "Show me the [symbol]" → camera zooms to spine vertebra
  - "Show me the council" → camera zooms to cortex
  - "Show me the vulture" → camera zooms to vulture orbiter
  - "Show me the budget" → opens BudgetMicroBar
  - "Show me the memory" → opens MemoryBrowser
  - "Show me the stigmergy" → opens StigmergyPanel
  - "Hide all panels" → minimizes all HUD panels
  - "Maximize editor" → maximizes CodeEditor window
- Confirmation dialog for destructive commands
- Visual feedback: microphone icon pulses when listening

**Step 2.10:** Add being-state-aware panel opacity:
- When being is active (streaming, deliberating) → panels more transparent (0.75)
- When being is idle → panels more opaque (0.92)
- CSS transition: 0.5s var(--ag-float)

**Step 2.11:** Run unit tests for all Phase 2 components. Verify 100% pass.

/browser Open the browser preview. Verify:
1. Spine vertebrae map to RepoMap (size, glow, color, active state)
2. Cortex shows 6 sub-cortex nodes with gradient glows
3. Aura reflects energy state (color, opacity, pulse, particles)
4. Lightning shows cloud routing (provider colors, thickness)
5. Aurora shows verification results (green/red/amber)
6. Orbiters animate spawn/die/success/fail
7. Trails decay in real-time
8. Scars pulse on recurrence
9. Click interactions open floating panels
10. Voice commands zoom camera correctly
11. All updates via SSE, not polling
12. Performance stays at 60fps with all effects active

Report test results. Mark Phase 2 complete. STOP. Wait for my approval before Phase 3.

---

### PHASE 3: SECURITY & ECOSYSTEM OBSERVATORY

/walkthrough Execute Phase 3 step by step.

**Step 3.1:** Build `frontend/src/observatory/CouncilDeliberationPanel.jsx` — wrapped in HUDPanel, tint="purple".
- 6 radial gauges, one per ganglion
- Gauge shows gradient type (positive/caution/negative) and intensity (0-1)
- Security gauge = red-bordered, lock icon
- Synthesis gauge = verdict arrow (proceed/abort/caution)
- History sparkline: last 5 gradients per ganglion
- Updates via SSE 'council-gradient' frames
- Click gauge → shows full gradient evidence

**Step 3.2:** Build `frontend/src/observatory/MemoryBrowser.jsx` — wrapped in HUDPanel, tint="purple".
- 4 tabs: Working (L1), Episodic (L2), Semantic (L3), Skills/Facts/Curriculum (L4)
- Search across all layers or filter by layer
- Results: content, source, timestamp, verification status, relevance score
- L3: vector similarity score
- L4: success rate, freshness, reuse factor
- Click result → full detail view
- "Quarantine" button for suspicious entries (operator-only)
- Updates via SSE or API polling

**Step 3.3:** Build `frontend/src/observatory/StigmergyPanel.jsx` — wrapped in HUDPanel, tint="cyan".
- Grid of patches (file paths or symbol IDs)
- Each patch: success density (green), failure density (red), caution density (amber), exploration density (blue)
- Color intensity = pheromone strength
- Size = number of deposits
- Click patch → deposit history with timestamps
- Real-time updates via SSE 'stigmergy-deposit' frames
- Filter by deposit type

**Step 3.4:** Build `frontend/src/observatory/VultureFeed.jsx` — wrapped in HUDPanel, tint="amber".
- Stream of findings, newest at top
- Detector icon, threat level badge, description, location, timestamp
- Threat levels: LOW (blue), MEDIUM (amber), HIGH (orange), CRITICAL (red with pulse)
- CRITICAL findings:
  - Modal alert with sound
  - Being recoils (defensive posture, red aura pulse)
  - Notification badge on panel header
- "Quarantine" button (operator-only)
- "Restore" button for quarantined items (within 7-day window)
- Real-time via SSE 'vulture-finding' frames
- Search/filter by detector, threat level, date range

**Step 3.5:** Build `frontend/src/observatory/EcosystemDashboard.jsx` — wrapped in HUDPanel, tint="green".
- 8 cards: Dependency, API, Input, Model, Git, TLS, FS, Config
- Each card: status icon (green/yellow/red), last scan timestamp, findings count, "Scan Now" button
- Click card → expandable detail view
- Dependency: list of packages with CVE status
- API: list of endpoints with anomaly status
- Model: checksum verification status
- Real-time updates via SSE 'ecosystem-scan' frames

**Step 3.6:** Build `frontend/src/observatory/SettingsPanel.jsx` — wrapped in HUDPanel, tint="base".
- Operator-owned config (not colony-modifiable)
- .env variables display (read-only)
- Local config editor (operator-owned paths only)
- Theme toggle (dark/light)
- Reduced motion toggle
- Voice command sensitivity slider
- Panel opacity slider
- Reset layout button (restore default panel positions)

**Step 3.7:** Add WebSocket fallback to `frontend/src/superbrain/lib/websocketAdapter.js`:
- Detect SSE failure (timeout or error)
- Fallback to WebSocket connection
- Same frame types, same handlers
- Reconnect logic with exponential backoff
- Visual indicator: connection status icon in status cluster

**Step 3.8:** Run unit tests for all Phase 3 components. Verify 100% pass.

/browser Open the browser preview. Verify:
1. Council deliberation panel shows 6 gauges with live gradients
2. Memory browser searches all 4 layers
3. Stigmergy panel shows patch densities
4. Vulture feed shows findings, CRITICAL triggers modal+sound+being recoil
5. Ecosystem dashboard shows all 8 scanners
6. Settings panel allows config changes
7. WebSocket fallback works when SSE is blocked
8. All panels are draggable, resizable, minimizable, closable
9. Performance stays at 60fps

Report test results. Mark Phase 3 complete. STOP. Wait for my approval before Phase 4.

---

### PHASE 4: VOICE, MOBILE & POLISH

/walkthrough Execute Phase 4 step by step.

**Step 4.1:** Build `frontend/src/components/VoiceCommandHandler.jsx`:
- Web Speech API (SpeechRecognition)
- Continuous listening mode (toggle on/off)
- Command list:
  - "Show me the [symbol]" → camera zooms to spine vertebra
  - "Show me the council" → camera zooms to cortex
  - "Show me the vulture" → camera zooms to vulture orbiter
  - "Show me the budget" → opens BudgetMicroBar
  - "Show me the memory" → opens MemoryBrowser
  - "Show me the stigmergy" → opens StigmergyPanel
  - "Show me the ecosystem" → opens EcosystemDashboard
  - "Hide all panels" → minimizes all HUD panels
  - "Open file tree" → opens FileTree
  - "Open terminal" → toggles TerminalPanel
  - "Maximize editor" → maximizes CodeEditor
  - "Close all" → closes all panels except FileTree and Terminal
- Destructive commands require confirmation: "Are you sure?"
- Visual feedback: microphone icon pulses when listening, command text appears in HUD
- Error handling: "Command not recognized" with suggestion

**Step 4.2:** Build `frontend/src/components/MobileHUD.jsx`:
- Responsive layout for screens < 768px
- Bottom sheet for panels (swipe up to open, swipe down to close)
- Tab bar for quick panel switching
- Touch gestures: pinch to zoom on 3D canvas, swipe to rotate, tap to select vertebra
- Collapsible command cortex (swipe up from bottom)
- Full-screen editor mode (hides 3D canvas temporarily)
- Orientation change handling
- Performance: reduce 3D detail on mobile (lower LOD, fewer particles)

**Step 4.3:** Performance audit:
- 3D canvas FPS: target 60fps, minimum 45fps
- First Contentful Paint: < 1.5s
- Time to Interactive: < 3s
- JS bundle size: < 150kb gzipped (tree-shake Monaco, split chunks)
- Memory usage: < 200MB (dispose Monaco models on tab close, limit open tabs to 5)
- Lighthouse score: > 90
- Use React DevTools Profiler to find slow renders
- Use Chrome DevTools Performance tab to find frame drops
- Optimize R3F render loop (reduce draw calls, LOD for distant vertebrae)

**Step 4.4:** Accessibility audit:
- All components have aria-label and role attributes
- File tree: keyboard navigable (arrow keys, Enter, Space, typeahead)
- Editor: aria-label with filename
- Diff viewer: announces "Showing diff for [filename]"
- Terminal: aria-live="polite" for new output
- Modals: trap focus, close button, Escape key
- Reduced motion: all animations disabled, transitions instant
- Color contrast: all text >= 4.5:1 against backgrounds
- Screen reader: status announcements for council deliberation, vulture findings, verification results
- Voice commands: text alternatives (keyboard shortcuts)
- Test with NVDA or VoiceOver
- Run axe-core automated audit

**Step 4.5:** Final integration test:
- All 4 phases working together
- Open FileTree → click file → opens CodeEditor → edit → save → triggers verification → aurora bloom → council deliberation → cortex glow → approval flow → diff viewer → terminal output
- Stress test: 10 simultaneous SSE events, verify no frame drops
- Error test: disconnect backend, verify "offline" state, reconnect, verify recovery
- Security test: XSS attempt in chat, verify sanitizeToText blocks it

**Step 4.6:** Generate final artifacts:

/artifact Generate the complete GAGOS v10 Frontend Architecture Document:
- Component hierarchy diagram
- Event flow diagram (SSE → cognitionBus → 3D being / HUD panels)
- API endpoint summary table
- Design system token reference
- Performance budget results
- Accessibility audit results
- Security checklist results

/artifact Generate the GAGOS v10 Frontend README:
- Installation instructions
- Development server setup
- Build commands
- Testing commands
- Deployment guide
- Troubleshooting section

/artifact Generate the GAGOS v10 Frontend Changelog:
- Phase 1: Floating Workbench (list all components)
- Phase 2: 3D Cognition Mapping (list all mappings)
- Phase 3: Security & Ecosystem (list all panels)
- Phase 4: Voice & Polish (list all features)
- Known issues
- Future roadmap

**Step 4.7:** Deploy to production:

/deploy Deploy the GAGOS v10 frontend to the production environment. Verify:
- Build succeeds with no errors
- All assets load correctly
- HTTPS enforced
- API endpoints reachable
- SSE connection stable
- 3D canvas renders at 60fps on production hardware
- All floating panels work correctly
- Voice commands work in production
- Mobile layout works on real devices

Report deployment status. Mark Phase 4 complete. Mark ENTIRE PROJECT complete.

---

### SCHEDULED BACKGROUND TASKS

/schedule Set up these recurring tasks:

1. **Daily at 02:00 UTC:** Run Ecosystem Scanner full scan (all 8 scanners). Report findings as artifact.
2. **Daily at 03:00 UTC:** Run Vulture full scan (all 7 specializations). Report findings as artifact.
3. **Daily at 04:00 UTC:** Refresh RepoMap (rebuild symbol graph). Report symbol count and coverage.
4. **Every 30 minutes:** Apply Stigmergy field decay (update pheromone intensities). Report field health score.
5. **Every 24 hours:** Memory compaction (L2 Episodic prune, L3 Semantic deduplication). Report space saved.
6. **Weekly on Sunday 00:00 UTC:** Generate Council Self-Assessment report (decision quality, deliberation efficiency, ganglion performance, constitutional health, operator satisfaction). Report composite score.

All tasks must log to the tamper-evident audit ledger. All tasks must respect energy state (hibernation = skip non-essential tasks).

---

### AGENT MANAGER — PARALLEL SUBAGENTS

/agent Launch these subagents in parallel for maximum efficiency:

**Subagent 1: "Workbench Builder"**
- Focus: Phase 1 components (FileTree, CodeEditor, DiffViewer, TerminalPanel, HUDPanel)
- Constraints: Must use existing tokens.css and index.css. Must follow glass morphism. Must be accessible.
- Deliverable: All Phase 1 components built and tested.

**Subagent 2: "3D Cognition Mapper"**
- Focus: Phase 2 (spine=RepoMap, cortex=council, aura=energy, lightning=routing, aurora=verification, orbiters=castes, trails=stigmergy, scars=mistakes)
- Constraints: Must not drop 3D canvas below 60fps. Must use existing event architecture. Must add click interactions.
- Deliverable: All backend events mapped to 3D being with click interactions.

**Subagent 3: "Observatory Builder"**
- Focus: Phase 3 components (CouncilDeliberationPanel, MemoryBrowser, StigmergyPanel, VultureFeed, EcosystemDashboard, SettingsPanel)
- Constraints: Must use HUDPanel shell. Must update via SSE. Must handle CRITICAL alerts.
- Deliverable: All Phase 3 components built and tested.

**Subagent 4: "Polish & Performance"**
- Focus: Phase 4 (VoiceCommandHandler, MobileHUD, performance audit, accessibility audit, deployment)
- Constraints: Must not break existing functionality. Must pass all audits. Must deploy cleanly.
- Deliverable: Phase 4 complete, production deployed.

Each subagent reports progress to the main agent. The main agent coordinates dependencies (e.g., Subagent 2 needs Subagent 1's HUDPanel, Subagent 3 needs Subagent 2's event mappings).

---

### BROWSER VERIFICATION CHECKLIST

/browser After each phase, verify these in the browser preview:

**Phase 1:**
- [ ] 3D canvas renders at 60fps
- [ ] HUD panels have backdrop-filter blur
- [ ] Being is visible behind panels
- [ ] Max 3 blurred panels active
- [ ] File tree shows scoped files
- [ ] Monaco editor opens with syntax highlighting
- [ ] Diff viewer shows side-by-side diffs
- [ ] Terminal shows command output
- [ ] Budget bar shows energy state
- [ ] All panels draggable, resizable, minimizable, closable
- [ ] Spawn animation plays

**Phase 2:**
- [ ] Spine vertebrae map to RepoMap
- [ ] Cortex shows 6 sub-cortex nodes
- [ ] Aura reflects energy state
- [ ] Lightning shows cloud routing
- [ ] Aurora shows verification results
- [ ] Orbiters animate correctly
- [ ] Trails decay in real-time
- [ ] Scars pulse on recurrence
- [ ] Click interactions work
- [ ] Voice commands zoom camera
- [ ] Performance stays at 60fps

**Phase 3:**
- [ ] Council deliberation panel shows live gradients
- [ ] Memory browser searches all layers
- [ ] Stigmergy panel shows patch densities
- [ ] Vulture feed shows findings
- [ ] CRITICAL triggers modal+sound+being recoil
- [ ] Ecosystem dashboard shows all 8 scanners
- [ ] Settings panel allows config changes
- [ ] WebSocket fallback works
- [ ] All panels work correctly
- [ ] Performance stays at 60fps

**Phase 4:**
- [ ] Voice commands work correctly
- [ ] Mobile layout is usable
- [ ] Performance budget met (60fps, <2s FCP, <150kb JS)
- [ ] Accessibility requirements met
- [ ] All integration tests pass
- [ ] Production deployment successful

---

### VOICE COMMAND TEST SUITE

/voice Test these voice commands in the browser preview:

1. "Show me the router" → camera zooms to `aios.core.router` vertebra
2. "Show me the gateway" → camera zooms to `aios.security.gateway` vertebra
3. "Show me the council" → camera zooms to cortex
4. "Show me the vulture" → camera zooms to vulture orbiter
5. "Show me the budget" → opens BudgetMicroBar
6. "Show me the memory" → opens MemoryBrowser
7. "Show me the stigmergy" → opens StigmergyPanel
8. "Hide all panels" → minimizes all HUD panels
9. "Open file tree" → opens FileTree
10. "Open terminal" → toggles TerminalPanel
11. "Maximize editor" → maximizes CodeEditor
12. "Close all" → closes all panels except FileTree and Terminal

Report recognition accuracy and response latency for each command.

---

### FINAL INSTRUCTIONS

1. Execute Phase 1 completely before starting Phase 2.
2. Execute Phase 2 completely before starting Phase 3.
3. Execute Phase 3 completely before starting Phase 4.
4. Use /task to track progress. Mark each task complete.
5. Use /walkthrough for step-by-step execution within each phase.
6. Use /agent for parallel subagents where dependencies allow.
7. Use /artifact for structured outputs (architecture docs, README, changelog).
8. Use /browser for visual verification after each phase.
9. Use /voice for voice command testing in Phase 4.
10. Use /schedule for background tasks.
11. Use /deploy for production deployment.
12. STOP after each phase and wait for my approval.

Do not skip any step. Do not skip any command. Do not proceed without approval.

Begin with Phase 1, Step 1.1: Build HUDPanel.jsx.
