"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the isolated Marine chatbot deployment."""

    app_name: str = "Marine WhatsApp Chatbot"
    app_env: str = "development"
    app_revision: str = "local"
    debug: bool = False
    log_level: str = "INFO"
    public_base_url: str | None = None

    tenant_code: str = "marine"
    active_location: str | None = None
    active_product: str | None = None

    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None

    exotel_account_sid: str | None = "echt61"
    exotel_api_key: SecretStr | None = None
    exotel_api_token: SecretStr | None = None
    exotel_api_base_url: str = "https://api.exotel.com"
    exotel_whatsapp_from: str | None = None
    exotel_status_callback_url: str | None = None
    exotel_outbound_enabled: bool = False
    exotel_signature_validation_enabled: bool = False

    openai_api_key: SecretStr | None = None
    openai_chat_model: str | None = None
    openai_embedding_model: str | None = None
    openai_embedding_dimensions: int | None = None
    marine_knowledge_base_path: str = "documents/active/ECHT_MARINE_KNOWLEDGE_BASE_V2.md"
    marine_knowledge_max_sections: int = Field(default=4, ge=1, le=8)

    chatbot_enabled: bool = False
    interactive_whatsapp_enabled: bool = False
    conversation_session_ttl_minutes: int = Field(default=30, ge=1)
    app_timezone: str = "Asia/Kolkata"

    zoho_crm_enabled: bool = False
    zoho_accounts_base_url: str = "https://accounts.zoho.in"
    zoho_api_base_url: str = "https://www.zohoapis.in"
    zoho_client_id: SecretStr | None = None
    zoho_client_secret: SecretStr | None = None
    zoho_refresh_token: SecretStr | None = None
    zoho_leads_module: str = "Leads"

    def exotel_is_configured(self) -> bool:
        return bool(
            self.exotel_account_sid
            and self.exotel_api_key
            and self.exotel_api_token
            and self.exotel_whatsapp_from
        )

    def zoho_is_configured(self) -> bool:
        return bool(
            self.zoho_client_id
            and self.zoho_client_secret
            and self.zoho_refresh_token
        )

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("tenant_code")
    @classmethod
    def validate_tenant_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "marine":
            raise ValueError("This deployment must use TENANT_CODE=marine.")
        return normalized

    @field_validator("openai_embedding_dimensions", mode="before")
    @classmethod
    def empty_embedding_dimensions_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached runtime settings."""

    return Settings()
