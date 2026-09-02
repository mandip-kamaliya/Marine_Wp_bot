"""Provider adapters are tested without paid or live API calls."""

import httpx
import pytest

from app.integrations.exotel import ExotelClient
from app.integrations.zoho import ZohoClient, build_zoho_lead
from app.services.marine_sales import MarineContext


def test_exotel_builds_list_for_five_primary_actions() -> None:
    client = ExotelClient(
        account_sid="echt61",
        api_key="test-key",
        api_token="test-token",
        whatsapp_from="+917948502803",
    )
    payload = client.build_reply_payload(
        to_number="+919876543210",
        body="What are you looking for today?",
        actions=[{"id": f"option_{number}", "title": f"Option {number}"} for number in range(5)],
        custom_data="draft-1",
    )
    message = payload["whatsapp"]["messages"][0]

    assert message["from"] == "+917948502803"
    assert message["to"] == "+919876543210"
    assert message["content"]["interactive"]["type"] == "list"
    assert len(message["content"]["interactive"]["action"]["sections"][0]["rows"]) == 5
    assert message["custom_data"] == "draft-1"


@pytest.mark.asyncio
async def test_exotel_posts_to_marine_account_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.exotel.com/v2/accounts/echt61/messages"
        return httpx.Response(202, json={"response": {"whatsapp": {"messages": [{"sid": "provider-1"}]}}})

    client = ExotelClient(
        account_sid="echt61",
        api_key="test-key",
        api_token="test-token",
        whatsapp_from="+917948502803",
        transport=httpx.MockTransport(handler),
    )
    try:
        sid = await client.send_reply(to_number="+919876543210", body="Hello")
    finally:
        await client.aclose()

    assert sid == "provider-1"


def test_zoho_lead_contains_full_marine_context() -> None:
    context = MarineContext(
        customer_name="Rahul Mehta",
        customer_phone="+919876543210",
        primary_intent="buy_product",
        product="Pontoon Boat",
        application="Resort",
        passenger_capacity=12,
        project_location="Udaipur",
        water_body="Lake",
        company_name="Lake View Resorts",
        quantity=2,
        timeline="Within 1–3 Months",
    )
    lead = build_zoho_lead(context)

    assert lead["First_Name"] == "Rahul"
    assert lead["Last_Name"] == "Mehta"
    assert lead["Company"] == "Lake View Resorts"
    assert lead["Phone"] == "+919876543210"
    assert "Product: Pontoon Boat" in lead["Description"]
    assert "Passenger capacity: 12" in lead["Description"]


@pytest.mark.asyncio
async def test_zoho_refreshes_token_then_creates_lead() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "temporary-access-token"})
        assert request.headers["Authorization"] == "Zoho-oauthtoken temporary-access-token"
        return httpx.Response(201, json={"data": [{"details": {"id": "zoho-lead-1"}}]})

    client = ZohoClient(
        accounts_base_url="https://accounts.zoho.in",
        api_base_url="https://www.zohoapis.in",
        client_id="test-client",
        client_secret="test-secret",
        refresh_token="test-refresh",
        transport=httpx.MockTransport(handler),
    )
    try:
        lead_id = await client.create_lead(MarineContext(customer_name="Rahul"))
    finally:
        await client.aclose()

    assert lead_id == "zoho-lead-1"
    assert len(requests) == 2
