"""GAGOS's own identity, its credits, its clerk, and its day (2026-10-30).

The operator: GAGOS makes its own PRs for its own work, Claude Code (chief) and
Codex review it, the frontier models and GAGOS's clerk get their credit, and
GAGOS runs the loop itself. Pinned here, without a network or a model:

* GAGOS's GitHub App asks for the least it needs, its JWT verifies, and its
  token is narrowed to one repository and two permissions and never appears in
  argv; its keys are local-only, never handed to production;
* the models are credited by name, with an address that is nobody's inbox;
* the clerk summarises a disagreement, or its refusal is recorded;
* the day follows the rules agreed with Codex: blocked while GAGOS's previous
  PR is open (recorded, never caught up), one batch of at most two proposals
  per UTC day, and finishing reviews is not a new batch.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from aios.operations import github_app as gha
from aios.operations import keystore as ks
from tools import gagos_daily as tool
from tests.test_gagos_daily import _proposal


# --------------------------------------------------------------------- the App


def test_the_app_asks_for_the_least_a_delivery_needs() -> None:
    manifest = gha.manifest(owner="o", repo="r", redirect_url="http://127.0.0.1:1/cb")
    assert manifest["default_permissions"] == {
        "contents": "write",
        "pull_requests": "write",
        "metadata": "read",
    }
    assert (
        manifest["public"] is False and manifest["hook_attributes"]["active"] is False
    )
    assert "administration" not in manifest["default_permissions"]


def _rsa_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return key, pem


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_the_app_jwt_is_short_lived_and_verifies() -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key, pem = _rsa_pem()
    token = gha.app_jwt("123", pem, now=1_000_000)
    header, payload, signature = token.split(".")
    claims = json.loads(_unb64(payload))
    assert json.loads(_unb64(header)) == {"alg": "RS256", "typ": "JWT"}
    assert claims == {"iat": 999_940, "exp": 999_940 + 540, "iss": "123"}
    key.public_key().verify(
        _unb64(signature),
        f"{header}.{payload}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


class _Response:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = (
            status,
            payload,
            json.dumps(payload),
        )

    def json(self):
        return self._payload


def test_the_token_is_one_repository_and_two_permissions() -> None:
    _key, pem = _rsa_pem()
    calls: list = []

    def http(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        if url.endswith("/installation"):
            return _Response(200, {"id": 42})
        return _Response(201, {"token": "ghs_secret"})

    creds = gha.AppCredentials(app_id="1", slug="gagos-o", private_key_pem=pem)
    assert gha.installation_token(creds, owner="o", repo="r", http=http) == "ghs_secret"
    assert calls[1] == (
        "POST",
        "https://api.github.com/app/installations/42/access_tokens",
        {
            "repositories": ["r"],
            "permissions": {"contents": "write", "pull_requests": "write"},
        },
    )


def test_a_refusal_from_github_is_an_error_not_a_token() -> None:
    _key, pem = _rsa_pem()
    creds = gha.AppCredentials(app_id="1", slug="s", private_key_pem=pem)
    with pytest.raises(gha.GitHubAppError, match="404"):
        gha.installation_token(
            creds,
            owner="o",
            repo="r",
            http=lambda *a, **k: _Response(404, {"message": "Not Found"}),
        )


def test_the_push_token_never_appears_in_argv_or_a_url() -> None:
    env = gha.git_auth_env("ghs_secret")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert (
        "ghs_secret" not in env["GIT_CONFIG_VALUE_0"]
    )  # base64, in the environment only
    assert (
        base64.b64decode(env["GIT_CONFIG_VALUE_0"].split()[-1]).decode()
        == "x-access-token:ghs_secret"
    )


def test_the_apps_keys_are_local_only() -> None:
    store = ks.MemoryKeystore()
    for name in ks.LOCAL_ONLY:
        store.set(name, "value")
    assert ks.production_environment(store) == {}, (
        "production is never handed GAGOS's App"
    )
    assert gha.stored_credentials(store) == gha.AppCredentials(
        "value", "value", "value"
    )
    with pytest.raises(ValueError):
        store.set("SOMETHING_ELSE", "x")


def test_no_app_means_the_operators_login_and_the_pr_says_so(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(ks, "default_keystore", lambda: ks.MemoryKeystore())
    assert tool._github_app(tmp_path) is None
    assert "no GitHub identity of its own" in tool.PR_FOOTER_NO_APP
    assert "its own GitHub App" in tool.PR_FOOTER_APP
    # Honest about merging (Codex's post-merge review of #566): a rule GAGOS
    # keeps, not a lock GitHub enforces.
    assert "cannot merge" not in tool.PR_FOOTER_APP
    assert (
        "no code that merges" in tool.PR_FOOTER_APP
        and "not a lock" in tool.PR_FOOTER_APP
    )


# --------------------------------------------------------------------- credits


def test_the_frontier_models_are_credited_by_name() -> None:
    assert tool.model_name("mistral.mistral-large-3-675b-instruct").startswith(
        "Mistral Large 3"
    )
    assert tool.model_name("gpt-6.1-sol") == "GPT-6.1 sol (OpenAI, via Codex)"
    assert tool.model_name("some-new-model") == "some-new-model"
    assert tool.credit_email("mistral.mistral-large-3-675b-instruct").endswith(
        "@models.invalid"
    )


def _both(led, pid, codex="accept", claude="accept"):
    led.record_review(pid, "codex", model="gpt-6.1-sol", verdict=codex, reason="c")
    led.record_review(
        pid, "claude", model="claude-opus-5-5", verdict=claude, reason="k"
    )


def test_a_gagos_pr_credits_who_did_the_work(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _proposal(led)
    _both(led, pid)
    text = tool.report(led, in_pr=[pid])
    assert "**Credits**" in text
    assert "reviewed by Claude Code, chief reviewer: Claude Opus 5.5" in text
    assert "reviewed by Codex: GPT-6.1 sol" in text
    assert "orchestrated, checked and delivered by GAGOS" in text


# --------------------------------------------------------------------- the clerk


class _Clerk:
    def __init__(self, status, output=None, reason=None):
        self.result = SimpleNamespace(
            status=status,
            model_id="qwen2.5-coder:7b" if status == "completed" else "none",
            structured_output=output,
            failure_reason=reason,
        )
        self.requests: list = []

    def run_advisory_job(self, request):
        self.requests.append(request)
        return self.result


def test_the_clerk_summarises_a_disagreement_locally(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _proposal(led)
    _both(led, pid, codex="reject")
    [p] = led.disagreements_without_clerk()
    clerk = _Clerk(
        "completed",
        {"summary": "Codex doubts the JSX runtime.", "crux": "tsconfig jsx"},
    )
    job = tool.clerk_summarise(p, led.reviews(pid), service=clerk)
    assert (
        job["summary"] == "Codex doubts the JSX runtime."
        and job["model"] == "qwen2.5-coder:7b"
    )
    request = clerk.requests[0]
    assert request.job_profile.value == "summarise_disagreement"
    assert "Codex: reject: c" in request.redacted_payload


def test_a_clerk_with_no_admitted_model_is_recorded_not_hidden(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    pid = _proposal(led)
    _both(led, pid, claude="reject")
    from aios.operations import clerk_admin

    refusing = _Clerk("rejected", reason="no admitted model may take this job")
    monkeypatch.setattr(clerk_admin, "default_service", lambda: refusing)
    assert tool.cmd_clerk(SimpleNamespace()) == 0
    assert refusing.requests, "the real clerk path was asked"
    assert led.clerk_job(pid)["status"] == "rejected"
    assert led.disagreements_without_clerk() == [], "summarised once, refusal included"
    assert "GAGOS's clerk could not summarise: no admitted model" in tool.report(led)


# --------------------------------------------------------------------- the day


@pytest.fixture()
def day(tmp_path, monkeypatch):
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool.config, "DATA_DIR", tmp_path)
    calls: list = []
    monkeypatch.setattr(
        tool, "cmd_propose", lambda a: calls.append(("propose", a.budget)) or 0
    )
    monkeypatch.setattr(
        tool, "cmd_review", lambda a: calls.append(("review", a.reviewer)) or 0
    )
    monkeypatch.setattr(tool, "cmd_clerk", lambda a: calls.append(("clerk",)) or 0)
    monkeypatch.setattr(
        tool, "cmd_deliver", lambda a: calls.append(("deliver", a.open_pr)) or 0
    )
    monkeypatch.setattr(
        tool, "_git", lambda root, *args: calls.append(("git",) + args) and ""
    )
    args = SimpleNamespace(project=str(tmp_path), model="m", region="r")
    return led, calls, args


def test_a_day_is_blocked_while_gagoss_previous_pr_is_open(day, monkeypatch) -> None:
    led, calls, args = day
    pid = _proposal(led)
    led.record_delivery(
        pid, branch="b", outcome="delivered", pr_url="https://github.com/o/r/pull/9"
    )
    monkeypatch.setattr(tool, "_pr_state", lambda url: "OPEN")
    assert tool.cmd_daily(args) == 0
    assert ("propose", 2) not in calls and not any(c[0] == "deliver" for c in calls)
    [d] = led.days()
    assert d["status"] == "blocked" and "pull/9" in d["reason"]
    assert ("review", "claude") in calls, "finishing reviews is not a new batch"


def test_an_unknown_pr_state_blocks_the_day(day, monkeypatch) -> None:
    led, calls, args = day
    pid = _proposal(led)
    led.record_delivery(pid, branch="b", outcome="delivered", pr_url="u")
    monkeypatch.setattr(tool, "_pr_state", lambda url: "UNKNOWN")
    tool.cmd_daily(args)
    assert led.days()[0]["status"] == "blocked"


def test_one_batch_of_at_most_two_proposals_per_day(day, monkeypatch) -> None:
    led, calls, args = day
    monkeypatch.setattr(tool, "_pr_state", lambda url: "MERGED")
    assert tool.cmd_daily(args) == 0
    assert ("propose", 2) in calls and ("deliver", True) in calls
    assert calls.index(("review", "claude")) < calls.index(("review", "codex")), (
        "the chief first"
    )
    calls.clear()
    _proposal(led)  # today's batch exists now
    tool.cmd_daily(args)
    assert not any(c[0] == "propose" for c in calls)


def test_the_day_writes_its_report(day, monkeypatch, tmp_path) -> None:
    _led, _calls, args = day
    monkeypatch.setattr(tool, "_pr_state", lambda url: "MERGED")
    tool.cmd_daily(args)
    assert list((tmp_path / "gagos_daily" / "reports").glob("*.md"))


# --------------------------------------------------------------------- direction


def _finding(rel, rule="no-unused-vars"):
    return dw.Finding(rel=rel, rule=rule, warnings=((1, 1, "x"),))


def test_the_operators_direction_steers_the_work(tmp_path) -> None:
    path = tmp_path / "direction.json"
    assert dw.load_direction(path) == dw.Direction(), "none on file is no direction"
    direction = dw.set_direction(
        path,
        dw.Direction(
            notes=("Calm, quiet surfaces; never touch the palette.",),
            focus=("frontend/src/workbench/",),
            avoid=("frontend/src/livingMirror/being/",),
        ),
        said="calm surfaces, workbench first, leave the being alone",
    )
    assert direction.updated and dw.load_direction(path) == direction
    work = direction.steer(
        [
            _finding("frontend/src/a.jsx"),
            _finding("frontend/src/livingMirror/being/B.tsx"),
            _finding("frontend/src/workbench/W.jsx"),
        ]
    )
    assert [f.rel for f in work] == [
        "frontend/src/workbench/W.jsx",
        "frontend/src/a.jsx",
    ]
    history = (tmp_path / "direction_history.jsonl").read_text(encoding="utf-8")
    assert "leave the being alone" in history


def test_the_direct_command_records_and_reports_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tool.config, "DATA_DIR", tmp_path)
    args = SimpleNamespace(
        note=["Polish before features."],
        rules=None,
        focus=None,
        avoid=None,
        clear=False,
        said="polish first",
    )
    assert tool.cmd_direct(args) == 0
    led = dw.DailyLedger(tmp_path / "l.db")
    assert "Polish before features." in tool.report(led)


# --------------------------------------------------------------------- the eye


def test_the_eye_uses_gagos_own_profiles(tmp_path, monkeypatch) -> None:
    from tools import gagos_eye as eye

    monkeypatch.setattr(eye.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(eye, "chrome", lambda: "chrome.exe")
    argv = eye.shot_argv("http://x", tmp_path / "o.png", size="800x450", wait_ms=1000)
    assert "--headless=new" in argv and "--window-size=800,450" in argv
    assert f"--user-data-dir={tmp_path / 'gagos_eye' / 'shot-profile'}" in argv
    assert (
        f"--user-data-dir={tmp_path / 'gagos_eye' / 'window-profile'}"
        in eye.window_argv("http://x")
    )


def test_an_eye_that_saw_nothing_says_so(tmp_path, monkeypatch) -> None:
    from tools import gagos_eye as eye

    monkeypatch.setattr(eye.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(eye, "chrome", lambda: "chrome.exe")
    with pytest.raises(eye.EyeUnavailable):
        eye.shot("http://x", tmp_path / "o.png", run=lambda *a, **k: None)


# --------------------------------------------------------------------- Codex's review of #566


def _committed(led, branch="gagos/daily-x"):
    pid = _proposal(led)
    _both(led, pid)
    led.record_delivery(pid, branch=branch, outcome="committed", commit_sha="c")
    return pid


def test_work_is_delivered_only_when_its_pr_exists(tmp_path, monkeypatch) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _committed(led)
    assert led.proposals()[0]["status"] == "committed"
    monkeypatch.setattr(tool, "_branch_prs", lambda root, branch, app: [])

    def push_fails(root, *args):
        raise tool.subprocess.CalledProcessError(1, "git push")

    monkeypatch.setattr(tool, "_git", push_fails)
    with pytest.raises(tool.PublishFailed):
        tool.publish(led, tmp_path, "gagos/daily-x", [pid], None)
    assert led.proposals()[0]["status"] == "committed", "a failed push is not delivered"
    assert led.pending_publication() == {"gagos/daily-x": [pid]}


def test_a_pr_whose_response_was_lost_is_found_not_opened_twice(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _committed(led)
    monkeypatch.setattr(tool, "_github_app", lambda root: None)
    monkeypatch.setattr(
        tool,
        "_branch_prs",
        lambda root, branch, app: [
            {"url": "https://github.com/o/r/pull/7", "state": "OPEN", "head": "c"}
        ],
    )
    monkeypatch.setattr(tool, "_git", lambda *a: pytest.fail("nothing is pushed again"))
    assert tool.publish_pending(led, tmp_path) is None
    assert led.proposals()[0]["status"] == "delivered"
    assert led.pr_urls() == ["https://github.com/o/r/pull/7"]


def test_unpublished_work_blocks_the_next_day(tmp_path, monkeypatch) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _committed(led)
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(tool, "_github_app", lambda root: None)

    def cannot(root, branch, app):
        raise tool.PublishFailed("offline")

    monkeypatch.setattr(tool, "_branch_prs", cannot)
    calls: list = []
    monkeypatch.setattr(tool, "cmd_propose", lambda a: calls.append("propose") or 0)
    monkeypatch.setattr(tool, "cmd_review", lambda a: 0)
    monkeypatch.setattr(tool, "cmd_clerk", lambda a: 0)
    monkeypatch.setattr(tool, "cmd_deliver", lambda a: calls.append("deliver") or 0)
    tool.cmd_daily(SimpleNamespace(project=str(tmp_path), model="m", region="r"))
    assert calls == [] and led.days()[0]["status"] == "blocked"


def test_the_day_is_claimed_atomically(tmp_path) -> None:
    """Codex's review of #566: two overlapping runs each proposed two."""
    import threading

    led = dw.DailyLedger(tmp_path / "l.db")
    wins: list = []
    barrier = threading.Barrier(8)

    def claim():
        barrier.wait()
        wins.append(dw.DailyLedger(tmp_path / "l.db").reserve_day("2026-10-31"))

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1
    led.record_day("2026-11-01", "blocked", "previous PR open")
    assert led.reserve_day("2026-11-01"), "a day only blocked can still run later"
    assert not led.reserve_day("2026-11-01")


