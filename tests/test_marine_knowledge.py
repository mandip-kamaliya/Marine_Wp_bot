from pathlib import Path

from app.services.marine_knowledge import MarineKnowledgeService
from app.services.marine_sales import MarineContext, process_marine_message


KB = Path(__file__).resolve().parents[1] / "documents/active/ECHT_MARINE_KNOWLEDGE_BASE_V2.md"


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


def test_commercial_question_is_answered_cautiously_and_handed_over():
    service = MarineKnowledgeService(KB, responder)
    result = process_marine_message(
        "What is the Pontoon price and delivery time?", MarineContext(), knowledge=service,
    )
    assert result.handover is True
    assert result.handover_reason == "commercial_or_technical_confirmation"


def test_internal_only_sections_are_never_retrieved():
    seen = []
    service = MarineKnowledgeService(
        KB, lambda _question, sections: seen.extend(section.heading for section in sections) or "Safe answer",
        max_sections=8,
    )
    service.answer("What facts must the bot not say without confirmation?")
    assert not any("INTERNAL ONLY" in heading or "FACTS THE BOT" in heading for heading in seen)
