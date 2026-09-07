"""Durable orchestration for one normalized Marine WhatsApp message."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.integrations.exotel import ExotelClient, ExotelOutboundError
from app.integrations.zoho import ZohoClient, ZohoIntegrationError
from app.repositories.marine import DuplicateInboundMessageError, MarineRepository
from app.schemas.exotel_webhook import NormalizedInboundMessage
from app.services.marine_sales import MarineContext, process_marine_message
from app.services.marine_knowledge import build_marine_knowledge_service
from app.services.marine_understanding import build_marine_understanding_service

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class ProcessingResult:
    status: str
    draft_id: str | None = None
    provider_message_id: str | None = None


class MarineInboundProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: MarineRepository,
        exotel: ExotelClient | None,
        zoho: ZohoClient | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.exotel = exotel
        self.zoho = zoho
        self.knowledge = build_marine_knowledge_service(settings)
        self.understanding = build_marine_understanding_service(settings)

    async def process(self, message: NormalizedInboundMessage) -> ProcessingResult:
        if message.business_whatsapp_number != self.settings.exotel_whatsapp_from:
            logger.warning("marine_inbound_wrong_business_number message_id=%s", message.external_message_id)
            return ProcessingResult("wrong_business_number")

        customer = await run_in_threadpool(
            self.repository.get_or_create_customer,
            message.customer_whatsapp_number,
            message.profile_name,
        )
        conversation = await run_in_threadpool(
            self.repository.get_or_create_conversation,
            customer["id"],
            message.business_whatsapp_number,
        )
        try:
            await run_in_threadpool(
                self.repository.store_inbound,
                message,
                customer_id=customer["id"],
                conversation_id=conversation["id"],
            )
        except DuplicateInboundMessageError:
            logger.info("marine_inbound_duplicate message_id=%s", message.external_message_id)
            return ProcessingResult("duplicate")

        if conversation.get("mode") == "human":
            return ProcessingResult("human_mode")

        context = self.repository.load_context(conversation)
        context.customer_phone = message.customer_whatsapp_number
        if not context.customer_name and message.profile_name:
            context.customer_name = message.profile_name
        reply = process_marine_message(
            message.content or "", context, knowledge=self.knowledge,
            understanding=self.understanding,
        )
        await run_in_threadpool(
            self.repository.save_context, conversation["id"], reply.context
        )

        lead: dict[str, object] | None = None
        if reply.handover:
            lead = await run_in_threadpool(
                self.repository.create_lead_and_handover,
                customer_id=customer["id"],
                conversation_id=conversation["id"],
                reply=reply,
            )

        draft, _ = await run_in_threadpool(
            self.repository.create_outbound_draft,
            customer_id=customer["id"],
            conversation_id=conversation["id"],
            inbound_message_id=message.external_message_id,
            reply=reply,
        )
        draft_id = str(draft["id"])

        if lead is not None and self.zoho is not None:
            await self._sync_zoho(lead, reply.context)

        if not self.settings.exotel_outbound_enabled:
            return ProcessingResult("drafted", draft_id=draft_id)
        if self.exotel is None:
            logger.error("marine_exotel_not_configured draft_id=%s", draft_id)
            return ProcessingResult("outbound_not_configured", draft_id=draft_id)

        claim_token = str(uuid4())
        claimed = await run_in_threadpool(
            self.repository.claim_outbound, draft_id, claim_token
        )
        if not claimed:
            return ProcessingResult("already_claimed", draft_id=draft_id)

        try:
            provider_sid = await self.exotel.send_reply(
                to_number=message.customer_whatsapp_number,
                body=reply.text,
                actions=[action.model_dump() for action in reply.actions],
                custom_data=draft_id,
                status_callback=self.settings.exotel_status_callback_url,
            )
        except ExotelOutboundError:
            await run_in_threadpool(
                self.repository.mark_outbound_uncertain, draft_id, claim_token
            )
            logger.exception("marine_exotel_send_uncertain draft_id=%s", draft_id)
            return ProcessingResult("reconciliation_required", draft_id=draft_id)

        completed = await run_in_threadpool(
            self.repository.complete_outbound,
            draft_id,
            claim_token,
            provider_sid,
        )
        if not completed:
            logger.error("marine_outbound_completion_failed draft_id=%s", draft_id)
            return ProcessingResult(
                "reconciliation_required",
                draft_id=draft_id,
                provider_message_id=provider_sid,
            )
        return ProcessingResult("sent", draft_id=draft_id, provider_message_id=provider_sid)

    async def _sync_zoho(self, lead: dict[str, object], context: MarineContext) -> None:
        try:
            zoho_lead_id = await self.zoho.create_lead(context)
        except ZohoIntegrationError:
            logger.exception("marine_zoho_sync_failed lead_id=%s", lead.get("id"))
            await run_in_threadpool(
                self.repository.mark_zoho_sync,
                str(lead["id"]),
                zoho_lead_id=None,
                success=False,
            )
            return
        await run_in_threadpool(
            self.repository.mark_zoho_sync,
            str(lead["id"]),
            zoho_lead_id=zoho_lead_id,
            success=True,
        )
