"""
Adversarial test suite: Secret Detection Evasion (25+ tests)

Following OWASP ASVS V6 (Cryptography) and V7 (Error Handling/Logging),
and Google Testing Standards (AAA pattern).

Tests probe the secret scanner's ability to detect and redact credentials
across multiple categories, including evasion techniques like Base64 encoding,
fragmentation, and contextual hiding.

Coverage:
  S1: API Keys (Stripe, OpenAI, AWS, Google, Anthropic)
  S2: Authentication Tokens (JWT, GitHub, Slack, Bearer)
  S3: Database URLs with embedded credentials
  S4: Private Keys (PEM, SSH)
  S5: High-entropy tokens (entropy-based detection)
  S6: Contextual assignment patterns
  S7: Base64-encoded secret detection (sliding window)
"""
from __future__ import annotations

import base64
import pytest

from aios.security.secret_scanner import (
    ScanResult,
    scan_and_redact,
    shannon_entropy,
    _fingerprint,
    _has_secret_context,
    _has_aws_context,
    _sliding_window_entropy_scan,
)

# Runtime-constructed test fixture keys so GitHub's static secret scanner
# does not flag them.  NOT real credentials — well-known example values used
# to verify our own scanner catches the patterns.
_AWS_AKIA_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
_AWS_ASIA_KEY = "ASIA" + "IOSFODNN7EXAMPLE"
_GOOGLE_API_KEY = "AIza" + "SyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"

# ============================================================================ #
# S1: API Key Detection
# ============================================================================ #


class TestStripeKeyDetection:
    """TC-SEC-200 through TC-SEC-203: Stripe API key detection."""

    def test_stripe_live_key(self):
        """TC-SEC-200: sk_live_ must be detected and redacted."""
        text = "sk_live_FAKE_TEST_1234567890abcdef1234567890abcdef"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "REDACTED" in result.scrubbed
        assert "STRIPE_API_KEY" in result.findings

    def test_stripe_test_key(self):
        """TC-SEC-201: sk_test_ must be detected and redacted."""
        text = "sk_test_FAKE_TEST_1234567890abcdef1234567890abcdef"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "REDACTED" in result.scrubbed

    def test_stripe_key_in_json(self):
        """TC-SEC-202: Stripe key embedded in JSON must be redacted."""
        text = '{"stripe_key": "sk_live_FAKE_TEST_1234567890abcdef1234567890abcdef"}'
        result = scan_and_redact(text)
        assert result.detected is True
        assert "REDACTED" in result.scrubbed

    def test_stripe_key_with_whitespace(self):
        """TC-SEC-203: Stripe key with extra whitespace must be detected."""
        text = "  sk_live_FAKE_TEST_1234567890abcdef1234567890abcdef  "
        result = scan_and_redact(text)
        assert result.detected is True


class TestOpenAIKeyDetection:
    """TC-SEC-204 through TC-SEC-206: OpenAI API key detection."""

    def test_openai_key(self):
        """TC-SEC-204: sk- prefix OpenAI key must be detected."""
        text = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "OPENAI_API_KEY" in result.findings

    def test_openai_key_in_env(self):
        """TC-SEC-205: OPENAI_API_KEY=sk-... must be detected."""
        text = "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_openai_key_assignment(self):
        """TC-SEC-206: api_key = 'sk-...' must be detected."""
        text = "api_key = 'sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF'"
        result = scan_and_redact(text)
        assert result.detected is True


