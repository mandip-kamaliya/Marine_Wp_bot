"""Durable Marine inbound-to-outbound orchestration tests."""

from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.repositories.marine import DuplicateInboundMessageError
from app.schemas.exotel_webhook import NormalizedInboundMessage
from app.services.marine_inbound import MarineInboundProcessor
from app.services.marine_sales import MarineContext


class FakeRepository:
    def __init__(self, *, duplicate=False, mode="bot", claim=True):
        self.duplicate, self.mode, self.claim = duplicate, mode, claim
        self.saved_context = None
        self.completed = None
        self.uncertain = False
        self.draft_count = 0

    def get_or_create_customer(self, number, name):
        return {"id": "customer-1", "whatsapp_number": number, "name": name}
    def get_or_create_conversation(self, customer_id, business_number):
        return {"id": "conversation-1", "mode": self.mode, "flow_context": {}}
    def store_inbound(self, message, **kwargs):
        if self.duplicate: raise DuplicateInboundMessageError
        return {"id": "inbound-1"}
    def load_context(self, conversation): return MarineContext()
    def save_context(self, conversation_id, context): self.saved_context = context; return True
    def create_outbound_draft(self, **kwargs):
        self.draft_count += 1
        return {"id": "draft-1"}, True
    def claim_outbound(self, draft_id, claim_token): return self.claim
    def complete_outbound(self, draft_id, claim_token, provider_sid):
        self.completed = provider_sid
        return True
    def mark_outbound_uncertain(self, draft_id, claim_token): self.uncertain = True
    def create_lead_and_handover(self, **kwargs): return {"id": "lead-1"}
    def mark_zoho_sync(self, *args, **kwargs): pass


class FakeExotel:
    def __init__(self): self.calls = []
    async def send_reply(self, **kwargs):
        self.calls.append(kwargs)
        return "provider-1"


def message(*, business_number="+917948502803"):
    return NormalizedInboundMessage(
        external_message_id="message-1",
        customer_whatsapp_number="+919876543210",
        business_whatsapp_number=business_number,
        profile_name="Rahul",
        message_type="text",
        content="Hello",
        received_at=datetime(2026, 9, 2, tzinfo=UTC),
    )


def settings(*, outbound=True):
    return Settings(
        _env_file=None,
        exotel_whatsapp_from="+917948502803",
        exotel_outbound_enabled=outbound,
    )


@pytest.mark.asyncio
async def test_new_customer_welcome_is_drafted_claimed_and_sent_once():
    repository, exotel = FakeRepository(), FakeExotel()
    processor = MarineInboundProcessor(
        settings=settings(), repository=repository, exotel=exotel
    )

    result = await processor.process(message())

    assert result.status == "sent"
    assert result.provider_message_id == "provider-1"
    assert repository.saved_context.state == "primary_intent"
    assert repository.completed == "provider-1"
    assert len(exotel.calls) == 1
    assert len(exotel.calls[0]["actions"]) == 5


@pytest.mark.asyncio
async def test_duplicate_inbound_does_not_create_or_send_another_draft():
    repository, exotel = FakeRepository(duplicate=True), FakeExotel()
    processor = MarineInboundProcessor(
        settings=settings(), repository=repository, exotel=exotel
    )

    result = await processor.process(message())

    assert result.status == "duplicate"
    assert repository.draft_count == 0
    assert exotel.calls == []


@pytest.mark.asyncio
async def test_outbound_kill_switch_stores_draft_without_sending():
    repository, exotel = FakeRepository(), FakeExotel()
    processor = MarineInboundProcessor(
        settings=settings(outbound=False), repository=repository, exotel=exotel
    )

    result = await processor.process(message())

    assert result.status == "drafted"
    assert repository.draft_count == 1
    assert exotel.calls == []


@pytest.mark.asyncio
async def test_wrong_business_number_never_touches_database_or_exotel():
    repository, exotel = FakeRepository(), FakeExotel()
    processor = MarineInboundProcessor(
        settings=settings(), repository=repository, exotel=exotel
    )

    result = await processor.process(message(business_number="+917948502801"))

    assert result.status == "wrong_business_number"
    assert repository.draft_count == 0
    assert exotel.calls == []


@pytest.mark.asyncio
async def test_human_mode_records_inbound_but_never_sends_bot_reply():
    repository, exotel = FakeRepository(mode="human"), FakeExotel()
    processor = MarineInboundProcessor(
        settings=settings(), repository=repository, exotel=exotel
    )

    result = await processor.process(message())

    assert result.status == "human_mode"
    assert repository.draft_count == 0
    assert exotel.calls == []
