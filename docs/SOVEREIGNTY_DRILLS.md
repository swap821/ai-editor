# Sovereignty drills — local-first, measured live

*Production hardening slice H6 (docs/PRODUCTION_HARDENING.md, on #453).*

```
python tools/sovereignty_drills.py            # all three, ~10 minutes on CPU
```

Each drill runs in a child process on throwaway data, through the **real
app**: real routes, router, failover and privacy filter, with the **real local
model** (the configured `AIOS_LLM_MODEL`) in Ollama's seat. Only the cloud
transport is controlled. The drills never hold a real cloud key. The report
goes to `<data>/drills/sovereignty.json`.

| Drill | Setup | Pass means |
|---|---|---|
| offline | Cloud-primary runtime profile; the process's network is cut at the socket (loopback only); a real Bedrock client tries the network | the local model answered |
| failover | Cloud-primary; Bedrock's transport throttles | the cloud was tried, then the local model answered (never tried = `not_reached`) |
| privacy | An explicit Bedrock pick; the real client and its privacy filter over a recording transport; a prompt carrying a credential and a local path | neither reached the transport |

## First live run — 2026-10-11, master `7cb550e9`, `qwen2.5:3b`

Evidence: `release/drills/sovereignty-2026-10-11.json`.

- **offline: pass.**
  - Bedrock was tried and blocked at the socket: 15 blocked lookups of the
    Bedrock endpoint, from botocore retries across its candidate models.
  - The local model answered: *"The code prints the string 'Paris' to the
    console."*
- **failover: pass.** Bedrock was tried 3 times, throttled each time, and the
  local model answered.
- **privacy: pass.** One cloud request was made, carrying no credential and no
  local path. The agent's system prompt **is** sent, scrubbed.

## What the drills found on the way

1. **`auto` never uses the cloud by default.**
   - Routing policy comes from the **runtime profile** (`aios/runtime/profiles.json`).
   - `local-first`, the built-in default, never routes `auto` to the cloud.
   - `operator`, the profile active on the operator's machine, allows cloud
     for reasoning and coding but **prefers local**, so a capable local model
     still wins.
   - Only `autonomous` puts the cloud first.
   - Failover and the network cut therefore only matter in a cloud-primary
     profile. That is where the drills run them, and the report says so.
2. **`AIOS_ROUTER_CLOUD_TASKS` does not decide `auto` routing.**
   - The variable is documented as the opt-in (config.py, bootstrap's `.env`
     template, the router's own docstring), but `/api/generate` reads the
     runtime profile.
   - The constitution's cloud policy still defaults to that variable, so
     there are two answers to "may this leave the machine?". This is the
     *one law* gap of slice H7. Which source is the law is the operator's
     decision.
3. **The privacy filter never claimed what one constant said.**
   - `_GENERIC_SYSTEM_PROMPT` ("never transmits the real one") was defined
     and never used.
   - The filter sends the system prompt with credentials, secrets and paths
     scrubbed. A cloud agent needs its instructions.
   - The dead constant is removed and the module docstring now says what it
     does.
4. **The fallback cloud catalogue is not this account's.**
   - When model discovery is unavailable, the router ranks a curated list
     headed by Claude 3.5 Sonnet, which this AWS account cannot invoke ("not
     available for this account").
   - With discovery working (the operator's key can list models), the live
     list is used instead.
