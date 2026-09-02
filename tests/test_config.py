"""Configuration isolation tests."""

from app.config import Settings


def test_defaults_are_marine_specific_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.tenant_code == "marine"
    assert settings.app_name == "Marine WhatsApp Chatbot"
    assert settings.chatbot_enabled is False
    assert settings.exotel_outbound_enabled is False
    assert settings.exotel_whatsapp_from is None

