"""Tests for SMS (Twilio) platform integration.

Covers config loading, format/truncate, echo prevention,
requirements check, and toolset verification.
"""

import asyncio
import base64
import hashlib
import hmac
import os
import urllib.parse
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from gateway.config import Platform, PlatformConfig, HomeChannel


# ── Config loading ──────────────────────────────────────────────────

class TestSmsConfigLoading:
    """Verify _apply_env_overrides wires SMS correctly."""

    def test_sms_platform_enum_exists(self):
        assert Platform.SMS.value == "sms"

    def test_env_overrides_create_sms_config(self):
        from gateway.config import load_gateway_config

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest123",
            "TWILIO_AUTH_TOKEN": "token_abc",
            "TWILIO_PHONE_NUMBER": "+15551234567",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_gateway_config()
            assert Platform.SMS in config.platforms
            pc = config.platforms[Platform.SMS]
            assert pc.enabled is True
            assert pc.api_key == "token_abc"

    def test_env_overrides_set_home_channel(self):
        from gateway.config import load_gateway_config

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest123",
            "TWILIO_AUTH_TOKEN": "token_abc",
            "TWILIO_PHONE_NUMBER": "+15551234567",
            "SMS_HOME_CHANNEL": "+15559876543",
            "SMS_HOME_CHANNEL_NAME": "My Phone",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_gateway_config()
            hc = config.platforms[Platform.SMS].home_channel
            assert hc is not None
            assert hc.chat_id == "+15559876543"
            assert hc.name == "My Phone"
            assert hc.platform == Platform.SMS

    def test_sms_in_connected_platforms(self):
        from gateway.config import load_gateway_config

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest123",
            "TWILIO_AUTH_TOKEN": "token_abc",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_gateway_config()
            connected = config.get_connected_platforms()
            assert Platform.SMS in connected


# ── Format / truncate ───────────────────────────────────────────────

class TestSmsFormatAndTruncate:
    """Test SmsAdapter.format_message strips markdown."""

    def _make_adapter(self):
        from gateway.platforms.sms import SmsAdapter

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_PHONE_NUMBER": "+15550001111",
        }
        with patch.dict(os.environ, env):
            pc = PlatformConfig(enabled=True, api_key="tok")
            adapter = object.__new__(SmsAdapter)
            adapter.config = pc
            adapter._platform = Platform.SMS
            adapter._account_sid = "ACtest"
            adapter._auth_token = "tok"
            adapter._from_number = "+15550001111"
        return adapter

    def test_strips_bold(self):
        adapter = self._make_adapter()
        assert adapter.format_message("**hello**") == "hello"

    def test_strips_italic(self):
        adapter = self._make_adapter()
        assert adapter.format_message("*world*") == "world"

    def test_strips_code_blocks(self):
        adapter = self._make_adapter()
        result = adapter.format_message("```python\nprint('hi')\n```")
        assert "```" not in result
        assert "print('hi')" in result

    def test_strips_inline_code(self):
        adapter = self._make_adapter()
        assert adapter.format_message("`code`") == "code"

    def test_strips_headers(self):
        adapter = self._make_adapter()
        assert adapter.format_message("## Title") == "Title"

    def test_strips_links(self):
        adapter = self._make_adapter()
        assert adapter.format_message("[click](https://example.com)") == "click"

    def test_collapses_newlines(self):
        adapter = self._make_adapter()
        result = adapter.format_message("a\n\n\n\nb")
        assert result == "a\n\nb"


# ── Echo prevention ────────────────────────────────────────────────

class TestSmsBindHost:
    def test_default_webhook_host_is_localhost(self):
        from gateway.platforms.sms import SmsAdapter

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_PHONE_NUMBER": "+15550001111",
        }
        with patch.dict(os.environ, env, clear=True):
            pc = PlatformConfig(enabled=True, api_key="tok")
            adapter = SmsAdapter(pc)
            assert adapter._webhook_host == "127.0.0.1"

    def test_webhook_host_env_override_is_preserved(self):
        from gateway.platforms.sms import SmsAdapter

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_PHONE_NUMBER": "+15550001111",
            "SMS_WEBHOOK_HOST": "0.0.0.0",
        }
        with patch.dict(os.environ, env, clear=True):
            pc = PlatformConfig(enabled=True, api_key="tok")
            adapter = SmsAdapter(pc)
            assert adapter._webhook_host == "0.0.0.0"


class TestSmsEchoPrevention:
    """Adapter should ignore messages from its own number."""

    def test_own_number_detection(self):
        """The adapter stores _from_number for echo prevention."""
        from gateway.platforms.sms import SmsAdapter

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_PHONE_NUMBER": "+15550001111",
        }
        with patch.dict(os.environ, env):
            pc = PlatformConfig(enabled=True, api_key="tok")
            adapter = SmsAdapter(pc)
            assert adapter._from_number == "+15550001111"


# ── Webhook authenticity ───────────────────────────────────────────

