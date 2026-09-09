"""Deterministic, KB-backed product metadata for the Marine sales experience."""

from __future__ import annotations

from dataclasses import dataclass


PLACEHOLDER = "[CONTENT TO BE ADDED]"


@dataclass(frozen=True)
class MarineProduct:
    product_id: str
    name: str
    category: str
    short_description: str
    applications: tuple[str, ...]
    specifications: tuple[tuple[str, str], ...]
    image_url: str | None = None
    gallery_urls: tuple[str, ...] = ()
    content_status: str = "approved"
    available: bool = True


def _product(
    product_id: str, name: str, category: str, description: str,
    applications: tuple[str, ...], *specifications: tuple[str, str],
) -> MarineProduct:
    return MarineProduct(product_id, name, category, description, applications, specifications)


PRODUCTS: dict[str, MarineProduct] = {
    "speed_boat": _product("speed_boat", "Speed Boat", "boats", PLACEHOLDER, (PLACEHOLDER,),
        ("Capacity", PLACEHOLDER), ("Length", PLACEHOLDER), ("Hull", PLACEHOLDER), ("Engine", PLACEHOLDER), ("Certification", PLACEHOLDER)),
    "pontoon_24ft": _product("pontoon_24ft", "Aluminium Cruise Pontoon Boat — 24 FT", "boats", "A 24-foot, 12-seater aluminium cruise pontoon for leisure cruising, tourism and group outings.", ("Leisure cruising", "Tourism", "Group outings"),
        ("Capacity", "12 passengers"), ("Length", "24 ft"), ("Beam", "10 ft"), ("Hull & structure", "AL 5052"), ("Steering", "Hydraulic"), ("Certification", "CE certified")),
    "electric_tritoon": _product("electric_tritoon", "Electric Cruise Tritoon Boat", "boats", "A 20-foot, 12-seater electric tritoon for eco-friendly leisure cruising and tourism.", ("Eco-friendly cruising", "Tourism"),
        ("Capacity", "12 passengers"), ("Length", "20 ft"), ("Hull & structure", "AL 5052"), ("Battery storage", "Centre pontoon with four battery spaces"), ("Certification", "CE certified")),
    "pontoon_20ft": _product("pontoon_20ft", "Aluminium Cruise Pontoon Boat — 20 FT", "boats", "A 20-foot, 12-seater aluminium cruise pontoon for leisure cruising, resorts and tourism.", ("Resorts", "Tourism", "Leisure cruising"),
        ("Capacity", "12 passengers"), ("Length", "20 ft"), ("Hull & structure", "AL 5052"), ("Steering", "Hydraulic"), ("Certification", "CE certified")),
    "party_boat": _product("party_boat", "Party Boat", "boats", "A large-capacity boat for on-water events and entertainment.", ("Events", "Entertainment"),
        ("Capacity", "Maximum 80 passengers"), ("Beam", "33 ft"), ("Material", "Marine-grade aluminium, 5052 and 6063"), ("Recommended propulsion", "3 x 90 HP OBM")),
    "modern_house_boat": _product("modern_house_boat", "Modern House Boat", "boats", "A 37 ft x 15 ft luxury aluminium houseboat for leisure stays and long-term living on water.", ("Leisure stays", "Water-based living"),
        ("Dimensions", "37 ft x 15 ft"), ("Hull", "Aluminium"), ("Engine", "Twin 60 HP remote-control outboard motors"), ("Steering", "Hydraulic")),
    "aqua_cycle_twin": _product("aqua_cycle_twin", "LLDPE Aluminium Aqua Cycle Twin", "water_recreation", "A two-seater adult pedal boat for water parks and leisure centres.", ("Water parks", "Leisure centres"),
        ("Seating", "2 adults"), ("Material", "LLDPE"), ("Frame", "Marine-grade aluminium"), ("Dimensions", "3318 x 2275 x 2345 mm with wheel")),
    "modular_floating_dock": _product("modular_floating_dock", "Modular Floating Dock Platform", "floating_solutions", "A modular LLDPE system for docks, jetties and floating platforms.", ("Docks", "Jetties", "Floating platforms"),
        ("Module dimensions", "3 m x 2 m x 400 mm"), ("Material", "UV-stabilized, food-grade-approved LLDPE"), ("Load", "1.5 tonnes uniformly distributed per module"), ("Certification", "CE certified")),
    "g_plus_1_house_boat": _product("g_plus_1_house_boat", "G+1 Modern House Boat", "floating_solutions", "A compact G+1 floating houseboat with one bedroom and one bathroom.", ("Floating accommodation",),
        ("Size", "3.20 x 8.20 m"), ("Usable area", "26.24 sq. m"), ("Layout", "1 bedroom, 1 bathroom")),
    "floating_house": _product("floating_house", "Floating House", "floating_solutions", "A floating house for residential or resort use with a customizable interior layout.", ("Residential use", "Resorts"), ("Size", "3 x 9.3 m")),
    "floating_capsule": _product("floating_capsule", "Floating Modern Capsule", "floating_solutions", "A modern floating capsule for boutique resorts, glamping and eco-tourism.", ("Boutique resorts", "Glamping", "Eco-tourism"), ("Size", "3.40 x 12 m")),
    "a_shape_cottage": _product("a_shape_cottage", "A-Shape Floating Cottage", "floating_solutions", "An A-frame floating cottage for eco-resorts and glamping.", ("Eco-resorts", "Glamping"), ("Size", "3.20 x 6 m")),
    "floating_villa": _product("floating_villa", "Floating Villa", "floating_solutions", "A premium floating villa for luxury resort accommodation or water-based living.", ("Luxury resorts", "Water-based living"), ("Size", "3.40 x 8.50 m")),
}


def product_actions() -> tuple[tuple[str, str], ...]:
    return (("quote_product", "Get Quotation"), ("view_specs", "View Specifications"), ("view_photos", "See More Photos"), ("talk_expert", "Talk to Expert"))


def render_product_card(product: MarineProduct) -> str:
    details = "\n".join(f"• {label}: {value}" for label, value in product.specifications[:5])
    applications = "\n".join(f"• {item}" for item in product.applications[:3])
    return (f"🚤 {product.name}\n\n{product.short_description}\n\nKey details:\n{details}\n\n"
            f"Suitable for:\n{applications}\n\nCustomization is available based on project requirements.\n\nWhat would you like to do?")


def render_specifications(product: MarineProduct) -> str:
    details = "\n".join(f"• {label}: {value}" for label, value in product.specifications)
    return f"📋 {product.name} — Specifications\n\n{details}\n\nFor final configuration and project suitability, our team will confirm the details."


def products_in_category(category: str) -> tuple[MarineProduct, ...]:
    return tuple(product for product in PRODUCTS.values() if product.category == category and product.available)
