from pathlib import Path

from app.services.marine_knowledge import MarineKnowledgeService
from app.services.marine_sales import MarineContext, process_marine_message
from app.services.marine_understanding import MarineUnderstandingService


KB = Path(__file__).resolve().parents[1] / "documents/active/ECHT_MARINE_KNOWLEDGE_BASE_V2.md"
PRODUCT_CATALOG = Path(__file__).resolve().parents[1] / "documents/active/ECHT_MARINE_PRODUCT_CATALOG.md"


def responder(question, sections):
    headings = " ".join(section.heading for section in sections).casefold()
    if "aqua cycle" in headings:
        return "The Aqua Cycle is a two-seater pedal watercraft with a marine-grade aluminium frame and 100% virgin LLDPE floats."
    if "luxury pontoon" in headings or "pontoon" in headings:
        return "Published Luxury Pontoon configurations include 8, 10 and 12 seats, with final configuration confirmed by ECHT Marine."
    return "The ECHT Marine team can confirm the current approved details."


def test_aqua_cycle_question_uses_approved_knowledge_before_menu_flow():
    service = MarineKnowledgeService(KB, responder)
    result = process_marine_message(
        "What material is the Aqua Cycle?", MarineContext(), knowledge=service,
    )
    assert "LLDPE" in result.text
    assert "two-seater" in result.text
    assert result.context.state == "primary_intent"
    assert result.handover is False


def test_commercial_question_collects_details_without_inventing_a_price():
    service = MarineKnowledgeService(KB, responder)
    result = process_marine_message(
        "What is the Pontoon price?", MarineContext(), knowledge=service,
        understanding=MarineUnderstandingService(),
    )
    assert result.handover is False
    assert "Pricing depends" in result.text


def test_internal_only_sections_are_never_retrieved():
    seen = []
    service = MarineKnowledgeService(
        KB, lambda _question, sections: seen.extend(section.heading for section in sections) or "Safe answer",
        max_sections=8,
    )
    service.answer("What facts must the bot not say without confirmation?")
    assert not any("INTERNAL ONLY" in heading or "FACTS THE BOT" in heading for heading in seen)


def test_rich_free_text_merges_facts_then_asks_only_next_missing_requirement():
    result = process_marine_message(
        "I need 2 Pontoon Boats for my resort in Udaipur, around 12 people each. What is the price?",
        MarineContext(),
        understanding=MarineUnderstandingService(),
    )

    assert result.context.product == "Pontoon Boat"
    assert result.context.application == "Resort / Hotel"
    assert result.context.quantity == 2
    assert result.context.passenger_capacity == 12
    assert result.context.project_location == "Udaipur"
    assert "Pricing depends" in result.text
    assert "lake, river, reservoir or coastal" in result.text
    assert "how many passengers" not in result.text.casefold()
    assert "project city" not in result.text.casefold()


def test_question_interrupts_old_state_then_returns_to_next_missing_fact():
    service = MarineKnowledgeService(KB, responder)
    result = process_marine_message(
        "12 people, what engine does it use?",
        MarineContext(product="Pontoon Boat", application="Resort / Hotel", state="project_location"),
        knowledge=service,
        understanding=MarineUnderstandingService(),
    )

    assert result.context.passenger_capacity == 12
    assert "Published Luxury Pontoon" in result.text
    assert "project city or location" in result.text


def test_live_stock_request_is_handed_to_a_person_not_invented():
    result = process_marine_message(
        "Do you have a Pontoon Boat in stock and available now?",
        MarineContext(), understanding=MarineUnderstandingService(),
    )

    assert result.handover is True
    assert result.handover_reason == "live_inventory_requested"


def test_product_catalog_adds_party_boat_knowledge_without_replacing_v2():
    seen = []
    service = MarineKnowledgeService(
        (KB, PRODUCT_CATALOG),
        lambda _question, sections: seen.extend(section.heading for section in sections) or "The Party Boat carries up to 80 passengers.",
    )

    answer = service.answer("How many passengers can the Party Boat carry?")

    assert answer is not None
    assert "P007" in " ".join(seen)
