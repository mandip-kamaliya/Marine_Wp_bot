"""Extract usable Marine sales facts from a customer's latest message.

This layer is deliberately separate from the sales flow.  It can use OpenAI
when configured, but always has a conservative local fallback so a customer
message is never ignored merely because an AI request is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Callable

from app.config import Settings

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class MarineUnderstanding:
    product: str | None = None
    application: str | None = None
    passenger_capacity: int | None = None
    quantity: int | None = None
    project_location: str | None = None
    water_body: str | None = None
    timeline: str | None = None
    asks_question: bool = False
    asks_price: bool = False
    asks_quote: bool = False
    asks_live_availability: bool = False
    asks_confirmed_delivery: bool = False
    asks_custom_engineering: bool = False
    asks_tender: bool = False
    asks_human: bool = False

    @property
    def has_entities(self) -> bool:
        return any((
            self.product, self.application, self.passenger_capacity, self.quantity,
            self.project_location, self.water_body, self.timeline,
        ))


Extractor = Callable[[str], MarineUnderstanding | None]


class MarineUnderstandingService:
    def __init__(self, extractor: Extractor | None = None) -> None:
        self._extractor = extractor

    def understand(self, text: str) -> MarineUnderstanding:
        fallback = _fallback(text)
        if self._extractor is None:
            return fallback
        try:
            extracted = self._extractor(text)
        except Exception as error:
            logger.warning("marine_understanding_failed reason=%s", type(error).__name__)
            return fallback
        if extracted is None:
            return fallback
        return _merge(extracted, fallback)


def build_marine_understanding_service(settings: Settings) -> MarineUnderstandingService:
    """Build optional structured OpenAI extraction without making it mandatory."""
    key, model = settings.openai_api_key, settings.openai_chat_model
    if key is None or not isinstance(model, str) or not model.strip():
        return MarineUnderstandingService()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key.get_secret_value(), timeout=12.0, max_retries=0)

        def extract(text: str) -> MarineUnderstanding | None:
            response = client.responses.create(
                model=model.strip(),
                instructions=(
                    "Extract facts only from the latest ECHT Marine customer message. "
                    "Return JSON only. Never infer a price, availability, delivery promise, "
                    "or engineering suitability. Use null when a field is absent. "
                    "Allowed product values: Pontoon Boat, Aqua Cycle, Bumper Boat, Speed Boat, "
                    "Jet Ski, House Boat, Kayak / Paddle Boat, Floating Jetty, HDPE Rescue Boat, "
                    "Boat Ambulance, Weed Harvesting Boat, Fire Fighting Boat, Launch Boat. "
                    "Allowed application values: Resort / Hotel, Tourism Project, Commercial Rides, "
                    "Private Use, Waterfront Development. JSON keys: product, application, "
                    "passenger_capacity, quantity, project_location, water_body, timeline, "
                    "asks_question, asks_price, asks_quote, asks_live_availability, "
                    "asks_confirmed_delivery, asks_custom_engineering, asks_tender, asks_human."
                ),
                input=text,
            )
            raw = getattr(response, "output_text", "")
            if not isinstance(raw, str):
                return None
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            allowed = MarineUnderstanding.__dataclass_fields__
            return MarineUnderstanding(**{key: value for key, value in data.items() if key in allowed})

        return MarineUnderstandingService(extract)
    except Exception as error:
        logger.warning("marine_understanding_openai_unavailable reason=%s", type(error).__name__)
        return MarineUnderstandingService()


def _merge(primary: MarineUnderstanding, fallback: MarineUnderstanding) -> MarineUnderstanding:
    values = {
        name: getattr(primary, name) if getattr(primary, name) not in (None, False) else getattr(fallback, name)
        for name in MarineUnderstanding.__dataclass_fields__
    }
    return MarineUnderstanding(**values)


def _fallback(text: str) -> MarineUnderstanding:
    value = text.strip()
    lowered = value.casefold()
    product = _find_product(lowered)
    application = _find_application(lowered)
    capacity = _find_number(r"\b(\d{1,3})\s*(?:people|persons|passengers?|pax|seats?|seater)\b", lowered)
    quantity = _find_number(r"\b(\d{1,3})\s*(?:boats?|units?|pieces?)\b", lowered)
    if quantity is None and product and "need" in lowered:
        quantity = _find_number(r"\bneed\s+(\d{1,3})\b", lowered)
    location = _find_location(value)
    water_body = next((item.title() for item in ("lake", "river", "reservoir", "coastal") if item in lowered), None)
    return MarineUnderstanding(
        product=product,
        application=application,
        passenger_capacity=capacity,
        quantity=quantity,
        project_location=location,
        water_body=water_body,
        timeline=_find_timeline(lowered),
        asks_question=("?" in value or bool(re.search(r"\b(?:what|which|how|can|do|does|is|are|tell|explain)\b", lowered))),
        asks_price=bool(re.search(r"\b(?:price|cost|pricing|rate)\b", lowered)),
        asks_quote=bool(re.search(r"\b(?:quote|quotation|proposal)\b", lowered)),
        asks_live_availability=bool(re.search(r"\b(?:in stock|available now|availability|ready stock)\b", lowered)),
        asks_confirmed_delivery=bool(re.search(r"\b(?:delivery date|deliver by|confirmed delivery|lead time)\b", lowered)),
        asks_custom_engineering=bool(re.search(r"\b(?:custom engineering|structural design|engine selection|certification)\b", lowered)),
        asks_tender="tender" in lowered,
        asks_human=bool(re.search(r"\b(?:talk to|speak to|call me|sales person|human|representative)\b", lowered)),
    )


def _find_product(value: str) -> str | None:
    products = (
        ("floating jetty", "Floating Jetty"), ("weed harvesting", "Weed Harvesting Boat"),
        ("boat ambulance", "Boat Ambulance"), ("rescue boat", "HDPE Rescue Boat"),
        ("fire fighting", "Fire Fighting Boat"), ("launch boat", "Launch Boat"),
        ("pontoon", "Pontoon Boat"), ("aqua cycle", "Aqua Cycle"),
        ("bumper boat", "Bumper Boat"), ("speed boat", "Speed Boat"),
        ("jet ski", "Jet Ski"), ("house boat", "House Boat"),
        ("kayak", "Kayak / Paddle Boat"), ("paddle boat", "Kayak / Paddle Boat"),
    )
    return next((name for phrase, name in products if phrase in value), None)


def _find_application(value: str) -> str | None:
    items = (
        ("resort", "Resort / Hotel"), ("hotel", "Resort / Hotel"),
        ("tourism", "Tourism Project"), ("commercial", "Commercial Rides"),
        ("rides", "Commercial Rides"), ("private", "Private Use"),
        ("waterfront", "Waterfront Development"),
    )
    return next((name for phrase, name in items if phrase in value), None)


def _find_number(pattern: str, value: str) -> int | None:
    match = re.search(pattern, value)
    return int(match.group(1)) if match else None


def _find_location(value: str) -> str | None:
    match = re.search(r"\b(?:in|at|near)\s+([A-Z][A-Za-z .'-]{1,48})(?=$|[,.!?])", value)
    if not match:
        return None
    candidate = match.group(1).strip()
    return candidate if candidate.casefold() not in {"a", "the", "my resort"} else None


def _find_timeline(value: str) -> str | None:
    if "immediate" in value or "asap" in value:
        return "Immediately"
    if "1-3 month" in value or "1 to 3 month" in value:
        return "Within 1–3 Months"
    if "3-6 month" in value or "3 to 6 month" in value:
        return "Within 3–6 Months"
    return None