def test_a_pr_body_carries_no_raw_direction(tmp_path, monkeypatch) -> None:
    """Codex's review of #566: his raw direction notes reached GitHub."""
    monkeypatch.setattr(tool.config, "DATA_DIR", tmp_path)
    dw.set_direction(
        tmp_path / "gagos_daily" / "direction.json",
        dw.Direction(notes=("keep C:/Users/kumar/private/plan.md in mind",)),
        said="x",
    )
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _proposal(led)
    body = tool.report(
        led,
        in_pr=[pid],
        scrub=lambda t: t.replace("C:/Users/kumar/private/plan.md", "[PATH REDACTED]"),
    )
    assert "private/plan.md" not in body and "[PATH REDACTED]" in body


# --------------------------------------------------------------------- Codex's post-merge review of #566


def test_an_old_pr_never_absorbs_new_work(tmp_path, monkeypatch) -> None:
    """A's PR on the branch was merged; B, committed later on the same branch
    name, must not be marked delivered against A's URL."""
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _committed(led)  # its commit is "c"
    monkeypatch.setattr(
        tool,
        "_branch_prs",
        lambda root, branch, app: [
            {"url": "https://github.com/o/r/pull/7", "state": "MERGED", "head": "a"}
        ],
    )
    monkeypatch.setattr(tool, "_git", lambda *a: pytest.fail("nothing is pushed"))
    with pytest.raises(tool.PublishFailed, match="another commit"):
        tool.publish(led, tmp_path, "gagos/daily-x", [pid], None)
    assert led.proposals()[0]["status"] == "committed"
    assert led.pending_publication() == {"gagos/daily-x": [pid]}
    assert led.pr_urls() == []


