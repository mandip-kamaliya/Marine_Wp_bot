"""Marine Exotel inbound webhook."""

import json
import logging
from functools import lru_cache
import hashlib
import hmac

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from app.config import get_settings
from app.integrations.exotel import ExotelClient, ExotelPayloadError, normalize_exotel_payload
from app.integrations.supabase import get_supabase_client
from app.integrations.zoho import ZohoClient
from app.repositories.marine import MarineRepository
from app.services.marine_inbound import MarineInboundProcessor

router = APIRouter(prefix="/webhooks/exotel", tags=["exotel"])
logger = logging.getLogger("uvicorn.error")


@lru_cache
def get_marine_processor() -> MarineInboundProcessor:
    settings = get_settings()
    repository = MarineRepository(get_supabase_client())
    exotel = None
    if settings.exotel_is_configured():
        exotel = ExotelClient(
            account_sid=settings.exotel_account_sid or "",
            api_key=settings.exotel_api_key.get_secret_value(),
            api_token=settings.exotel_api_token.get_secret_value(),
            whatsapp_from=settings.exotel_whatsapp_from or "",
            api_base_url=settings.exotel_api_base_url,
        )
    zoho = None
    if settings.zoho_crm_enabled and settings.zoho_is_configured():
        zoho = ZohoClient(
            accounts_base_url=settings.zoho_accounts_base_url,
            api_base_url=settings.zoho_api_base_url,
            client_id=settings.zoho_client_id.get_secret_value(),
            client_secret=settings.zoho_client_secret.get_secret_value(),
            refresh_token=settings.zoho_refresh_token.get_secret_value(),
            leads_module=settings.zoho_leads_module,
        )
    return MarineInboundProcessor(
        settings=settings, repository=repository, exotel=exotel, zoho=zoho
    )


def _valid_signature(raw_body: bytes, signature: str | None) -> bool:
    settings = get_settings()
    if not settings.exotel_signature_validation_enabled:
        return True
    if not signature or not settings.exotel_api_token:
        return False
    supplied = signature.removeprefix("sha256=").strip()
    expected = hmac.new(
        settings.exotel_api_token.get_secret_value().encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


async def _process_messages(messages) -> None:
    processor = get_marine_processor()
    for message in messages:
        try:
            result = await processor.process(message)
            logger.info(
                "marine_inbound_completed message_id=%s status=%s",
                message.external_message_id,
                result.status,
            )
        except Exception:
            logger.exception("marine_inbound_processing_failed message_id=%s", message.external_message_id)


@router.post("/inbound", status_code=200)
async def receive_inbound_message(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Validate promptly, then process durable work after acknowledging Exotel."""

    raw_body = await request.body()
    if not _valid_signature(raw_body, request.headers.get("X-Exotel-Signature")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ExotelPayloadError("Webhook body must be an object.")
        messages = normalize_exotel_payload(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    except ExotelPayloadError:
        raise HTTPException(status_code=400, detail="Invalid payload") from None

    for message in messages:
        logger.info(
            "marine_inbound_normalized message_id=%s message_type=%s",
            message.external_message_id,
            message.message_type,
        )
    if messages and get_settings().chatbot_enabled:
        background_tasks.add_task(_process_messages, messages)
    return Response(status_code=200)
