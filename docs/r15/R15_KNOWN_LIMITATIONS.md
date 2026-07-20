# R15 Known Limitations

1. **State Machine Concurrency**: Concurrent access to SQLite during high-volume `cortex_bus` emissions can still occasionally cause `OperationalError: locked` despite retry decorators.
2. **Sandbox Leakage Constraints**: While the maintenance sandboxes use `tempfile`, aggressive disk usage by a broken script could still theoretically exhaust the host machine's drive space.
3. **Frontend Caching**: The SSE streams can sometimes drop a message if the React component unmounts mid-frame. A robust reconnection strategy is slated for R16.
4. **Model Hysteresis**: Large context sizes on local models (`llama3.1:8b`) may exhibit looping behavior on complex refactoring tasks without sufficient intermediate validation.
