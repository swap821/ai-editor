# Making the sandbox stronger, not just its absence visible

**Date:** 2026-09-14
**Follows:** #341 (M12 refuses to run with no isolation boundary)

#341 made a missing sandbox *visible and refused*. That is necessary and not
sufficient: refusing to run is not the same as having something worth running
inside. This is the other half — the container M12 depends on, made stronger and
made to prove it.

## The principle, applied to the sandbox instead of the gateway

M12's whole argument is that a control you have only *declared* is not a control
you have *got*. The 43-model cohort found two adjudication bugs that way, and
this repository has already shipped one container control that was present in
the argv and ineffective in the container: the workspace bind mount was
read-write by default, so a sandboxed command could write `aios/security/` — the
frozen spine that judges it — and `.aios/state/ORGAN_GREEN_LEDGER.json`, the
record of its own status. Live until 2026-08-19.

So the same question gets pointed at the sandbox: **which of these controls has
actually been executed, and which are just strings in an argv?**

### Executed before this change

| control | proven by |
|---|---|
| workspace bind mount is read-only | `test_the_sandbox_cannot_write_the_tree_that_judges_it` |
| scope roots remain writable | `test_the_sandbox_can_still_write_its_own_scope_root` |
| writable set matches the live authority | `test_the_writable_set_matches_the_declared_scope_roots` |

### Only ever argv strings — now executed

| control | new probe |
|---|---|
| `--network none` | `test_the_sandbox_has_no_network` |
| `--read-only` rootfs | `test_the_sandbox_root_filesystem_is_read_only` |
| `/tmp` tmpfs writable | `test_the_sandbox_can_still_write_its_tmpfs` |

Each asserts **both directions**, following the rule the existing file
established: "the network is unreachable" passes trivially in a container that
cannot run anything at all, so the network probe is paired with a control that
proves the interpreter runs. A probe that fails because `python` is missing can
never be mistaken for containment.

## The resource nothing bounded

`--memory`, `--cpus` and `--pids-limit` cap what a sandboxed command consumes
*inside* the container. **None of them cap what it writes** — and the scope roots
are bind-mounted read-write from the host, so the container's writable surface is
the operator's disk.

Taking the machine down that way requires no containment escape. It is a
supported operation performed to excess, by a command M12 accepted from a model
seconds after the model invented it.

Added:

```
--ulimit fsize=536870912    # 512 MiB, AIOS_CONTAINER_FSIZE_MB
--ulimit core=0
```

`RLIMIT_FSIZE` is per-file, so this is a ceiling on any single artefact rather
than a quota. 512 MiB is three orders of magnitude above the largest legitimate
thing a verification run produces (a test log) and far below "fills a laptop".
The constructor floors it at 16 MiB, so a caller passing `0` gets the floor
rather than `RLIMIT_FSIZE=0`, which would forbid writing *any* file and turn a
protection into an outage.

Core dumps are disabled because they are as large as the process image and carry
whatever was in memory when the command crashed — which, for a sandbox that just
ran model-authored code, is the wrong thing to leave on disk. Nothing here
debugs from a core file.

Both directions again: `test_the_sandbox_cannot_fill_the_host_disk` asserts a
1 GiB write is refused, and `test_the_fsize_cap_still_allows_a_normal_artefact`
asserts 1 MiB succeeds — because a cap that refuses ordinary output is an outage
wearing a security costume.

## Honest limits

- **The new container probes have not been executed on this machine.** Docker is
  not running here — which is what #341 was about. They are gated on
  `AIOS_EXECUTOR_INTEGRATION=1` and run in the CI job that builds the worker
  image and has a real daemon, alongside the existing containment probes. Their
  first real execution is that job, not this document.
- Argv construction for both `--ulimit` flags *is* asserted locally, in
  `test_docker_runner_uses_locked_down_container_contract`. That proves the flag
  is passed; the integration probes are what prove Docker honours it. Keeping
  both is the point — the 2026-08-19 escape passed the argv assertion.
- Probes avoid shell composition: `parse_argv` rejects `;&|<>` outright, so the
  Python one-liners inline their imports (`__import__('socket')...`) rather than
  using two statements.
- Not addressed: seccomp is left at Docker's default rather than pinned to an
  explicit profile, and no user-namespace remapping is configured. Both are real
  further hardening and neither is free to verify without a daemon here.