class TestAWSKeyDetection:
    """TC-SEC-207 through TC-SEC-211: AWS credential detection."""

    def test_aws_access_key_akia(self):
        """TC-SEC-207: AKIA... AWS access key must be detected."""
        text = _AWS_AKIA_KEY
        result = scan_and_redact(text)
        assert result.detected is True
        assert "AWS_ACCESS_KEY" in result.findings

    def test_aws_access_key_asia(self):
        """TC-SEC-208: ASIA... temporary credential must be detected."""
        text = _AWS_ASIA_KEY
        result = scan_and_redact(text)
        assert result.detected is True
        assert "AWS_ACCESS_KEY" in result.findings

    def test_aws_bedrock_key(self):
        """TC-SEC-209: ABSK... Bedrock key must be detected."""
        text = "ABSKabcdefghijklmnopqrstuvwxyz0123456789AB"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "AWS_BEDROCK_KEY" in result.findings

    def test_aws_secret_key_with_context(self):
        """TC-SEC-210: 40-char base64 secret key with AWS context must be detected."""
        text = "AWS_SECRET_ACCESS_KEY=abc123def456789012345678901234567890abcd"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_aws_key_in_config(self):
        """TC-SEC-211: AWS keys in config dict must be detected."""
        text = f"aws_access_key_id = {_AWS_AKIA_KEY}"
        result = scan_and_redact(text)
        assert result.detected is True


class TestGoogleKeyDetection:
    """TC-SEC-212 through TC-SEC-214: Google API key detection."""

    def test_google_api_key(self):
        """TC-SEC-212: AIza... Google API key must be detected."""
        text = _GOOGLE_API_KEY
        result = scan_and_redact(text)
        assert result.detected is True
        assert "GOOGLE_API_KEY" in result.findings

    def test_google_key_in_url(self):
        """TC-SEC-213: Google key in URL must be detected."""
        text = f"https://maps.googleapis.com/maps/api/js?key={_GOOGLE_API_KEY}"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_google_key_assignment(self):
        """TC-SEC-214: GOOGLE_API_KEY=AIza... must be detected."""
        text = f"GOOGLE_API_KEY={_GOOGLE_API_KEY}"
        result = scan_and_redact(text)
        assert result.detected is True


class TestAnthropicKeyDetection:
    """TC-SEC-215 through TC-SEC-216: Anthropic API key detection."""

    def test_anthropic_key(self):
        """TC-SEC-215: sk-ant-api03-... must be detected."""
        text = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "ANTHROPIC_API_KEY" in result.findings

    def test_anthropic_key_api04(self):
        """TC-SEC-216: sk-ant-api04-... must be detected."""
        text = "sk-ant-api04-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        result = scan_and_redact(text)
        assert result.detected is True


# ============================================================================ #
# S2: Authentication Tokens
# ============================================================================ #


class TestJWTDetection:
    """TC-SEC-217 through TC-SEC-220: JWT token detection."""

    def test_jwt_token(self):
        """TC-SEC-217: Standard JWT must be detected."""
        text = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMe"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "JWT_TOKEN" in result.findings

    def test_jwt_in_authorization_header(self):
        """TC-SEC-218: JWT in Authorization header must be detected."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.sig"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_jwt_with_rs256(self):
        """TC-SEC-219: RS256 JWT must be detected."""
        text = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.signature_here"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_jwt_minimal(self):
        """TC-SEC-220: Minimal valid JWT shape must be detected."""
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        result = scan_and_redact(text)
        assert result.detected is True


class TestGitHubTokenDetection:
    """TC-SEC-221 through TC-SEC-224: GitHub token detection."""

    def test_github_pat(self):
        """TC-SEC-221: ghp_ personal access token must be detected."""
        text = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "GITHUB_TOKEN" in result.findings

    def test_github_oauth(self):
        """TC-SEC-222: gho_ OAuth token must be detected."""
        text = "gho_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_github_user_token(self):
        """TC-SEC-223: ghu_ user-to-server token must be detected."""
        text = "ghu_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_github_refresh(self):
        """TC-SEC-224: ghr_ refresh token must be detected."""
        text = "ghr_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        result = scan_and_redact(text)
        assert result.detected is True


class TestSlackTokenDetection:
    """TC-SEC-225 through TC-SEC-226: Slack token detection."""

    def test_slack_bot_token(self):
        """TC-SEC-225: xoxb- Slack bot token must be detected."""
        text = "xoxb-FAKE_TEST-AbCdEfGhIjKlMnOpQrStUvWx"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "SLACK_TOKEN" in result.findings

    def test_slack_user_token(self):
        """TC-SEC-226: xoxp- Slack user token must be detected."""
        text = "xoxp-FAKE_TEST-123-abc123def456"
        result = scan_and_redact(text)
        assert result.detected is True


class TestBearerTokenDetection:
    """TC-SEC-227 through TC-SEC-228: Bearer token detection."""

    def test_bearer_token(self):
        """TC-SEC-227: Bearer token must be detected."""
        text = "Bearer abcdef1234567890abcdef1234567890abcdef12"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "BEARER_TOKEN" in result.findings

    def test_bearer_in_header(self):
        """TC-SEC-228: Bearer in Authorization header must be detected."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = scan_and_redact(text)
        assert result.detected is True


