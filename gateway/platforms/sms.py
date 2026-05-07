"""SMS (Twilio) platform adapter.

Connects to the Twilio REST API for outbound SMS and runs an aiohttp
webhook server to receive inbound messages.

Shares credentials with the optional telephony skill — same env vars:
  - TWILIO_ACCOUNT_SID
  - TWILIO_AUTH_TOKEN
  - TWILIO_PHONE_NUMBER  (E.164 from-number, e.g. +15551234567)

Gateway-specific env vars:
  - SMS_WEBHOOK_HOST       (default 127.0.0.1)
  - SMS_WEBHOOK_PORT       (default 8080)
  - SMS_WEBHOOK_PUBLIC_URL (external URL used for Twilio signature validation)
  - SMS_INSECURE_NO_AUTH   (true to bypass signature validation for local tests only)
  - SMS_MAX_WEBHOOK_BYTES  (default 65536)
  - SMS_ALLOWED_USERS      (comma-separated E.164 phone numbers)
  - SMS_ALLOW_ALL_USERS    (true/false)
  - SMS_HOME_CHANNEL       (phone number for cron delivery)
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
MAX_SMS_LENGTH = 1600  # ~10 SMS segments
DEFAULT_WEBHOOK_PORT = 8080
DEFAULT_WEBHOOK_HOST = "127.0.0.1"
DEFAULT_MAX_WEBHOOK_BYTES = 65_536

# E.164 phone number pattern for redaction
_PHONE_RE = re.compile(r"\+[1-9]\d{6,14}")


def _redact_phone(phone: str) -> str:
    """Redact a phone number for logging: +15551234567 -> +1555***4567."""
    if not phone:
        return "<none>"
    if len(phone) <= 8:
        return phone[:2] + "***" + phone[-2:] if len(phone) > 4 else "****"
    return phone[:5] + "***" + phone[-4:]


def check_sms_requirements() -> bool:
    """Check if SMS adapter dependencies are available."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))


