"""Exotel webhook envelopes and normalized inbound messages."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExotelWhatsAppMessageInput(BaseModel):
    """One incoming WhatsApp message in Exotel's confirmed envelope."""

    callback_type: str
    sid: str | None = None
    from_: str = Field(alias="from")
    to: str
    timestamp: datetime
    profile_name: str | None = None
    content: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class ExotelWhatsAppPayload(BaseModel):
    messages: list[ExotelWhatsAppMessageInput]

    model_config = ConfigDict(extra="allow")


class ExotelWhatsAppEnvelope(BaseModel):
    whatsapp: ExotelWhatsAppPayload

    model_config = ConfigDict(extra="allow")


class NormalizedInboundMessage(BaseModel):
    """Provider-neutral input passed to future Marine business logic."""

    external_provider: Literal["exotel"] = "exotel"
    external_message_id: str
    customer_whatsapp_number: str
    business_whatsapp_number: str
    profile_name: str | None = None
    message_type: Literal["text", "interactive", "other"]
    content: str | None = None
    received_at: datetime