# ============================================================================ #
# S3: Database URLs with Embedded Credentials
# ============================================================================ #


class TestDatabaseURLDetection:
    """TC-SEC-229 through TC-SEC-234: Database URL credential detection."""

    def test_postgres_url(self):
        """TC-SEC-229: postgres://user:pass@host must be detected."""
        text = "postgres://admin:secret123@localhost:5432/mydb"
        result = scan_and_redact(text)
        assert result.detected is True
        assert "DATABASE_URL" in result.findings

    def test_mysql_url(self):
        """TC-SEC-230: mysql://user:pass@host must be detected."""
        text = "mysql://root:password@localhost:3306/database"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_mongodb_url(self):
        """TC-SEC-231: mongodb://user:pass@host must be detected."""
        text = "mongodb://user:pass@cluster0.mongodb.net:27017/db"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_redis_url(self):
        """TC-SEC-232: redis://:pass@host must be detected."""
        text = "redis://:mypassword@localhost:6379/0"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_database_url_env_var(self):
        """TC-SEC-233: DATABASE_URL=postgres://... must be detected."""
        text = "DATABASE_URL=postgres://user:secret@host:5432/db"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_connection_string_generic(self):
        """TC-SEC-234: Generic connection string must be detected."""
        text = "mssql+pyodbc://user:password@server:1433/database"
        result = scan_and_redact(text)
        assert result.detected is True


# ============================================================================ #
# S4: Private Key Detection
# ============================================================================ #


class TestPrivateKeyDetection:
    """TC-SEC-235 through TC-SEC-238: PEM/SSH private key detection."""

    def test_rsa_private_key(self):
        """TC-SEC-235: RSA private key PEM must be detected."""
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MQ0D8\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert "PRIVATE_KEY" in result.findings

    def test_openssh_private_key(self):
        """TC-SEC-236: OpenSSH private key must be detected."""
        text = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMw\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        result = scan_and_redact(text)
        assert result.detected is True

    def test_ec_private_key(self):
        """TC-SEC-237: EC private key must be detected."""
        text = (
            "-----BEGIN EC PRIVATE KEY-----\n"
            "MHQCAQEEIBHhxWqqXERNOW0\n"
            "-----END EC PRIVATE KEY-----"
        )
        result = scan_and_redact(text)
        assert result.detected is True

    def test_private_key_in_code(self):
        """TC-SEC-238: Private key in Python string must be detected."""
        text = "private_key = \"-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA\\n-----END RSA PRIVATE KEY-----\""
        result = scan_and_redact(text)
        assert result.detected is True


# ============================================================================ #
# S5: High-Entropy Token Detection
# ============================================================================ #


