# R15 Demo Script

## Goal
Demonstrate the Sovereign Intelligence Flywheel from end to end.

## Script Steps
1. **Boot**: Start the backend and frontend. Note the empty active task queue.
2. **Hiring**: Trigger a hiring proposal from the `MissionControlPanel`. Switch to the `IntelligenceHiringPanel` and click 'Accept'. Observe the new cloud-frontier connection.
3. **Local Registry**: Open the `LocalWorkforcePanel`. Add `qwen2.5-coder:7b`. Verify the API accurately returns the local model metadata.
4. **Maintenance Trigger**: Manually run the maintenance scanner. Introduce a synthetic failing test in `tests/test_cortex_bus.py`.
5. **Resolution**: Observe the Maintenance Lifecycle Engine detect the failure, delegate to the Local Workforce, resolve the issue, and rescan to green.
6. **Emergency Stop**: Trigger the Global Emergency Stop from the UI. Note how all queued tasks immediately drain and freeze.