def test_publication_pushes_the_exact_commit(tmp_path, monkeypatch) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    pid = _committed(led)
    monkeypatch.setattr(tool, "_branch_prs", lambda root, branch, app: [])
    pushed: list = []
    monkeypatch.setattr(tool, "_git", lambda root, *args: pushed.append(args) or "")
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda argv, **k: SimpleNamespace(stdout="https://github.com/o/r/pull/9\n"),
    )
    assert tool.publish(led, tmp_path, "gagos/daily-x", [pid], None).endswith("/9")
    assert pushed == [("push", "-q", "origin", "c:refs/heads/gagos/daily-x")]
    assert led.proposals()[0]["status"] == "delivered"


def test_a_later_delivery_the_same_day_gets_its_own_branch(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "_today", lambda: "2026-11-01")
    assert tool.delivery_branch(led) == "gagos/daily-2026-11-01"
    stale = _proposal(led)
    led.record_delivery(stale, branch="gagos/daily-2026-11-01", outcome="stale")
    assert tool.delivery_branch(led) == "gagos/daily-2026-11-01", (
        "a delivery that committed nothing does not use the branch up"
    )
    _committed(led, branch="gagos/daily-2026-11-01")
    assert tool.delivery_branch(led) == "gagos/daily-2026-11-01-2"
    _committed(led, branch="gagos/daily-2026-11-01-2")
    assert tool.delivery_branch(led) == "gagos/daily-2026-11-01-3"


