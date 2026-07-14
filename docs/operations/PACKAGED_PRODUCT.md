# GAGOS packaged product

Slice 23 provides one local launcher and one production browser origin.

## Launcher

From the repository root:

```text
gagos start --profile production
gagos status
gagos open
gagos stop
```

`gagos` starts the Compose topology for production and demo. Development may
use `gagos start --profile development` to run the API directly for debugging.
That development path is intentionally not available to the production
profile. If Docker is unavailable, production start refuses instead of
silently executing workers on the host.

Production requires operator-supplied, non-placeholder values for
`AIOS_API_TOKEN`, `AIOS_EXECUTOR_TOKEN`, and
`AIOS_GRAFANA_ADMIN_PASSWORD`. The launcher never prints those values or
creates default credentials. Store them in the local environment or `.env`
with appropriate file permissions.

## Same-origin topology

The gateway serves the built frontend on `127.0.0.1:3000` by default and
proxies `/api/`, `/health`, and `/metrics` to the control plane over the
private Compose network. The control-plane port is loopback-only; browser
requests use relative URLs in the production build, so session cookies and
SSE remain same-origin.

The executor remains the only service that receives the Docker socket. The
launcher does not perform project migration, overwrite project roots, or
invent a project enrollment; those remain explicit operator flows.