class SmsAdapter(BasePlatformAdapter):
    """
    Twilio SMS <-> Hermes gateway adapter.

    Each inbound phone number gets its own Hermes session (multi-tenant).
    Replies are always sent from the configured TWILIO_PHONE_NUMBER.
    """

    MAX_MESSAGE_LENGTH = MAX_SMS_LENGTH

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.SMS)
        self._account_sid: str = os.environ["TWILIO_ACCOUNT_SID"]
        self._auth_token: str = os.environ["TWILIO_AUTH_TOKEN"]
        self._from_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")
        self._webhook_port: int = int(
            os.getenv("SMS_WEBHOOK_PORT", str(DEFAULT_WEBHOOK_PORT))
        )
        self._webhook_host: str = os.getenv("SMS_WEBHOOK_HOST", DEFAULT_WEBHOOK_HOST).strip() or DEFAULT_WEBHOOK_HOST
        self._webhook_public_url: str = os.getenv("SMS_WEBHOOK_PUBLIC_URL", "").strip()
        self._insecure_no_auth: bool = os.getenv("SMS_INSECURE_NO_AUTH", "").lower() in ("true", "1", "yes")
        self._max_webhook_bytes: int = int(os.getenv("SMS_MAX_WEBHOOK_BYTES", str(DEFAULT_MAX_WEBHOOK_BYTES)))
        self._runner = None
        self._http_session: Optional["aiohttp.ClientSession"] = None

    def _basic_auth_header(self) -> str:
        """Build HTTP Basic auth header value for Twilio."""
        creds = f"{self._account_sid}:{self._auth_token}"
        encoded = base64.b64encode(creds.encode("ascii")).decode("ascii")
        return f"Basic {encoded}"

    # ------------------------------------------------------------------
    # Required abstract methods
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        import aiohttp
        from aiohttp import web

        if not self._from_number:
            logger.error("[sms] TWILIO_PHONE_NUMBER not set — cannot send replies")
            return False

        app = web.Application()
        app.router.add_post("/webhooks/twilio", self._handle_webhook)
        app.router.add_get("/health", lambda _: web.Response(text="ok"))

        if self._webhook_host == "0.0.0.0":
            logger.warning("[sms] Listening on 0.0.0.0 exposes the Twilio webhook server to the network. Use only behind trusted auth/proxy controls.")
        if self._insecure_no_auth:
            logger.warning("[sms] SMS_INSECURE_NO_AUTH=true disables Twilio webhook signature validation. Use only for local testing.")

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._webhook_host, self._webhook_port)
        await site.start()
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        self._running = True

        logger.info(
            "[sms] Twilio webhook server listening on %s:%d, from: %s",
            self._webhook_host,
            self._webhook_port,
            _redact_phone(self._from_number),
        )
        return True

    async def disconnect(self) -> None:
        if self._http_session:
            await self._http_session.close()
            self._http_session = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._running = False
        logger.info("[sms] Disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        import aiohttp

        formatted = self.format_message(content)
        chunks = self.truncate_message(formatted)
        last_result = SendResult(success=True)

        url = f"{TWILIO_API_BASE}/{self._account_sid}/Messages.json"
        headers = {
            "Authorization": self._basic_auth_header(),
        }

        session = self._http_session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        try:
            for chunk in chunks:
                form_data = aiohttp.FormData()
                form_data.add_field("From", self._from_number)
                form_data.add_field("To", chat_id)
                form_data.add_field("Body", chunk)

                try:
                    async with session.post(url, data=form_data, headers=headers) as resp:
                        body = await resp.json()
                        if resp.status >= 400:
                            error_msg = body.get("message", str(body))
                            logger.error(
                                "[sms] send failed to %s: %s %s",
                                _redact_phone(chat_id),
                                resp.status,
                                error_msg,
                            )
                            return SendResult(
                                success=False,
                                error=f"Twilio {resp.status}: {error_msg}",
                            )
                        msg_sid = body.get("sid", "")
                        last_result = SendResult(success=True, message_id=msg_sid)
                except Exception as e:
                    logger.error("[sms] send error to %s: %s", _redact_phone(chat_id), e)
                    return SendResult(success=False, error=str(e))
        finally:
            # Close session only if we created a fallback (no persistent session)
            if not self._http_session and session:
                await session.close()

        return last_result

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "dm"}

    # ------------------------------------------------------------------
    # SMS-specific formatting
    # ------------------------------------------------------------------

    def format_message(self, content: str) -> str:
        """Strip markdown — SMS renders it as literal characters."""
        content = re.sub(r"\*\*(.+?)\*\*", r"\1", content, flags=re.DOTALL)
        content = re.sub(r"\*(.+?)\*", r"\1", content, flags=re.DOTALL)
        content = re.sub(r"__(.+?)__", r"\1", content, flags=re.DOTALL)
        content = re.sub(r"_(.+?)_", r"\1", content, flags=re.DOTALL)
        content = re.sub(r"```[a-z]*\n?", "", content)
        content = re.sub(r"`(.+?)`", r"\1", content)
        content = re.sub(r"^#{1,6}\s+", "", content, flags=re.MULTILINE)
        content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    # ------------------------------------------------------------------
    # Twilio webhook handler
    # ------------------------------------------------------------------

    def _webhook_validation_url(self, request) -> str:
        if self._webhook_public_url:
            return self._webhook_public_url
        return str(request.url)

    def _valid_twilio_signature(self, url: str, form: Dict[str, list[str]], signature: str) -> bool:
        if not signature:
            return False
        parts = [url]
        for key in sorted(form):
            for value in form[key]:
                parts.append(key)
                parts.append(value)
        payload = "".join(parts).encode("utf-8")
        digest = hmac.new(self._auth_token.encode("utf-8"), payload, hashlib.sha1).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature)

    async def _handle_webhook(self, request) -> "aiohttp.web.Response":
        from aiohttp import web

        try:
            raw = await request.read()
            if len(raw) > self._max_webhook_bytes:
                return web.Response(
                    text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    content_type="application/xml",
                    status=413,
                )
            form = urllib.parse.parse_qs(raw.decode("utf-8"))
        except Exception as e:
            logger.error("[sms] webhook parse error: %s", e)
            return web.Response(
                text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                content_type="application/xml",
                status=400,
            )

        if not self._insecure_no_auth:
            signature = request.headers.get("X-Twilio-Signature", "")
            if not self._valid_twilio_signature(self._webhook_validation_url(request), form, signature):
                logger.warning("[sms] rejected webhook with invalid Twilio signature")
                return web.Response(
                    text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    content_type="application/xml",
                    status=403,
                )

        # Extract fields (parse_qs returns lists)
        from_number = (form.get("From", [""]))[0].strip()
        to_number = (form.get("To", [""]))[0].strip()
        text = (form.get("Body", [""]))[0].strip()
        message_sid = (form.get("MessageSid", [""]))[0].strip()

        if not from_number or not text:
            return web.Response(
                text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                content_type="application/xml",
            )

        # Ignore messages from our own number (echo prevention)
        if from_number == self._from_number:
            logger.debug("[sms] ignoring echo from own number %s", _redact_phone(from_number))
            return web.Response(
                text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                content_type="application/xml",
            )

        logger.info(
            "[sms] inbound from %s -> %s: %s",
            _redact_phone(from_number),
            _redact_phone(to_number),
            text[:80],
        )

        source = self.build_source(
            chat_id=from_number,
            chat_name=from_number,
            chat_type="dm",
            user_id=from_number,
            user_name=from_number,
        )
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=form,
            message_id=message_sid,
        )

        # Non-blocking: Twilio expects a fast response
        task = asyncio.create_task(self.handle_message(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Return empty TwiML — we send replies via the REST API, not inline TwiML
        return web.Response(
            text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            content_type="application/xml",
        )
