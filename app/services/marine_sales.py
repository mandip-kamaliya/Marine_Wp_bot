"""Deterministic ECHT Marine sales qualification flow."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.services.marine_knowledge import MarineKnowledgeService, looks_like_knowledge_question


class MarineAction(BaseModel):
    id: str
    title: str


class MarineContext(BaseModel):
    """Values remembered throughout one customer conversation."""

    state: str = "new"
    customer_phone: str | None = None
    customer_name: str | None = None
    primary_intent: str | None = None
    product: str | None = None
    application: str | None = None
    passenger_capacity: int | None = None
    project_location: str | None = None
    water_body: str | None = None
    company_name: str | None = None
    quantity: int | None = None
    timeline: str | None = None
    jetty_use: str | None = None
    jetty_size: str | None = None
    vessel_types: str | None = None
    work_solution: str | None = None
    organisation_type: str | None = None
    tender_available: bool | None = None
    support_type: str | None = None
    support_reference: str | None = None


class MarineReply(BaseModel):
    text: str
    context: MarineContext
    actions: list[MarineAction] = Field(default_factory=list)
    handover: bool = False
    handover_reason: str | None = None
    lead_priority: Literal["normal", "high", "hot"] = "normal"


PRIMARY_ACTIONS = [
    MarineAction(id="marine_buy_products", title="Boats & Water Recreation"),
    MarineAction(id="marine_floating_jetty", title="Floating Jetty / Waterfront"),
    MarineAction(id="marine_work_rescue", title="Work & Rescue Boats"),
    MarineAction(id="marine_service_order", title="Service / Existing Order"),
    MarineAction(id="marine_talk", title="Talk to ECHT Marine"),
]

PRODUCT_ACTIONS = [
    MarineAction(id="product_pontoon", title="Pontoon Boat"),
    MarineAction(id="product_aqua_cycle", title="Aqua Cycle"),
    MarineAction(id="product_bumper_boat", title="Bumper Boat"),
    MarineAction(id="product_speed_boat", title="Speed Boat"),
    MarineAction(id="product_jet_ski", title="Jet Ski"),
    MarineAction(id="product_house_boat", title="House Boat"),
    MarineAction(id="product_kayak_paddle", title="Kayak / Paddle Boat"),
    MarineAction(id="product_unsure", title="Not sure — help me choose"),
]

PONTOON_USE_ACTIONS = [
    MarineAction(id="use_resort", title="Resort / Hotel"),
    MarineAction(id="use_tourism", title="Tourism Project"),
    MarineAction(id="use_commercial", title="Commercial Rides"),
    MarineAction(id="use_private", title="Private Use"),
    MarineAction(id="use_waterfront", title="Waterfront Development"),
    MarineAction(id="use_other", title="Other"),
]

QUOTE_ACTIONS = [
    MarineAction(id="marine_get_quotation", title="Get Quotation"),
    MarineAction(id="marine_view_details", title="View More Details"),
    MarineAction(id="marine_talk", title="Talk to Sales"),
]


def start_marine_flow(*, customer_phone: str | None = None) -> MarineReply:
    context = MarineContext(state="primary_intent", customer_phone=customer_phone)
    return MarineReply(
        text=(
            "👋 Welcome to ECHT Marine\n\n"
            "We design and supply boats, water-recreation products and floating marine "
            "solutions for resorts, tourism projects, waterfront developments, government "
            "organisations and private clients.\n\nWhat are you looking for today?"
        ),
        context=context,
        actions=PRIMARY_ACTIONS,
    )


def process_marine_message(
    text: str,
    context: MarineContext,
    *,
    knowledge: MarineKnowledgeService | None = None,
) -> MarineReply:
    """Advance the explicit flow while retaining previously captured answers."""

    value = text.strip()
    normalized = _normalize(value)
    if _is_human_request(normalized):
        return _handover(context, "customer_requested_human", "I'll connect you with our ECHT Marine team.")
    if knowledge is not None and looks_like_knowledge_question(value):
        answer = knowledge.answer(value)
        if answer is not None:
            if context.state == "new":
                context.state = "primary_intent"
            return MarineReply(
                text=answer.text,
                context=context,
                actions=[] if answer.handover else PRIMARY_ACTIONS,
                handover=answer.handover,
                handover_reason=answer.handover_reason,
                lead_priority="high" if answer.handover else "normal",
            )
    if context.state == "new":
        return start_marine_flow(customer_phone=context.customer_phone)

    handlers = {
        "primary_intent": _primary_intent,
        "product": _product,
        "pontoon_use": _pontoon_use,
        "pontoon_capacity": _pontoon_capacity,
        "project_location": _project_location,
        "water_body": _water_body,
        "recommendation": _recommendation,
        "quote_name": _quote_name,
        "quote_company": _quote_company,
        "quote_quantity": _quote_quantity,
        "quote_timeline": _quote_timeline,
        "chooser_goal": _chooser_goal,
        "chooser_capacity": _chooser_capacity,
        "jetty_use": _jetty_use,
        "jetty_location": _jetty_location,
        "jetty_water_body": _jetty_water_body,
        "jetty_size": _jetty_size,
        "jetty_vessels": _jetty_vessels,
        "work_solution": _work_solution,
        "organisation_type": _organisation_type,
        "tender_available": _tender_available,
        "support_type": _support_type,
        "support_reference": _support_reference,
    }
    handler = handlers.get(context.state)
    if handler is None:
        return start_marine_flow(customer_phone=context.customer_phone)
    return handler(value, normalized, context.model_copy(deep=True))


def _primary_intent(value: str, normalized: str, context: MarineContext) -> MarineReply:
    if _matches(normalized, "marine_buy_products", "buy", "boat", "water recreation"):
        context.primary_intent, context.state = "buy_product", "product"
        return MarineReply(text="Great. Which product are you interested in?", context=context, actions=PRODUCT_ACTIONS)
    if _matches(normalized, "marine_floating_jetty", "floating jetty", "waterfront", "jetty"):
        context.primary_intent, context.state = "floating_jetty", "jetty_use"
        return MarineReply(text="Certainly. What will the floating jetty primarily be used for?", context=context, actions=_actions("Passenger Boarding", "Boat Berthing", "Jet Ski / Water Sports", "Resort Waterfront", "Marina", "Custom Project", prefix="jetty"))
    if _matches(normalized, "marine_work_rescue", "work boat", "rescue"):
        context.primary_intent, context.state = "work_rescue", "work_solution"
        return MarineReply(text="Which solution are you looking for?", context=context, actions=_actions("HDPE Rescue Boat", "Boat Ambulance", "Weed Harvesting Boat", "Fire Fighting Boat", "Launch Boat", prefix="work"))
    if _matches(normalized, "marine_service_order", "service", "existing order", "support"):
        context.primary_intent, context.state = "support", "support_type"
        return MarineReply(text="Sure. What do you need help with?", context=context, actions=_actions("Existing Order", "Delivery Status", "Service / Maintenance", "Spare Parts", "AMC", "Complaint", "Talk to Support", prefix="support"))
    return MarineReply(text="Please choose the option that best matches your requirement.", context=context, actions=PRIMARY_ACTIONS)


def _product(value: str, normalized: str, context: MarineContext) -> MarineReply:
    products = {
        "pontoon": "Pontoon Boat", "aqua cycle": "Aqua Cycle", "bumper": "Bumper Boat",
        "speed": "Speed Boat", "jet ski": "Jet Ski", "house": "House Boat",
        "kayak": "Kayak / Paddle Boat", "paddle": "Kayak / Paddle Boat",
    }
    if "unsure" in normalized or "not sure" in normalized or "help me choose" in normalized:
        context.state = "chooser_goal"
        return MarineReply(text="No problem — I'll help you choose. 😊\n\nWhat are you planning to create?", context=context, actions=_actions("Premium Guest Experience", "Water-sports Activity", "Passenger Transportation", "Resort Attraction", "Rescue / Emergency Service", "Waterfront Infrastructure", prefix="goal"))
    product = next((name for key, name in products.items() if key in normalized), None)
    if product is None:
        return MarineReply(text="Please select a product, or choose ‘Not sure — help me choose’.", context=context, actions=PRODUCT_ACTIONS)
    context.product = product
    if product == "Pontoon Boat":
        context.state = "pontoon_use"
        return MarineReply(text="What are you planning to use the Pontoon Boat for?", context=context, actions=PONTOON_USE_ACTIONS)
    context.state = "project_location"
    return MarineReply(text=f"Great choice. Where will the {product} be operated? Please share the project city or location. 📍", context=context)


def _pontoon_use(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.application = _clean_action_value(value, "use")
    context.state = "pontoon_capacity"
    return MarineReply(text="Approximately how many passengers would you like to accommodate?", context=context)


def _pontoon_capacity(value: str, normalized: str, context: MarineContext) -> MarineReply:
    count = _positive_integer(value)
    if count is None:
        return MarineReply(text="Please share the required passenger capacity. For example: 12 people", context=context)
    context.passenger_capacity = count
    context.state = "project_location"
    return MarineReply(text="Perfect. Where will the boat be operated? Please share the project city or location. 📍", context=context)


def _project_location(value: str, normalized: str, context: MarineContext) -> MarineReply:
    if not value:
        return MarineReply(text="Please share the project city or location. 📍", context=context)
    context.project_location = value
    context.state = "water_body"
    return MarineReply(text="Is it for a lake, river, reservoir or coastal location?", context=context, actions=_actions("Lake", "River", "Reservoir", "Coastal Location", prefix="water"))


def _water_body(value: str, normalized: str, context: MarineContext) -> MarineReply:
    allowed = ("lake", "river", "reservoir", "coastal")
    selected = next((item for item in allowed if item in normalized), None)
    if selected is None:
        return MarineReply(text="Please choose the operating water body.", context=context, actions=_actions("Lake", "River", "Reservoir", "Coastal Location", prefix="water"))
    context.water_body = selected.title()
    context.state = "recommendation"
    capacity = context.passenger_capacity or 0
    recommended = min((8, 10, 12), key=lambda option: abs(option - capacity)) if capacity else 8
    return MarineReply(
        text=(f"Based on your requirement, a {recommended}-seater Pontoon configuration could be suitable.\n\n"
              "Published options include:\n• Up to 22 ft configurations\n• Marine-grade aluminium construction\n"
              "• Mechanical / hydraulic steering options\n• Custom seating, canopy, flooring, music and branding options\n\n"
              "The final engine and configuration should be selected according to your operating conditions.\n\n"
              "Would you like me to arrange a quotation?"),
        context=context,
        actions=QUOTE_ACTIONS,
    )


def _recommendation(value: str, normalized: str, context: MarineContext) -> MarineReply:
    if _matches(normalized, "marine_get_quotation", "quotation", "quote"):
        context.state = "quote_name"
        return MarineReply(text="Sure. I just need a few details for the ECHT Marine team.\n\nMay I have your name?", context=context)
    if _matches(normalized, "marine_view_details", "view more", "details"):
        return MarineReply(text="Our team can share the relevant technical specifications and configuration options. Would you like a quotation or a sales consultation?", context=context, actions=QUOTE_ACTIONS)
    return MarineReply(text="Please select how you would like to continue.", context=context, actions=QUOTE_ACTIONS)


def _quote_name(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.customer_name, context.state = value, "quote_company"
    return MarineReply(text="Company / organisation name?", context=context)


def _quote_company(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.company_name, context.state = value, "quote_quantity"
    return MarineReply(text="Required quantity?", context=context)


def _quote_quantity(value: str, normalized: str, context: MarineContext) -> MarineReply:
    quantity = _positive_integer(value)
    if quantity is None:
        return MarineReply(text="Please enter the required quantity. For example: 2", context=context)
    context.quantity, context.state = quantity, "quote_timeline"
    return MarineReply(text="When are you planning to start the project?", context=context, actions=_actions("Immediately", "Within 1–3 Months", "Within 3–6 Months", "Exploring Currently", prefix="timeline"))


def _quote_timeline(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.timeline = _clean_action_value(value, "timeline")
    context.state = "handover"
    return MarineReply(text=_lead_confirmation(context), context=context, handover=True, handover_reason="quotation_requested", lead_priority="hot")


def _chooser_goal(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.application, context.state = _clean_action_value(value, "goal"), "chooser_capacity"
    return MarineReply(text="Got it. Approximately how many guests or passengers would you like to accommodate at a time?", context=context)


def _chooser_capacity(value: str, normalized: str, context: MarineContext) -> MarineReply:
    count = _positive_integer(value)
    if count is None:
        return MarineReply(text="Please share an approximate number. For example: 10 guests", context=context)
    context.passenger_capacity, context.state = count, "product"
    recommendations = _recommend_products(context.application or "", count)
    return MarineReply(text=f"Based on your requirement, you could consider:\n• " + "\n• ".join(recommendations) + "\n\nWhich option would you like to explore?", context=context, actions=PRODUCT_ACTIONS)


def _jetty_use(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.jetty_use, context.state = _clean_action_value(value, "jetty"), "jetty_location"
    return MarineReply(text="Where is the project located? 📍", context=context)


def _jetty_location(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.project_location, context.state = value, "jetty_water_body"
    return MarineReply(text="What type of water body is it?", context=context)


def _jetty_water_body(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.water_body, context.state = value, "jetty_size"
    return MarineReply(text="Approximately what jetty length or area do you require?", context=context)


def _jetty_size(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.jetty_size, context.state = value, "jetty_vessels"
    return MarineReply(text="What types of vessels will use it?", context=context)


def _jetty_vessels(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.vessel_types, context.state = value, "handover"
    return MarineReply(text="Thank you. Floating-jetty design depends on water conditions, vessel type, loading and site requirements. I'll pass these details to our marine engineering and sales team for the correct configuration.", context=context, handover=True, handover_reason="floating_jetty_design", lead_priority="high")


def _work_solution(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.work_solution, context.state = _clean_action_value(value, "work"), "organisation_type"
    return MarineReply(text="Is this requirement for a government department, private organisation or commercial project?", context=context, actions=_actions("Government Department", "Private Organisation", "Commercial Project", prefix="org"))


def _organisation_type(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.organisation_type = _clean_action_value(value, "org")
    if "government" in normalized:
        context.state = "tender_available"
        return MarineReply(text="Do you already have a tender or technical specification?", context=context, actions=[MarineAction(id="tender_yes", title="Yes"), MarineAction(id="tender_no", title="No")])
    context.state = "handover"
    return MarineReply(text="Thank you. I'll connect you with our work-boat sales team to discuss the correct configuration.", context=context, handover=True, handover_reason="work_boat_requirement", lead_priority="high")


def _tender_available(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.tender_available = normalized in {"yes", "tender yes"} or normalized.endswith(" yes")
    context.state = "handover"
    priority: Literal["normal", "high", "hot"] = "hot" if context.tender_available else "high"
    return MarineReply(text="Thank you. Our ECHT Marine team will assist with your work and rescue boat requirement.", context=context, handover=True, handover_reason="government_tender" if context.tender_available else "government_requirement", lead_priority=priority)


def _support_type(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.support_type, context.state = _clean_action_value(value, "support"), "support_reference"
    return MarineReply(text="Please share your order reference or a short description of the issue.", context=context)


def _support_reference(value: str, normalized: str, context: MarineContext) -> MarineReply:
    context.support_reference, context.state = value, "handover"
    return MarineReply(text="Thank you. I've shared this with the ECHT Marine support team. A team member will assist you.", context=context, handover=True, handover_reason="existing_customer_support", lead_priority="high")


def _handover(context: MarineContext, reason: str, text: str) -> MarineReply:
    context.state = "handover"
    return MarineReply(text=text, context=context, handover=True, handover_reason=reason, lead_priority="high")


def _lead_confirmation(context: MarineContext) -> str:
    return (f"Thank you, {context.customer_name}. ✅\n\nI've captured your requirement:\n\n"
            f"Product: {context.product or 'Marine solution'}\nUse: {context.application or 'Not specified'}\n"
            f"Location: {context.project_location or 'Not specified'}\nWater Body: {context.water_body or 'Not specified'}\n"
            f"Quantity: {context.quantity or 'Not specified'}\nTimeline: {context.timeline or 'Not specified'}\n\n"
            "Our ECHT Marine team can now prepare the appropriate configuration and quotation.")


def _recommend_products(application: str, capacity: int) -> list[str]:
    lowered = application.casefold()
    if "rescue" in lowered or "emergency" in lowered:
        return ["HDPE Rescue Boat", "Boat Ambulance"]
    if "waterfront" in lowered:
        return ["Floating Jetty", "Pontoon Boat", "House Boat"]
    if "sport" in lowered:
        return ["Jet Ski", "Aqua Cycle", "Bumper Boat"]
    if capacity >= 8:
        return ["Pontoon Boat", "House Boat", "Speed Boat"]
    return ["Pontoon Boat", "Aqua Cycle", "Kayak / Paddle Boat"]


def _positive_integer(value: str) -> int | None:
    match = re.search(r"\b(\d+)\b", value)
    if match is None:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _matches(normalized: str, *choices: str) -> bool:
    return any(_normalize(choice) in normalized for choice in choices)


def _is_human_request(normalized: str) -> bool:
    return any(phrase in normalized for phrase in ("talk to echt marine", "talk to sales", "talk to support", "human", "sales person"))


def _clean_action_value(value: str, prefix: str) -> str:
    cleaned = re.sub(rf"^{re.escape(prefix)}[_\s-]*", "", value, flags=re.IGNORECASE)
    return cleaned.replace("_", " ").strip().title()


def _actions(*titles: str, prefix: str) -> list[MarineAction]:
    return [MarineAction(id=f"{prefix}_{_normalize(title).replace(' ', '_')}", title=title) for title in titles]
