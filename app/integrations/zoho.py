"""Disabled-by-default Zoho CRM lead adapter for qualified Marine leads."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.marine_sales import MarineContext


class ZohoIntegrationError(RuntimeError):
    """Raised when Zoho authentication or lead creation fails."""


def build_zoho_lead(context: MarineContext) -> dict[str, Any]:
    """Use standard Zoho fields; business-specific values stay in Description."""

    name = (context.customer_name or "WhatsApp Lead").strip()
    parts = name.split(maxsplit=1)
    first_name = parts[0] if len(parts) == 2 else None
    last_name = parts[-1]
    details = [
        "Source: ECHT Marine WhatsApp Chatbot",
        f"Intent: {context.primary_intent or 'Not captured'}",
        f"Product: {context.product or context.work_solution or 'Not captured'}",
        f"Application: {context.application or context.jetty_use or 'Not captured'}",
        f"Passenger capacity: {context.passenger_capacity or 'Not captured'}",
        f"Project location: {context.project_location or 'Not captured'}",
        f"Water body: {context.water_body or 'Not captured'}",
        f"Quantity: {context.quantity or 'Not captured'}",
        f"Timeline: {context.timeline or 'Not captured'}",
        f"Support type: {context.support_type or 'Not applicable'}",
    ]
    lead: dict[str, Any] = {
        "Last_Name": last_name,
        "Company": context.company_name or "Individual / Not provided",
        "Lead_Source": "WhatsApp",
        "Description": "\n".join(details),
    }
    if first_name:
        lead["First_Name"] = first_name
    if context.customer_phone:
        lead["Phone"] = context.customer_phone
    return lead


class ZohoClient:
    def __init__(
        self,
        *,
        accounts_base_url: str,
        api_base_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        leads_module: str = "Leads",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.accounts_base_url = accounts_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.leads_module = leads_module
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), transport=transport)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def create_lead(self, context: MarineContext) -> str:
        token_response = await self.client.post(
            f"{self.accounts_base_url}/oauth/v2/token",
            params={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
        )
        if token_response.status_code != 200:
            raise ZohoIntegrationError("Zoho OAuth refresh failed.")
        access_token = token_response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ZohoIntegrationError("Zoho OAuth response did not contain an access token.")

        response = await self.client.post(
            f"{self.api_base_url}/crm/v7/{self.leads_module}",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            json={"data": [build_zoho_lead(context)]},
        )
        if response.status_code not in {200, 201, 202}:
            raise ZohoIntegrationError("Zoho lead creation failed.")
        result = response.json()
        try:
            record_id = result["data"][0]["details"]["id"]
        except (KeyError, IndexError, TypeError) as error:
            raise ZohoIntegrationError("Zoho response did not contain a lead ID.") from error
        if not isinstance(record_id, str) or not record_id:
            raise ZohoIntegrationError("Zoho response contained an invalid lead ID.")
        return record_id
