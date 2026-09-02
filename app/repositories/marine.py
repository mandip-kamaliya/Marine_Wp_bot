"""Persistence operations for Marine conversations and outbound delivery."""

from datetime import UTC, datetime
from typing import Any

from app.schemas.exotel_webhook import NormalizedInboundMessage
from app.services.marine_sales import MarineContext, MarineReply


class DuplicateInboundMessageError(RuntimeError):
    pass


class MarineRepository:
    def __init__(self, client: Any) -> None:
        self.client = client

    def get_or_create_customer(self, whatsapp_number: str, name: str | None) -> dict[str, Any]:
        existing = self.client.table("customers").select("*").eq(
            "whatsapp_number", whatsapp_number
        ).maybe_single().execute()
        if isinstance(getattr(existing, "data", None), dict):
            return existing.data
        response = self.client.table("customers").insert({
            "whatsapp_number": whatsapp_number,
            "name": name,
        }).execute()
        return response.data[0]

    def get_or_create_conversation(
        self, customer_id: str, business_number: str
    ) -> dict[str, Any]:
        existing = (
            self.client.table("conversations").select("*")
            .eq("customer_id", customer_id)
            .eq("business_whatsapp_number", business_number)
            .is_("closed_at", "null").maybe_single().execute()
        )
        if isinstance(getattr(existing, "data", None), dict):
            return existing.data
        response = self.client.table("conversations").insert({
            "customer_id": customer_id,
            "business_whatsapp_number": business_number,
            "state": "new",
            "mode": "bot",
            "flow_context": {},
        }).execute()
        return response.data[0]

    def store_inbound(
        self,
        message: NormalizedInboundMessage,
        *,
        customer_id: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        try:
            response = self.client.table("messages").insert({
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "direction": "inbound",
                "message_type": message.message_type,
                "content": message.content,
                "external_provider": "exotel",
                "external_message_id": message.external_message_id,
                "received_at": message.received_at.isoformat(),
            }).execute()
        except Exception as error:
            if getattr(error, "code", None) == "23505":
                raise DuplicateInboundMessageError from error
            raise
        return response.data[0]

    def load_context(self, conversation: dict[str, Any]) -> MarineContext:
        data = conversation.get("flow_context")
        if not isinstance(data, dict) or not data:
            return MarineContext(customer_phone=None)
        return MarineContext.model_validate(data)

    def save_context(self, conversation_id: str, context: MarineContext) -> bool:
        response = self.client.table("conversations").update({
            "state": context.state,
            "flow_context": context.model_dump(mode="json"),
        }).eq("id", conversation_id).execute()
        return bool(response.data)

    def create_outbound_draft(
        self,
        *,
        customer_id: str,
        conversation_id: str,
        inbound_message_id: str,
        reply: MarineReply,
    ) -> tuple[dict[str, Any], bool]:
        existing = (
            self.client.table("messages").select("*")
            .eq("direction", "outbound")
            .eq("related_inbound_message_id", inbound_message_id)
            .maybe_single().execute()
        )
        if isinstance(getattr(existing, "data", None), dict):
            return existing.data, False
        response = self.client.table("messages").insert({
            "conversation_id": conversation_id,
            "customer_id": customer_id,
            "direction": "outbound",
            "message_type": "interactive" if reply.actions else "text",
            "content": reply.text,
            "actions": [action.model_dump() for action in reply.actions],
            "related_inbound_message_id": inbound_message_id,
            "draft_status": "pending",
            "delivery_status": "draft",
        }).execute()
        return response.data[0], True

    def claim_outbound(self, draft_id: str, claim_token: str) -> bool:
        response = self.client.rpc("claim_outbound_draft", {
            "p_draft_id": draft_id,
            "p_claim_token": claim_token,
        }).execute()
        return response.data is True

    def complete_outbound(
        self, draft_id: str, claim_token: str, provider_message_id: str
    ) -> bool:
        response = self.client.rpc("complete_outbound_draft", {
            "p_draft_id": draft_id,
            "p_claim_token": claim_token,
            "p_provider_message_id": provider_message_id,
        }).execute()
        return response.data is True

    def mark_outbound_uncertain(self, draft_id: str, claim_token: str) -> None:
        self.client.table("messages").update({
            "draft_status": "reconciliation_required",
        }).eq("id", draft_id).eq("send_claim_token", claim_token).execute()

    def create_lead_and_handover(
        self,
        *,
        customer_id: str,
        conversation_id: str,
        reply: MarineReply,
    ) -> dict[str, Any]:
        reason = reply.handover_reason or "sales_assistance"
        idempotency_key = f"{conversation_id}:{reason}"
        existing = self.client.table("leads").select("*").eq(
            "idempotency_key", idempotency_key
        ).maybe_single().execute()
        if isinstance(getattr(existing, "data", None), dict):
            return existing.data
        lead_response = self.client.table("leads").insert({
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "idempotency_key": idempotency_key,
            "lead_type": reason,
            "priority": reply.lead_priority,
            "requirement": reply.context.model_dump(mode="json"),
        }).execute()
        self.client.table("handovers").upsert({
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "reason": reason,
            "assigned_team": "marine_sales",
            "context_snapshot": reply.context.model_dump(mode="json"),
        }, on_conflict="conversation_id,reason").execute()
        self.client.table("conversations").update({
            "mode": "human",
            "state": "handover",
            "handover_reason": reason,
            "assigned_team": "marine_sales",
        }).eq("id", conversation_id).execute()
        return lead_response.data[0]

    def mark_zoho_sync(self, lead_id: str, *, zoho_lead_id: str | None, success: bool) -> None:
        self.client.table("leads").update({
            "zoho_sync_status": "synced" if success else "failed",
            "zoho_lead_id": zoho_lead_id,
            "zoho_attempted_at": datetime.now(UTC).isoformat(),
        }).eq("id", lead_id).execute()
