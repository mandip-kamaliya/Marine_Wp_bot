"""ECHT Marine sales-flow behavior tests."""

from app.services.marine_sales import process_marine_message, start_marine_flow
from app.services.marine_understanding import MarineUnderstandingService


def advance(text: str, reply):
    return process_marine_message(text, reply.context)


def test_welcome_routes_to_pontoon_qualification() -> None:
    welcome = start_marine_flow(customer_phone="+919876543210")
    products = advance("marine_buy_products", welcome)
    use = advance("product_pontoon", products)

    assert welcome.context.customer_phone == "+919876543210"
    assert len(welcome.actions) == 5
    assert products.context.primary_intent == "buy_product"
    assert use.context.product == "Pontoon Boat"
    assert use.context.state == "pontoon_use"


def test_pontoon_quotation_retains_all_answers_and_does_not_ask_for_phone() -> None:
    reply = start_marine_flow(customer_phone="+919876543210")
    for answer in (
        "marine_buy_products",
        "product_pontoon",
        "use_resort",
        "12 people",
        "Udaipur",
        "water_lake",
        "marine_get_quotation",
        "Rahul Mehta",
        "Lake View Resorts",
        "2 boats",
        "timeline_within_1_3_months",
    ):
        reply = advance(answer, reply)

    assert reply.handover is True
    assert reply.handover_reason == "quotation_requested"
    assert reply.lead_priority == "hot"
    assert reply.context.customer_phone == "+919876543210"
    assert reply.context.customer_name == "Rahul Mehta"
    assert reply.context.product == "Pontoon Boat"
    assert reply.context.application == "Resort"
    assert reply.context.passenger_capacity == 12
    assert reply.context.project_location == "Udaipur"
    assert reply.context.water_body == "Lake"
    assert reply.context.quantity == 2
    assert "mobile number" not in reply.text.casefold()


def test_invalid_capacity_is_corrected_without_losing_previous_answers() -> None:
    reply = start_marine_flow()
    for answer in ("buy a boat", "pontoon", "tourism project"):
        reply = advance(answer, reply)

    invalid = advance("not sure", reply)
    valid = process_marine_message(
        "10 passengers", invalid.context, understanding=MarineUnderstandingService(),
    )

    assert "project city or location" in invalid.text
    assert invalid.context.application == "Tourism Project"
    assert valid.context.passenger_capacity == 10
    assert valid.context.state == "project_location"


def test_unsure_customer_receives_only_relevant_recommendations() -> None:
    reply = start_marine_flow()
    for answer in ("marine_buy_products", "product_unsure", "goal_water_sports_activity"):
        reply = advance(answer, reply)
    recommendations = advance("6 guests", reply)

    assert "Jet Ski" in recommendations.text
    assert "Aqua Cycle" in recommendations.text
    assert recommendations.text.count("\n• ") == 3


def test_floating_jetty_project_is_handed_to_engineering_sales() -> None:
    reply = start_marine_flow()
    for answer in (
        "marine_floating_jetty",
        "jetty_boat_berthing",
        "Goa",
        "Coastal",
        "20 metres",
        "Speed boats and jet skis",
    ):
        reply = advance(answer, reply)

    assert reply.handover is True
    assert reply.handover_reason == "floating_jetty_design"
    assert reply.context.project_location == "Goa"
    assert reply.context.jetty_size == "20 metres"


def test_government_tender_is_hot_human_lead() -> None:
    reply = start_marine_flow()
    for answer in (
        "marine_work_rescue",
        "work_hdpe_rescue_boat",
        "org_government_department",
        "tender_yes",
    ):
        reply = advance(answer, reply)

    assert reply.handover is True
    assert reply.handover_reason == "government_tender"
    assert reply.lead_priority == "hot"
    assert reply.context.tender_available is True


def test_existing_customer_uses_support_flow_not_sales_flow() -> None:
    reply = start_marine_flow()
    for answer in (
        "marine_service_order",
        "support_service_maintenance",
        "Order EM-102 needs motor service",
    ):
        reply = advance(answer, reply)

    assert reply.handover is True
    assert reply.handover_reason == "existing_customer_support"
    assert reply.context.support_reference == "Order EM-102 needs motor service"


def test_customer_can_request_human_from_any_active_state() -> None:
    welcome = start_marine_flow()
    reply = advance("I want to talk to a sales person", welcome)

    assert reply.handover is True
    assert reply.handover_reason == "customer_requested_human"


def test_pontoon_uncertain_capacity_moves_to_location_without_inventing_a_seat_count() -> None:
    reply = start_marine_flow()
    for answer in ("marine_buy_products", "product_pontoon", "use_resort", "not sure"):
        reply = advance(answer, reply)

    assert reply.context.passenger_capacity is None
    assert reply.context.state == "project_location"
    assert "project city or location" in reply.text


def test_pontoon_completion_never_defaults_to_an_eight_seater() -> None:
    reply = start_marine_flow()
    for answer in (
        "marine_buy_products", "product_pontoon", "use_resort", "12 people", "Udaipur", "water_lake",
    ):
        reply = advance(answer, reply)

    assert "8-seater" not in reply.text
    assert "Pontoon Boat requirement" in reply.text
    assert "Final capacity" in reply.text


def test_speed_boat_selection_stays_in_speed_boat_qualification() -> None:
    reply = start_marine_flow()
    for answer in (
        "marine_buy_products", "product_speed_boat", "speed_use_water_sports", "idk", "Goa", "water_coastal_location",
    ):
        reply = advance(answer, reply)

    assert reply.context.product == "Speed Boat"
    assert reply.context.passenger_capacity is None
    assert "Speed Boat requirement" in reply.text
    assert "Pontoon" not in reply.text
