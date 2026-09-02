"""Exotel inbound normalization and endpoint tests."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.integrations.exotel import normalize_exotel_payload
from app.main import app


PAYLOAD = {
    "whatsapp": {
        "messages": [
            {
                "callback_type": "incoming_message",
                "sid": "marine-message-1",
                "from": "91 98765-43210",
                "to": "+917900000001",
                "timestamp": "2026-09-02T10:00:00+05:30",
                "profile_name": "Test Customer",
                "content": {"type": "text", "text": {"body": "Hello Marine"}},
            }
        ]
    }
}


def test_normalizes_customer_business_number_and_text() -> None:
    message = normalize_exotel_payload(PAYLOAD)[0]

    assert message.external_message_id == "marine-message-1"
    assert message.customer_whatsapp_number == "+919876543210"
    assert message.business_whatsapp_number == "+917900000001"
    assert message.message_type == "text"
    assert message.content == "Hello Marine"


def test_inbound_webhook_acknowledges_valid_message() -> None:
    settings = get_settings()
    previous = settings.chatbot_enabled
    settings.chatbot_enabled = False
    try:
        response = TestClient(app).post("/webhooks/exotel/inbound", json=PAYLOAD)
    finally:
        settings.chatbot_enabled = previous

    assert response.status_code == 200


def test_inbound_webhook_rejects_invalid_payload() -> None:
    response = TestClient(app).post("/webhooks/exotel/inbound", json={"unexpected": True})

    assert response.status_code == 400
