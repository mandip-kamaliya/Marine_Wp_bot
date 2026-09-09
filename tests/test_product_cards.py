"""Product-card-first sales flow regression tests."""

from app.services.marine_sales import MarineContext, process_marine_message, start_marine_flow
from app.services.marine_understanding import MarineUnderstandingService
import pytest


def test_speed_boat_selection_shows_a_card_before_qualification() -> None:
    welcome = start_marine_flow()
    products = process_marine_message("marine_buy_products", welcome.context)
    card = process_marine_message("product_speed_boat", products.context)

    assert card.context.state == "product_card"
    assert card.context.product_id == "speed_boat"
    assert "[CONTENT TO BE ADDED]" in card.text
    assert [action.id for action in card.actions] == ["quote_product", "view_specs", "view_photos", "talk_expert"]


def test_card_actions_keep_product_context_and_do_not_invent_photos() -> None:
    card = process_marine_message("I want a speed boat", MarineContext(), understanding=MarineUnderstandingService())
    specs = process_marine_message("view_specs", card.context)
    photos = process_marine_message("view_photos", specs.context)

    assert "Specifications" in specs.text
    assert "[CONTENT TO BE ADDED]" in specs.text
    assert "photos will be added shortly" in photos.text.casefold()
    assert photos.context.product_id == "speed_boat"


def test_pontoon_request_offers_known_models_then_shows_selected_card() -> None:
    choices = process_marine_message("I need a pontoon boat", MarineContext(), understanding=MarineUnderstandingService())
    card = process_marine_message("product_pontoon_24ft", choices.context)

    assert choices.context.state == "product"
    assert any(action.id == "product_pontoon_24ft" for action in choices.actions)
    assert card.context.state == "product_card"
    assert card.context.product_id == "pontoon_24ft"
    assert "12 passengers" in card.text


def test_quotation_starts_after_card_action_and_reuses_known_customer_facts() -> None:
    card = process_marine_message(
        "I need a 12 seater pontoon boat for my resort in Ahmedabad.",
        MarineContext(), understanding=MarineUnderstandingService(),
    )
    selected = process_marine_message("product_pontoon_20ft", card.context)
    quote = process_marine_message("quote_product", selected.context)

    assert quote.context.intent == "quotation"
    assert quote.context.application == "Resort / Hotel"
    assert quote.context.passenger_capacity == 12
    assert quote.context.project_location == "Ahmedabad"
    assert quote.context.state == "water_body"
    assert "lake, river, reservoir or coastal" in quote.text


def test_expert_handover_collects_only_a_missing_name() -> None:
    card = process_marine_message("I want a speed boat", MarineContext(), understanding=MarineUnderstandingService())
    ask_name = process_marine_message("talk_expert", card.context)
    handover = process_marine_message("Riya Shah", ask_name.context)

    assert ask_name.context.state == "expert_name"
    assert handover.handover is True
    assert handover.context.customer_name == "Riya Shah"


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("quote_use_private", "Private Use"),
        ("quote_use_resort", "Resort / Hotel"),
        ("quote_use_tourism", "Tourism Project"),
        ("quote_use_government", "Government / Institutional Project"),
        ("quote_use_commercial", "Commercial Operation"),
    ],
)
def test_quotation_records_each_supported_use_case(action: str, expected: str) -> None:
    card = process_marine_message("I want a speed boat", MarineContext(), understanding=MarineUnderstandingService())
    use_case = process_marine_message("quote_product", card.context)
    next_reply = process_marine_message(action, use_case.context)

    assert next_reply.context.application == expected
    assert next_reply.context.state == "speed_boat_capacity"
