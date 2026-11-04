#!/bin/sh
# Runs the frontend's tests inside the sealed verify-web image (2026-11-03).
#
#   verify_web_run.sh related|run <path relative to frontend/> ...
#
# The container is the executor's: no network, a read-only root, the checkout
# mounted read-only at /workspace, only /tmp (64 MiB, noexec) writable. So the
# frontend's tracked files are copied to /tmp, the image's node_modules (built
# from package-lock.json, at its own path) is linked in beside them, and every
# cache and temporary file is kept under /tmp. The image's node_modules is
# never written to.
#
# What it prints last is one line, GAGOS-VITEST-JSON, then vitest's JSON
# report, so test output on stdout cannot be mistaken for the result.
set -u

mode="$1"
shift

work=/tmp/web
rm -rf "$work"
mkdir -p "$work" /tmp/cache /tmp/xdg
# A copy without node_modules (a checkout that has one must not shadow ours).
(cd /workspace/frontend && tar -cf - --exclude=./node_modules .) | (cd "$work" && tar -xf -)
# node_modules here is a directory of links, not one link: vite writes its
# bundled config into node_modules/.vite-temp, which must be writable.
mkdir "$work/node_modules"
for entry in /opt/web/node_modules/* /opt/web/node_modules/.bin; do
    ln -s "$entry" "$work/node_modules/$(basename "$entry")"
done
cd "$work" || exit 2

# The frontend's own config, plus one thing: modules keep the path they were
# imported by. Without it, vite sees a package at its real path in the image
# (/opt/web/node_modules/...) while a test that mocks
# '../../node_modules/<package>/...' names it under the copy, and the mock never
# matches (bodySpeechContinuity.test.tsx, measured on the first run).
cat >"$work/vitest.sandbox.config.mjs" <<'EOF'
import { mergeConfig } from 'vitest/config'
import base from './vite.config.js'

export default async (env) =>
  mergeConfig(typeof base === 'function' ? await base(env) : base, {
    resolve: { preserveSymlinks: true },
  })
EOF

export HOME=/tmp TMPDIR=/tmp XDG_CACHE_HOME=/tmp/xdg NODE_ENV=test CI=1
export npm_config_cache=/tmp/cache VITE_CACHE_DIR=/tmp/cache/vite

node node_modules/vitest/vitest.mjs "$mode" "$@" --config vitest.sandbox.config.mjs --run --passWithNoTests \
    --reporter=json --outputFile=/tmp/vitest.json --maxWorkers=2 \
    --cache=false >/tmp/vitest.log 2>&1
code=$?

echo
echo GAGOS-VITEST-JSON
if [ -f /tmp/vitest.json ]; then
    cat /tmp/vitest.json
else
    tail -n 20 /tmp/vitest.log >&2
fi
exit "$code"