def test_a_blocked_hour_never_clears_the_days_claim(day, monkeypatch) -> None:
    """Codex's reproduction: PR states MERGED, UNKNOWN, MERGED and a batch that
    failed without rows ran two batches on one UTC day."""
    led, calls, args = day
    earlier = led.record_proposal(
        dw.Finding(rel="frontend/src/A.jsx", rule="no-unused-vars", warnings=()),
        base_text="a",
        base_commit="c" * 40,
        model="m",
        new_text="b",
        verdict=dw.StaticVerdict(True, "ok", 1),
        day="2026-01-01",
    )
    led.record_delivery(earlier, branch="b", outcome="delivered", pr_url="u")
    states = iter(["MERGED", "UNKNOWN", "MERGED"])
    monkeypatch.setattr(tool, "_pr_state", lambda url: next(states))
    monkeypatch.setattr(
        tool, "cmd_propose", lambda a: calls.append(("propose", a.budget)) or 1
    )
    for _ in range(3):
        tool.cmd_daily(args)
    assert calls.count(("propose", 2)) == 1, "one batch per UTC day"
    assert [d["status"] for d in led.days()] == ["ran"]


def test_an_earlier_ledgers_run_day_keeps_its_claim(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "l.db"
    dw.DailyLedger(path)
    db = sqlite3.connect(path)
    with db:  # as the first version left it
        db.execute("DROP TABLE day_claims")
        db.execute("INSERT INTO days VALUES ('2026-10-31', 'ran', NULL, 't')")
    db.close()
    assert not dw.DailyLedger(path).reserve_day("2026-10-31")


def test_claudes_failed_process_gives_no_verdict(monkeypatch) -> None:
    from tests.test_gagos_daily import _fake_run

    monkeypatch.setattr(tool, "_claude_executable", lambda: "claude.exe")
    accepting = {
        "is_error": False,
        "structured_output": {"verdict": "accept", "reason": "fine"},
    }
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        _fake_run(stdout=json.dumps(accepting), stderr="crashed", returncode=1),
    )
    with pytest.raises(tool.ReviewUnavailable, match="exited 1"):
        tool.run_claude("p", model=None, timeout_s=5)


