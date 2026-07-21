# Changelog

All notable changes to the GAGOS Frontend will be documented in this file.

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