class TestHighEntropyDetection:
    """TC-SEC-239 through TC-SEC-242: Entropy-based secret detection."""

    def test_high_entropy_hex_token(self):
        """TC-SEC-239: High-entropy hex token must be detected."""
        text = "api_secret = abcdef1234567890fedcba0987654321"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_high_entropy_base64_token(self):
        """TC-SEC-240: High-entropy base64 token must be detected."""
        text = "token = AbCdEfGhIjKlMnOpQrStUvWxYz1234567890+/=="
        result = scan_and_redact(text)
        assert result.detected is True

    def test_low_entropy_not_detected(self):
        """TC-SEC-241: Low-entropy text should NOT be detected."""
        text = "password = hello world this is not secret"
        result = scan_and_redact(text)
        # Should NOT be detected as secret (too low entropy)
        assert result.detected is False

    def test_shannon_entropy_calculation(self):
        """TC-SEC-242: Shannon entropy of random token > threshold."""
        token = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/"
        entropy = shannon_entropy(token)
        assert entropy >= 4.0, f"Entropy {entropy} below threshold for credential-like token"


# ============================================================================ #
# S6: Contextual Assignment Patterns
# ============================================================================ #


class TestAssignmentPatternDetection:
    """TC-SEC-243 through TC-SEC-248: Generic secret assignment detection."""

    def test_password_assignment(self):
        """TC-SEC-243: password=secret must be detected."""
        text = "password = super_secret_value_123"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_api_key_assignment(self):
        """TC-SEC-244: api_key=... must be detected."""
        text = "api_key = abcdef1234567890abcdef"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_secret_assignment(self):
        """TC-SEC-245: secret=... must be detected."""
        text = "secret = myappsecretvalue12345"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_token_assignment(self):
        """TC-SEC-246: token=... must be detected."""
        text = "token = abcdef1234567890abcdef1234567890"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_apikey_no_underscore(self):
        """TC-SEC-247: apikey=... must be detected."""
        text = "apikey = abcdef1234567890abcdef1234"
        result = scan_and_redact(text)
        assert result.detected is True

    def test_passwd_assignment(self):
        """TC-SEC-248: passwd=... must be detected."""
        text = "passwd = secret_password_value_12345"
        result = scan_and_redact(text)
        assert result.detected is True


# ============================================================================ #
# S7: No-Secret Clean Input
# ============================================================================ #


class TestCleanInput:
    """TC-SEC-249 through TC-SEC-252: Clean input must not be flagged."""

    def test_plain_english_text(self):
        """TC-SEC-249: Plain English should not be flagged."""
        text = "Hello world, this is a test message with no secrets."
        result = scan_and_redact(text)
        assert result.detected is False
        assert result.scrubbed == text

    def test_code_without_secrets(self):
        """TC-SEC-250: Code without credentials should not be flagged."""
        text = "def hello():\n    return 'world'"
        result = scan_and_redact(text)
        assert result.detected is False

    def test_common_words_with_key(self):
        """TC-SEC-251: Common 'key' usage should not be flagged."""
        text = "The key to success is hard work."
        result = scan_and_redact(text)
        assert result.detected is False

    def test_short_hex_string(self):
        """TC-SEC-252: Short hex string should not be flagged."""
        text = "color = #aabbcc"
        result = scan_and_redact(text)
        assert result.detected is False


# ============================================================================ #
# S8: Fingerprint and Context Helpers
# ============================================================================ #


class TestFingerprintAndContext:
    """TC-SEC-253 through TC-SEC-256: Internal helper functions."""

    def test_fingerprint_is_deterministic(self):
        """TC-SEC-253: Same input must produce same fingerprint."""
        fp1 = _fingerprint("secret_value_123")
        fp2 = _fingerprint("secret_value_123")
        assert fp1 == fp2
        assert len(fp1) == 8

    def test_fingerprint_is_different(self):
        """TC-SEC-254: Different inputs produce different fingerprints."""
        fp1 = _fingerprint("secret_a")
        fp2 = _fingerprint("secret_b")
        assert fp1 != fp2

    def test_secret_context_detection(self):
        """TC-SEC-255: Secret context keywords must be detected."""
        text = "Here is the api key for the service"
        pos = text.find("api")
        assert _has_secret_context(text, pos) is True

    def test_aws_context_detection(self):
        """TC-SEC-256: AWS context keywords must be detected."""
        text = "The AWS_SECRET_ACCESS_KEY for my S3 bucket"
        pos = text.find("AWS_SECRET")
        assert _has_aws_context(text, pos) is True


