# The learning loop, closed once on a live model — 2026-09-07

**Result: the loop closes. A replay re-created a deleted file with the
bytes a human had approved, driven from a real model's turn.**

The matrix (`2026-09-07-matrix.md`) constructs each situation directly.
This does not: a real local model drives a real `ToolAgent` turn, that
turn's own steps become a skill, the compiler decides what to compile,
and the replay runs against the filesystem.

```
model   : qwen2.5:1.5b
sandbox : C:\Users\kumar\AppData\Local\Temp\replay-session-3kum1qpr\training_ground
flag    : AIOS_REPLAY_APPROVED_WRITES = True

[1] real turn on a live model, human-approved creation
    events: 79   file landed: True
    approval recorded by the real path: True
[2] skill -> playbook
    compiled: 1   playbooks: 1
[3] delete the target, replay the playbook
    events : ['cerebellum_step', 'cerebellum_step_done']
    verdict: cerebellum_step_done 
    output : Created greeting.py (44 bytes, 2 line(s)):
--- /dev/null
+++ b/greeting.py
@@ -0,0 +1,2 @@
+def hello(name):
+    return

  file restored by the replay : True
  bytes match the approval    : True
```

## What the run actually establishes

The chain, with nothing stubbed in the middle:

```
real Ollama turn -> approved write lands -> approval recorded by the real path
-> skill recorded -> playbook compiled -> target deleted -> replay re-creates it
```

The recording step matters most. `record_approval` fires from `ToolAgent`'s
approved-creations path — the same code a resumed HTTP turn runs — rather than
being called directly by the harness. Until this run, nothing had ever shown
that hook firing outside a unit test.

## Two things the first attempt got wrong

**It picked an embedding model.** `_pick_model` chose the smallest installed
model, which was `nomic-embed-text`. That answers `/api/tags` and cannot hold a
conversation, so the "real turn" produced 4 events and nothing useful. Smallest
is not the same as smallest model that can chat.

**It asked the wrong object for the playbooks.** A `Cerebellum` loads its cache
on construction, so one built *before* the compile reported zero playbooks while
the database held one. `compiled: 1  playbooks: 0` — a contradiction visible only
because both numbers were printed. Had the script printed just one of them it
would have looked like a compilation failure and sent me after the wrong thing.

## What it does NOT establish

**Not a rate.** One session. The open question from #316 is untouched: if
recorded files are usually stale by replay time, playbooks abstain and the
practical gain is near zero. That needs sustained real use.

**Not the HTTP capability layer.** The approval is supplied through
`ToolAgent`'s approved-creations path, not through enrollment and capability
tokens. That layer is exercised by the organ-55 drivers and adds nothing to the
question this run asks.

**Not a general-model claim.** `qwen2.5:1.5b` is the smallest chat model
installed here, chosen so the run is about the loop rather than the GPU.
