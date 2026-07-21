# GAGOS Frontend Architecture (v10)

## Overview
The GAGOS frontend is a single-page React application that serves as the visual "nervous system" for the underlying AI Operating System (AI-OS). Unlike traditional dashboards, this interface renders the state of the AI as a diegetic 3D entity alongside a crisp 2D product layer (GagosChrome) for telemetry and interaction.

## Core Stack
- **React 18**: The primary UI rendering library.
- **Three.js & React Three Fiber**: For rendering the 3D biological representation of the AI-OS state on the `<WorkspaceCanvas>`.
- **Tailwind CSS v4**: For rapid utility styling and design tokens.
- **Vite**: The build tool and development server.

## Major Components
### 1. `SuperbrainApp.jsx`
The primary application root that orchestrates the entire UI. It sets up the z-index stacking context (Canvas at z=0, Chrome at z=10).

### 2. The 3D Canvas (`WorkspaceCanvas`)
Renders the diegetic 3D hero organism. State changes from the backend (like api verification events) emit visual effects in the 3D scene (e.g. `Aurora`, `Lightning`, `Pheromones`).

### 3. `GagosChrome` (The 2D HUD)
A crisp glassmorphism product layer DOM-sibling to the canvas. Contains various specialized HUD panels:
- **`MemoryBrowser`**: Queries past experiences and lessons.
- **`StigmergyPanel`**: Maps semantic correlations (graphs).
- **`VultureFeed`**: Displays cleanup, recycling, and error logs.
- **`EcosystemDashboard`**: High-level health and swarm telemetry metrics.
- **`SettingsPanel`**: Operator overrides for AIOS settings.
- **`CouncilDeliberationPanel`**: Visualizes the internal dialog of the multi-agent council.
- **`CodeEditor` & `TerminalPanel`**: Tools for viewing and editing code directly within the OS.

### 4. `MobileHUD` & `VoiceCommandHandler`
Responsive wrapper for mobile devices and a continuous-listening speech-to-text interface (via Web Speech API) allowing the operator to speak directly to the AI-OS.

## State Management & Communication
- **Server-Sent Events (SSE)**: Real-time telemetry is streamed from the backend (`aiosAdapter.sse.ts`).
- **WebSocket Fallback**: (`websocketAdapter.ts`) Provides a resilient fallback if SSE drops.
- **Cognition Bus**: Internal event bus that dispatches UI interactions back to the AI-OS agents.
