# Changelog

All notable changes to the GAGOS Frontend will be documented in this file.

## [v10.1.0] - 2026-09-24

### Added
- **Physical state projection**: The GAGOS surface now projects truthful cortex,
  conductor, branch, membrane, memory, verification, recovery, and materialization
  cues from the existing semantic presentation state.
- **Physical state gallery**: A deterministic development gallery exposes bounded
  resting, active, worker, verification, recovery, stale, stopped, and reduced-motion
  fixtures for visual and accessibility inspection.
- **Accessibility and renderer recovery seams**: Gallery state changes announce
  their fixture and motion mode through a bounded live region, while renderer loss
  remains explicit and recoverable without implying backend failure.

### Changed
- Added bounded physical resource metrics, worker lifecycle projection, reduced-motion
  handling, and verification/council visual cues with tests and evidence artifacts.
- Documented the physical-embodiment RFC, baseline, implementation report, validation
  packet, deterministic soak results, and live backend evidence.

## [v10.0.0] - 2026-07-09

### Added
- **Floating Workbench HUD**: Complete glassmorphism UI overlay using `tokens.css`.
- **EcosystemDashboard**: Displays real-time metrics of agents and overall AIOS sovereignty.
- **VultureFeed**: Displays errors, recycling, and system audit logs dynamically.
- **StigmergyPanel**: Uses semantic graph analysis to show node relationships (e.g. file dependencies, logic maps).
- **SettingsPanel**: UI preferences, global thresholds, and AIOS autonomy overrides.
- **MemoryBrowser**: Queries long-term experiences.jsonl and memory logs.
- **VoiceCommandHandler**: Web Speech API integration for continuous voice commands.
- **MobileHUD**: Responsive wrapper for small devices.
- **WebSocket Fallback**: Fallback adapter (`websocketAdapter.ts`) in case SSE fails.

### Changed
- Refactored `SuperbrainApp.jsx` to load `GagosChrome` and all new HUD panels properly with the correct z-index hierarchy.
- Updated global stylesheet (`index.css`) to bridge Tailwind v4 utility classes and map to custom CSS variables for premium styling.
- `index.css` animations enhanced with smooth keyframes (`workspaceIn`, `auraBreath`, `auraPulse`).

### Fixed
- Fixed mobile panel constraints so `HUDPanel` items don't overflow the viewport width.
- Unit testing setup (Vitest + React Testing Library) fully configured and resolving properly with mocked WebSocket classes.
