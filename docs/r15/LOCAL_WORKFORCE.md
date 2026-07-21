# Local Workforce Registry & Hierarchy

## Overview
The Local Workforce Registry is the core component that manages all hired and admitted AI models operating within the AI-OS boundaries. It ensures that only properly qualified models are permitted to perform tasks.

## Security Boundaries
1. **No Self-Authority**: Models cannot approve their own actions, including their own admission to the registry.
2. **Persistence**: The workforce hierarchy is durable across restarts. It uses the `registry.db` SQLite store.
3. **Emergency Stop**: The local workforce respects global emergency stop signals, ceasing task consumption immediately.

## Schema
- `worker_id` (UUID)
- `model_id` (string)
- `roles` (list of enum)
- `approved_at` (timestamp)
- `revoked_at` (timestamp, nullable)