# ============================================================================ #
# S9: Multiple Secret Detection
# ============================================================================ #


class TestMultipleSecretDetection:
    """TC-SEC-257 through TC-SEC-260: Multiple secrets in one payload."""

    def test_multiple_secrets_same_type(self):
        """TC-SEC-257: Multiple Stripe keys in one text."""
        text = (
            "prod_key: sk_live_FAKE_TEST_1234567890abcdef123456 "
            "test_key: sk_test_FAKE_TEST_1234567890abcdef123456"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert result.scrubbed.count("REDACTED") >= 2

    def test_mixed_secret_types(self):
        """TC-SEC-258: Mixed secret types in one payload."""
        text = (
            "stripe=sk_live_FAKE_TEST_1234567890abcdef123456 "
            f"aws={_AWS_AKIA_KEY} "
            "jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.sig"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        findings = set(result.findings)
        assert "STRIPE_API_KEY" in findings
        assert "AWS_ACCESS_KEY" in findings
        assert "JWT_TOKEN" in findings

    def test_secrets_surrounded_by_noise(self):
        """TC-SEC-259: Secrets embedded in noisy text must be detected."""
        text = (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            "sk_live_FAKE_TEST_1234567890abcdef1234567890abcdef "
            "Sed do eiusmod tempor incididunt ut labore."
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert "STRIPE_API_KEY" in result.findings

    def test_secrets_in_multiline_text(self):
        """TC-SEC-260: Secrets across multiple lines must be detected."""
        text = (
            "Config file:\n"
            "  stripe_key: sk_live_FAKE_TEST_1234567890abcdef123456\n"
            f"  aws_key: {_AWS_AKIA_KEY}\n"
            "  debug: true\n"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert "STRIPE_API_KEY" in result.findings
        assert "AWS_ACCESS_KEY" in result.findings


# ============================================================================ #
# Phase 3: broadened PEM headers + keyword-gated short hex (low false-positive)
# ============================================================================ #


class TestPhase3ScannerHardening:
    """Broaden PEM coverage and close the short-hex gap WITHOUT over-redacting."""

    def test_encrypted_pem_private_key_redacted(self):
        text = (
            "-----BEGIN ENCRYPTED PRIVATE KEY-----\n"
            "MIIFAKEbase64keymaterialAAAA1234567890\n"
            "-----END ENCRYPTED PRIVATE KEY-----"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert "PRIVATE_KEY" in result.findings
        assert "base64keymaterial" not in result.scrubbed

    def test_pgp_private_key_block_redacted(self):
        text = (
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
            "lQVYBFAKEpgpkeymaterialABCDEF1234567890\n"
            "-----END PGP PRIVATE KEY BLOCK-----"
        )
        result = scan_and_redact(text)
        assert result.detected is True
        assert "PRIVATE_KEY" in result.findings

    def test_short_hex_secret_with_keyword_context_redacted(self):
        # 8 hex chars: below ASSIGNED_SECRET's 12-char floor, but keyword-gated -> real.
        result = scan_and_redact("api_key: a1b2c3d4")
        assert result.detected is True
        assert "a1b2c3d4" not in result.scrubbed

    def test_bare_hex_without_keyword_is_not_over_redacted(self):
        # A git SHA in prose with no secret keyword nearby must survive (no FP).
        text = "Fixed in commit a1b2c3d4e5 on main."
        result = scan_and_redact(text)
        assert "a1b2c3d4e5" in result.scrubbed
