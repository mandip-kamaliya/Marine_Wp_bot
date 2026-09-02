"""Marine persistence behavior without a live Supabase project."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.repositories.marine import DuplicateInboundMessageError, MarineRepository
from app.schemas.exotel_webhook import NormalizedInboundMessage
from app.services.marine_sales import MarineContext, MarineReply


class FakeDatabaseError(Exception):
    code = "23505"


class FakeQuery:
    def __init__(self, client, table: str):
        self.client, self.table_name = client, table
        self.operation, self.payload, self.filters = "select", None, []

    def select(self, value): self.operation = "select"; return self
    def insert(self, value): self.operation, self.payload = "insert", value; return self
    def update(self, value): self.operation, self.payload = "update", value; return self
    def upsert(self, value, **kwargs): self.operation, self.payload = "upsert", value; return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def is_(self, key, value): self.filters.append((key, value)); return self
    def maybe_single(self): return self
    def execute(self): return self.client.execute(self)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = []
        self.rpc_responses = []

    def table(self, name): return FakeQuery(self, name)
    def execute(self, query):
        self.calls.append((query.table_name, query.operation, query.payload, query.filters))
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return SimpleNamespace(data=response)
    def rpc(self, name, params):
        self.calls.append(("rpc", name, params, []))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_responses.pop(0)))


def inbound() -> NormalizedInboundMessage:
    return NormalizedInboundMessage(
        external_message_id="message-1",
        customer_whatsapp_number="+919876543210",
        business_whatsapp_number="+917948502803",
        message_type="text",
        content="Hello",
        received_at=datetime(2026, 9, 2, tzinfo=UTC),
    )


def test_duplicate_inbound_provider_message_is_rejected() -> None:
    client = FakeClient()
    client.responses = [FakeDatabaseError()]
    repository = MarineRepository(client)

    with pytest.raises(DuplicateInboundMessageError):
        repository.store_inbound(inbound(), customer_id="customer-1", conversation_id="conversation-1")


def test_context_round_trip_uses_structured_json() -> None:
    client = FakeClient()
    client.responses = [[{"id": "conversation-1"}]]
    repository = MarineRepository(client)
    context = MarineContext(state="pontoon_capacity", product="Pontoon Boat", application="Resort")

    assert repository.save_context("conversation-1", context) is True
    restored = repository.load_context({"flow_context": context.model_dump(mode="json")})

    assert restored.state == "pontoon_capacity"
    assert restored.product == "Pontoon Boat"
    assert restored.application == "Resort"


def test_existing_outbound_draft_prevents_duplicate_creation() -> None:
    client = FakeClient()
    client.responses = [{"id": "draft-1", "content": "Existing"}]
    repository = MarineRepository(client)
    reply = MarineReply(text="New response", context=MarineContext())

    draft, created = repository.create_outbound_draft(
        customer_id="customer-1",
        conversation_id="conversation-1",
        inbound_message_id="message-1",
        reply=reply,
    )

    assert created is False
    assert draft["id"] == "draft-1"
    assert len(client.calls) == 1


def test_atomic_claim_and_completion_use_database_functions() -> None:
    client = FakeClient()
    client.rpc_responses = [True, True]
    repository = MarineRepository(client)

    assert repository.claim_outbound("draft-1", "claim-1") is True
    assert repository.complete_outbound("draft-1", "claim-1", "provider-1") is True
    assert client.calls[0][1] == "claim_outbound_draft"
    assert client.calls[1][1] == "complete_outbound_draft"


def test_lead_and_handover_are_created_once_per_reason() -> None:
    client = FakeClient()
    client.responses = [None, [{"id": "lead-1"}], [{"id": "handover-1"}], [{"id": "conversation-1"}]]
    repository = MarineRepository(client)
    reply = MarineReply(
        text="Our team will contact you.",
        context=MarineContext(customer_name="Rahul", product="Pontoon Boat"),
        handover=True,
        handover_reason="quotation_requested",
        lead_priority="hot",
    )

    lead = repository.create_lead_and_handover(
        customer_id="customer-1", conversation_id="conversation-1", reply=reply
    )

    assert lead["id"] == "lead-1"
    insert_call = next(call for call in client.calls if call[0] == "leads" and call[1] == "insert")
    assert insert_call[2]["idempotency_key"] == "conversation-1:quotation_requested"
    assert insert_call[2]["priority"] == "hot"
