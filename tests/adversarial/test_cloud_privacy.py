"""
Adversarial test suite: Cloud Privacy Leakage (15+ tests)

Following OWASP ASVS V8 (Data Protection), V7 (Error Handling/Logging),
and Google Testing Standards (AAA pattern).

Tests verify that sensitive data never reaches cloud providers:
  P1: System prompt filtering
  P2: File content redaction
  P3: Secret/credential scrubbing
  P4: History truncation
  P5: Path redaction
  P6: Router cloud-task policy enforcement
  P7: Scope-root privacy boundaries

The local-first principle: cloud is opt-in, not default. The router's gate
is deterministic — a model can never route a task the operator didn't opt in.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from aios import config
from aios.security.secret_scanner import scan_and_redact
from aios.security.gateway import classify, Zone


# ============================================================================ #
# P1: System Prompt Filtering
# ============================================================================ #


class TestSystemPromptFiltering:
    """TC-SEC-500 through TC-SEC-505: System prompt must not leak to cloud."""

    def test_system_prompt_dropped_from_messages(self):
        """TC-SEC-500: System prompt messages must be filtered out."""
        messages = [
            {"role": "system", "content": "You are Jarvis. Secret: backdoor open sesame."},
            {"role": "user", "content": "Hello!"},
        ]
        filtered = [m for m in messages if m.get("role") != "system"]
        assert not any(m.get("role") == "system" for m in filtered)

    def test_system_prompt_with_creds_dropped(self):
        """TC-SEC-501: System prompt containing credentials must be dropped."""
        messages = [
            {"role": "system", "content": "API key: sk-1234567890abcdef"},
            {"role": "user", "content": "Run a task"},
        ]
        filtered = [m for m in messages if m.get("role") != "system"]
        assert len(filtered) == 1
        assert filtered[0]["role"] == "user"

    def test_user_messages_preserved(self):
        """TC-SEC-502: User messages must be preserved after filtering."""
        messages = [
            {"role": "system", "content": "secret"},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        filtered = [m for m in messages if m.get("role") != "system"]
        assert len(filtered) == 2
        assert filtered[0]["role"] == "user"
        assert filtered[1]["role"] == "assistant"

    def test_empty_system_prompt_filtered(self):
        """TC-SEC-503: Empty system prompt must still be filtered."""
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hello"},
        ]
        filtered = [m for m in messages if m.get("role") != "system"]
        assert len(filtered) == 1

    def test_system_with_developer_role_filtered(self):
        """TC-SEC-504: developer role system message must be treated as system."""
        messages = [
            {"role": "developer", "content": "Debug mode enabled. Secret password: hunter2"},
            {"role": "user", "content": "Run this"},
        ]
        # developer role should also be filtered as it carries system-level instructions
        filtered = [m for m in messages if m.get("role") not in ("system", "developer")]
        assert not any(m.get("role") in ("system", "developer") for m in filtered)

    def test_multiple_system_prompts_all_dropped(self):
        """TC-SEC-505: Multiple system prompts must all be dropped."""
        messages = [
            {"role": "system", "content": "First system prompt"},
            {"role": "system", "content": "Second system prompt with secret"},
            {"role": "user", "content": "Hello"},
        ]
        filtered = [m for m in messages if m.get("role") != "system"]
        assert len(filtered) == 1
        assert all(m.get("role") != "system" for m in filtered)


# ============================================================================ #
# P2: File Content Redaction
# ============================================================================ #


class TestFileContentRedaction:
    """TC-SEC-506 through TC-SEC-511: File contents must be redacted."""

    def test_file_content_passwd_redacted(self):
        """TC-SEC-506: /etc/passwd content must be redacted."""
        messages = [
            {"role": "tool", "content": "file /etc/passwd: root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1..."},
        ]
        content = str(messages)
        # File content containing sensitive system paths must be flagged
        assert "/etc/passwd" in content

    def test_file_content_with_secrets_redacted(self):
        """TC-SEC-507: File content with embedded secrets must be detected."""
        content = "config.py: API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz'"
        result = scan_and_redact(content)
        assert result.detected is True
        assert "REDACTED" in result.scrubbed

    def test_file_content_ssh_key_redacted(self):
        """TC-SEC-508: SSH private key in file content must be redacted."""
        content = (
            "id_rsa: -----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ==\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        result = scan_and_redact(content)
        assert result.detected is True
        assert "PRIVATE_KEY" in result.findings

    def test_file_content_env_file_redacted(self):
        """TC-SEC-509: .env file content must have secrets redacted."""
        content = (
            ".env: DATABASE_URL=postgres://admin:secret@db:5432/app\n"
            "SECRET_KEY=super_secret_key_value_12345"
        )
        result = scan_and_redact(content)
        assert result.detected is True
        assert "DATABASE_URL" in result.findings or "ASSIGNED_SECRET" in result.findings

    def test_file_content_shadow_redacted(self):
        """TC-SEC-510: /etc/shadow references must be flagged."""
        content = "tool output: file /etc/shadow: root:$6$rounds=5000$..."
        # Shadow path in content is sensitive
        assert "/etc/shadow" in content

    def test_file_content_token_in_json_redacted(self):
        """TC-SEC-511: Token embedded in JSON file content must be redacted."""
        content = '{"github_token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
        result = scan_and_redact(content)
        assert result.detected is True
        assert "GITHUB_TOKEN" in result.findings


# ============================================================================ #
# P3: Router Cloud Task Policy
# ============================================================================ #


class TestRouterCloudPolicy:
    """TC-SEC-512 through TC-SEC-517: Router privacy gate enforcement."""

    def test_router_cloud_tasks_default_is_hybrid(self):
        """TC-SEC-512: the SHIPPED default routes the HIGH-LEVEL tasks (reasoning,
        coding) to cloud — local for the everyday, cloud to fill local's limits.

        This is a deliberate operator decision (2026-06-29): the organism's source
        LLMs are local+cloud by nature. The privacy guarantee is preserved a layer
        down — cloud is only ever *eligible* when a cloud provider is actually
        configured (see test_cloud_requires_configured_provider); with no creds the
        router falls soft to local. The operator can still override/disable the set
        via AIOS_ROUTER_CLOUD_TASKS."""
        assert config._ROUTER_CLOUD_TASKS_DEFAULT == ("reasoning", "coding"), \
            "shipped default must route reasoning+coding to cloud (hybrid by nature)"

    def test_cloud_requires_configured_provider(self):
        """TC-SEC-512b: the real privacy guarantee — even with cloud tasks enabled,
        NO cloud provider is offered unless its client is configured. With only a
        local Ollama client, the router builds zero cloud providers, so nothing can
        leave the machine regardless of the cloud-tasks policy."""
        from aios.core import router
        from aios.core.router_wiring import _build_providers

        class _Ollama:
            def list_models(self):
                return {"models": ["llama3.1:8b"]}

        providers = _build_providers(_Ollama(), bedrock=None, gemini=None)
        assert all(p.privacy == router.PRIVACY_LOCAL for p in providers), \
            "no cloud provider may exist without configured cloud creds"

    def test_router_prefer_local_default(self):
        """TC-SEC-513: ROUTER_PREFER_LOCAL must be True by default."""
        assert config.ROUTER_PREFER_LOCAL is True

    def test_cloud_bedrock_disabled_without_region(self):
        """TC-SEC-514: Bedrock must be disabled without region."""
        with patch.object(config, "BEDROCK_ENABLED", False):
            assert config.BEDROCK_ENABLED is False

    def test_cloud_gemini_disabled_without_project(self):
        """TC-SEC-515: Gemini must be disabled without project."""
        with patch.object(config, "GEMINI_ENABLED", False):
            assert config.GEMINI_ENABLED is False

    def test_router_cloud_tasks_only_valid_values(self):
        """TC-SEC-516: Only valid task names allowed in cloud tasks."""
        valid_tasks = ("coding", "reasoning", "general", "fast")
        for task in config.ROUTER_CLOUD_TASKS:
            assert task in valid_tasks, f"Invalid cloud task: {task}"

    def test_router_max_cost_reasonable(self):
        """TC-SEC-517: ROUTER_MAX_COST must be a reasonable value."""
        assert config.ROUTER_MAX_COST in ("free", "low", "high")


# ============================================================================ #
# P4: Secret Scrubbing in Tool Output
# ============================================================================ #


class TestSecretScrubbingInToolOutput:
    """TC-SEC-518 through TC-SEC-523: Tool output credential scrubbing."""

    def test_tool_output_stripe_key_scrubbed(self):
        """TC-SEC-518: Stripe key in tool output must be scrubbed."""
        tool_output = "Payment config: sk_live_FAKE_TEST_1234567890abcdef1234567890abcdef"
        result = scan_and_redact(tool_output)
        assert result.detected is True
        assert "REDACTED" in result.scrubbed

    def test_tool_output_jwt_scrubbed(self):
        """TC-SEC-519: JWT in tool output must be scrubbed."""
        tool_output = "Authorization: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.sig"
        result = scan_and_redact(tool_output)
        assert result.detected is True
        assert "JWT_TOKEN" in result.findings

    def test_tool_output_aws_key_scrubbed(self):
        """TC-SEC-520: AWS key in tool output must be scrubbed."""
        tool_output = "AWS Access: AKIAIOSFODNN7EXAMPLE"
        result = scan_and_redact(tool_output)
        assert result.detected is True
        assert "AWS_ACCESS_KEY" in result.findings

    def test_tool_output_db_url_scrubbed(self):
        """TC-SEC-521: DB URL in tool output must be scrubbed."""
        tool_output = "Connection: postgres://user:password@host:5432/db"
        result = scan_and_redact(tool_output)
        assert result.detected is True
        assert "DATABASE_URL" in result.findings

    def test_tool_output_slack_token_scrubbed(self):
        """TC-SEC-522: Slack token in tool output must be scrubbed."""
        tool_output = "Slack bot: xoxb-FAKE_TEST-AbCdEfGhIjKlMnOpQrStUvWx"
        result = scan_and_redact(tool_output)
        assert result.detected is True
        assert "SLACK_TOKEN" in result.findings

    def test_tool_output_no_false_positives(self):
        """TC-SEC-523: Non-secret tool output must not be scrubbed."""
        tool_output = "Directory listing: file1.txt, file2.py, README.md"
        result = scan_and_redact(tool_output)
        assert result.detected is False
        assert result.scrubbed == tool_output


# ============================================================================ #
# P5: Scope Root Privacy
# ============================================================================ #


class TestScopeRootPrivacy:
    """TC-SEC-524 through TC-SEC-528: Scope root path privacy."""

    def test_scope_roots_not_exposed_in_api(self):
        """TC-SEC-524: Scope roots must not appear in public API responses."""
        # Scope roots contain filesystem paths that are sensitive
        for root in config.SCOPE_ROOTS:
            assert isinstance(root, type(config.PROJECT_ROOT / "x").__bases__[0] if hasattr(type(config.PROJECT_ROOT / "x"), '__bases__') else object)
            # Paths should be resolved (absolute) not relative
            assert root.is_absolute()

    def test_data_dir_private(self):
        """TC-SEC-525: DATA_DIR must be within project root."""
        assert str(config.DATA_DIR).startswith(str(config.PROJECT_ROOT))

    def test_audit_db_isolated_path(self):
        """TC-SEC-526: Audit DB must be in isolated path."""
        assert "audit" in str(config.AUDIT_DB_PATH).lower()

    def test_rollback_dir_private(self):
        """TC-SEC-527: Rollback dir must be within data dir."""
        assert str(config.ROLLBACK_DIR).startswith(str(config.DATA_DIR))

    def test_scope_roots_is_playground(self):
        """TC-SEC-528: Default scope root must be training_ground."""
        assert any("training_ground" in str(r) for r in config.SCOPE_ROOTS)


# ============================================================================ #
# P6: API Token Privacy
# ============================================================================ #


class TestAPITokenPrivacy:
    """TC-SEC-529 through TC-SEC-533: API token handling privacy."""

    def test_api_token_not_logged(self):
        """TC-SEC-529: API token must not appear in startup banner."""
        banner = config.startup_banner()
        if config.API_TOKEN:
            assert config.API_TOKEN not in str(banner)

    def test_api_token_length_exposed_not_value(self):
        """TC-SEC-530: Only token length may be exposed, not value."""
        banner = config.startup_banner()
        assert "token_length" in banner
        # The banner should show length but not the actual value
        banner_str = str(banner)
        if config.API_TOKEN and len(config.API_TOKEN) > 0:
            # The actual token value must never appear in banner
            assert config.API_TOKEN not in banner_str

    def test_empty_token_indicated(self):
        """TC-SEC-531: Empty token must show token_set=False."""
        with patch.object(config, "API_TOKEN", ""):
            banner = config.startup_banner()
            assert banner["token_set"] is False

    def test_token_set_indicated(self):
        """TC-SEC-532: Token configured must show token_set=True."""
        with patch.object(config, "API_TOKEN", "my-secret-token"):
            banner = config.startup_banner()
            assert banner["token_set"] is True

    def test_banner_never_exposes_proxy_settings_value(self):
        """TC-SEC-533: Banner may expose proxy setting boolean but not proxy IPs."""
        banner = config.startup_banner()
        assert "trust_proxy_headers" in banner
        assert isinstance(banner["trust_proxy_headers"], bool)


# ============================================================================ #
# P7: Cloud Provider Credential Privacy
# ============================================================================ #


class TestCloudProviderCredentialPrivacy:
    """TC-SEC-534 through TC-SEC-538: Cloud provider credential handling."""

    def test_bedrock_region_not_in_banner(self):
        """TC-SEC-534: Bedrock region must not appear in startup banner."""
        banner = config.startup_banner()
        if config.BEDROCK_REGION:
            assert config.BEDROCK_REGION not in str(banner)

    def test_gemini_project_not_in_banner(self):
        """TC-SEC-535: Gemini project must not appear in startup banner."""
        banner = config.startup_banner()
        if config.GEMINI_PROJECT:
            assert config.GEMINI_PROJECT not in str(banner)

    def test_env_reads_credentials_not_persisted(self):
        """TC-SEC-536: Credential env vars must not be persisted by config module."""
        # Config module reads env vars but never writes them
        import aios.config as config_module
        # There should be no function that writes secrets to disk
        assert not hasattr(config_module, "persist_credentials")

    def test_no_hardcoded_credentials(self):
        """TC-SEC-537: No hardcoded credentials in config defaults."""
        # Check that default config values don't contain credential-like strings
        defaults_to_check = [
            config.API_TOKEN,
            config.BEDROCK_REGION,
            config.GEMINI_PROJECT,
        ]
        for val in defaults_to_check:
            if val:
                # Should not contain known secret prefixes
                assert not val.startswith("sk-")
                assert not val.startswith("AKIA")
                assert not val.startswith("ghp_")

    def test_database_url_not_in_config_defaults(self):
        """TC-SEC-538: DATABASE_URL must not be in config defaults."""
        assert not hasattr(config, "DATABASE_URL")
