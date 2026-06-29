// troikaConfig.ts — run troika text typesetting on the MAIN THREAD, not a worker.
//
// drei's <Text> (troika-three-text) defaults to a web worker that it builds from a
// blob: URL and bootstraps by stringifying functions + reconstructing them with
// `new Function` inside the worker. Under a hardened CSP that needs `'unsafe-eval'`
// AND `blob:` in script-src — the two relaxations we most want gone. With
// useWorker:false troika typesets on the main thread (no blob worker, no eval), so
// the CSP can drop both. Must run BEFORE the first <Text> mounts (troika ignores
// configureTextBuilder after the first font request) — imported as a side effect at
// the very top of main.jsx.
//
// Trade-off: text layout is synchronous on the main thread. The being's text is
// small + changes rarely, so the frame cost is negligible; the security win
// (no eval, no blob script) is worth it for this local-first app.
import { configureTextBuilder } from 'troika-three-text';

configureTextBuilder({ useWorker: false });