def test_a_broken_app_never_becomes_the_operators_login(monkeypatch, tmp_path) -> None:
    store = ks.MemoryKeystore()
    for name in ks.LOCAL_ONLY:
        store.set(name, "value")
    monkeypatch.setattr(ks, "default_keystore", lambda: store)
    monkeypatch.setattr(tool, "_owner_repo", lambda root: ("o", "r"))

    def refused(*a, **k):
        raise gha.GitHubAppError("installation revoked")

    monkeypatch.setattr(gha, "installation_token", refused)
    with pytest.raises(tool.PublishFailed, match="revoked"):
        tool._github_app(tmp_path)

    def unreadable():
        raise ks.KeystoreUnavailable("locked")

    monkeypatch.setattr(ks, "default_keystore", unreadable)
    with pytest.raises(tool.PublishFailed, match="cannot be read"):
        tool._github_app(tmp_path)


@pytest.mark.parametrize(
    "present",
    [
        ("GAGOS_GITHUB_APP_ID",),
        ("GAGOS_GITHUB_APP_SLUG",),
        ("GAGOS_GITHUB_APP_PRIVATE_KEY",),
        ("GAGOS_GITHUB_APP_ID", "GAGOS_GITHUB_APP_SLUG"),
        ("GAGOS_GITHUB_APP_ID", "GAGOS_GITHUB_APP_PRIVATE_KEY"),
        ("GAGOS_GITHUB_APP_SLUG", "GAGOS_GITHUB_APP_PRIVATE_KEY"),
    ],
)
def test_a_partly_stored_app_never_becomes_the_operators_login(
    present, monkeypatch, tmp_path
) -> None:
    """Codex's review of #567: a missing private key read as "no App"."""
    store = ks.MemoryKeystore()
    for name in present:
        store.set(name, "value")
    monkeypatch.setattr(ks, "default_keystore", lambda: store)
    with pytest.raises(tool.PublishFailed, match="partly stored"):
        tool._github_app(tmp_path)


