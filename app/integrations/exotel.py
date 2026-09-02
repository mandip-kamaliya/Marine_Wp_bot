"""Exotel inbound payload normalization."""

from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any

import httpx

from app.schemas.exotel_webhook import (
    ExotelWhatsAppEnvelope,
    ExotelWhatsAppMessageInput,
    NormalizedInboundMessage,
)


class ExotelPayloadError(ValueError):
    """Raised when an inbound payload cannot be safely normalized."""


class ExotelOutboundError(RuntimeError):
    """Raised when Exotel does not accept an outbound message."""


class ExotelClient:
    """Small Marine adapter using the proven Exotel v2 WhatsApp payload."""

    def __init__(
        self,
        *,
        account_sid: str,
        api_key: str,
        api_token: str,
        whatsapp_from: str,
        api_base_url: str = "https://api.exotel.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.whatsapp_from = whatsapp_from
        self.api_base_url = api_base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            auth=httpx.BasicAuth(api_key, api_token),
            timeout=httpx.Timeout(10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    def build_reply_payload(
        self,
        *,
        to_number: str,
        body: str,
        actions: list[dict[str, str]] | None = None,
        custom_data: str | None = None,
        status_callback: str | None = None,
    ) -> dict[str, Any]:
        actions = actions or []
        if actions:
            if len(actions) <= 3:
                interactive = {
                    "type": "button",
                    "body": {"text": body},
                    "action": {"buttons": [
                        {"type": "reply", "reply": {"id": item["id"], "title": item["title"][:20]}}
                        for item in actions
                    ]},
                }
            else:
                interactive = {
                    "type": "list",
                    "body": {"text": body},
                    "action": {
                        "button": "View Options",
                        "sections": [{
                            "title": "ECHT Marine",
                            "rows": [
                                {"id": item["id"], "title": item["title"][:24]}
                                for item in actions
                            ],
                        }],
                    },
                }
            content: dict[str, Any] = {"type": "interactive", "interactive": interactive}
        else:
            content = {"type": "text", "text": {"body": body}}

        message: dict[str, Any] = {
            "from": self.whatsapp_from,
            "to": to_number,
            "content": content,
        }
        if custom_data:
            message["custom_data"] = custom_data
        payload: dict[str, Any] = {"whatsapp": {"messages": [message]}}
        if status_callback:
            payload["status_callback"] = status_callback
        return payload

    async def send_reply(self, **kwargs: Any) -> str:
        payload = self.build_reply_payload(**kwargs)
        endpoint = f"{self.api_base_url}/v2/accounts/{self.account_sid}/messages"
        response = await self.client.post(endpoint, json=payload)
        if response.status_code != 202:
            raise ExotelOutboundError(f"Exotel rejected outbound message with HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as error:
            raise ExotelOutboundError("Exotel acceptance response was not JSON.") from error
        sid = _find_provider_sid(data)
        if sid is None:
            raise ExotelOutboundError("Exotel acceptance response did not include a message SID.")
        return sid


def _find_provider_sid(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("sid", "message_sid"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_provider_sid(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _find_provider_sid(value)
            if found:
                return found
    return None


def normalize_exotel_payload(payload: dict[str, Any]) -> list[NormalizedInboundMessage]:
    """Normalize incoming messages from the confirmed Exotel envelope."""

    try:
        envelope = ExotelWhatsAppEnvelope.model_validate(payload)
    except Exception as error:
        raise ExotelPayloadError("Unsupported Exotel payload envelope.") from error

    return [
        _normalize_message(message)
        for message in envelope.whatsapp.messages
        if message.callback_type == "incoming_message"
    ]


def _normalize_message(message: ExotelWhatsAppMessageInput) -> NormalizedInboundMessage:
    customer_number = _normalize_phone(message.from_)
    business_number = _normalize_phone(message.to)
    message_type, content = _extract_content(message.content)
    received_at = _as_utc(message.timestamp)
    message_id = message.sid or _fallback_message_id(
        customer_number=customer_number,
        business_number=business_number,
        received_at=received_at,
        message_type=message_type,
        content=content,
    )
    return NormalizedInboundMessage(
        external_message_id=message_id,
        customer_whatsapp_number=customer_number,
        business_whatsapp_number=business_number,
        profile_name=message.profile_name,
        message_type=message_type,
        content=content,
        received_at=received_at,
    )


def _extract_content(content: dict[str, Any]) -> tuple[str, str | None]:
    if content.get("type") == "text":
        text = content.get("text")
        body = text.get("body") if isinstance(text, dict) else None
        return "text", body if isinstance(body, str) else None
    if content.get("type") == "interactive":
        interactive = content.get("interactive")
        if isinstance(interactive, dict):
            reply_type = interactive.get("type")
            reply = interactive.get(reply_type) if isinstance(reply_type, str) else None
            if isinstance(reply, dict):
                identifier = reply.get("id")
                title = reply.get("title")
                value = identifier if isinstance(identifier, str) else title
                return "interactive", value if isinstance(value, str) else None
        return "interactive", None
    return "other", None


def _normalize_phone(value: str) -> str:
    normalized = re.sub(r"[\s()\-]", "", value)
    if not re.fullmatch(r"\+?[1-9][0-9]{7,14}", normalized):
        raise ExotelPayloadError("Invalid WhatsApp number.")
    return normalized if normalized.startswith("+") else f"+{normalized}"


def _fallback_message_id(
    *,
    customer_number: str,
    business_number: str,
    received_at: datetime,
    message_type: str,
    content: str | None,
) -> str:
    canonical = json.dumps(
        {
            "from": customer_number,
            "to": business_number,
            "timestamp": received_at.isoformat(),
            "message_type": message_type,
            "content": content,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
