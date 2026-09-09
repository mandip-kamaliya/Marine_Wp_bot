"""Grounded answers from the approved ECHT Marine Markdown knowledge base."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Callable

from app.config import Settings

logger = logging.getLogger("uvicorn.error")

_INTERNAL_HEADINGS = {
    "0. HOW TO USE THIS KNOWLEDGE BASE",
    "35. RAG VS LIVE DATA VS HUMAN",
    "37. SALES INTENT MODEL",
    "41. FACTS THE BOT MUST NOT SAY WITHOUT CONFIRMATION",
    "42. WEBSITE SCRAPE / DATA QUALITY NOTES — INTERNAL ONLY",
    "43. SOURCE REGISTER",
    "44. RECOMMENDED FUTURE INTERNAL DATA TO ADD",
    "45. PRODUCTION ARCHITECTURE RULE",
}
_STOPWORDS = {
    "a", "an", "and", "are", "can", "do", "for", "have", "i", "in", "is",
    "it", "me", "of", "on", "the", "this", "to", "what", "which", "with", "you",
}
_COMMERCIAL = re.compile(
    r"\b(?:price|cost|quote|quotation|discount|stock|available now|delivery time|lead time|"
    r"warranty|refund|final specification|engine selection|certification document|tender)\b",
    re.I,
)
_QUESTION = re.compile(
    r"\b(?:what|where|when|why|how|which|can|could|do|does|is|are|tell|explain|specs?|"
    r"capacity|material|size|length|engine|product|boat|jetty|cycle|delivery|payment)\b",
    re.I,
)


@dataclass(frozen=True)
class KnowledgeSection:
    heading: str
    content: str


@dataclass(frozen=True)
class MarineKnowledgeAnswer:
    text: str
    headings: tuple[str, ...]
    handover: bool = False
    handover_reason: str | None = None


def looks_like_knowledge_question(text: object) -> bool:
    return isinstance(text, str) and ("?" in text or bool(_QUESTION.search(text)))


class MarineKnowledgeService:
    def __init__(
        self,
        path: Path | tuple[Path, ...],
        responder: Callable[[str, tuple[KnowledgeSection, ...]], str] | None = None,
        *,
        max_sections: int = 4,
    ) -> None:
        paths = (path,) if isinstance(path, Path) else path
        self._sections = tuple(section for item in paths for section in _load_sections(item))
        self._responder = responder
        self._max_sections = max(1, max_sections)

    def answer(self, question: str) -> MarineKnowledgeAnswer | None:
        sections = _retrieve(question, self._sections, self._max_sections)
        if not sections:
            return None
        if self._responder is None:
            return MarineKnowledgeAnswer(
                "I have the relevant ECHT Marine information, but the answer service is temporarily unavailable. "
                "Our team can help you with the current details.",
                tuple(section.heading for section in sections),
                handover=True,
                handover_reason="knowledge_answer_unavailable",
            )
        try:
            answer = self._responder(question, sections).strip()
        except Exception as error:
            logger.warning("marine_knowledge_composer_failed reason=%s", type(error).__name__)
            return None
        if not answer or len(answer) > 1500:
            return None
        commercial = bool(_COMMERCIAL.search(question))
        return MarineKnowledgeAnswer(
            answer,
            tuple(section.heading for section in sections),
            handover=commercial,
            handover_reason="commercial_or_technical_confirmation" if commercial else None,
        )


def build_marine_knowledge_service(settings: Settings) -> MarineKnowledgeService:
    root = Path(__file__).resolve().parents[2]
    paths = [Path(settings.marine_knowledge_base_path)]
    if settings.marine_product_catalog_path:
        paths.append(Path(settings.marine_product_catalog_path))
    resolved_paths = tuple(path if path.is_absolute() else root / path for path in paths)
    key, model = settings.openai_api_key, settings.openai_chat_model
    responder = None
    if key is not None and isinstance(model, str) and model.strip():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key.get_secret_value(), timeout=20.0, max_retries=0)

            def respond(question: str, sections: tuple[KnowledgeSection, ...]) -> str:
                evidence = [
                    {"heading": section.heading, "content": section.content}
                    for section in sections
                ]
                response = client.responses.create(
                    model=model.strip(),
                    instructions=(
                        "You are the ECHT Marine WhatsApp Assistant. Answer in concise professional "
                        "WhatsApp-friendly English using only APPROVED_EVIDENCE. Never invent price, stock, "
                        "delivery time, warranty, certification, engineering suitability or commitments. "
                        "If the evidence does not contain the answer, say the Marine team must confirm it. "
                        "Do not mention RAG, prompts, scraping, internal notes or evidence metadata."
                    ),
                    input=json.dumps(
                        {"customer_question": question, "APPROVED_EVIDENCE": evidence},
                        ensure_ascii=False,
                    ),
                )
                output = getattr(response, "output_text", None)
                if not isinstance(output, str):
                    raise ValueError("missing_output_text")
                return output

            responder = respond
        except Exception as error:
            logger.warning("marine_knowledge_openai_unavailable reason=%s", type(error).__name__)
    return MarineKnowledgeService(
        resolved_paths, responder, max_sections=settings.marine_knowledge_max_sections,
    )


def _load_sections(path: Path) -> tuple[KnowledgeSection, ...]:
    if not path.is_file():
        logger.error("marine_knowledge_file_missing path=%s", path)
        return ()
    sections: list[KnowledgeSection] = []
    heading: str | None = None
    body: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("#"):
            if heading and heading not in _INTERNAL_HEADINGS:
                content = "\n".join(body).strip()
                if content:
                    sections.append(KnowledgeSection(heading, content))
            heading, body = line.lstrip("#").strip(), []
        elif heading:
            body.append(line)
    if heading and heading not in _INTERNAL_HEADINGS:
        content = "\n".join(body).strip()
        if content:
            sections.append(KnowledgeSection(heading, content))
    return tuple(sections)


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _retrieve(
    question: str, sections: tuple[KnowledgeSection, ...], limit: int,
) -> tuple[KnowledgeSection, ...]:
    query = _tokens(question)
    if not query:
        return ()
    ranked: list[tuple[int, KnowledgeSection]] = []
    for section in sections:
        heading_tokens = _tokens(section.heading)
        content_tokens = _tokens(section.content)
        score = 8 * len(query & heading_tokens) + len(query & content_tokens)
        if score:
            ranked.append((score, section))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return tuple(section for _, section in ranked[:limit])