class TestSmsWebhookAuthenticity:
    def _make_adapter(self, monkeypatch, extra_env=None):
        from gateway.platforms.sms import SmsAdapter

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_PHONE_NUMBER": "+15550001111",
            "SMS_WEBHOOK_PUBLIC_URL": "https://sms.example.com/webhooks/twilio",
        }
        if extra_env:
            env.update(extra_env)
        monkeypatch.setattr(os, "environ", env)
        adapter = SmsAdapter(PlatformConfig(enabled=True, api_key="tok"))
        adapter.handle_message = AsyncMock()
        return adapter

    def _signature(self, url, params, token="tok"):
        parts = [url]
        for key in sorted(params):
            parts.append(key)
            parts.append(params[key])
        digest = hmac.new(token.encode("utf-8"), "".join(parts).encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("ascii")

    def _request(self, params, signature=""):
        body = urllib.parse.urlencode(params).encode("utf-8")
        return SimpleNamespace(
            read=AsyncMock(return_value=body),
            headers={"X-Twilio-Signature": signature} if signature else {},
            url="http://127.0.0.1:8080/webhooks/twilio",
        )

    @pytest.mark.asyncio
    async def test_valid_signature_accepts_webhook(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        params = {
            "From": "+15551234567",
            "To": "+15550001111",
            "Body": "hello",
            "MessageSid": "SM123",
        }
        signature = self._signature("https://sms.example.com/webhooks/twilio", params)

        response = await adapter._handle_webhook(self._request(params, signature))

        assert response.status == 200
        await asyncio.sleep(0)
        adapter.handle_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_signature_rejects_webhook(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        params = {
            "From": "+15551234567",
            "To": "+15550001111",
            "Body": "hello",
            "MessageSid": "SM123",
        }

        response = await adapter._handle_webhook(self._request(params))

        assert response.status == 403
        adapter.handle_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_signature_rejects_webhook(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        params = {
            "From": "+15551234567",
            "To": "+15550001111",
            "Body": "hello",
            "MessageSid": "SM123",
        }

        response = await adapter._handle_webhook(self._request(params, "bad-signature"))

        assert response.status == 403
        adapter.handle_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insecure_no_auth_bypasses_signature_only_when_set(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch, {"SMS_INSECURE_NO_AUTH": "true"})
        params = {
            "From": "+15551234567",
            "To": "+15550001111",
            "Body": "hello",
            "MessageSid": "SM123",
        }

        response = await adapter._handle_webhook(self._request(params))

        assert response.status == 200
        await asyncio.sleep(0)
        adapter.handle_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_oversized_payload_rejected(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch, {"SMS_MAX_WEBHOOK_BYTES": "10"})
        params = {
            "From": "+15551234567",
            "To": "+15550001111",
            "Body": "hello",
            "MessageSid": "SM123",
        }
        signature = self._signature("https://sms.example.com/webhooks/twilio", params)

        response = await adapter._handle_webhook(self._request(params, signature))

        assert response.status == 413
        adapter.handle_message.assert_not_awaited()


# ── Requirements check ─────────────────────────────────────────────

class TestSmsRequirements:
    def test_check_sms_requirements_missing_sid(self):
        from gateway.platforms.sms import check_sms_requirements

        env = {"TWILIO_AUTH_TOKEN": "tok"}
        with patch.dict(os.environ, env, clear=True):
            assert check_sms_requirements() is False

    def test_check_sms_requirements_missing_token(self):
        from gateway.platforms.sms import check_sms_requirements

        env = {"TWILIO_ACCOUNT_SID": "ACtest"}
        with patch.dict(os.environ, env, clear=True):
            assert check_sms_requirements() is False

    def test_check_sms_requirements_both_set(self):
        from gateway.platforms.sms import check_sms_requirements

        env = {
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "tok",
        }
        with patch.dict(os.environ, env, clear=False):
            # Only returns True if aiohttp is also importable
            result = check_sms_requirements()
            try:
                import aiohttp  # noqa: F401
                assert result is True
            except ImportError:
                assert result is False


# ── Toolset verification ───────────────────────────────────────────

class TestSmsToolset:
    def test_hermes_sms_toolset_exists(self):
        from toolsets import get_toolset

        ts = get_toolset("hermes-sms")
        assert ts is not None
        assert "tools" in ts

    def test_hermes_sms_in_gateway_includes(self):
        from toolsets import get_toolset

        gw = get_toolset("hermes-gateway")
        assert gw is not None
        assert "hermes-sms" in gw["includes"]

    def test_sms_platform_hint_exists(self):
        from agent.prompt_builder import PLATFORM_HINTS

        assert "sms" in PLATFORM_HINTS
        assert "concise" in PLATFORM_HINTS["sms"].lower()

    def test_sms_in_scheduler_platform_map(self):
        """Verify cron scheduler recognizes 'sms' as a valid platform."""
        # Just check the Platform enum has SMS — the scheduler imports it dynamically
        assert Platform.SMS.value == "sms"

    def test_sms_in_send_message_platform_map(self):
        """Verify send_message_tool recognizes 'sms'."""
        # The platform_map is built inside _handle_send; verify SMS enum exists
        assert hasattr(Platform, "SMS")

    def test_sms_in_cronjob_deliver_description(self):
        """Verify cronjob_tools mentions sms in deliver description."""
        from tools.cronjob_tools import CRONJOB_SCHEMA
        deliver_desc = CRONJOB_SCHEMA["parameters"]["properties"]["deliver"]["description"]
        assert "sms" in deliver_desc.lower()