def test_any_failure_of_a_stored_app_stops_publication(monkeypatch, tmp_path) -> None:
    store = ks.MemoryKeystore()
    for name in ks.LOCAL_ONLY:
        store.set(name, "value")
    monkeypatch.setattr(ks, "default_keystore", lambda: store)
    monkeypatch.setattr(tool, "_owner_repo", lambda root: ("o", "r"))

    def offline(*a, **k):
        raise OSError("network unreachable")

    monkeypatch.setattr(gha, "installation_token", offline)
    with pytest.raises(tool.PublishFailed, match="network unreachable"):
        tool._github_app(tmp_path)


def test_nothing_gagos_runs_calls_a_merge() -> None:
    """That GAGOS never merges is a rule of its code: pinned here."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    for rel in ("tools/gagos_daily.py", "aios/operations/github_app.py"):
        source = (repo / rel).read_text(encoding="utf-8")
        assert not re.search(r"/merge\b|[\"']merge[\"']", source), rel


def test_a_missing_port_manifest_owns_the_whole_port_root(tmp_path) -> None:
    from aios.maintenance import frontend_static as fs

    managed = tmp_path / fs.PORT_ROOT / "Managed.jsx"
    managed.parent.mkdir(parents=True)
    managed.write_text("x", encoding="utf-8")
    rel = f"{fs.PORT_ROOT}/Managed.jsx"
    manifest = tmp_path / fs.PORT_MANIFEST
    assert rel in fs.port_managed(tmp_path), "missing"
    for broken in ("{", "[]", '{"version": 2}', '{"files": ["Managed.jsx"]}'):
        manifest.write_text(broken, encoding="utf-8")
        assert rel in fs.port_managed(tmp_path), broken
    manifest.write_text('{"files": {}}', encoding="utf-8")
    assert fs.port_managed(tmp_path) == frozenset(), (
        "an explicit empty one owns nothing"
    )
    manifest.write_text('{"files": {"Managed.jsx": "sha"}}', encoding="utf-8")
    assert fs.port_managed(tmp_path) == {rel}


def test_a_failed_look_keeps_the_last_one(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from tools import gagos_eye as eye

    monkeypatch.setattr(eye.config, "DATA_DIR", tmp_path)
    out = tmp_path / "o.png"
    out.write_bytes(b"previous")

    def no_chrome():
        raise eye.EyeUnavailable("Google Chrome is not installed")

    monkeypatch.setattr(eye, "chrome", no_chrome)
    with pytest.raises(eye.EyeUnavailable):
        eye.shot("http://x", out, run=pytest.fail)
    assert out.read_bytes() == b"previous"
    monkeypatch.setattr(eye, "chrome", lambda: "chrome.exe")
    with pytest.raises(eye.EyeUnavailable):
        eye.shot("http://x", out, size="wide", run=pytest.fail)
    with pytest.raises(eye.EyeUnavailable):
        eye.shot("http://x", out, run=lambda *a, **k: None)
    assert out.read_bytes() == b"previous"
    assert list(tmp_path.glob("*.capturing*")) == []

    def chrome_writing(code):
        def run(argv, **kwargs):
            target = next(a for a in argv if a.startswith("--screenshot="))
            Path(target.split("=", 1)[1]).write_bytes(b"new")
            return SimpleNamespace(returncode=code)

        return run

    # Codex's review of #567: a failing Chrome that wrote partial bytes.
    with pytest.raises(eye.EyeUnavailable, match="exited 1"):
        eye.shot("http://x", out, run=chrome_writing(1))
    assert out.read_bytes() == b"previous"
    assert list(tmp_path.glob("*.capturing*")) == []
    eye.shot("http://x", out, run=chrome_writing(0))
    assert out.read_bytes() == b"new"


def test_the_eye_opens_pages_only(tmp_path, monkeypatch) -> None:
    from tools import gagos_eye as eye

    monkeypatch.setattr(eye.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(eye, "chrome", lambda: "chrome.exe")
    for bad in (
        "--user-data-dir=C:/elsewhere",
        "file:///C:/x.html",
        "javascript:x",
        "x",
    ):
        with pytest.raises(eye.EyeUnavailable):
            eye.window_argv(bad)
        with pytest.raises(eye.EyeUnavailable):
            eye.shot_argv(bad, tmp_path / "o.png", size="800x450", wait_ms=1)
    assert eye.window_argv("http://127.0.0.1:5173/")[-1] == "http://127.0.0.1:5173/"


def test_a_changed_silencer_is_refused() -> None:
    from tests.test_gagos_daily import FINDING, _result

    before = (
        "// eslint-disable-next-line no-console\nconsole.log(1);\nconst unused = 1;\n"
    )
    after = "// eslint-disable-next-line no-unused-vars\nconsole.log(1);\nconst unused = 1;\n"
    verdict = dw.static_verdict(FINDING, before, after, _result(), _result())
    assert not verdict.passed and "disable comment" in verdict.reason


def test_an_unchanged_silencer_cannot_be_retargeted() -> None:
    """Codex's review of #567: deleting the line under an unchanged
    disable-next-line moves it onto the next warning."""
    from tests.test_gagos_daily import FINDING, _result

    before = (
        "// eslint-disable-next-line no-unused-vars\n"
        "const hidden = 1;\n"
        "const visible = 2;\n"
    )
    after = "// eslint-disable-next-line no-unused-vars\nconst visible = 2;\n"
    verdict = dw.static_verdict(FINDING, before, after, _result(), _result())
    assert not verdict.passed and "disable comment" in verdict.reason
    kept = before.replace("const visible = 2;\n", "")
    assert dw.static_verdict(FINDING, before, kept, _result(), _result()).passed, (
        "a silencer left over the same line is not a change"
    )
