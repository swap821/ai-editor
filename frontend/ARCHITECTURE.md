# GAGOS Frontend Architecture (v10)

## Overview
The GAGOS frontend is a single-root React application that serves as the visual
"nervous system" for the underlying AI Operating System (AI-OS). It renders the
state of the system as a diegetic 3D entity alongside a product-authored 2D
conversation layer and an explicit Expert/Mirror workbench. Beginner mode is
the default; Expert/Mirror exposes more of the same measured state without
creating a second authority.

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

### 4. `LivingWorkspaceShell` & voice surfaces
`LivingWorkspaceShell` hosts the backend-backed Expert/Mirror workbench and
truthful runtime surfaces. Voice is an optional conversation channel through
`GagosChrome`; it never redeems an approval or authorizes a mutation.

## State Management & Communication
- **Server-Sent Events (SSE)**: supervised turns use `aiosAdapter.ts`, while
  `aiosMirror.ts` consumes the canonical mirror snapshot/journal stream.
- **Cognition Bus**: Internal event bus translates admitted backend events into
  bounded body reactions; it never creates authority.
- **Mirror store/registry**: typed state and event admission preserve measured,
  stale, unavailable, blocked, and verified distinctions.
